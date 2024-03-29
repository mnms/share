from __future__ import print_function

import hashlib
import json
import sys
from os.path import join as path_join
import os
from time import gmtime, strftime
import shutil
import yaml
import socket

import click
import fire
from ask import askBool, askInt, askPassword, ask
from fire.core import FireExit
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.lexers import PygmentsLexer
from pygments.lexers.sql import SqlLexer
from rediscluster.exceptions import ClusterError

import utils
from cli import Cli
from cluster import Cluster
from config import get_config, get_cur_cluster_id, get_env_dict, \
    get_node_ip_list, get_root_of_cli_config
import config
from deploy_util import DeployUtil, DEPLOYED, PENDING, CLEAN
from log import logger
import log
from net import get_ssh, ssh_execute_async, ssh_execute, get_sftp, is_exist
import net
from prompt import get_cli_prompt
from sql import FbSql, fbsql
from thriftserver import ThriftServer
from utils import CommandError, TableReport, clear_screen, style
from rsync_over_sftp import RsyncOverSftp
from center import Center
import color
import ask_util
import cluster_util
import editor
from exceptions import (
    PropsKeyError,
    SSHConnectionError,
    HostConnectionError,
    HostNameError,
    FileNotExistError,
    YamlSyntaxError,
    PropsSyntaxError,
)


fb_completer = WordCompleter([
    'thriftserver', 'deploy', 'flashbase', 'fb', 'restart', 'start', 'stop'],
    ignore_case=True)

user_info = {
    'user': None,
    'print_mode': 'screen'
}


def run_monitor():
    """Run monitor command

    Monitor remote logs
    """
    ip_list = get_node_ip_list()
    i = 1
    msg = ''
    for ip in ip_list:
        msg += '%d) %s\n' % (i, ip)
        i += 1
    target_num = int(askInt(text=msg, default='1'))
    logger.info('Ok. %s' % target_num)
    target_index = target_num - 1
    ip = ip_list[target_index]
    client = get_ssh(ip)
    envs = get_env_dict(ip, 0)
    redis_log = envs['sr2_redis_log']
    command = 'tail -f {redis_log}/*'.format(redis_log=redis_log)
    ssh_execute_async(client=client, command=command)


# def run_deploy_v3(cluster_id=None, history_save=True, force=False):
def run_deploy(cluster_id=None, history_save=True):
    # validate cluster id
    if cluster_id is None:
        cluster_id = get_cur_cluster_id()
        if cluster_id < 1:
            msg = 'Select cluster first or type cluster id with argument'
            logger.error(msg)
            return
    if not cluster_util.validate_id(cluster_id):
        logger.error('Invalid cluster id: {}'.format(cluster_id))
        return

    # validate option
    if not isinstance(history_save, bool):
        logger.error("option '--history-save' can use only 'True' or 'False'")
        return
    logger.debug("option '--history-save': {}".format(history_save))
    # if not isinstance(force, bool):
    #     logger.error("option '--force' can use only 'True' or 'False'")
    #     return
    # logger.debug("option '--force': {}".format(force))
    _deploy(cluster_id, history_save)


