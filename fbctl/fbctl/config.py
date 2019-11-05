import os
import socket
from os.path import join as path_join
from time import gmtime, strftime
import re
import subprocess
import shutil

import yaml

from log import logger
from exceptions import (
    FileNotExistError,
    YamlSyntaxError,
    PropsSyntaxError,
    ClusterIdError,
    ClusterNotExistError,
    PropsError,
    PropsKeyError,
)

# start_port = 18000


def get_local_ip():
    return socket.gethostbyname(socket.getfqdn())


def get_local_ip_list():
    return [
        socket.gethostbyname(socket.gethostname()),
        socket.gethostname(),
        'localhost',
        '127.0.0.1'
    ]


def get_root_of_cli_config():
    if 'FBPATH' not in os.environ:
        msg = [
            'To start using fbctl, you should set env FBPATH',
            'ex)',
            'export FBPATH=$HOME/.flashbase'
        ]
        logger.error('\n'.join(msg))
        exit(1)
    p = os.environ['FBPATH']
    if not os.path.exists(p):
        os.path.mkdir(p)
    return os.environ['FBPATH']


def get_cur_cluster_id(allow_empty_id=False):
    """Get cur cluster id

    :return: cluster #
    """
    root_of_cli_config = get_root_of_cli_config()
    head_path = path_join(root_of_cli_config, 'HEAD')
    if not os.path.exists(head_path):
        with open(head_path, 'w') as fd:
            fd.writelines(str(-1))
    with open(head_path, 'r') as fd:
        line = fd.readline().strip()
        cluster_id = line
    if line == '-1' and allow_empty_id:
        return -1
    if not line.decode('utf-8').isdecimal():
        raise ClusterIdError(cluster_id)
    cluster_id = int(cluster_id)
    base_directory = get_base_directory()
    buf = os.listdir(base_directory)
    buf = filter(lambda x: x.startswith('cluster_'), buf)
    buf = map(lambda x: int(x[8:]), buf)
    cluster_list = []
    for cid in buf:
        cluster_dir = 'cluster_{}'.format(cid)
        cluster_path = os.path.join(base_directory, cluster_dir)
        if not os.path.isfile(os.path.join(cluster_path, '.deploy.state')):
            cluster_list.append(int(cid))
    if cluster_id not in cluster_list:
        raise ClusterNotExistError(cluster_id)
    return cluster_id


def get_repo_cluster_path(cluster_id=-1):
    """Get repo cluster path

    Let cur cluster id is 1, then return ${root_of_cli_config}/clusters/1

    :return: repo cluster path
    """
    root_of_cli_config = get_root_of_cli_config()
    if cluster_id < 0:
        cluster_id = get_cur_cluster_id()
    return path_join(root_of_cli_config, 'clusters', str(cluster_id))


def get_repo_cluster_template_path():
    """Get repo cluster template path

    Let cur cluster id is 1, then return ${root_of_cli_config}/clusters/template

    :return: repo cluster template path
    """
    root_of_cli_config = get_root_of_cli_config()
    return path_join(root_of_cli_config, 'clusters', 'template')


def get_config(cluster_id=-1, template=False):
    """Get config

    :param cluster_id: target cluster #
    :param template: If true, get config from template
    :return: config dict
    """
    if template:
        cur_cluster_path = get_repo_cluster_template_path()
    else:
        cur_cluster_path = get_repo_cluster_path(cluster_id)
    yml_path = path_join(cur_cluster_path, 'config.yaml')
    with open(yml_path, 'r') as fd:
        fb_config = yaml.safe_load(fd)
        return fb_config
    assert False
    return None


def get_node_ip_list(cluster_id=-1):
    """Get node ip list from config

    :param cluster_id: target cluster #
    :return: list of ip
    """
    if cluster_id == -1:
        cluster_id = get_cur_cluster_id()
    path_of_fb = get_path_of_fb(cluster_id)
    props_path = path_of_fb['redis_properties']
    key = 'sr2_redis_master_hosts'
    nodes = get_props(props_path, key, [])
    ip_list = []
    for node in nodes:
        ip = socket.gethostbyname(node)
        ip_list.append(ip)
    return ip_list


def get_master_host_list(cluster_id=None):
    if cluster_id is None:
        cluster_id = get_cur_cluster_id()
    path_of_fb = get_path_of_fb(cluster_id)
    props_path = path_of_fb['redis_properties']
    key = 'sr2_redis_master_hosts'
    hosts = get_props(props_path, key, [])
    return hosts


