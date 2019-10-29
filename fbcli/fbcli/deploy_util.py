import fileinput
import socket
from os.path import join as path_join
import os

from exceptions import PropsKeyError
from config import get_node_ip_list
from log import logger
from net import get_ssh, ssh_execute, get_home_path, get_sftp
from rsync_over_sftp import RsyncOverSftp
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
        if type(nodes) is type(str()):
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

        if not net.is_exist(client, installer_path):
            raise FileNotExistError(installer_path)

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

    @staticmethod
    def rsync_and_update_conf():
        fb_config = config.get_config()
        cluster_id = config.get_cur_cluster_id()
        nodes = fb_config['nodes']
        repo_path = config.get_root_of_cli_config()
        DeployUtil.yaml_to_redis_props(repo_path, cluster_id, None)
        DeployUtil.rsync(repo_path, nodes, None)
        DeployUtil.overwrite_conf(None)

    @staticmethod
    def rsync(repo_path, nodes, report):
        """rsync local(in repo_path) to nodes

        :param repo_path: .flashbase folder path (in bash env) in local
        :param nodes: target node address(ip)
        :param report: for making log
        """
        my_address = config.get_local_ip_list()
        for node in nodes:
            # ignore myself
            if node in my_address:
                continue
            logger.debug('Start sync %s' % node)
            sftp = RsyncOverSftp(host=node, port=22)
            src = dst = repo_path
            exclude = [r'^logs/']
            logger.debug('rsync to %s:%s' % (node, dst))
            sftp.sync(src, dst, download=False, exclude=exclude, delete=False)
            logger.debug('Success sync %s' % node)
        if report:
            report.success()

    @staticmethod
    def install_v1(nodes, cluster_id, release, repo_path, tsr2_service_dir,
        report):
        installer = path_join(repo_path, 'releases', release)
        dest = path_join(tsr2_service_dir, 'cluster_%d' % cluster_id)
        command = '''chmod 755 {installer}; \
        PATH=${{PATH}}:/usr/sbin; \
        {installer} --full {dest}'''.format(installer=installer, dest=dest)
        for node in nodes:
            client = get_ssh(node)
            ssh_execute(client=client, command=command)
        report.success()

    @staticmethod
    def overwrite_conf(report):
        logger.debug('_overwrite_conf')
        fb_config = config.get_config()
        nodes = fb_config['nodes']
        cluster_home = config.get_repo_cluster_path()
        tsr2_home = config.get_tsr2_home()
        src = path_join(cluster_home, 'tsr2-conf')
        dest = path_join(tsr2_home, 'conf')
        command = '''cp -a {src}/* {dest}'''.format(src=src, dest=dest)
        for node in nodes:
            client = get_ssh(node)
            ssh_execute(client=client, command=command)
            logger.debug('overwrite_conf success [{node}]'.format(node=node))
        if report:
            report.success()

    @staticmethod
    def yaml_to_redis_props(repo_path, cluster_id, report=None):
        node_ip_list = get_node_ip_list()
        ip_list_str = ' '.join(node_ip_list)
        conf_path = path_join(repo_path, 'clusters', str(cluster_id),
                              'tsr2-conf')

        fb_config = config.get_config()
        slave_enabled = config.is_slave_enabled()
        slave_off = ''
        if not slave_enabled:
            slave_off = '#'

        d = {
            'ip_list_str': ip_list_str,
            'master_from': fb_config['master_ports']['from'],
            'master_to': fb_config['master_ports']['to'],
            'slave_from': fb_config['slave_ports']['from'],
            'slave_to': fb_config['slave_ports']['to'],
            'slave_off': slave_off,
            'ssd_count': fb_config['ssd']['count'],
            'flash_db_path': fb_config['prefix']['flash_db_path'],
            'redis_data': fb_config['prefix']['redis_data'],
            'redis_db_path': fb_config['prefix']['redis_db_path'],
        }

        t = '''
#!/bin/bash

## Master hosts and ports
export SR2_REDIS_MASTER_HOSTS=( {ip_list_str} )
export SR2_REDIS_MASTER_PORTS=( $(seq {master_from} {master_to}) )

## Slave hosts and ports (optional)
{slave_off}export SR2_REDIS_SLAVE_HOSTS=( {ip_list_str} )
{slave_off}export SR2_REDIS_SLAVE_PORTS=( $(seq {slave_from} {slave_to}) )

## only single data directory in redis db and flash db
## Must exist below variables; 'SR2_REDIS_DATA', 'SR2_REDIS_DB_PATH' and 'SR2_FLASH_DB_PATH'
#export SR2_REDIS_DATA="/nvdrive0/nvkvs/redis"
#export SR2_REDIS_DB_PATH="/nvdrive0/nvkvs/redis"
#export SR2_FLASH_DB_PATH="/nvdrive0/nvkvs/flash"

## multiple data directory in redis db and flash db
export SSD_COUNT={ssd_count}
#export HDD_COUNT=3
export SR2_REDIS_DATA="{redis_data}"
export SR2_REDIS_DB_PATH="{redis_db_path}"
export SR2_FLASH_DB_PATH="{flash_db_path}"

#######################################################
# Example : only SSD data directory
#export SSD_COUNT=3
#export SR2_REDIS_DATA="/ssd_"
#export SR2_REDIS_DB_PATH="/ssd_"
#export SR2_FLASH_DB_PATH="/ssd_"
#######################################################
        '''
        s = t.format(**d)
        logger.debug(s)
        redis_properties = path_join(conf_path, 'redis.properties')
        with open(redis_properties, 'w') as fd:
            fd.write(s)
        if report:
            report.success()
