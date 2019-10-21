import os
import shutil
from os.path import join as path_join

import yaml
from ask import ask, askInt

import config
from center import Center
from config import get_config, get_root_of_cli_config
from deploy_util import DeployUtil
from log import logger
from net import get_ssh, ssh_execute
from rediscli_util import RedisCliUtil
from redistrib2.custom_trib import rebalance_cluster_cmd
from utils import DuplicatedError, open_vim_editor
import cluster_util
import ask_util
import editor
from functools import reduce


def _change_cluster(cluster_id):
    root_of_cli_config = get_root_of_cli_config()
    head_path = path_join(root_of_cli_config, 'HEAD')
    cluster_list = cluster_util.get_cluster_list()
    if cluster_id not in cluster_list + [-1]:
        return False, 'Cluster not exist: {}'.format(cluster_id)
    with open(head_path, 'w') as fd:
        fd.write('%s' % cluster_id)
    return True, ''


class Cluster(object):
    """This is cluster command
    """

    def __init__(self, print_mode='screen'):
        self._print_mode = print_mode

    def stop(self, force=False, reset=False):
        """Stop cluster
        """
        center = Center()
        if reset:
            center.clean()
        center.wait_until_kill_all_redis_process(force)

    def start(self):
        """Start cluster
        """
        center = Center()
        center.start_redis_process()
        result = center.wait_until_all_redis_process_up()
        if not result:
            logger.error('Fail to start redis up to maximum attempt')
            return

    def create(self):
        """Create cluster

        Before create cluster, all redis should be started.
        """
        center = Center()
        center.create_cluster()

    def clean(self):
        """Start cluster
        """
        center = Center()
        center.clean()

    def clone(self, src, dest):
        """Clone cluster config from existing cluster config

        This command does not include deployment.

        :param src: src cluster #
        :param dest: dest cluster #
        """
        logger.warning('clone disable')
        return
        self._print('Cluster clone from %s to %s' % (src, dest))
        cluster_list = _ls()
        if str(dest) in cluster_list:
            raise DuplicatedError('cluster')
        if src < 0:
            config = get_config(template=True)
            src = 'template'
        else:
            config = get_config(src)
        release = self._installer()
        nodes = self._nodes(','.join(config['nodes']))
        start_port, end_port = self._ports(dest)
        ssd_count = str(self._ssd_count(config['ssd']['count']))
        src = str(src)
        dest = str(dest)
        root_of_cli_config = get_root_of_cli_config()
        cluster_path = path_join(root_of_cli_config, 'clusters')
        src_path = path_join(cluster_path, src)
        dest_path = path_join(cluster_path, dest)
        shutil.copytree(src_path, dest_path)
        offset = 50
        Cluster.save_yaml(
            cluster_id=dest,
            release=release,
            nodes=nodes,
            master_start_port=start_port,
            master_end_port=end_port,
            master_enabled=True,
            slave_start_port=start_port + offset,
            slave_end_port=end_port + offset,
            slave_enabled=False,
            ssd_count=ssd_count)
        self.use(dest)

    def use(self, cluster_id):
        """Change selected cluster

        :param cluster_id: target cluster #
        """
        success, message = _change_cluster(cluster_id)
        if success:
            cluster_id = '-' if cluster_id == -1 else cluster_id
            self._print('Cluster %s selected.' % cluster_id)
        else:
            logger.warn('Fail: %s' % message)

    def ls(self):
        """Check cluster list"""
        logger.info(cluster_util.get_cluster_list())

    def restart(self, force=False, reset=False):
        """Restart redist cluster
        :param force: If true, send SIGKILL. If not, send SIGINT
        :param reset: If true, clean(rm data).
        """
        Center().restart(force, reset)

    def edit(self):
        """Open vim to edit config file"""
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        # path_of_cli = config.get_path_of_cli(cluster_id)
        # if not os.path.exists(path_of_cli['cluster_path']):
        #     logger.debug(
        #         "FileNotExisted: '{}'".format(
        #             path_of_cli['cluster_path']))
        #     os.system('mkdir -p {}'.format(path_of_cli['cluster_path']))
        #     logger.debug("CreateDir: '{}'".format(path_of_cli['cluster_path']))
        # if not os.path.exists(path_of_cli['conf_path']):
        #     logger.debug(
        #         "FileNotExisted: '{}'".format(
        #             path_of_cli['conf_path']))
        #     shutil.copytree(path_of_fb['conf_path'], path_of_cli['conf_path'])
        #     logger.debug("CopyTree: '{}'".format(path_of_cli['cluster_path']))
        editor.edit(path_of_fb['redis_properties'], syntax='sh')
        cluster_util.rsync_fb_conf()

    def sync_conf(self):
        """Sync conf files like redis.properties"""
        logger.info('sync conf start.')
        DeployUtil.rsync_and_update_conf()
        logger.info('sync conf finish.')

    def rowcount(self):
        """Query and show cluster row count"""
        logger.debug('rowcount')
        # open-redis-cli-all info Tablespace | grep totalRows | awk -F ',
        # ' '{print $4}' | awk -F '=' '{sum += $2} END {print sum}'
        ip_list = config.get_node_ip_list()
        port_list = config.get_master_port_list()
        outs, meta = RedisCliUtil.command_raw_all(
            'info Tablespace', ip_list, port_list)
        lines = outs.splitlines()
        key = 'totalRows'
        filtered_lines = (filter(lambda x: key in x, lines))
        ld = RedisCliUtil.to_list_of_dict(filtered_lines)
        # row_count = reduce(lambda x, y: {key: int(x[key]) + int(y[key])}, ld)
        row_count = reduce(lambda x, y: x + int(y[key]), ld, 0)
        self._print(row_count)

    def rebalance(self, ip, port):
        """Rebalance

        :param ip: rebalance target ip
        :param port: rebalance target port
        """
        rebalance_cluster_cmd(ip, port)

    def _print(self, text):
        if self._print_mode == 'screen':
            logger.info(text)

    def _ssd_count(self, default):
        ssd_count = int(askInt(text='SSD count?', default=str(default)))
        return ssd_count

    def _ports(self, cluster_id):
        ports_per_one_host = int(askInt(
            text='How many ports do you need per one host?',
            default='3'))
        self._print('Ok. %s' % ports_per_one_host)
        offset = 100
        start_port = config.start_port + cluster_id * offset
        end_port = start_port + ports_per_one_host - 1
        start_port = askInt(text='Type start port?', default=str(start_port))
        self._print('Ok. %s' % start_port)
        end_port = askInt(text='Type end port?', default=str(end_port))
        self._print('Ok. %s' % end_port)
        return start_port, end_port

    def _nodes(self, default):
        host_list = ask(
            text='Please type host list(comma segmented)? default:',
            default=default)
        self._print('Ok. %s' % host_list)
        host_list = [x.strip() for x in host_list.split(',')]
        return host_list

    def _installer(self):
        path_of_cli = config.get_path_of_cli(None)
        release_path = path_of_cli['release_path']
        installer_list = os.listdir(release_path)
        installer_list = list(
            filter(
                lambda x: x != '.gitignore',
                installer_list))
        installer_list.sort(reverse=True)
        for i, v in enumerate(installer_list):
            installer_list[i] = '\t({}) {}'.format(i, v)
        '''
        Select installer

        [ INSTALLER LIST ]
            (1) tsr2-installer.bin.flashbase_v1.1.12.centos
            (2) tsr2-installer.bin.flashbase_v1.1.11.centos
            (3) tsr2-installer.bin.flashbase_v1.1.10.centos

        Please enter the number or the path of the installer you want to use
        '''

        msg = [
            'Select installer',
            '[ INSTALLER LIST ]',
            '\n'.join(installer_list),
            '\n',
            'Please enter the number or the path of the installer you want to use',
        ]
        '\n'.join(msg)
        t = '[ INSTALLER LIST ]\n{}\n'.format('\n'.join(installer_list))
        name = ask(
            text='Please type installer. if you want another, type absolute path of installer.\n\n{}'.format(
                t),
        )
        while True:
            if name in installer_list:
                break
            flag = os.path.exists(name)
            if flag:
                break
            name = ask(
                text='File not existed. Please confirm and type again'
            )
        self._print('Ok, {}'.format(name))
        return name

    @staticmethod
    def save_yaml(
            cluster_id,
            release,
            nodes,
            master_start_port,
            master_end_port,
            master_enabled,
            slave_start_port,
            slave_end_port,
            slave_enabled,
            ssd_count):
        root_of_cli_config = get_root_of_cli_config()
        cluster_path = path_join(root_of_cli_config, 'clusters')
        yaml_path = path_join(cluster_path, cluster_id, 'config.yaml')
        with open(yaml_path, 'r') as fd:
            config = yaml.load(fd)
            config['release'] = release
            config['nodes'] = nodes

            config['master_ports']['from'] = int(master_start_port)
            config['master_ports']['to'] = int(master_end_port)
            config['master_ports']['enabled'] = bool(master_enabled)

            config['slave_ports']['from'] = int(slave_start_port)
            config['slave_ports']['to'] = int(slave_end_port)
            config['slave_ports']['enabled'] = bool(slave_enabled)

            config['ssd']['count'] = int(ssd_count)
        with open(yaml_path, 'w') as fd:
            yaml.dump(config, fd, default_flow_style=False)
