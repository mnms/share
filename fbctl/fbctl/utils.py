#!/usr/bin/python
# -*- coding: UTF-8 -*-
import json
import os
import sys
from os.path import join as path_join

from prompt_toolkit.styles import Style
from rediscluster import StrictRedisCluster
from terminaltables import AsciiTable

import config
import editor
from log import logger
from exceptions import ConvertError


class TermColor:
    """This is for term text color
    """
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    @staticmethod
    def green(msg):
        return TermColor.OKGREEN + msg + TermColor.ENDC

    @staticmethod
    def fail(msg):
        return TermColor.FAIL + msg + TermColor.ENDC

    @staticmethod
    def blue(msg):
        return TermColor.OKBLUE + msg + TermColor.ENDC


class RangeChecker(object):
    """This class for checking range of index

    Update min max value
    """
    def __init__(self):
        self.min_index = 99999999
        self.max_index = 0

    def check(self, cur_index):
        """Update min, max index value
        :param cur_index: cur index
        """
        if self.min_index > cur_index:
            self.min_index = cur_index
        if self.max_index < cur_index:
            self.max_index = cur_index


def print_table(meta):
    """Print data as table format
    """
    table = AsciiTable(meta)
    print(table.table)


def get_ip_port_tuple_list(ip_list, port_list):
    """Convert as ip | port tuple data(list)
    """
    targets = []
    for ip in ip_list:
        for port in port_list:
            targets.append((ip, port))
    return targets


def get_ip_port_dict_list(ip_list, port_list):
    """Convert as ip | port dict list
    """
    targets = []
    for ip in ip_list:
        for port in port_list:
            targets.append({'host': ip, 'port': port})
    return targets


class Error(Exception):
    """Base class for exceptions in this module."""
    pass


class DuplicatedError(Error):
    def __init__(self, target):
        self.target = target
        logger.error('DuplicatedError: %s' % target)


class CommandError(Error):
    def __init__(self, exit_status, command, hostname, port):
        self.exit_status = exit_status
        self.command = command
        self.hostname = hostname
        self.port = port
        logger.error('''CommandError: 
exit_status="{exit_status}"
command="{command}"
host:port="{hostname}:{port}"'''.format(
            exit_status=exit_status,
            command=command,
            hostname=hostname,
            port=port))


# table print
def tprint(dictionary, header=['key', 'value']):
    """Table print dictionary

    :param dictionary: dictionary
    :param header: header
    """
    items = dictionary.items()
    sorted_list = sorted(items, key=lambda x: x[1])
    tr = TableReport(header)
    tr.data = sorted_list
    tr.print_out()


def tprint_list(rows, header=['key', 'value1', 'value2']):
    """Table print list

    :param rows: list
    :param header: header
    """
    tr = TableReport(header)
    tr.data = rows
    tr.print_out()


class TableReport(object):
    """This is for logging important information and print out as table format
    """
    def __init__(self, column):
        self.header = [column]
        self.data = []

    def append(self, item):
        """Append data

        :param item: data
        """
        self.data.append(item)

    def success(self):
        """Append success event as green color
        """
        self.data.append([
            sys._getframe(1).f_code.co_name,
            TermColor.green('ok')])

    def fail(self):
        """Append fail event as red color
        """
        self.data.append([
            sys._getframe(1).f_code.co_name,
            TermColor.fail('fail')])

    def print_out(self):
        """Print out result
        """
        table = AsciiTable(self.header + self.data)
        print(table.table)


def clear_screen():
    """Clear screen
    """
    os.system('cls' if os.name == 'nt' else 'clear')


style = Style.from_dict({
    'completion-menu.completion': 'bg:#008888 #ffffff',
    'completion-menu.completion.current': 'bg:#00aaaa #000000',
    'scrollbar.background': 'bg:#88aaaa',
    'scrollbar.button': 'bg:#222222',
})