def get_master_ip_list(cluster_id=None):
    if cluster_id is None:
        cluster_id = get_cur_cluster_id()
    hosts = get_master_host_list(cluster_id)
    ip_list = []
    for host in hosts:
        ip = socket.gethostbyname(host)
        ip_list.append(ip)
    return ip_list


def get_slave_host_list(cluster_id=None):
    if cluster_id is None:
        cluster_id = get_cur_cluster_id()
    path_of_fb = get_path_of_fb(cluster_id)
    props_path = path_of_fb['redis_properties']
    key = 'sr2_redis_slave_hosts'
    hosts = get_props(props_path, key, [])
    return hosts


def get_slave_ip_list(cluster_id=None):
    if cluster_id is None:
        cluster_id = get_cur_cluster_id()
    hosts = get_slave_host_list(cluster_id)
    ip_list = []
    for host in hosts:
        ip = socket.gethostbyname(host)
        ip_list.append(ip)
    return ip_list


def get_replicas(cluster_id=None):
    """Get replicas using master, slave port count

    :return: replicas
    """
    if cluster_id is None:
        cluster_id = get_cur_cluster_id()
    m_len = len(get_master_port_list(cluster_id))
    if m_len <= 0:
        raise PropsKeyError('sr2_redis_master_hosts')
    s_len = len(get_slave_port_list(cluster_id))
    if s_len <= 0:
        raise PropsKeyError('sr2_redis_slave_hosts')
    if s_len % m_len is not 0:
        msg = [
            'The number of slaves should be multiple values ',
            'with the number of masters.\n',
            'master: {}\n'.format(m_len),
            'slave: {}'.format(s_len),
        ]
        raise PropsError(''.join(msg))
    return s_len / m_len


def get_master_port_list(cluster_id=-1):
    """Get master port list

    :param cluster_id: target cluster #
    :return: master port list
    """
    if cluster_id == -1:
        cluster_id = get_cur_cluster_id()
    path_of_fb = get_path_of_fb(cluster_id)
    props_path = path_of_fb['redis_properties']
    key = 'sr2_redis_master_ports'
    ports = get_props(props_path, key, [])
    return ports


def get_slave_port_list(cluster_id=-1):
    """Get slave port list

    :return: slave port list
    """
    if cluster_id == -1:
        cluster_id = get_cur_cluster_id()
    path_of_fb = get_path_of_fb(cluster_id)
    props_path = path_of_fb['redis_properties']
    key = 'sr2_redis_slave_ports'
    ports = get_props(props_path, key, [])
    return ports


def is_slave_enabled():
    """Return slave enable or not using config

    :return: True | False
    """
    cluster_id = get_cur_cluster_id()
    path_of_fb = get_path_of_fb(cluster_id)
    props_path = path_of_fb['redis_properties']
    key = 'sr2_redis_slave_hosts'
    return is_key_enable(props_path, key)


def get_base_directory(expanduser=True):
    cli_config = get_cli_config()
    base_directory = cli_config['base_directory']
    if expanduser:
        base_directory = os.path.expanduser(base_directory)
    return base_directory


def get_tsr2_home(cluster_id=None):
    """Get tsr2 home path

    This is for deploy, copy redis.conf, backup remote logs, etc.

    :param cluster_id: target cluster #
    :return: tsr2 home path
    """
    if cluster_id is None:
        cluster_id = get_cur_cluster_id()
    base_directory = get_base_directory()
    tsr2_home = path_join(
        base_directory,
        'cluster_{}'.format(cluster_id),
        'tsr2-assembly-1.0.0-SNAPSHOT'
    )
    return tsr2_home


def get_sata_ssd_no(port, count, digit):
    if count < 1:
        return ''
    rest_number = str(port % count + 1).zfill(digit)
    return path_join(rest_number, 'nvkvs')


def get_ssd_disk_position(port, digit=2):
    user = os.environ['USER']
    cluster_id = get_cur_cluster_id()
    path_of_fb = get_path_of_fb(cluster_id)
    props_path = path_of_fb['redis_properties']
    ssd_count = int(get_props(props_path, 'ssd_count', 0))
    redis_data_prefix = get_props(props_path, 'sr2_redis_data')
    flash_db_path_prefix = get_props(props_path, 'sr2_flash_db_path')
    redis_data = path_join(
        redis_data_prefix + get_sata_ssd_no(port, ssd_count, digit),
        user,
    )
    flash_db_path = path_join(
        flash_db_path_prefix + get_sata_ssd_no(port, ssd_count, digit),
        user,
        'db/db-{port}'.format(port=port),
    )
    redis_dump = path_join(redis_data, 'dump')
    return {
        'sr2_redis_data': redis_data,
        'sr2_flash_db_path': flash_db_path,
        'sr2_redis_dump': redis_dump,
        'sr2_redis_db_path': flash_db_path,
    }


