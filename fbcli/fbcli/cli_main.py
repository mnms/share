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
    get_node_ip_list, get_root_of_cli_config, is_cluster_config_dir_exist
import config
from deploy_util import DeployUtil
from flashbase import Flashbase
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


def run_deploy(cluster_id=None, save=True, force=False):
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
    if type(save) is not type(bool()):
        logger.error("option '--save' can use only True or False")
        return
    logger.debug("option 'save': {}".format(save))
    if type(force) is not type(bool()):
        logger.error("option '--force' can use only True or False")
        return
    logger.debug("option 'force': {}".format(save))

    first_deploy = DeployUtil().is_first(cluster_id)
    pending = DeployUtil().is_pending(cluster_id)
    first = first_deploy or pending
    restore_yes = False
    current_time = strftime("%Y%m%d%H%M%s", gmtime())
    cluster_backup_dir = 'cluster_{}_bak_{}'.format(cluster_id, current_time)
    conf_backup_dir = 'cluster_{}_conf_bak_{}'.format(cluster_id, current_time)
    meta = [['NAME', 'VALUE']]
    local_ip = config.get_local_ip()

    # notice re-deploy
    if not first:
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
        logger.debug('delete cluster conf on cli')
        p = config.get_path_of_cli(cluster_id)
        p = path_join(p['cluster_path'], 'config.yaml')
        if os.path.isdir(p):
            shutil.rmtree(p)

    installer_path = ask_util.installer()
    meta.append(['installer', os.path.basename(installer_path)])

    nodes = []
    if first:
        nodes = ask_util.nodes(save)
    else:
        props_path = config.get_path_of_fb(cluster_id)['redis_properties']
        key = 'sr2_redis_master_hosts'
        nodes = config.get_props(props_path, key, [])
    if not nodes:
        logger.error('Nodes cannot empty')
        return
    meta.append(['nodes', '\n'.join(nodes)])

    if not first:
        restore_yes = askBool('Do you want to restore conf?', ['y', 'n'])
        meta.append(['restore', restore_yes])

    if first:
        m_ports, result = ask_util.master_ports(cluster_id)
        meta.append(['master ports', result])
        replicas = ask_util.replicas()
        if replicas > 0:
            m_count = len(m_ports)
            s_ports, result = ask_util.slave_ports(cluster_id, m_count, replicas)
            meta.append(['slave ports', result])
        ssd_count = ask_util.ssd_count(save=save)
        meta.append(['ssd count', ssd_count])
        prefix_of_rdp = ask_util.prefix_of_rdp(save=save)
        meta.append(['redis data path', prefix_of_rdp])
        prefix_of_rdbp = ask_util.prefix_of_rdbp(save=save)
        meta.append(['redis db path', prefix_of_rdbp])
        prefix_of_fdbp = ask_util.prefix_of_fdbp(save=save)
        meta.append(['flash db path', prefix_of_fdbp])

    # confirm info
    utils.print_table(meta)
    msg = [
        'Do you want to proceed with the deploy ',
        'accroding to the above information?',
    ]
    yes = askBool(''.join(msg), ['y', 'n'])
    if not yes:
        logger.info("Cancel deploy.")
        return

    # check node status
    logger.info('Check status of nodes...')
    success, msg = Center().check_node_connection(nodes, True)
    logger.debug(msg)
    if not success:
        msg = [
            'Cannot continue for the following reasons: ',
            msg,
        ]
        logger.error(''.join(msg))
        return

    success = Center().check_include_localhost(nodes)
    if not success:
        logger.error('Must include local node')
        return

    for node in nodes:
        if DeployUtil().is_pending(cluster_id, node):
            home_path = net.get_home_path(node)
            path_of_fb = config.get_path_of_fb(cluster_id, home_path=home_path)
            cluster_path = path_of_fb['cluster_path']
            client = get_ssh(node)
            if not client:
                logger.error("ssh connection fail: '{}'".format(node))
                return
            command = 'rm -rf {}'.format(cluster_path)
            ssh_execute(client=client, command=command)
            client.close()

    # check cluster exist
    if first:
        logger.info('Check lagacy...')
        meta = [['NODE', 'STATUS']]
        for node in nodes:
            can_deploy = True
            home_path = net.get_home_path(node)
            path_of_fb = config.get_path_of_fb(cluster_id, home_path=home_path)
            cluster_path = path_of_fb['cluster_path']
            client = get_ssh(node)
            if not client:
                logger.error("ssh connection fail: '{}'".format(node))
                return
            if net.is_exist(client, cluster_path):
                meta.append([node, color.red('CLUSTER EXIST')])
                can_deploy = False
                continue
            meta.append([node, color.green('OK')])
        if not can_deploy:
            logger.error('Cluster information exists on some nodes.')
            utils.print_table(meta)
            if not force:
                logger.error("If you trying to force, use option '--force'")
                return

    # backup conf
    if restore_yes:
        Center().conf_backup(local_ip, cluster_id, conf_backup_dir)

    # backup cluster
    for node in nodes:
        home_path = net.get_home_path(node)
        path_of_fb = config.get_path_of_fb(cluster_id, home_path=home_path)
        cluster_path = path_of_fb['cluster_path']
        client = get_ssh(node)
        if not client:
            logger.error("ssh connection fail: '{}'".format(node))
            return
        if net.is_exist(client, cluster_path):
            Center().cluster_backup(node, cluster_id, cluster_backup_dir)

    # install
    logger.info('Transfer installer and execute...')
    for node in nodes:
        home_path = net.get_home_path(node)
        path_of_fb = config.get_path_of_fb(cluster_id, home_path=home_path)
        cluster_path = path_of_fb['cluster_path']
        client = get_ssh(node)
        if not client:
            logger.error("ssh connection fail: '{}'".format(node))
            return
        command = 'mkdir -p {0} && touch {0}/.deploy.state'.format(cluster_path)
        ssh_execute(client=client, command=command)
        client.close()

        DeployUtil().transfer_installer(node, cluster_id, installer_path)
        DeployUtil().install(node, cluster_id, os.path.basename(installer_path))

    # set props
    if first:
        logger.info('Set up info...')
        path_of_fb = config.get_path_of_fb(cluster_id)
        conf_path = path_of_fb['conf_path']
        props_path = path_of_fb['redis_properties']

        key = 'sr2_redis_master_hosts'
        config.make_key_enable(props_path, key)
        config.set_props(props_path, key, nodes)

        key = 'sr2_redis_master_ports'
        config.make_key_enable(props_path, key)
        value = cluster_util.convert_list_2_seq(m_ports)
        config.set_props(props_path, key, value)

        key = 'sr2_redis_slave_hosts'
        config.make_key_enable(props_path, key)
        config.set_props(props_path, key, nodes)
        config.make_key_disable(props_path, key)

        if replicas > 0:
            key = 'sr2_redis_slave_hosts'
            config.make_key_enable(props_path, key)

            key = 'sr2_redis_slave_ports'
            config.make_key_enable(props_path, key)
            value = cluster_util.convert_list_2_seq(s_ports)
            config.set_props(props_path, key, value)

        key = 'ssd_count'
        config.make_key_enable(props_path, key)
        config.set_props(props_path, key, int(ssd_count))

        key = 'sr2_redis_data'
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_disable(props_path, key)
        config.set_props(props_path, key, prefix_of_rdp)

        key = 'sr2_redis_db_path'
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_disable(props_path, key)
        config.set_props(props_path, key, prefix_of_rdbp)

        key = 'sr2_flash_db_path'
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_disable(props_path, key)
        config.set_props(props_path, key, prefix_of_fdbp)

    conf_path = path_of_fb['conf_path']
    for node in nodes:
        if socket.gethostbyname(node) in [local_ip, '127.0.0.1']:
            continue
        client = get_ssh(node)
        if not client:
            logger.error("ssh connection fail: '{}'".format(node))
            return
        net.copy_dir_to_remote(client, conf_path, conf_path)
        client.close()

    # restore conf
    if restore_yes:
        for node in nodes:
            Center().conf_restore(node, cluster_id, conf_backup_dir)

    # set deploy state complete
    for node in nodes:
        home_path = net.get_home_path(node)
        if not home_path:
            return
        home_path = net.get_home_path(node)
        path_of_fb = config.get_path_of_fb(cluster_id, home_path=home_path)
        cluster_path = path_of_fb['cluster_path']
        client = get_ssh(node)
        if not client:
            logger.error("ssh connection fail: '{}'".format(node))
            return
        command = 'rm -r {}'.format(path_join(cluster_path, '.deploy.state'))
        ssh_execute(client=client, command=command)
        client.close()

    logger.info('Complete to deploy cluster {}'.format(cluster_id))
    Cluster().use(cluster_id)
    return


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