def create_cluster_connection_0():
    """Create cluster 0 for metadata db

    :return: redis cluster instance
    """
    cluster_id = 0
    ip_list = config.get_node_ip_list(cluster_id)
    port_list = config.get_master_port_list(cluster_id)
    startup_nodes = get_ip_port_dict_list(ip_list, port_list)
    rc = StrictRedisCluster(startup_nodes=startup_nodes,
                            decode_responses=True)
    return rc


def get_meta_data(key):
    """Get meta data from cluster 0

    :param key: key
    :return: metadata (string format)
    """
    rc = create_cluster_connection_0()
    return rc.get(key)


def get_meta_data_after_ensure(key, default_value={}):
    """Get meta data after ensure from cluster 0

    :param key: key
    :param default_value: default value (dict)
    :return: metadata (string format)
    """
    md = get_meta_data(key)
    if not md:
        rc = create_cluster_connection_0()
        rc.set(key, json.dumps(default_value))
        return get_meta_data(key)
    return md


def set_meta_data(key, value):
    """Set meta data to cluster 0

    :param key: key
    :param value: value
    """
    rc = create_cluster_connection_0()
    return rc.set(key, json.dumps(value))


def ensure_auth_data():
    """Ensure auth data
    """
    key = 'auth'
    return get_meta_data_after_ensure(key, {'root': {}})


def get_full_path_of_props(cluster_id=-1, target='config'):
    """Get full path of props

    When user wants to edit props files, use it.

    :param cluster_id: cluster #
    :param target: target config (config | master | slave | thriftserver)
    """
    targets = {
        'config': 'config.yaml',
        'master': 'tsr2-conf/redis-master.conf.template',
        'slave': 'tsr2-conf/redis-slave.conf.template',
        'thriftserver': 'tsr2-conf/thriftserver.properties',
    }
    home = config.get_repo_cluster_path(cluster_id)
    f = targets[target]
    full_path = path_join(home, f)
    return full_path


def open_vim_editor(target='config'):
    """Open vim editor
    :param target: config | master | slave | thriftserver
    """
    cluster_id = config.get_cur_cluster_id()
    full_path = get_full_path_of_props(cluster_id, target)
    editor.edit(full_path)


def clear_meta(key, value):
    """Clear meta
    """
    rc = create_cluster_connection_0()
    return rc.set(key, json.dumps(value))


def make_export_envs(ip, port):
    """Make export env
    """
    envs = config.get_env_dict(ip, port)
    cmd = '''\
export SR2_REDIS_HOME={sr2_redis_home} ; \
export SR2_REDIS_BIN={sr2_redis_bin} ; \
export SR2_REDIS_LIB={sr2_redis_lib} ; \
export SR2_REDIS_CONF={sr2_redis_conf} ; \
export SR2_REDIS_LOG={sr2_redis_log} ; \
export SR2_REDIS_DATA={sr2_redis_data} ; \
export SR2_REDIS_DUMP={sr2_redis_dump} ; \
export SR2_REDIS_DB_PATH={sr2_redis_db_path} ; \
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:{ld_library_path} ; \
export DYLD_LIBRARY_PATH=$DYLD_LIBRARY_PATH:{dyld_library_path}''' \
        .format(**envs)
    return cmd


def convert_list_2_hyphen(ports):
    '''
    converted as shown below
    [1, 2, 3, 5, 7, 8, 10]
    =>
    ['1-3', '5', '7-8', 10]
    '''
    logger.debug('ports: {}'.format(ports))
    ret = []
    s = ports[0]
    pre = ports[0] - 1
    try:
        for port in ports:
            if pre != port - 1:
                if s != pre:
                    ret.append('{}-{}'.format(s, pre))
                else:
                    ret.append(str(s))
                s = port
            pre = port
        if s != pre:
            ret.append('{}-{}'.format(s, pre))
        else:
            ret.append(str(s))
        logger.debug('converted: {}'.format(ret))
        return ret
    except Exception:
        raise ConvertError("Invalid ports: '{}'".format(ports))
