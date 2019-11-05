from __future__ import print_function

import errno
import socket
import time
from threading import Thread
from os.path import join as path_join
import os
import sys
import shutil

import paramiko
import requests
from redistrib2 import command as trib
from redistrib2.exceptions import RedisIOError

import utils
from log import logger
from exceptions import (
    SSHConnectionError,
    HostConnectionError,
    HostNameError,
    SSHCommandError,
)


def get_ssh(host, port=22):
    """Create SSHClient, connect TCP, and return it

    :param host: host
    :param port: port
    :return: socket (SSHClient)
    """
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.load_system_host_keys()
        client.connect(hostname=host, port=port)
        client.hostname = host
        client.port = port
        return client
    except paramiko.ssh_exception.NoValidConnectionsError:
        raise HostConnectionError(host)
    except paramiko.ssh_exception.AuthenticationException:
        raise SSHConnectionError(host)
    except socket.gaierror:
        raise HostNameError(host)


def get_sftp(client):
    """Open sftp

    :param client: SSHClient instance
    :return: opened sftp instance
    """
    try:
        sftp = client.open_sftp()
        return sftp
    except Exception as e:
        logger.debug(e)


def __ssh_execute_async_thread(channel, command):
    channel.exec_command(command)
    while True:
        if channel.exit_status_ready():
            break
        try:
            msg = channel.recv(4096)
            print(msg, end='')
        except socket.error as e:
            err = e.args[0]
            if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                time.sleep(1)
                continue
            else:
                print(e)
                break


def ssh_execute_async(client, command):
    """Execute ssh asynchronous

    This for for not terminating process (like tail -f)

    :param client: SSHClient
    :param command: command
    """
    channel = client.get_transport().open_session()
    t = Thread(
        target=__ssh_execute_async_thread,
        args=(channel, command,))
    t.daemon = True
    t.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        channel.close()


def ssh_execute(client, command, allow_status=[0]):
    """Execute ssh blocking I/O

    We get allow_status as an input.
    We ignore some error status, if it exist in allow_status.

    :param client: SSHClient
    :param command: command
    :param allow_status: list of allow status.
    """
    try:
        logger.debug('[ssh_execute] %s' % command)
        stdin, stdout, stderr = client.exec_command(command)
    except Exception as e:
        print(e)
        raise e
    stdout_msg = ''
    stderr_msg = ''

    stdout_msg = stdout.read()
    if stdout_msg is not "":
        logger.debug('---------------- command to : %s' % client.hostname)
        logger.debug(command)
        logger.debug('---------------- stdout')
        logger.debug(stdout_msg)

    stderr_msg = stderr.read()
    if stderr_msg is not "":
        logger.debug('---------------- command to : %s' % client.hostname)
        logger.debug(command)
        if len(stderr_msg) > 0:
            logger.debug('---------------- stderr')
            logger.debug(stderr_msg)

    exit_status = stdout.channel.recv_exit_status()
    if exit_status not in allow_status:
        host = client.hostname
        raise SSHCommandError(exit_status, host, stderr_msg)
    return exit_status, stdout_msg, stderr_msg


def is_dir(client, file_path):
    """Determine if directory or not

    :param client: SSHClient
    :param file_path: absolute path of file
    """
    command = "[ -d '{}' ] && echo True || echo False".format(file_path)
    _, stdout, _ = ssh_execute(client, command)
    return stdout.strip() == 'True'


def is_exist(client, file_path):
    """Determine if exist or not

    :param client: SSHClient
    :param file_path: absolute path of file
    """
    command = "[ -e '{}' ] && echo True || echo False".format(file_path)
    _, stdout, _ = ssh_execute(client, command)
    return stdout.strip() == 'True'


def copy_dir_to_remote(client, local_path, remote_path):
    """copy directory from local to remote
    if already file exist, overwrite file
    copy all files recursively
    directory must exist

    :param client: SSHClient
    :param local_path: absolute path of file
    :param remote_path: absolute path of file
    """
    logger.debug('copy_dir_to_remote')
    logger.debug('copy FROM localhost:{} TO node:{}'.format(
        local_path,
        remote_path
    ))
    sftp = get_sftp(client)
    listdir = os.listdir(local_path)
    for f in listdir:
        r_path = path_join(remote_path, f)
        l_path = path_join(local_path, f)
        if os.path.isdir(l_path):
            if not is_exist(client, r_path):
                sftp.mkdir(r_path)
            copy_dir_to_remote(client, l_path, r_path)
        else:
            sftp.put(l_path, r_path)


def copy_dir_from_remote(client, remote_path, local_path):
    """copy directory from remote to local

    if already file exist, overwrite file
    copy all files recursively
    directory must exist

    :param client: SSHClient
    :param remote_path: absolute path of file
    :param local_path: absolute path of file
    """
    logger.debug('copy FROM node:{} TO localhost:{}'.format(remote_path, local_path))
    sftp = get_sftp(client)
    listdir = sftp.listdir(remote_path)
    for f in listdir:
        r_path = path_join(remote_path, f)
        l_path = path_join(local_path, f)
        if is_dir(client, r_path):
            if not os.path.exists(l_path):
                os.mkdir(l_path)
            copy_dir_from_remote(client, r_path, l_path)
        else:
            sftp.get(r_path, l_path)


def get_home_path(host):
    client = get_ssh(host)
    command = 'echo $HOME'
    _, stdout, _ = ssh_execute(client, command)
    client.close()
    return stdout.strip()


def ping(host, duration=3):
    command = 'ping -c 1 -t {} {} > /dev/null 2>&1'.format(duration, host)
    response = os.system(command)
    print(response)
    logger.debug('ping to {}, respose: {}'.format(host, response))
    if response is not 0:
        raise HostConnectionError(host, status_code=response)


def is_port_empty(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = True
    status = 'OK'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((host, port))
    except socket.error as e:
        result = False
        if e.errno == errno.EADDRINUSE:
            status = 'USED'
            logger.debug('{}:{} is already in use'.format(host, port))
        else:
            status = 'FAIL'
            logger.exception(e)
    except Exception as e:
        result = False
        status = 'FAIL'
        logger.exception(e)
    finally:
        return result, status


def get_ip(host):
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        raise HostNameError(host)
    return ip


def download_file(url, file_path):
    download_path = file_path + '.download'
    file_name = os.path.basename(file_path)
    try:
        with open(download_path, 'wb') as f:
            logger.info('Downloading {}'.format(file_name))
            logger.debug('url: {}'.format(url))
            logger.debug('installer name: {}'.format(file_name))
            response = requests.get(url, stream=True)
            response.raise_for_status()
            total_length = response.headers.get('content-length')
            if total_length is None:
                f.write(response.content)
            else:
                done_length = 0
                total_length = int(total_length)
                for data in response.iter_content(chunk_size=4096):
                    done_length += len(data)
                    f.write(data)
                    done = int(100 * done_length / total_length)
                    comp = '=' * (done / 2)
                    remain = ' ' * (50 - (done / 2))
                    progress = '\r[{}{}] {}%'.format(comp, remain, done)
                    sys.stdout.write(progress)
                    sys.stdout.flush()
            print('')
            shutil.move(download_path, file_path)
            return True
    except requests.exceptions.HTTPError as ex:
        logger.warning(ex)
        return False
    except KeyboardInterrupt as ex:
        print('')
        raise ex
    except BaseException as ex:
        class_name = ex.__class__.__name__
        logger.warning('{}: {}'.format(class_name, url))
        return False
    finally:
        if os.path.isfile(download_path):
            os.remove(download_path)
