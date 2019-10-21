from __future__ import print_function

import fileinput
import random
import subprocess
from os.path import join as path_join

import config
import utils
from log import logger


class RedisCliUtil(object):
    @staticmethod
    def to_list_of_dict(target_lines):
        """convert list to list of dict

        :param target_lines: list
        :return: list of dict
        """
        l = []
        for line in target_lines:
            _, value_str = line.split(':')
            value_strs = value_str.split(',')
            d = {}
            for value_str in value_strs:
                key, value = value_str.split('=')
                d[key] = value
            l.append(d)
        return l

    @staticmethod
    def command(
        sub_cmd, cluster_id=-1, mute=False, formatter=None, host=None, port=0):
        """Send redis-cli command

        :param sub_cmd: sub command
        :param cluster_id: target cluster #
        :param mute: without stdout
        :param formatter: If set, call formatter with output string
        :param host: host
        :param port: port
        :return: output string
        """
        ip_list = config.get_node_ip_list(cluster_id)
        port_list = config.get_master_port_list(cluster_id)
        if host:
            ip_list = [host]
            port_list = [port]
        outs = RedisCliUtil.command_raw(sub_cmd, ip_list, port_list)
        if mute:
            return outs
        if formatter:
            formatter(outs)
        else:
            logger.info(outs)
        return outs

    @staticmethod
    def command_all(sub_cmd, cluster_id=-1, formatter=None):
        """Send redis-cli command to all

        :param sub_cmd: sub command
        :param cluster_id: target cluster #
        :param formatter: if set, call formatter with output string
        """
        if cluster_id < 0:
            cluster_id = config.get_cur_cluster_id()
        ip_list = config.get_node_ip_list(cluster_id)
        port_list = config.get_master_port_list(cluster_id)
        outs, meta = RedisCliUtil.command_raw_all(
            sub_cmd, ip_list, port_list)
        if formatter:
            formatter(meta)
        else:
            logger.debug(outs)

    @staticmethod
    def command_raw(sub_cmd, ip_list, port_list):
        """Send redis-cli command raw

        :param sub_cmd: sub command
        :param ip_list: ip list
        :param port_list: port list
        :return: output string
        """
        logger.debug('command_raw')
        targets = utils.get_ip_port_tuple_list(ip_list, port_list)
        count = len(targets)
        index = random.randrange(0, count)
        target = targets[index]
        ip, port = target
        # logger.info('redis-cli connect to %s:%s' % (ip, port))
        outs = ''
        redis_cli = path_join(config.get_tsr2_home(), 'bin', 'redis-cli')
        env = utils.make_export_envs(ip, port)
        command = '{env}; {redis_cli} -h {ip} -p {port} {sub_cmd}'.format(
            env=env,
            redis_cli=redis_cli,
            ip=ip,
            port=port,
            sub_cmd=sub_cmd)
        try:
            stdout = subprocess.check_output(command, shell=True)
            outs += stdout
        except subprocess.CalledProcessError as ex:
            logger.debug('exception: %s' % str(ex))
        logger.debug('subprocess: %s' % command)
        return outs

    @staticmethod
    def command_raw_all(sub_cmd, ip_list, port_list):
        """Send redis-cli command raw to all

        :param sub_cmd: sub command
        :param ip_list: ip list
        :param port_list: port list
        :return: (output string, meta)
        """
        logger.debug('command_raw_all')
        targets = utils.get_ip_port_tuple_list(ip_list, port_list)
        outs = ''
        stdout = ''
        meta = [['addr', 'stdout']]
        for ip, port in targets:
            env = utils.make_export_envs(ip, port)
            redis_cli = path_join(config.get_tsr2_home(), 'bin', 'redis-cli')
            command = '{env}; {redis_cli} -c -h {ip} -p {port} {sub_cmd}'.format(
                redis_cli=redis_cli,
                ip=ip,
                port=port,
                env=env,
                sub_cmd=sub_cmd)
            logger.debug('subprocess: %s' % command)
            try:
                stdout = subprocess.check_output(command, shell=True)
                outs += stdout
                meta.append(['%s:%s' % (ip, port), stdout])
            except subprocess.CalledProcessError as ex:
                logger.debug('exception: %s' % str(ex))
        return outs, meta

    @staticmethod
    def save_redis_template_config(key, value):
        """Save redis template config to file

        :param key: key
        :param value: value
        """
        key = key.strip()
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        master_template = path_of_fb['master_template']
        slave_template = path_of_fb['slave_template']
        RedisCliUtil._save_config(master_template, key, value)
        RedisCliUtil._save_config(slave_template, key, value)

    @staticmethod
    def _save_config(f, key, value):
        inplace_count = 0
        for line in fileinput.input(f, inplace=True):
            if line.startswith(key):
                msg = '{key} {value}'.format(key=key, value=value)
                inplace_count += 1
                print(msg)
            else:
                print(line, end='')
        logger.debug('inplace: %d (%s)' % (inplace_count, f))
        if inplace_count == 1:
            logger.info('save config(%s) success' % f)
        else:
            logger.warn('save config(%s) fail(%d)' % (f, inplace_count))