def fbcli_edit():
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
        self.flashbase = Flashbase()
        self.cluster = Cluster()
        self.thriftserver = ThriftServer()
        self.ll = log.set_level
        self.cli = Cli()
        self.passwd = run_passwd
        self.adduser = run_adduser
        self.import_conf = run_import_conf
        self.sql = run_fbsql
        self.c = run_cluster_use
        self.edit = fbcli_edit


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
    except KeyboardInterrupt as e:
        logger.warning('\b\bKeyboardInterrupt')
    except KeyError as e:
        logger.warn('[%s] command fail' % text)
        logger.exception(e)
    except TypeError as e:
        logger.exception(e)
    except CommandError as e:
        logger.exception(e)
    except FireExit as e:
        pass
        # if e.code is not 0:
        #     logger.exception(e)
    except BaseException as ex:
        logger.exception(ex)


def run_test():
    import center
    ip = '127.0.0.1'
    port = 18001
    center.Infra().update_redis_conf(ip, port)


def _repair_meta_cluster():
    _ = get_root_of_cli_config()  # check repo path
    meta_cluster_id = 0
    dir_exist = is_cluster_config_dir_exist(meta_cluster_id)
    if dir_exist:
        logger.info('Meta cluster config exist. (go to next step)')
    else:
        logger.info('Meta cluster config not exist.')
        yes = askBool('Do you want to create META CLUSTER config folder?')
        if yes:
            template = -1
            Cluster().clone(template, meta_cluster_id)
            _repair_meta_cluster()
        else:
            logger.info('aborted')
            exit(1)
    _run_deploy(0)
    yes = askBool('Do you want to restart cluster?')
    if yes:
        force = askBool('(Watch out) Do you want forced restart?', default='n')
        reset = askBool('(Watch out) Do you want reset?', default='n')
        Cluster().restart(force=force, reset=reset)
        exit(0)


def _is_meta_cluster_ok():
    get_root_of_cli_config()  # check repo path
    try:
        utils.create_cluster_connection_0()
        return True
    except:
        return False


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
    base_directory = cli_config['base_directory']
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