def get_path_of_fb(cluster_id):
    base_directory = get_base_directory()
    cluster_dir = 'cluster_{}'.format(cluster_id)
    cluster_path = path_join(base_directory, cluster_dir)
    cluster_backup_path = path_join(base_directory, 'backup')
    release_path = path_join(base_directory, 'releases')
    sr2_home = get_tsr2_home(cluster_id)
    conf_path = path_join(sr2_home, 'conf')
    redis_properties = path_join(conf_path, 'redis.properties')
    master_template = path_join(conf_path, 'redis-master.conf.template')
    slave_template = path_join(conf_path, 'redis-slave.conf.template')
    thrift_properties = path_join(conf_path, 'thriftserver.properties')
    sr2_redis_log = path_join(sr2_home, 'logs', 'redis')
    sr2_redis_conf = path_join(sr2_home, 'conf', 'redis')
    sr2_redis_conf_temp = path_join(sr2_home, 'conf', 'temp')
    sr2_redis_bin = path_join(sr2_home, 'bin')
    sr2_redis_lib = path_join(sr2_home, 'lib')

    return {
        'base_directory': base_directory,
        'cluster_path': cluster_path,
        'cluster_backup_path': cluster_backup_path,
        'conf_path': conf_path,
        'release_path': release_path,
        'redis_properties': redis_properties,
        'master_template': master_template,
        'slave_template': slave_template,
        'thrift_properties': thrift_properties,
        'sr2_redis_home': sr2_home,
        'sr2_redis_log': sr2_redis_log,
        'sr2_redis_conf': sr2_redis_conf,
        'sr2_redis_conf_temp': sr2_redis_conf_temp,
        'sr2_redis_bin': sr2_redis_bin,
        'sr2_redis_lib': sr2_redis_lib,
    }


def get_env_dict(ip, port):
    """Collection of env

    Build env from config and return it as dict type.

    :param ip: ip
    :param port: port
    :return: dict
    """

    ssd_disk_position = get_ssd_disk_position(port)
    cluster_id = get_cur_cluster_id()
    path_of_fb = get_path_of_fb(cluster_id)
    return {
        'sr2_redis_home': path_of_fb['sr2_redis_home'],
        'sr2_redis_bin': path_of_fb['sr2_redis_bin'],
        'sr2_redis_lib': path_of_fb['sr2_redis_lib'],
        'sr2_redis_conf': path_of_fb['sr2_redis_conf'],
        'sr2_redis_log': path_of_fb['sr2_redis_log'],
        'sr2_redis_data': ssd_disk_position['sr2_redis_data'],
        'sr2_redis_dump': ssd_disk_position['sr2_redis_dump'],
        'sr2_flash_db_path': ssd_disk_position['sr2_flash_db_path'],
        'sr2_redis_db_path': ssd_disk_position['sr2_redis_db_path'],
        'ld_library_path': ':'.join([
            '{}/native'.format(path_of_fb['sr2_redis_lib']),
            '/usr/lib64',
        ]),
        'dyld_library_path': ':'.join([
            '{}/native'.format(path_of_fb['sr2_redis_lib']),
            '/usr/lib64',
        ]),
        'sr2_redis_host': ip,
        'sr2_redis_port': port,
    }


def get_path_of_cli(cluster_id):
    root_of_cli_config = os.path.expanduser(get_root_of_cli_config())
    conf_backup_path = path_join(root_of_cli_config, 'conf_backup')
    release_path = path_join(root_of_cli_config, 'releases')
    cluster_path = path_join(root_of_cli_config, 'clusters', str(cluster_id))
    conf_path = path_join(cluster_path, 'conf')
    redis_properteis = path_join(conf_path, 'redis.properties')

    return {
        'cli_config_root': root_of_cli_config,
        'conf_backup_path': conf_backup_path,
        'release_path': release_path,
        'cluster_path': cluster_path,
        'conf_path': conf_path,
        'redis_properties': redis_properteis,
    }