def _deploy(cluster_id, history_save):
    deploy_state = DeployUtil().get_state(cluster_id)
    if deploy_state == DEPLOYED:
        q = [
            color.YELLOW,
            '(Watch out) ',
            'Cluster {} is already deployed. '.format(cluster_id),
            'Do you want to deploy again?',
            color.ENDC,
        ]
        yes = askBool(''.join(q), default='n')
        if not yes:
            logger.info('Cancel deploy.')
            return

    restore_yes = None
    current_time = strftime("%Y%m%d%H%M%s", gmtime())
    cluster_backup_dir = 'cluster_{}_bak_{}'.format(cluster_id, current_time)
    conf_backup_dir = 'cluster_{}_conf_bak_{}'.format(cluster_id, current_time)
    tmp_backup_dir = 'cluster_{}_conf_bak_{}'.format(cluster_id, 'tmp')
    meta = [['NAME', 'VALUE']]
    path_of_fb = config.get_path_of_fb(cluster_id)
    conf_path = path_of_fb['conf_path']
    props_path = path_of_fb['redis_properties']
    cluster_path = path_of_fb['cluster_path']
    path_of_cli = config.get_path_of_cli(cluster_id)
    conf_backup_path = path_of_cli['conf_backup_path']
    tmp_backup_path = path_join(conf_backup_path, tmp_backup_dir)
    local_ip = config.get_local_ip()

    # ask installer
    installer_path = ask_util.installer()
    installer_name = os.path.basename(installer_path)
    meta.append(['installer', installer_name])

    # ask restore conf
    if deploy_state == DEPLOYED:
        restore_yes = ask_util.askBool('Do you want to restore conf?')
        meta.append(['restore', restore_yes])

    # input props
    hosts = []
    if deploy_state == DEPLOYED:
        if restore_yes:
            meta += DeployUtil().get_meta_from_props(props_path)
            hosts = config.get_props(props_path, 'sr2_redis_master_hosts')
        else:
            if os.path.exists(tmp_backup_path):
                q = 'There is a history of modification. Do you want to load?'
                yes = ask_util.askBool(q)
                if not yes:
                    shutil.rmtree(tmp_backup_path)
            if not os.path.exists(tmp_backup_path):
                shutil.copytree(conf_path, tmp_backup_path)
            tmp_props_path = path_join(tmp_backup_path, 'redis.properties')
            editor.edit(tmp_props_path, syntax='sh')
            meta += DeployUtil().get_meta_from_props(tmp_props_path)
            hosts = config.get_props(tmp_props_path, 'sr2_redis_master_hosts')
    else:
        props_dict = ask_util.props(cluster_id, save=history_save)
        hosts = props_dict['hosts']
        meta += DeployUtil().get_meta_from_dict(props_dict)
    utils.print_table(meta)

    msg = [
        'Do you want to proceed with the deploy ',
        'accroding to the above information?',
    ]
    yes = askBool(''.join(msg))
    if not yes:
        logger.info("Cancel deploy.")
        return

    # check node status
    logger.info('Check status of hosts...')
    success = Center().check_hosts_connection(hosts, True)
    if not success:
        logger.error('There are unavailable host')
        return
    logger.debug('Connection of all hosts ok')
    success = Center().check_include_localhost(hosts)
    if not success:
        logger.error('Must include localhost')
        return

    # if pending, delete legacy on each hosts
    for host in hosts:
        if DeployUtil().get_state(cluster_id, host) == PENDING:
            client = get_ssh(host)
            command = 'rm -rf {}'.format(cluster_path)
            ssh_execute(client=client, command=command)
            client.close()

    # added_hosts = post_hosts - pre_hosts
    logger.info('Checking for cluster exist...')
    meta = [['HOST', 'STATUS']]
    added_hosts = set(hosts)
    if deploy_state == DEPLOYED:
        pre_hosts = config.get_props(props_path, 'sr2_redis_master_hosts')
        added_hosts -= set(pre_hosts)
    can_deploy = True
    for host in added_hosts:
        client = get_ssh(host)
        if net.is_exist(client, cluster_path):
            meta.append([host, color.red('CLUSTER EXIST')])
            can_deploy = False
            continue
        meta.append([host, color.green('CLEAN')])
    utils.print_table(meta)
    if not can_deploy:
        logger.error('Cluster information exist on some hosts.')
        return
        # if not force:
        #     logger.error("If you trying to force, use option '--force'")
        #     return

    # backup conf
    if deploy_state == DEPLOYED:
        Center().conf_backup(local_ip, cluster_id, conf_backup_dir)

    # backup cluster
    backup_hosts = []
    if deploy_state == DEPLOYED:
        backup_hosts += set(pre_hosts)
    # if force:
    #     backup_hosts += added_hosts
    for host in backup_hosts:
        cluster_path = path_of_fb['cluster_path']
        client = get_ssh(host)
        Center().cluster_backup(host, cluster_id, cluster_backup_dir)
        client.close()

    # transfer & install
    logger.info('Transfer installer and execute...')
    for host in hosts:
        logger.info(host)
        client = get_ssh(host)
        cmd = 'mkdir -p {0} && touch {0}/.deploy.state'.format(cluster_path)
        ssh_execute(client=client, command=cmd)
        client.close()
        DeployUtil().transfer_installer(host, cluster_id, installer_path)
        DeployUtil().install(host, cluster_id, installer_name)

    # setup props
    if deploy_state == DEPLOYED:
        if restore_yes:
            tag = conf_backup_dir
        else:
            tag = tmp_backup_dir
        Center().conf_restore(local_ip, cluster_id, tag)
    else:
        key = 'sr2_redis_master_hosts'
        config.make_key_enable(props_path, key)
        config.set_props(props_path, key, props_dict['hosts'])

        key = 'sr2_redis_master_ports'
        config.make_key_enable(props_path, key)
        value = cluster_util.convert_list_2_seq(props_dict['master_ports'])
        config.set_props(props_path, key, value)

        key = 'sr2_redis_slave_hosts'
        config.make_key_enable(props_path, key)
        config.set_props(props_path, key, props_dict['hosts'])
        config.make_key_disable(props_path, key)

        if props_dict['replicas'] > 0:
            key = 'sr2_redis_slave_hosts'
            config.make_key_enable(props_path, key)

            key = 'sr2_redis_slave_ports'
            config.make_key_enable(props_path, key)
            value = cluster_util.convert_list_2_seq(props_dict['slave_ports'])
            config.set_props(props_path, key, value)

        key = 'ssd_count'
        config.make_key_enable(props_path, key)
        config.set_props(props_path, key, props_dict['ssd_count'])

        key = 'sr2_redis_data'
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_disable(props_path, key)
        config.set_props(props_path, key, props_dict['prefix_of_rdp'])

        key = 'sr2_redis_db_path'
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_disable(props_path, key)
        config.set_props(props_path, key, props_dict['prefix_of_rdbp'])

        key = 'sr2_flash_db_path'
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_disable(props_path, key)
        config.set_props(props_path, key, props_dict['prefix_of_fdbp'])

    # synk props
    logger.info('Sync conf...')
    for node in hosts:
        if socket.gethostbyname(node) in config.get_local_ip_list():
            continue
        client = get_ssh(node)
        if not client:
            logger.error("ssh connection fail: '{}'".format(node))
            return
        net.copy_dir_to_remote(client, conf_path, conf_path)
        client.close()

    # set deploy state complete
    if os.path.exists(tmp_backup_path):
        shutil.rmtree(tmp_backup_path)
    for node in hosts:
        home_path = net.get_home_path(node)
        if not home_path:
            return
        path_of_fb = config.get_path_of_fb(cluster_id)
        cluster_path = path_of_fb['cluster_path']
        client = get_ssh(node)
        command = 'rm -rf {}'.format(path_join(cluster_path, '.deploy.state'))
        ssh_execute(client=client, command=command)
        client.close()

    logger.info('Complete to deploy cluster {}'.format(cluster_id))
    Cluster().use(cluster_id)


