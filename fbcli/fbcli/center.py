import datetime
import time
from os.path import join as path_join
import os
from threading import Thread
import socket

from config import get_env_dict
import config
from log import logger
from net import get_ssh, ssh_execute, get_home_path, get_sftp
import net
from rediscli_util import RedisCliUtil
from redistrib2 import command as trib
from utils import get_ip_port_tuple_list, make_export_envs
from deploy_util import DeployUtil
from terminaltables import AsciiTable
import ask_util
import color
from hiredis import ProtocolError
from exceptions import SSHConnectionError, HostConnectionError, HostNameError
import color


def get_ps_list_command(port_list):
    port_filter = '|'.join(str(x) for x in port_list)
    command = """ps -ef | \
grep 'redis' | \
grep -v 'ps -ef' | \
egrep '({port_filter})'""".format(port_filter=port_filter)
    return command


class Center(object):
    def __init__(self):
        self.ip_list = []
        self.master_ip_list = []
        self.slave_ip_list = []
        self.master_port_list = []
        self.slave_port_list = []

    def get_nodes(self, cluster_id):
        nodes = ['fb-node-0.fb-node-svc', 'fb-node-1.fb-node-svc']
        return nodes

    def update_redis_conf(self):
        """Update redis config
        """
        logger.debug('update_redis_conf')
        self._update_ip_port()
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        master_template_path = path_of_fb['master_template']
        slave_template_path = path_of_fb['slave_template']
        for ip in self.ip_list:
            client = get_ssh(ip)
            redis_conf_dir = path_join(path_of_fb['conf_path'], 'redis')
            ssh_execute(client=client, command='mkdir -p %s' % redis_conf_dir)
            self._update_redis_conf(
                client,
                master_template_path,
                redis_conf_dir,
                ip,
                self.master_port_list
            )
            self._update_redis_conf(
                client,
                slave_template_path,
                redis_conf_dir,
                ip,
                self.slave_port_list
            )
            client.close()
        logger.info('update_redis_conf complete')

    def backup_server_logs(self):
        """Backup server logs"""
        logger.debug('backup_server_logs')
        self._update_ip_port()
        for ip in self.ip_list:
            backup_path = self.__get_redis_log_backup_path()
            client = get_ssh(ip)
            ssh_execute(
                client=client,
                command='mkdir -p %s' % backup_path)
            for port in (self.master_port_list + self.slave_port_list):
                redis_log_path = path_join(
                    config.get_tsr2_home(), 'logs', 'redis')
                command = '''mv {redis_log_path}/*{port}.log {backup_path} &> /dev/null'''.format(
                    redis_log_path=redis_log_path,
                    port=port,
                    backup_path=backup_path)
                ssh_execute(
                    client=client,
                    command=command,
                    allow_status=[0, 1])

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

    def start_redis_process(self):
        """Start redis process"""
        logger.debug('start_redis_process.')
        self._update_ip_port()
        # DeployUtil.rsync_and_update_conf()
        self.update_redis_conf()
        self.backup_server_logs()
        self.create_redis_data_directory()
        self.create_redis_log_directory()

        for ip in self.ip_list:
            for port in self.master_port_list:
                self._start_redis_process(ip, port, 'M')
            for port in self.slave_port_list:
                self._start_redis_process(ip, port, 'S')
        logger.info('start_redis_process complete.')

    def wait_until_kill_all_redis_process(self, force=False):
        """Wait until kill all redis process.

        After calculating live process count, send KILL signal

        :param force: If true, send SIGKILL. If not, send SIGINT
        """

        logger.info('wait_until_kill_all_redis_process start.')
        self._update_ip_port()
        max_try_count = 10
        for i in range(0, max_try_count):
            alive_count = self.get_alive_redis_process_count()
            logger.info(
                'Alive redis process: %s (try count: %s)' % (alive_count, i))
            if alive_count > 0:
                self.stop_redis(force)
                time.sleep(3)
            else:
                logger.info('wait_until_kill_all_redis_process complete.')
                return
        raise Exception('wait_until_kill_all_redis_process', 'max try error')

    def get_alive_redis_process_count(self):
        """Calculate alive process count

        :return: alive process count
        """

        self._update_ip_port()
        ps_list_command = get_ps_list_command(
            self.master_port_list + self.slave_port_list)
        command = '''{ps_list_command} | wc -l'''.format(
            ps_list_command=ps_list_command)
        logger.debug(command)
        command2 = """ps -ef | grep 'redis-rdb-to-slaves' | grep -v 'grep' | wc -l"""
        total_count = 0
        for ip in self.ip_list:
            client = get_ssh(ip)
            exit_status, stdout_msg, stderr_msg = ssh_execute(
                client=client,
                command=command)
            c = int(stdout_msg)
            total_count += c
            exit_status, stdout_msg, stderr_msg = ssh_execute(
                client=client,
                command=command2)
            c = int(stdout_msg)
            total_count += c
        return total_count

    def create_cluster(self):
        """Create cluster
        """
        logger.info('>>> Creating cluster')
        logger.debug('create cluster start')
        self._update_ip_port()
        result = self.confirm_node_port_info()
        if not result:
            logger.warn('Cancel create')
            return
        targets = get_ip_port_tuple_list(self.ip_list, self.master_port_list)
        try:
            trib.create(targets, max_slots=16384)
        except Exception as ex:
            logger.error(str(ex))
            return
        if len(self.slave_port_list) > 0:
            self._replicate()
        logger.info('create cluster complete.')

    def confirm_node_port_info(self):
        meta = [['HOST', 'PORT', 'TYPE']]
        for node in self.master_ip_list:
            for port in self.master_port_list:
                meta.append([node, port, 'MASTER'])
        for node in self.slave_ip_list:
            for port in self.slave_port_list:
                meta.append([node, port, 'SLAVE'])
        table = AsciiTable(meta)
        print(table.table)
        msg = [
            'Do you want to proceed with the create ',
            'according to the above information?',
        ]
        yes = ask_util.askBool(''.join(msg), ['y', 'n'])
        return yes

    def check_port_available(self):
        all_enable = True
        logger.info('Check status of ports for master...')
        meta = [['HOST', 'PORT', 'STATUS']]
        for node in self.master_ip_list:
            for port in self.master_port_list:
                result, status = net.is_port_empty(node, port)
                if not result:
                    all_enable = False
                    meta.append([node, port, color.red(status)])
                    continue
                meta.append([node, port, color.green(status)])
        table = AsciiTable(meta)
        print(table.table)

        if self.slave_ip_list:
            logger.info('Check status of ports for slave...')
            meta = [['HOST', 'PORT', 'STATUS']]
            for node in self.slave_ip_list:
                for port in self.slave_port_list:
                    result, status = net.is_port_empty(node, port)
                    if not result:
                        all_enable = False
                        meta.append([node, port, color.red(status)])
                        continue
                    meta.append([node, port, color.green(status)])
            table = AsciiTable(meta)
            print(table.table)
        return all_enable

    def stop_redis(self, force=False):
        """Stop redis

        :param force: If true, send SIGKILL. If not, send SIGINT
        """
        logger.debug('stop_all_redis start')
        # d = self.get_ip_port_dict_using_cluster_nodes_cmd()
        d = self.ip_list
        for ip in d:
            ports = self.master_port_list + self.slave_port_list
            ps_list_command = get_ps_list_command(ports)
            pid_list = "{ps_list_command} | awk '{{print $2}}'".format(
                ps_list_command=ps_list_command)
            signal = 'SIGKILL' if force else 'SIGINT'
            command = 'kill -s {signal} $({pid_list})' \
                .format(pid_list=pid_list, signal=signal)
            client = get_ssh(ip)
            ssh_execute(
                client=client,
                command=command,
                allow_status=[-1, 0, 1, 2, 123, 130])
        logger.debug('stop_redis, send ps kill signal to redis processes')

    def create_redis_data_directory(self):
        """Create redis data directory
        Create redis data directory using ssh and mkdir
        """
        logger.debug('create_redis_data_directory start.')
        self._update_ip_port()
        targets = get_ip_port_tuple_list(
            self.ip_list, self.master_port_list + self.slave_port_list)
        for ip, port in targets:
            envs = get_env_dict(ip, port)
            redis_data = envs['sr2_redis_data']
            flash_db_path = envs['sr2_flash_db_path']
            client = get_ssh(ip)
            ssh_execute(
                client=client,
                command='mkdir -p %s %s' % (redis_data, flash_db_path))
        logger.debug('create_redis_data_directory complete.')

    def create_redis_log_directory(self):
        """Create redis log directory using ssh and mkdir
        """
        logger.debug('create_redis_log_directory start')
        self._update_ip_port()
        for ip in self.ip_list:
            envs = get_env_dict(self.ip_list, 0)
            client = get_ssh(ip)
            ssh_execute(
                client=client,
                command='mkdir -p %s' % envs['sr2_redis_log'])
        logger.debug('create_redis_log_directory complete')

    def wait_until_all_redis_process_up(self):
        """Wait until all redis process up
        """
        logger.debug('wait_until_all_redis_process_up start.')
        self._update_ip_port()
        total_process_count = \
            len(self.ip_list) * \
            (len(self.master_port_list) + len(self.slave_port_list))
        max_try_count = 10
        for i in range(0, max_try_count):
            alive_count = self.get_alive_redis_process_count()
            if total_process_count > alive_count:
                logger.info('redis process(total: %d / cur: %d)' % (
                    total_process_count, alive_count))
                time.sleep(1)
            else:
                logger.info('All redis process up complete')
                return True
        return False

    def restart(self, force, reset):
        """Restart redis

        Stop redis + start redis

        :param force: If true, send SIGKILL. If not, send SIGINT
        :param reset: If true, clean(rm data).
        """
        logger.debug('restart start.')
        self._update_ip_port()
        if reset:
            self.clean()
        self.wait_until_kill_all_redis_process(force)
        self.start_redis_process()
        result = self.wait_until_all_redis_process_up()
        if not result:
            logger.error('Fail to start redis up to maximum attempt')
            return
        if reset:
            self.create_cluster()
        logger.debug('restart finish.')

    def clean(self):
        """Clean (data)

        Clean data
        """
        logger.debug('clean start')
        ip_list = config.get_node_ip_list()
        master_port_list = config.get_master_port_list()
        slave_port_list = config.get_slave_port_list()
        self._rm_data(ip_list, master_port_list, slave_port_list)
        self._rm_conf(ip_list, master_port_list, slave_port_list)
        self._rm_nodes_conf(ip_list, master_port_list, slave_port_list)
        logger.info('clean complete')

    def check_hosts_connection(self, hosts, show_result=False):
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
                host_status.append([host, color.red('UNKNOWN HOST')])
                logger.debug('{} gethostbyname... FAIL'.format(host))
            except HostConnectionError:
                host_status.append([host, color.red('CONNECTION FAIL')])
                logger.debug('{} connection... FAIL'.format(host))
            except SSHConnectionError:
                host_status.append([host, color.red('SSH FAIL')])
                logger.debug('{} ssh... FAIL'.format(host))
        if show_result:
            table = AsciiTable([['HOST', 'STATUS']] + host_status)
            print(table.table)
        if len(hosts) != success_count:
            return False
        return True

    def check_include_localhost(self, hosts):
        logger.debug('Check include localhost')
        for host in hosts:
            try:
                ip_addr = socket.gethostbyname(host)
                if ip_addr in [config.get_local_ip(), '127.0.0.1']:
                    return True
            except socket.gaierror:
                raise HostNameError(host)
        return False

    def __append_conf(self, ip, port_list, remove_dirs):
        for port in port_list:
            envs = get_env_dict(ip, port)
            conf_home = envs['sr2_redis_conf']
            remove_dirs.append(
                path_join(conf_home, 'redis-%d.conf' % port))

    def _rm_conf(self, ip_list, master_port_list, slave_port_list):
        for ip in ip_list:
            remove_dirs = []
            self.__append_conf(ip, master_port_list, remove_dirs)
            self.__append_conf(ip, slave_port_list, remove_dirs)
            folders = ' '.join(remove_dirs)
            command = 'rm -fr {folders}'.format(folders=folders)
            logger.debug(command)
            client = get_ssh(ip)
            ssh_execute(client=client, command=command)

    def __append_data_dirs(self, ip, port_list, remove_dirs):
        for port in port_list:
            envs = get_env_dict(ip, port)
            redis_data = envs['sr2_redis_data']
            remove_dirs.append(envs['sr2_flash_db_path'])
            remove_dirs.append(
                path_join(redis_data, 'appendonly-%d.aof' % port))
            remove_dirs.append(
                path_join(redis_data, 'dump-%d.rdb' % port))

    def _rm_data(self, ip_list, master_port_list, slave_port_list):
        for ip in ip_list:
            remove_dirs = []
            self.__append_data_dirs(ip, master_port_list, remove_dirs)
            self.__append_data_dirs(ip, slave_port_list, remove_dirs)
            folders = ' '.join(remove_dirs)
            command = 'rm -fr {folders}'.format(folders=folders)
            logger.debug(command)
            client = get_ssh(ip)
            ssh_execute(client=client, command=command)

    def __append_nodes_conf(self, ip, port_list, cmds):
        for port in port_list:
            envs = get_env_dict(ip, port)
            redis_data = envs['sr2_redis_data']
            conf_file = 'nodes-%d.conf' % port
            cmd = "find %s -name '%s' -exec rm -f {} \\;;" % (
                redis_data, conf_file)
            cmds.append(cmd)

    def _rm_nodes_conf(self, ip_list, master_port_list, slave_port_list):
        for ip in ip_list:
            cmds = []
            self.__append_nodes_conf(ip, master_port_list, cmds)
            self.__append_nodes_conf(ip, slave_port_list, cmds)
            command = ' '.join(cmds)
            logger.debug(command)
            client = get_ssh(ip)
            ssh_execute(client=client, command=command, allow_status=[0, 1])

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

    def _update_ip_port(self):
        self.ip_list = config.get_node_ip_list()
        self.master_ip_list = self.ip_list
        self.slave_ip_list = config.get_slave_ip_list()
        self.master_port_list = config.get_master_port_list()
        self.slave_port_list = config.get_slave_port_list()

    def _update_redis_conf(self, client, template_path, redis_conf_dir, ip,
        port_list):
        for port in port_list:
            target_conf = path_join(
                redis_conf_dir,
                'redis-{port}.conf'.format(port=port))
            envs = get_env_dict(ip, port)
            export_envs = '''
export SR2_REDIS_DATA={sr2_redis_data}
export SR2_REDIS_HOST={sr2_redis_host}
export SR2_REDIS_PORT={sr2_redis_port}
export SR2_FLASH_DB_PATH={sr2_flash_db_path}
                '''.format(**envs)

            command = '''{export_envs}
                cat {template_path} | envsubst > {target_conf}'''.format(
                export_envs=export_envs,
                template_path=template_path,
                target_conf=target_conf)
            ssh_execute(
                client=client,
                command=command)

    @staticmethod
    def __get_redis_log_path_file(port):
        dt = datetime.datetime.now()
        date = dt.strftime("%Y%m%d-%H%M%S")
        log_file = path_join(
            config.get_tsr2_home(), 'logs', 'redis',
            'servers-{date}-{port}.log'.format(date=date, port=port))
        return log_file

    @staticmethod
    def __get_redis_log_backup_path():
        log_file = path_join(config.get_tsr2_home(), 'logs', 'redis', 'backup')
        return log_file

    def _start_redis_process(self, ip, port, m_or_s):
        logger.info('[%s] Start redis (%s:%d)' % (m_or_s, ip, port))
        client = get_ssh(ip)
        redis_server = path_join(config.get_tsr2_home(), 'bin', 'redis-server')
        conf = path_join(config.get_tsr2_home(), 'conf', 'redis',
                         'redis-{port}.conf'.format(port=port))
        log_file = self.__get_redis_log_path_file(port)
        env = make_export_envs(ip, port)
        command = '''{env} ; {redis_server} {conf} >> {log_file} &'''.format(
            env=env,
            redis_server=redis_server,
            conf=conf,
            log_file=log_file)
        exit_status, stdout_msg, stderr_msg = ssh_execute(
            client=client,
            command=command)

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
        for ip in self.ip_list:
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
