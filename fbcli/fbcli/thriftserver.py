import datetime
import json
import subprocess as sp
import time
from os.path import join as path_join

from ask import askInt

import config
import utils
from log import logger
from net import get_ssh, ssh_execute, ssh_execute_async


def _get_sh_envs(file_name):
    source = 'source %s' % file_name
    dump = '/usr/bin/python -c "import os, json;print json.dumps(dict(os.environ))"'
    pipe = sp.Popen(
        ['/bin/bash', '-c',
         '%s ; export HIVE_PORT=${HIVE_PORT} export HIVE_HOST=${HIVE_HOST} && %s' % (
         source, dump)],
        stdout=sp.PIPE)
    env = json.loads(pipe.stdout.read())
    return env


class ThriftServer(object):
    def clear_meta(self):
        """Command: thriftserver clear-meta

        Clear meta data
        """
        key = 'thriftserver'
        utils.clear_meta(key, {})

    def edit(self):
        """Command: thriftserver edit

        Open vim to edit thriftserver
        """
        key = 'thriftserver'
        utils.open_vim_editor(target=key)

        meta = utils.get_meta_data_after_ensure(key, default_value={})
        meta = json.loads(meta)
        cur_cluster_id = str(config.get_cur_cluster_id())
        now = datetime.datetime.now()
        dt = now.strftime("%Y-%m-%d %H:%M:%S")
        meta[cur_cluster_id] = dt
        utils.set_meta_data(key, meta)

    def start(self):
        """Start thriftserver
        """
        ip, port, cluster_id = self._get_thriftserver_info()
        logger.debug('Start thriftserver (%s:%d)' % (ip, port))
        client = get_ssh(ip)
        if not client:
            logger.info('! ssh connection fail: %s' % ip)
            return
        exec_file = path_join(
            config.get_tsr2_home(cluster_id),
            'sbin',
            'thriftserver')
        env = ''  # TODO: import env
        command = '''{env} ; {exec_file} start &'''.format(
            env=env,
            exec_file=exec_file)
        logger.info(command)
        ssh_execute(
            client=client,
            command=command)

    def stop(self):
        """Stop thriftserver
        """
        logger.debug('stop thriftserver.')
        max_try_count = 10
        for i in range(0, max_try_count):
            alive_count = self._get_alive_process_count()
            logger.info('Alive thriftserver process: %s (try count: %s)' % (
                alive_count, i))
            if alive_count > 0:
                self._send_stop_signal()
                time.sleep(3)
            else:
                logger.info('thriftserver stop complete.')
                return
        raise Exception('thriftserver_stop_process', 'max try error')

    def monitor(self):
        """Monitor thriftserver (using tail -f)
        """
        cur_cluster_id = config.get_cur_cluster_id()
        logger.info('Start monitor cluster_id: %s' % cur_cluster_id)
        ip_list = config.get_node_ip_list()
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
        envs = config.get_env_dict(ip, 0)
        tl = envs['sr2_redis_log']  # TODO: change redis log path
        command = 'tail -f {tl}/*'.format(tl=tl)
        ssh_execute_async(client=client, command=command)

    def _send_stop_signal(self, force=False):
        ip, port, _ = self._get_thriftserver_info()
        pid_list = "ps -ef | grep 'thriftserver' | awk '{{print $2}}'"
        signal = 'SIGKILL' if force else 'SIGINT'
        command = 'kill -s {signal} $({pid_list})' \
            .format(pid_list=pid_list, signal=signal)
        client = get_ssh(ip)
        ssh_execute(
            client=client,
            command=command,
            allow_status=[-1, 0, 1, 123, 130])

    def _get_thriftserver_info(self):
        key = 'thriftserver'
        meta = utils.get_meta_data_after_ensure(key)
        cur_cluster_id = config.get_cur_cluster_id()
        if str(cur_cluster_id) in meta:
            full_path = utils.get_full_path_of_props(
                cluster_id=cur_cluster_id,
                target='thriftserver')
            my_envs = _get_sh_envs(full_path)
            ip = my_envs['HIVE_HOST']
            port = int(my_envs['HIVE_PORT'])
            ret = ip, port, cur_cluster_id
            logger.info('thriftserver_info: ', ret)
            return ret
        assert False, 'You should edit thriftserver.properties before use it'
        return 'localhost', 13000, 0

    def _get_alive_process_count(self):
        ps = "ps -ef | grep 'thriftserver'"
        command = '''{ps} | wc -l'''.format(ps=ps)
        total_count = 0
        ip, port, _ = self._get_thriftserver_info()
        client = get_ssh(ip)
        exit_status, stdout_msg, stderr_msg = ssh_execute(
            client=client,
            command=command)
        c = int(stdout_msg)
        total_count += c
        return total_count