def run_passwd():
    """Set password
    """
    user = user_info['user']
    password = askPassword('Password?')
    confirm = askPassword('Password again?')
    if password != confirm:
        logger.info('Password is not same')
        return
    h = hashlib.md5(password.encode())
    h2 = h.hexdigest()
    meta = json.loads(utils.get_meta_data('auth'))
    meta[user] = {'password': h2}
    utils.set_meta_data('auth', meta)
    logger.info('Password complete.')


def run_adduser(user):
    """Add user"""
    meta = json.loads(utils.get_meta_data('auth'))
    if user in meta:
        logger.info('User "%s" exist.' % user)
        return
    meta[user] = {}
    utils.set_meta_data('auth', meta)
    logger.info('User "%s" added.' % user)


def run_fbsql():
    user = user_info['user']
    fbsql(user)


def run_cluster_use(cluster_id):
    print_mode = user_info['print_mode']
    c = Cluster(print_mode)
    c.use(cluster_id)


def run_import_conf():
    def _to_config_yaml(
          cluster_id, release, nodes, master_start_port, master_end_port,
          master_enabled, slave_start_port, slave_end_port, slave_enabled,
          ssd_count):
        conf = {}
        conf['release'] = release
        conf['nodes'] = nodes
        conf['ssd'] = {}
        conf['master_ports'] = {}
        conf['slave_ports'] = {}
        conf['master_ports']['from'] = int(master_start_port)
        conf['master_ports']['to'] = int(master_end_port)
        conf['master_ports']['enabled'] = bool(master_enabled)
        conf['slave_ports']['from'] = int(slave_start_port)
        conf['slave_ports']['to'] = int(slave_end_port)
        conf['slave_ports']['enabled'] = bool(slave_enabled)
        conf['ssd']['count'] = int(ssd_count)

        root_of_cli_config = get_root_of_cli_config()
        cluster_base_path = path_join(root_of_cli_config, 'clusters')
        if not os.path.isdir(cluster_base_path):
            os.mkdir(cluster_base_path)
        cluster_path = path_join(root_of_cli_config, 'clusters', cluster_id)
        if not os.path.isdir(cluster_path):
            os.mkdir(cluster_path)
        yaml_path = path_join(cluster_path, 'config.yaml')
        with open(yaml_path, 'w') as fd:
            yaml.dump(conf, fd, default_flow_style=False)

    def _import_from_fb_to_cli_conf(rp_exists):
        for cluster_id in rp_exists:
            path_of_fb = config.get_path_of_fb(cluster_id)
            rp = path_of_fb['redis_properties']
            d = config.get_props_as_dict(rp)
            nodes = d['sr2_redis_master_hosts']
            master_start_port = 0
            master_end_port = 0
            slave_start_port = 0
            slave_end_port = 0
            master_enabled = 'sr2_redis_master_ports' in d
            slave_enabled = 'sr2_redis_slave_ports' in d
            if master_enabled:
                master_start_port = min(d['sr2_redis_master_ports'])
                master_end_port = max(d['sr2_redis_master_ports'])
            if slave_enabled:
                slave_start_port = min(d['sr2_redis_slave_ports'])
                slave_end_port = max(d['sr2_redis_slave_ports'])
            ssd_count = d['ssd_count']
            _to_config_yaml(
                cluster_id=cluster_id,
                release='',
                nodes=nodes,
                master_start_port=master_start_port,
                master_end_port=master_end_port,
                master_enabled=master_enabled,
                slave_start_port=slave_start_port,
                slave_end_port=slave_end_port,
                slave_enabled=slave_enabled,
                ssd_count=ssd_count)
            logger.info('Save config.yaml from redis.properties')

    def _get_cluster_ids_from_fb():
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        base_directory = path_of_fb['base_directory']
        dirs = [f for f in os.listdir(base_directory)
                if not os.path.isfile(os.path.join(base_directory, f))]
        cluster_ids = [d.split('_')[1] for d in dirs if 'cluster_' in d]
        return cluster_ids

    cluster_ids = _get_cluster_ids_from_fb()
    root_of_cli_config = get_root_of_cli_config()

    rp_exists = []
    rp_not_exists = []
    dest_folder_exists = []
    meta = [['cluster_id', 'state']]
    for cluster_id in cluster_ids:
        path_of_fb = config.get_path_of_fb(cluster_id)
        rp = path_of_fb['redis_properties']
        dest_path = path_join(root_of_cli_config, 'clusters', cluster_id)
        dest_path = path_join(dest_path, 'config.yaml')
        cluster_path = path_of_fb['cluster_path']
        deploy_state = path_join(cluster_path, '.deploy.state')
        pending = DeployUtil().is_pending(cluster_id)
        if os.path.exists(dest_path):
            dest_folder_exists.append(cluster_id)
            meta.append([cluster_id, 'SKIP(dest_exist)'])
        elif os.path.isfile(rp) and not os.path.isfile(deploy_state):
            rp_exists.append(cluster_id)
            meta.append([cluster_id, 'IMPORT'])
        else:
            rp_not_exists.append(cluster_id)
            meta.append([cluster_id, 'SKIP(broken)'])

    logger.info('Diff fb and cli conf folders.')
    utils.print_table(meta)
    if len(rp_exists) == 0:
        return
    import_yes = askBool('Do you want to import conf?', ['y', 'n'])
    if not import_yes:
        return

    _import_from_fb_to_cli_conf(rp_exists)


