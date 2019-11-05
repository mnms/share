import datetime
import time
from os.path import join as path_join
import os
from threading import Thread
import socket
from time import gmtime, strftime
import subprocess
import shutil

from config import get_env_dict
import config
from log import logger
from net import get_ssh, ssh_execute, get_home_path, get_sftp
import net
from rediscli_util import RedisCliUtil
from redistrib2 import command as trib
from utils import get_ip_port_tuple_list, make_export_envs
import utils
from deploy_util import DeployUtil, DEPLOYED
from terminaltables import AsciiTable
import ask_util
import color
from hiredis import ProtocolError
from exceptions import (
    SSHConnectionError,
    HostConnectionError,
    HostNameError,
    FileNotExistError,
    ClusterRedisError,
    ClusterNotExistError,
)
import color


def get_ps_list_command(port_list):
    port_filter = '|'.join(str(x) for x in port_list)
    command = [
        "ps -ef",
        "grep 'redis-server'",
        "grep -v 'ps -ef'",
        "egrep '({})'".format(port_filter)
    ]
    command = ' | '.join(command)
    return command


class Center(object):
    def __init__(self):
        self.master_host_list = []
        self.slave_host_list = []
        self.master_port_list = []
        self.slave_port_list = []
        self.all_host_list = []

    def sync_conf(self, show_result=False):
        logger.info('sync conf')
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        conf_path = path_of_fb['conf_path']
        my_address = config.get_local_ip_list()
        meta = [['HOST', 'STATUS']]
        no_cluster_flag = False
        for host in self.all_host_list:
            client = get_ssh(host)
            cluster_path = path_of_fb['cluster_path']
            if not net.is_dir(client, cluster_path):
                no_cluster_flag = True
                meta.append([host, color.red('NO CLUSTER')])
                continue
            client.close()
            meta.append([host, color.green('OK')])
        if no_cluster_flag:
            utils.print_table(meta)
            logger.error('Cancel sync conf')
            return False
        meta = [['HOST', 'STATUS']]
        error_flag = False
        for host in self.all_host_list:
            if net.get_ip(host) in my_address:
                meta.append([host, color.green('OK')])
                continue
            client = get_ssh(host)
            try:
                net.copy_dir_to_remote(client, conf_path, conf_path)
                meta.append([host, color.green('OK')])
            except BaseException as ex:
                logger.debug(ex)
                meta.append([host, color.red('FAIL')])
                error_flag = True
            finally:
                client.close()
        if error_flag or show_result:
            utils.print_table(meta)
        if error_flag:
            logger.error('Cancel sync conf')
            return False
        return True

    def configure_redis(self):
        logger.debug('configure redis')
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_conf_temp = path_of_fb['sr2_redis_conf_temp']
        if os.path.exists(sr2_redis_conf_temp):
            shutil.rmtree(sr2_redis_conf_temp)
        os.mkdir(sr2_redis_conf_temp)
        sr2_redis_conf = path_of_fb['sr2_redis_conf']
        if not os.path.exists(sr2_redis_conf):
            os.mkdir(sr2_redis_conf)
        for port in self.master_port_list:
            self.create_conf_from_template('redis-master.conf.template', port)
        if self.master_port_list:
            logger.info('Generate redis configuration files for master hosts')
        for port in self.slave_port_list:
            self.create_conf_from_template('redis-slave.conf.template', port)
        if self.slave_port_list:
            logger.info('Generate redis configuration files for slave hosts')
        command = 'cp -r {}/* {}'.format(sr2_redis_conf_temp, sr2_redis_conf)
        subprocess.check_output(command, shell=True)
        logger.debug('subprocess: {}'.format(command))

    def create_conf_from_template(self, template_name, port):
        file_name = 'redis-{}.conf'.format(port)
        logger.debug("create conf '{}' from '{}'".format(
            file_name,
            template_name
        ))
        pos = config.get_ssd_disk_position(port)
        export_envs = ' '.join([
            'export SR2_REDIS_DATA={}'.format(pos['sr2_redis_data']),
            'export SR2_REDIS_PORT={}'.format(port),
            'export SR2_FLASH_DB_PATH={}'.format(pos['sr2_flash_db_path']),
        ])
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        conf_path = path_of_fb['conf_path']
        sr2_redis_conf_temp = path_of_fb['sr2_redis_conf_temp']
        template_path = path_join(conf_path, template_name)
        target = path_join(sr2_redis_conf_temp, file_name)
        command = '{}; cat {} | envsubst > {}'.format(
            export_envs,
            template_path,
            target,
        )
        subprocess.check_output(command, shell=True)
        logger.debug('subprocess: {}'.format(command))

    def backup_server_logs(self):
        """
        Backup server logs
        Move redis log files to $SR2_REDIS_LOG/backup/<time-stamp>
        """
        logger.debug('backup_server_logs')
        logger.info('Backup redis master log in each MASTER hosts...')
        current_time = strftime("%Y%m%d-%H%M%S", gmtime())
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_log = path_of_fb['sr2_redis_log']
        backup_path = path_join(sr2_redis_log, 'backup', current_time)
        for host in self.master_host_list:
            logger.info(' - {}'.format(host))
            client = get_ssh(host)
            command = 'mkdir -p {}'.format(backup_path)
            ssh_execute(client, command)
            for port in self.master_port_list:
                command = 'mv {0}/*{1}*.log {2} &> /dev/null'.format(
                    sr2_redis_log,
                    port,
                    backup_path
                )
                ssh_execute(client, command, allow_status=[0, 1])
            client.close()
        if self.slave_host_list:
            logger.info('Backup redis slave log in each SLAVE hosts...')
        for host in self.slave_host_list:
            logger.info(' - {}'.format(host))
            client = get_ssh(host)
            command = 'mkdir -p {}'.format(backup_path)
            ssh_execute(client, command)
            for port in self.slave_port_list:
                command = 'mv {0}/*{1}*.log {2} &> /dev/null'.format(
                    sr2_redis_log,
                    port,
                    backup_path
                )
                ssh_execute(client, command, allow_status=[0, 1])
            client.close()

    def conf_backup(self, host, cluster_id, tag):
        logger.info('Backup conf of cluster {}...'.format(cluster_id))
        # prepare
        path_of_fb = config.get_path_of_fb(cluster_id)
        conf_path = path_of_fb['conf_path']
        path_of_cli = config.get_path_of_cli(cluster_id)
        conf_backup_path = path_of_cli['conf_backup_path']
        conf_backup_tag_path = path_join(conf_backup_path, tag)

        if not os.path.isdir(conf_backup_path):
            os.mkdir(conf_backup_path)

        # back up conf
        os.mkdir(conf_backup_tag_path)
        client = get_ssh(host)
        net.copy_dir_from_remote(client, conf_path, conf_backup_tag_path)
        client.close()

        logger.info('OK, {}'.format(tag))

    def cluster_backup(self, host, cluster_id, tag):
        logger.info('Backup cluster {} at {}...'.format(cluster_id, host))
        # prepare
        path_of_fb = config.get_path_of_fb(cluster_id)
        cluster_path = path_of_fb['cluster_path']
        cluster_backup_path = path_of_fb['cluster_backup_path']
        cluster_backup_tag_path = path_join(cluster_backup_path, tag)

        # back up cluster
        client = get_ssh(host)
        if not net.is_dir(client, cluster_backup_path):
            sftp = get_sftp(client)
            sftp.mkdir(cluster_backup_path)
            sftp.close()
        command = 'mv {} {}'.format(cluster_path, cluster_backup_tag_path)
        ssh_execute(client=client, command=command)
        client.close()
        logger.info('OK, {}'.format(tag))

    def conf_restore(self, host, cluster_id, tag):
        logger.debug('Restore conf to cluster {}...'.format(cluster_id))
        # prepare
        path_of_fb = config.get_path_of_fb(cluster_id)
        path_of_cli = config.get_path_of_cli(cluster_id)
        conf_path = path_of_fb['conf_path']
        conf_backup_path = path_of_cli['conf_backup_path']
        conf_backup_tag_path = path_join(conf_backup_path, tag)

        # restore conf
        client = get_ssh(host)
        net.copy_dir_to_remote(client, conf_backup_tag_path, conf_path)
        client.close()
        logger.debug('OK')

    def start_redis_process(self, profile=False):
        """ Start redis process
        """
        logger.debug('start_redis_process.')
        current_time = strftime("%Y%m%d-%H%M", gmtime())
        m_port = self.master_port_list
        s_port = self.slave_port_list
        for host in self.master_host_list:
            logger.info('Starting master nodes : {} : {} ...'.format(
                host,
                '|'.join(map(str, m_port))
            ))
            self.run_redis_process(host, m_port, profile, current_time)
        for host in self.slave_host_list:
            logger.info('Starting slave nodes : {} : {} ...'.format(
                host,
                '|'.join(map(str, s_port))
            ))
            self.run_redis_process(host, s_port, profile, current_time)

    def get_alive_redis_count(self, hosts, ports):
        logger.debug('get_alive_redis_count')
        logger.debug('hosts={}, ports={}'.format(hosts, ports))
        ps_list_command = get_ps_list_command(ports)
        command = '{} | wc -l'.format(ps_list_command)
        total = 0
        for host in hosts:
            client = get_ssh(host)
            _, stdout_msg, _ = ssh_execute(client=client, command=command)
            total += int(stdout_msg.strip())
        logger.debug('redis-server total={}'.format(total))
        cmd = "ps -ef | grep 'redis-rdb-to-slaves' | grep -v 'grep' | wc -l"
        redis_rdb_count = 0
        for host in hosts:
            client = get_ssh(host)
            _, stdout_msg, _ = ssh_execute(client=client, command=cmd)
            redis_rdb_count += int(stdout_msg.strip())
        logger.debug(command)
        logger.debug('redis-rbd-to-slaves total={}'.format(total))
        total += redis_rdb_count
        return total

    def get_alive_master_redis_count(self):
        logger.debug('get_alive_master_redis_count')
        hosts = self.master_host_list
        ports = self.master_port_list
        alive_count = self.get_alive_redis_count(hosts, ports)
        logger.debug('alive master count={}'.format(alive_count))
        return alive_count

    def get_alive_slave_redis_count(self):
        logger.debug('get_alive_slave_redis_count')
        hosts = self.slave_host_list
        ports = self.slave_port_list
        alive_count = self.get_alive_redis_count(hosts, ports)
        logger.debug('alive slave count={}'.format(alive_count))
        return alive_count

    def get_alive_all_redis_count(self):
        logger.debug('get_alive_all_redis_count')
        total_m = self.get_alive_master_redis_count()
        total_s = self.get_alive_slave_redis_count()
        return total_m + total_s

    def create_cluster(self, yes=False):
        """Create cluster
        """
        logger.info('>>> Creating cluster')
        logger.debug('create cluster start')
        result = self.confirm_node_port_info(skip=yes)
        if not result:
            logger.warn('Cancel create')
            return
        m_ip_list = list(map(net.get_ip, self.master_host_list))
        targets = get_ip_port_tuple_list(m_ip_list, self.master_port_list)
        try:
            trib.create(targets, max_slots=16384)
        except Exception as ex:
            logger.error(str(ex))
            return
        if len(self.slave_port_list) > 0:
            self._replicate()
        logger.info('create cluster complete.')

    def confirm_node_port_info(self, skip=False):
        replicas = config.get_replicas(self.cluster_id)
        meta = [['HOST', 'PORT', 'TYPE']]
        for node in self.master_host_list:
            for port in self.master_port_list:
                meta.append([node, port, 'MASTER'])
        for node in self.slave_host_list:
            for port in self.slave_port_list:
                meta.append([node, port, 'SLAVE'])
        table = AsciiTable(meta)
        print(table.table)
        print('replicas: {}\n'.format(replicas))
        if skip:
            return True
        msg = [
            'Do you want to proceed with the create ',
            'according to the above information?',
        ]
        yes = ask_util.askBool(''.join(msg), ['y', 'n'])
        return yes

    def stop_redis_process(self, host, ports, force=False):
        """Stop redis process
        """
        logger.debug('stop_redis_process')
        signal = 'SIGKILL' if force else 'SIGINT'
        ps_list_command = get_ps_list_command(ports)
        pid_list = "{} | awk '{{print $2}}'".format(ps_list_command)
        command = 'kill -s {} $({})'.format(signal, pid_list)
        client = get_ssh(host)
        ssh_execute(client, command, allow_status=[-1, 0, 1, 2, 123, 130])
        client.close()

    def stop_redis(self, force=False):
        """Stop redis

        :param force: If true, send SIGKILL. If not, send SIGINT
        """
        logger.debug('stop_redis')
        logger.info('Stopping master cluster of redis...')
        if self.slave_host_list:
            logger.info('Stopping slave cluster of redis...')
        total_count = len(self.master_host_list) * len(self.master_port_list)
        total_count += len(self.slave_host_list) * len(self.slave_port_list)
        max_try_count = 10
        while max_try_count > 0:
            alive_count = self.get_alive_all_redis_count()
            logger.info('cur: {} / total: {}'.format(alive_count, total_count))
            if alive_count <= 0:
                logger.info('Complete all redis process down')
                return True
            max_try_count -= 1
            if max_try_count % 3 == 0:
                for host in self.master_host_list:
                    self.stop_redis_process(host, self.master_port_list, force)
                for host in self.slave_host_list:
                    self.stop_redis_process(host, self.slave_port_list, force)
            time.sleep(1)
        raise ClusterRedisError('Fail to stop redis: max try exceed')

    def create_redis_data_directory(self):
        """ create directory SR2_REDIS_DATA, SR2_FLASH_DB_PATH
        """
        logger.debug('create_redis_data_directory')
        logger.debug('create redis data directory in each MASTER hosts')
        for host in self.master_host_list:
            client = get_ssh(host)
            for port in self.master_port_list:
                disk_pos = config.get_ssd_disk_position(port)
                redis_data = disk_pos['sr2_redis_data']
                flash_db_path = disk_pos['sr2_flash_db_path']
                command = 'mkdir -p %s %s' % (redis_data, flash_db_path)
                ssh_execute(client, command)
            client.close()
        if self.slave_host_list:
            logger.debug('create redis data directory in each SLAVE hosts')
        for host in self.slave_host_list:
            client = get_ssh(host)
            for port in self.slave_port_list:
                disk_pos = config.get_ssd_disk_position(port)
                redis_data = disk_pos['sr2_redis_data']
                flash_db_path = disk_pos['sr2_flash_db_path']
                command = 'mkdir -p %s %s' % (redis_data, flash_db_path)
                ssh_execute(client, command)
            client.close()

    def wait_until_all_redis_process_up(self):
        """Wait until all redis process up
        """
        logger.debug('wait_until_all_redis_process_up')
        logger.info('Wait until all redis process up...')
        total_count = len(self.master_host_list) * len(self.master_port_list)
        total_count += len(self.slave_host_list) * len(self.slave_port_list)
        max_try_count = 10
        while max_try_count > 0:
            alive_count = self.get_alive_all_redis_count()
            logger.info('cur: {} / total: {}'.format(alive_count, total_count))
            if alive_count >= total_count:
                logger.info('Complete all redis process up')
                if alive_count != total_count:
                    logger.warning('ClusterRedisWarning: too many process up')
                return True
            time.sleep(1)
            max_try_count -= 1
            msg = [
                'Fail to start redis: max try exceed',
                "Recommendation Command: 'monitor'"
            ]
        # raise ClusterRedisError('Fail to start redis: max try exceed')
        raise ClusterRedisError('\n'.join(msg))

    def check_hosts_connection(self, hosts=None, show_result=False):
        logger.debug('check hosts connection')
        logger.info('Check status of hosts...')
        if hosts is None:
            self.update_ip_port()
            hosts = self.all_host_list
        host_status = []
        success_count = 0
        for host in hosts:
            try:
                client = get_ssh(host)
                client.close()
                logger.debug('{} ssh... OK'.format(host))
                success_count += 1
                host_status.append([host, color.green('OK')])
            except HostNameError:
                show_result = True
                host_status.append([host, color.red('UNKNOWN HOST')])
                logger.debug('{} gethostbyname... FAIL'.format(host))
            except HostConnectionError:
                show_result = True
                host_status.append([host, color.red('CONNECTION FAIL')])
                logger.debug('{} connection... FAIL'.format(host))
            except SSHConnectionError:
                show_result = True
                host_status.append([host, color.red('SSH FAIL')])
                logger.debug('{} ssh... FAIL'.format(host))
        if show_result:
            table = AsciiTable([['HOST', 'STATUS']] + host_status)
            print(table.table)
        if len(hosts) != success_count:
            return False
        logger.info('OK')
        return True

    def check_include_localhost(self, hosts):
        logger.debug('check_include_localhost')
        for host in hosts:
            try:
                ip_addr = socket.gethostbyname(host)
                if ip_addr in [config.get_local_ip(), '127.0.0.1']:
                    return True
            except socket.gaierror:
                raise HostNameError(host)
        return False

    def _remove_node_conf(self, client, port):
        pos = config.get_ssd_disk_position(port)
        sr2_redis_data = pos['sr2_redis_data']
        file_name = 'nodes-{}.conf'.format(port)
        command = "find {} -name '{}' -exec rm -f {{}} \\;".format(
            sr2_redis_data,
            file_name,
        )
        ssh_execute(client, command, [0, 1])

    def remove_nodes_conf(self):
        logger.info('Removing master node configuration')
        for host in self.master_host_list:
            logger.info(' - {}'.format(host))
            client = get_ssh(host)
            for port in self.master_port_list:
                self._remove_node_conf(client, port)
            client.close()

        if self.slave_host_list:
            logger.info('Removing slave node configuration')
        for host in self.slave_host_list:
            logger.info(' - {}'.format(host))
            client = get_ssh(host)
            for port in self.slave_port_list:
                self._remove_node_conf(client, port)
            client.close()

    def remove_all_of_redis_log_force(self):
        logger.info('remove all of redis log')
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_log = path_of_fb['sr2_redis_log']
        command = 'rm -f {}/*.log'.format(sr2_redis_log)
        for host in self.master_host_list:
            client = get_ssh(host)
            ssh_execute(client, command)
            client.close()
            logger.info(' - {}'.format(host))

    def remove_generated_config(self):
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_conf = path_of_fb['sr2_redis_conf']
        logger.info('Removing redis generated master configuration files')
        for host in self.master_host_list:
            logger.info(' - {}'.format(host))
            client = get_ssh(host)
            for port in self.master_port_list:
                conf_file = 'redis-{}.conf'.format(port)
                conf_file_path = path_join(sr2_redis_conf, conf_file)
                command = 'rm -rf {}'.format(conf_file_path)
                ssh_execute(client, command)
            client.close()
        if self.slave_host_list:
            logger.info('Removing redis generated slave configuration files')
        for host in self.slave_host_list:
            logger.info(' - {}'.format(host))
            client = get_ssh(host)
            for port in self.slave_port_list:
                conf_file = 'redis-{}.conf'.format(port)
                conf_file_path = path_join(sr2_redis_conf, conf_file)
                command = 'rm -rf {}'.format(conf_file_path)
                ssh_execute(client, command)
            client.close()

    def _remove_data(self, client, port):
        pos = config.get_ssd_disk_position(port)
        sr2_redis_data = pos['sr2_redis_data']
        sr2_flash_db_path = pos['sr2_flash_db_path']
        target = [
            sr2_flash_db_path,
            '{}/appendonly-{}*.aof'.format(sr2_redis_data, port),
            '{}/dump-{}.rdb'.format(sr2_redis_data, port),
        ]
        command = 'rm -rf {}'.format(' '.join(target))
        ssh_execute(client, command)

    def remove_data(self):
        msg = [
            'Removing flash db directory, ',
            'appendonly and dump.rdb files in master',
        ]
        logger.info(''.join(msg))
        for host in self.master_host_list:
            logger.info(' - {}'.format(host))
            client = get_ssh(host)
            for port in self.master_port_list:
                self._remove_data(client, port)
            client.close()
        if self.slave_host_list:
            msg = [
                'Removing flash db directory, ',
                'appendonly and dump.rdb files in slave',
            ]
            logger.info(''.join(msg))
        for host in self.slave_host_list:
            logger.info(' - {}'.format(host))
            client = get_ssh(host)
            for port in self.slave_port_list:
                self._remove_data(client, port)
            client.close()

    def update_ip_port(self):
        logger.debug('update ip port')
        self.cluster_id = config.get_cur_cluster_id()
        self.master_host_list = config.get_master_host_list(self.cluster_id)
        self.slave_host_list = config.get_slave_host_list(self.cluster_id)
        self.master_port_list = config.get_master_port_list(self.cluster_id)
        self.slave_port_list = config.get_slave_port_list(self.cluster_id)
        m_host_list = self.master_host_list
        s_host_list = self.slave_host_list
        self.all_host_list = list(set(m_host_list + s_host_list))

    def run_redis_process(self, host, ports, profile, current_time):
        logger.debug('run_redis_process')
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_bin = path_of_fb['sr2_redis_bin']
        sr2_redis_conf = path_of_fb['sr2_redis_conf']
        sr2_redis_log = path_of_fb['sr2_redis_log']
        sr2_redis_lib = path_of_fb['sr2_redis_lib']

        # create log directory
        client = get_ssh(host)
        command = 'mkdir -p {}'.format(sr2_redis_log)
        ssh_execute(client, command)

        # redis-server run command
        redis_run_cmd = ['GLOBIGNORE=*;']
        if profile:
            redis_run_cmd.append(
                'MALLOC_CONF=prof_leak:true,lg_prof_sample:0,prof_final:true'
            )
            redis_run_cmd.append(
                'LD_PRELOAD={}/native/libjemalloc.so '.format(sr2_redis_lib)
            )
        redis_run_cmd.append('{}/redis-server'.format(sr2_redis_bin))

        for port in ports:
            log_file_name = 'servers-{}-{}.log'.format(current_time, port)
            conf_path = '{}/redis-{}.conf'.format(sr2_redis_conf, port)
            if not net.is_exist(client, conf_path):
                raise FileNotExistError(conf_path, host=host)
            cmd = '{env}; {redis_server} {conf} >> {log_path} 2>&1 &'.format(
                env=make_export_envs(host, port),
                redis_server=' '.join(redis_run_cmd),
                conf=conf_path,
                log_path=path_join(sr2_redis_log, log_file_name),
            )
            ssh_execute(client, cmd)

    def ensure_cluster_exist(self):
        logger.debug('ensure_cluster_exist')
        logger.info('Check cluster exist...')
        for host in self.all_host_list:
            logger.info(' - {}'.format(host))
            deploy_state = DeployUtil().get_state(self.cluster_id, host)
            if deploy_state != DEPLOYED:
                raise ClusterNotExistError(self.cluster_id, host=host)
        logger.info('OK')

    @staticmethod
    def _get_ip_port_dict_using_cluster_nodes_cmd():
        def mute_formatter(outs):
            pass

        outs = RedisCliUtil.command(
            sub_cmd='cluster nodes',
            formatter=mute_formatter)
        lines = outs.splitlines()
        d = {}
        for line in lines:
            rows = line.split(' ')
            addr = rows[1]
            if 'connected' in rows:
                (host, port) = addr.split(':')
                if host not in d:
                    d[host] = [port]
                else:
                    d[host].append(port)
        return d

    def _get_master_slave_pair_list(self):
        pl = []
        master_count = len(self.master_port_list)
        slave_count = len(self.slave_port_list)
        logger.info('replicas: %.2f' % (float(slave_count) / master_count))
        ss = list(self.slave_port_list)
        while len(ss) > 0:
            for master_port in self.master_port_list:
                if len(ss) == 0:
                    break
                slave_port = ss.pop(0)
                pl.append((master_port, slave_port))
        ret = []
        m_ip_list = list(map(net.get_ip, self.master_host_list))
        for ip in m_ip_list:
            for master_port, slave_port in pl:
                ret.append((ip, master_port, ip, slave_port))
        return ret

    @staticmethod
    def _replicate_thread(m_ip, m_port, s_ip, s_port):
        logger.info('replicate [M] %s %s - [S] %s %s' % (
            m_ip, m_port, s_ip, s_port))
        trib.replicate(m_ip, m_port, s_ip, s_port)

    def _replicate(self):
        threads = []
        pair_list = self._get_master_slave_pair_list()
        for m_ip, m_port, s_ip, s_port in pair_list:
            t = Thread(
                target=Center._replicate_thread,
                args=(m_ip, m_port, s_ip, s_port,))
            threads.append(t)
        for x in threads:
            x.start()
        count = 0
        for x in threads:
            x.join()
            count += 1
            logger.info('%d / %d meet complete.' % (count, len(threads)))
