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
from exceptions import (
    ClusterIdError,
    ClusterNotExistError,
    FlashbaseError,
    FileNotExistError,
)


def _change_cluster(cluster_id):
    if not isinstance(cluster_id, int):
        raise ClusterIdError(cluster_id)
    root_of_cli_config = get_root_of_cli_config()
    head_path = path_join(root_of_cli_config, 'HEAD')
    cluster_list = cluster_util.get_cluster_list()
    if cluster_id not in cluster_list + [-1]:
        raise ClusterNotExistError(cluster_id)
    with open(head_path, 'w') as fd:
        fd.write('%s' % cluster_id)


class Cluster(object):
    """This is cluster command
    """

    def __init__(self, print_mode='screen'):
        self._print_mode = print_mode

    def stop(self, force=False):
        """Stop cluster
        """
        if not isinstance(force, bool):
            logger.error("option '--force' can use only 'True' or 'False'")
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        center.stop_redis(force)

    def start(self, profile=False):
        """Start cluster
        """
        logger.debug("command 'cluster start'")
        if not isinstance(profile, bool):
            logger.error("option '--profile' can use only 'True' or 'False'")
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        center.ensure_cluster_exist()
        master_alive_count = center.get_alive_master_redis_count()
        if master_alive_count > 0:
            msg = [
                'Fail to start master nodes... ',
                'Must be checked running master processes!\n',
                'We estimate that ',
                "redis 'MASTER' processes is {}".format(master_alive_count)
            ]
            raise FlashbaseError(11, ''.join(msg))
        slave_alive_count = center.get_alive_slave_redis_count()
        if slave_alive_count > 0:
            msg = [
                'Fail to start master nodes... ',
                'Must be checked running master processes!\n',
                'We estimate that ',
                "redis 'SLAVE' processes is {}".format(slave_alive_count)
            ]
            raise FlashbaseError(12, ''.join(msg))
        center.backup_server_logs()
        center.create_redis_data_directory()
        try:
            center.start_redis_process(profile)
        except FileNotExistError as ex:
            logger.error(ex)
            logger.error("Recommendation Command: 'cluster configure'")
            return
        center.wait_until_all_redis_process_up()

    def create(self, yes=False):
        """Create cluster

        Before create cluster, all redis should be started.
        """
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        center.create_cluster(yes)

    def clean(self, logs=False, nodes=False, all=False, reset=False):
        """Clean cluster
        """
        if not isinstance(logs, bool):
            logger.error("option '--logs' can use only 'True' or 'False'")
            return
        if not isinstance(nodes, bool):
            logger.error("option '--nodes' can use only 'True' or 'False'")
            return
        if not isinstance(all, bool):
            logger.error("option '--all' can use only 'True' or 'False'")
            return
        if not isinstance(reset, bool):
            logger.error("option '--reset' can use only 'True' or 'False'")
            return
        center = Center()
        center.update_ip_port()
        if logs:
            center.remove_all_of_redis_log_force()
            return
        center.remove_generated_config()
        center.remove_data()
        if nodes or all or reset:
            center.remove_nodes_conf()

    def use(self, cluster_id):
        """Change selected cluster

        :param cluster_id: target cluster #
        """
        _change_cluster(cluster_id)
        cluster_id = '-' if cluster_id == -1 else cluster_id
        logger.info("Cluster '{}' selected.".format(cluster_id))

    def ls(self):
        """Check cluster list"""
        logger.info(cluster_util.get_cluster_list())

    def restart(
        self,
        force_stop=False,
        reset=False,
        cluster=False,
        profile=False,
        yes=False,
    ):
        """Restart redist cluster
        :param force: If true, send SIGKILL. If not, send SIGINT
        :param reset: If true, clean(rm data).
        """
        if not isinstance(force_stop, bool):
            msg = [
                "option '--force-stop' can use only ",
                "'True' or 'False'",
            ]
            logger.error(''.join(msg))
            return
        if not isinstance(reset, bool):
            logger.error("option '--reset' can use only 'True' or 'False'")
            return
        if not isinstance(cluster, bool):
            logger.error("option '--cluster' can use only 'True' or 'False'")
            return
        if not reset and cluster:
            msg = "option '--cluster' can used only with option '--reset'"
            logger.error(msg)
            return
        if not cluster and yes:
            msg = "option '--yes' can used only with option '--cluster'"
            logger.error(msg)
            return
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        center.stop_redis(force=force_stop)
        if reset:
            center.remove_generated_config()
            center.remove_data()
            center.remove_nodes_conf()
            center.configure_redis()
        self.start()
        if cluster:
            self.create(yes=yes)

    def edit(self, target='main', master=False, slave=False):
        """Open vim to edit config file"""
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        allow_target = ['main', 'template', 'thrift']
        if target not in allow_target:
            logger.error('Allow target is {}'.format(allow_target))
            return
        if target == 'template':
            if not (master or slave):
                msg = [
                    'Select type of template.',
                    "you can use option '--master' or '--slave'"
                ]
                logger.error(' '.join(msg))
                return
            if master and slave:
                logger.error('Select only one type.')
                return
            if master:
                target_path = path_of_fb['master_template']
            if slave:
                target_path = path_of_fb['slave_template']
        if target != 'template':
            if master:
                logger.error("'--master' can use only edit template")
                return
            if slave:
                logger.error("'--slave' can use only edit template")
                return
        if target == 'main':
            target_path = path_of_fb['redis_properties']
        if target == 'thrift':
            target_path = path_of_fb['thrift_properties']
        target_tmp_path = target_path + '.tmp'
        if os.path.exists(target_tmp_path):
            q = 'There is a history of modification. Do you want to load?'
            yes = ask_util.askBool(q)
            if not yes:
                os.remove(target_tmp_path)
        if not os.path.exists(target_tmp_path):
            shutil.copy(target_path, target_tmp_path)
        editor.edit(target_tmp_path, syntax='sh')
        if target == 'main':
            config.ensure_host_not_changed(target_tmp_path)
        shutil.copy(target_tmp_path, target_path)
        os.remove(target_tmp_path)
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        success = center.sync_conf()
        if success:
            logger.info('Complete edit')

    def configure(self):
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        center.configure_redis()
        center.sync_conf(show_result=True)

    def rowcount(self):
        """Query and show cluster row count"""
        logger.debug('rowcount')
        # open-redis-cli-all info Tablespace | grep totalRows | awk -F ',
        # ' '{print $4}' | awk -F '=' '{sum += $2} END {print sum}'
        host_list = config.get_master_host_list()
        port_list = config.get_master_port_list()
        outs, meta = RedisCliUtil.command_raw_all(
            'info Tablespace', host_list, port_list)
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