def run_delete(cluster_id=None):
    if not cluster_id:
        cluster_id = config.get_cur_cluster_id()
    valid = cluster_util.validate_id(cluster_id)
    if not valid:
        logger.error('Invalid cluster id: {}'.format(cluster_id))
        return
    if cluster_id not in cluster_util.get_cluster_list():
        logger.error('Cluster not exist: {}'.format(cluster_id))
        return
    cluster = Cluster()
    cluster.stop(force=True, reset=True)
    # delete cluster folder
    cli_cluster_path = config.get_path_of_cli(cluster_id)["cluster_path"]

    path_of_fb = config.get_path_of_fb(cluster_id)
    fb_cluster_path = path_of_fb["cluster_path"]
    props_path = path_of_fb['redis_properties']

    key = 'sr2_redis_master_hosts'
    nodes = config.get_props(props_path, key, [])
    for node in nodes:
        client = get_ssh(node)
        cmd = [
            'rm -rf {};'.format(fb_cluster_path),
            'rm -rf {}'.format(cli_cluster_path),
        ]
        ssh_execute(client=client, command=' '.join(cmd))
        client.close()
    if config.get_cur_cluster_id() == cluster_id:
        cluster.use(-1)


def run_edit():
    p = path_join(config.get_root_of_cli_config(), 'config')
    editor.edit(p, syntax='yaml')