def reset_conf_of_cli(cluster_id, backup=False):
    logger.debug('reset conf of cli')
    path_of_fb = get_path_of_fb(cluster_id)
    path_of_cli = get_path_of_cli(cluster_id)
    if backup and os.path.isdir(path_of_cli['conf_path']):
        current_time = strftime("%Y%m%d%H%M%s", gmtime())
        conf_backup_dir = 'cluster_{}_conf_bak_{}'.format(
            cluster_id, current_time)
        conf_backup_path = path_of_cli['conf_backup_path']
        shutil.copytree(
            path_of_fb['conf_path'],
            path_join(
                conf_backup_path,
                conf_backup_dir))
        logger.debug("conf backup: '{}'".format(conf_backup_dir))
    if not os.path.isdir(path_of_cli['cluster_path']):
        logger.debug(
            "FileNotExisted: '{}'".format(
                path_of_cli['cluster_path']))
        os.mkdir(path_of_cli['cluster_path'])
        logger.debug("CreateDir: '{}'".format(path_of_cli['cluster_path']))
    if os.path.isdir(path_of_cli['conf_path']):
        shutil.rmtree(path_of_cli['conf_path'], ignore_errors=True)
        logger.debug("RemoveDir: '{}'".format(path_of_cli['conf_path']))
    shutil.copytree(path_of_fb['conf_path'], path_of_cli['conf_path'])
    msg = [
        'copy tree',
        "from '{}'".format(path_of_fb['conf_path']),
        "to '{}'".format(path_of_cli['conf_path']),
    ]
    logger.debug(' '.join(msg))


def get_cli_config():
    root_of_cli_config = get_root_of_cli_config()
    conf_path = path_join(root_of_cli_config, 'config')
    conf_exist = os.path.exists(conf_path)
    if not conf_exist:
        with open(conf_path, 'w') as fd:
            fd.writelines("base_directory:")
    with open(path_join(root_of_cli_config, 'config'), 'r') as f:
        cli_config = yaml.safe_load(f)
    return cli_config


def save_cli_config(cli_config):
    root_of_cli_config = get_root_of_cli_config()
    with open(path_join(root_of_cli_config, 'config'), 'w') as f:
        yaml.dump(cli_config, f, default_flow_style=False)


def is_key_enable(props_path, key):
    with open(props_path, 'r') as f:
        key = key.upper()  # SR2_REDIS_MASTER_HOSTS
        lines = f.readlines()
        for i, line in enumerate(lines):
            p = re.compile(r'export {}=(\(.+\)|[^ \s\t\r\n\v\f]+)'.format(key))
            m = p.match(line)
            if m:
                return True
        return False


# FIXME: delete v1 flg after meeting
def make_key_enable(props_path, key, v1_flg=False):
    if is_key_enable(props_path, key):
        if not v1_flg:
            return
    with open(props_path, 'r') as f:
        buf = []
        key = key.upper()  # SR2_REDIS_MASTER_HOSTS
        lines = f.readlines()
        for i, line in enumerate(lines):
            p = re.compile(r'export {}=(\(.+\)|[^ \s\t\r\n\v\f]+)'.format(key))
            m = p.search(line)
            if line.strip().startswith('#') and m:
                s = m.start()
                buf.append(line[s:])
                buf = buf + lines[i + 1:]
                break
            buf.append(line)
    with open(props_path, 'w') as f:
        f.write(''.join(buf))


def make_key_disable(props_path, key):
    with open(props_path, 'r') as f:
        buf = []
        key = key.upper()  # SR2_REDIS_MASTER_HOSTS
        lines = f.readlines()
        for i, line in enumerate(lines):
            p = re.compile(r'export {}=(\(.+\)|[^ \s\t\r\n\v\f]+)'.format(key))
            m = p.match(line)
            if m:
                buf.append('#' + line)
                buf = buf + lines[i + 1:]
                break
            buf.append(line)
    with open(props_path, 'w') as f:
        f.write(''.join(buf))


def set_props(props_path, key, value):
    if isinstance(value, type(str())):
        value = '"{}"'.format(value)
    if type(value) in [type(list()), type(tuple()), type(set())]:
        def f(x): return '"{}"'.format(x) if isinstance(
            x, type(str())) and not x.startswith('$') else x
        value = map(f, value)
        def f(x): return str(x) if isinstance(x, type(int())) else x
        value = map(f, value)
        value = "( {} )".format(' '.join(value))
    key = key.upper()

    with open(props_path, 'r') as f:
        buf = []
        lines = f.readlines()
        for i, line in enumerate(lines):
            p = re.compile(r'export {}=(\(.+\)|[^ \s\t\r\n\v\f]+)'.format(key))
            m = p.match(line)
            if m:
                buf.append('export {}={}\n'.format(key, value))
                buf = buf + lines[i + 1:]
                break
            buf.append(line)
    with open(props_path, 'w') as f:
        f.write(''.join(buf))


