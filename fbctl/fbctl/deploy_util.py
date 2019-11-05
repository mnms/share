import fileinput
import socket
from os.path import join as path_join
import os

from exceptions import PropsKeyError
from config import get_node_ip_list
from log import logger
from net import get_ssh, ssh_execute, get_home_path, get_sftp
from utils import convert_list_2_hyphen
import config
import net
from exceptions import FileNotExistError


CLEAN = 101
PENDING = 102
DEPLOYED = 103


class DeployUtil(object):

    def get_state(self, cluster_id, host='127.0.0.1'):
        path_of_fb = config.get_path_of_fb(cluster_id)
        cluster_path = path_of_fb['cluster_path']
        state_file = path_join(cluster_path, '.deploy.state')
        client = get_ssh(host)
        if net.is_exist(client, state_file):
            return PENDING
        if net.is_dir(client, cluster_path):
            return DEPLOYED
        return CLEAN

    def is_pending(self, cluster_id, nodes=['127.0.0.1']):
        if isinstance(nodes, str):
            nodes = [nodes]
        for node in nodes:
            path_of_fb = config.get_path_of_fb(cluster_id)
            cluster_path = path_of_fb['cluster_path']
            deploy_state = path_join(cluster_path, '.deploy.state')
            client = get_ssh(node)
            if net.is_exist(client, deploy_state):
                client.close()
                return True
            client.close()
        return False

    def transfer_installer(self, host, cluster_id, installer_path):
        installer_path = os.path.expanduser(installer_path)
        path_of_fb = config.get_path_of_fb(cluster_id)
        name = os.path.basename(installer_path)
        dst = path_join(path_of_fb['release_path'], name)

        client = get_ssh(host)
        sftp = get_sftp(client)

        if not net.is_dir(client, path_of_fb['release_path']):
            logger.debug("Not exist releases directory at '{}'".format(host))
            sftp.mkdir(path_of_fb['release_path'])
            logger.debug("Create releases directory at '{}'".format(host))

        logger.debug('Check {}...'.format(name))
        if not net.is_exist(client, dst):
            logger.debug('FAIL')
            logger.debug("Transfer '{}' to '{}'...".format(name, host))
            sftp.put(installer_path, '{}.download'.format(dst))
            command = 'mv {0}.download {0}'.format(dst)
            ssh_execute(client=client, command=command)
        sftp.close()
        client.close()
        logger.debug('OK')

    def install(self, host, cluster_id, name):
        logger.debug('Deploy cluster {} at {}...'.format(cluster_id, host))
        path_of_fb = config.get_path_of_fb(cluster_id)
        release_path = path_of_fb['release_path']
        cluster_path = path_of_fb['cluster_path']
        if '/' in name:
            name = os.path.basename(name)
        installer_path = path_join(release_path, name)
        command = '''chmod 755 {0}; \
            PATH=${{PATH}}:/usr/sbin; \
            {0} --full {1}'''.format(installer_path, cluster_path)
        client = get_ssh(host)
        if not net.is_exist(client, installer_path):
            raise FileNotExistError(installer_path, host=host)
        ssh_execute(client=client, command=command)
        client.close()
        logger.debug('OK')

    def get_meta_from_props(self, props_path):
        try:
            dic = config.get_props_as_dict(props_path)
            ret = [['hosts', '\n'.join(dic['sr2_redis_master_hosts'])]]
            converted = convert_list_2_hyphen(dic['sr2_redis_master_ports'])
            ret += [['master ports', ', '.join(converted)]]
            if config.is_key_enable(props_path, 'sr2_redis_slave_ports'):
                converted = convert_list_2_hyphen(dic['sr2_redis_slave_ports'])
                ret += [['slave ports', ', '.join(converted)]]
            ret += [
                ['ssd count', dic['ssd_count']],
                ['redis data path', dic['sr2_redis_data']],
                ['redis db path', dic['sr2_redis_db_path']],
                ['flash db path', dic['sr2_flash_db_path']],
            ]
            return ret
        except KeyError as key:
            raise PropsKeyError(str(key))

    def get_meta_from_dict(self, props_dict):
        meta = []
        meta.append(['hosts', '\n'.join(props_dict['hosts'])])
        converted = convert_list_2_hyphen(props_dict['master_ports'])
        meta.append(['master ports', ', '.join(converted)])
        if props_dict['slave_ports']:
            converted = convert_list_2_hyphen(props_dict['slave_ports'])
            meta.append(['slave ports', ', '.join(converted)])
        meta.append(['ssd count', props_dict['ssd_count']])
        meta.append(['prefix_of_rdp', props_dict['prefix_of_rdp']])
        meta.append(['prefix_of_rdbp', props_dict['prefix_of_rdbp']])
        meta.append(['prefix_of_fdbp', props_dict['prefix_of_fdbp']])
        return meta