class Command(object):
    """This is Flashbase command line.
We use python-fire(https://github.com/google/python-fire)
for automatically generating CLIs

    - deploy: copy flashbase package to nodes
    - cli: redis-cli command wrapper
    - cluster: trib.rb cluster wrapper
    - sql: enter sql mode
    - flashbase: flashbase script wrapper (deprecated)
    - monitor: monitor logs
    - thriftserver: edit, start, stop thriftserver
    - ll: change log level to debug fbcli
    - adduser: add user
    - passwd: set password
    - c: change cluster #
    """

    def __init__(self):
        """Member variables will be cli
        """
        self.deploy = run_deploy
        self.monitor = run_monitor
        self.cluster = Cluster()
        self.thriftserver = ThriftServer()
        self.ll = log.set_level
        self.cli = Cli()
        self.passwd = run_passwd
        self.adduser = run_adduser
        self.import_conf = run_import_conf
        self.sql = run_fbsql
        self.c = run_cluster_use
        self.edit = run_edit
        self.delete = run_delete


def _handle(text):
    if text == '':
        return
    if text == 'clear':
        clear_screen()
        return
    try:
        fire.Fire(
            component=Command,
            command=text)
    except KeyboardInterrupt:
        logger.warning('\b\bCanceled')
    except KeyError as ex:
        logger.warn('[%s] command fail' % text)
        logger.exception(ex)
    except TypeError as ex:
        logger.exception(ex)
    except IOError as ex:
        if ex.errno == 2:
            logger.error("{}: '{}'".format('FileNotExistError', ex.filename))
        else:
            raise IOError(ex)
    except EOFError:
        logger.warning('\b\bCanceled')
    except CommandError as ex:
        logger.exception(ex)
    except FireExit as ex:
        pass
    except (
            PropsKeyError,
            HostNameError,
            HostConnectionError,
            SSHConnectionError,
            FileNotExistError,
            YamlSyntaxError,
            PropsSyntaxError,
    ) as ex:
        logger.error('{}: {}'.format(ex.class_name(), str(ex)))
    except BaseException as ex:
        logger.exception(ex)