def get_props(props_path, key, default=None):
    logger.debug('Get props key: {}, default: {}'.format(key, default))
    props = get_props_as_dict(props_path)
    logger.debug(props)
    try:
        return props[key]
    except KeyError as e:
        msg = [
            "Key error in props: '{}'".format(key),
            "get default '{}'".format(default),
        ]
        logger.debug(' '.join(msg))
        return default
    except IOError as e:
        msg = [
            "Props file is not existed",
            "get default '{}'".format(default),
        ]
        logger.warning(' '.join(msg))
        return default


def get_props_as_dict(props_path):
    ret = dict()
    with open(props_path, 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if line.strip().startswith('#'):
                continue
            p = re.compile(
                r'export [^ \s\t\r\n\v\f]+=(\(.+\)|[^ \s\t\r\n\v\f]+)')
            m = p.search(line)
            if not m:
                continue
            s = m.start()
            e = m.end()
            key, value = line[s:e + 1].replace('export ', '').split('=')
            value = value.strip()
            key = key.lower()
            p = re.compile(r'\(.*\)')
            m = p.match(value)
            def f(x): return int(x) if x.decode('utf-8').isdecimal() else x
            try:
                if m:
                    cmd = [
                        'FBCLI_TMP_ENV={}'.format(value),
                        '&&',
                        'echo ${FBCLI_TMP_ENV[@]}'
                    ]
                    cmd = ' '.join(cmd)
                    logger.debug('subprocess cmd: {}'.format(cmd))
                    value = subprocess.check_output(cmd, shell=True).strip()
                    logger.debug('subprocess result: {}'.format(value))
                    value = value.split(' ')
                    value = map(f, value)
                else:
                    cmd = 'echo {}'.format(value)
                    value = subprocess.check_output(cmd, shell=True).strip()
                    value = f(value)
                ret[key] = value
            except subprocess.CalledProcessError:
                raise PropsSyntaxError(value, i + 1)
    return ret


def get_deploy_history():
    file_path = path_join(get_root_of_cli_config(), 'deploy_history')
    default = {
        'hosts': ['127.0.0.1'],
        'master_count': 1,
        'replicas': 2,
        'ssd_count': 3,
        'prefix_of_rd': '~/sata_ssd/ssd_',
        'prefix_of_rdbp': '~/sata_ssd/ssd_',
        'prefix_of_fdbp': '~/sata_ssd/ssd_',
    }
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            yaml.dump(default, f, default_flow_style=False)
    try:
        with open(file_path, 'r') as f:
            ret = yaml.safe_load(f)
        if ret is None:
            with open(file_path, 'w') as f:
                yaml.dump(default, f, default_flow_style=False)
        with open(file_path, 'r') as f:
            ret = yaml.safe_load(f)
        with open(file_path, 'w') as f:
            d_keys = default.keys()
            r_keys = ret.keys()
            for key in d_keys:
                if key not in r_keys:
                    ret[key] = default[key]
            yaml.dump(ret, f, default_flow_style=False)
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)
    except yaml.scanner.ScannerError:
        raise YamlSyntaxError(file_path)


def save_deploy_history(history):
    file_path = path_join(get_root_of_cli_config(), 'deploy_history')
    with open(file_path, 'w') as f:
        yaml.dump(history, f, default_flow_style=False)


def ensure_host_not_changed(tmp_path):
    cluster_id = get_cur_cluster_id()
    path_of_fb = get_path_of_fb(cluster_id)
    props_path = path_of_fb['redis_properties']
    tmp_host_list = get_props(tmp_path, 'sr2_redis_master_hosts')
    master_host_list = get_props(props_path, 'sr2_redis_master_hosts')
    if sorted(master_host_list) != sorted(tmp_host_list):
        raise PropsError("Cannot edit 'SR2_REDIS_MASTER_HOSTS'")
    slave_enable = is_key_enable(props_path, 'sr2_redis_slave_hosts')
    if slave_enable:
        tmp_host_list = get_props(tmp_path, 'sr2_redis_slave_hosts')
        slave_host_list = get_props(props_path, 'sr2_redis_slave_hosts')
        if sorted(slave_host_list) != sorted(tmp_host_list):
            raise PropsError("Cannot edit 'SR2_REDIS_SLAVE_HOSTS'")