def run_test():
    import center
    ip = '127.0.0.1'
    port = 18001
    center.Infra().update_redis_conf(ip, port)


def _is_auth_ok(user, password):
    # if user == 'root':
    #     logger.info('You are root user.')
    if password:
        password = hashlib.md5(password)
        password = password.hexdigest()
    utils.ensure_auth_data()
    meta = json.loads(utils.get_meta_data('auth'))
    if user not in meta:
        logger.info('"%s" is not exist' % user)
        return False
    else:
        value = meta[user]
        if 'password' in value:
            if not password:
                password = hashlib.md5(askPassword('Password?'))
                password = password.hexdigest()
            if password == value['password']:
                return True
            else:
                return False
        elif 'password' not in value:
            return True
        else:
            return False


def _handle_file(user, file_name, cluster_id):
    if int(cluster_id) == 0:
        logger.info('You can not use cluster 0 for sql')
        exit(1)
    with open(file_name, 'r') as fd:
        all_text = fd.read()
        lines = all_text.split(';')
        for line in lines:
            print_mode = user_info['print_mode']
            FbSql(user=user, print_mode=print_mode).handle(text=line)


def _initial_check():
    client = get_ssh('localhost')
    if not client:
        logger.error('Need to ssh-keygen for localhost')
        exit(1)
    cli_config = config.get_cli_config()
    try:
        base_directory = cli_config['base_directory']
    except KeyError:
        pass
    except TypeError:
        root_of_cli_config = config.get_root_of_cli_config()
        conf_path = path_join(root_of_cli_config, 'config')
        os.system('rm {}'.format(conf_path))
        base_directory = None
    if not base_directory or not base_directory.startswith(('~', '/')):
        base_directory = ask_util.base_directory()
    base_directory = os.path.expanduser(base_directory)
    if not os.path.isdir(base_directory):
        os.system('mkdir -p {}'.format(base_directory))


@click.command()
@click.option('-u', '--user', default='root', help='User.')
@click.option('-p', '--password', default=None, help='Password.')
@click.option('-c', '--cluster_id', default=None, help='ClusterId.')
@click.option('-f', '--file', default=None, help='File.')
@click.option('-d', '--debug', default=False, help='Debug.')
def main(user, password, cluster_id, file, debug):
    _initial_check()
    if debug:
        log.set_mode('debug')

    if file:
        user_info['print_mode'] = 'file'
    logger.debug('Start fbcli')
    if not cluster_id:
        cluster_id = get_cur_cluster_id()
    run_cluster_use(cluster_id)
    if cluster_id not in cluster_util.get_cluster_list() + [-1]:
        root_of_cli_config = get_root_of_cli_config()
        head_path = path_join(root_of_cli_config, 'HEAD')
        with open(head_path, 'w') as fd:
            fd.write('%s' % '-1')

    if 'test' in sys.argv:
        run_test()
        exit(0)

    if file:
        _handle_file(user, file, cluster_id)
        exit(0)

    history = path_join(get_root_of_cli_config(), 'cli_history')
    session = PromptSession(
        lexer=PygmentsLexer(SqlLexer),
        completer=fb_completer,
        history=FileHistory(history),
        auto_suggest=AutoSuggestFromHistory(),
        style=style)
    while True:
        try:
            p = get_cli_prompt(user)
            logger.info(p)
            text = session.prompt()
            if text == "exit":
                break
            if 'fbcli' in text:
                old = text
                text = text.replace('fbcli', '')
                logger.info('> You can use "%s" instead of "%s"' % (text, old))
            _handle(text)
        except KeyboardInterrupt:
            continue
        except EOFError:
            break


if __name__ == '__main__':
    main()
