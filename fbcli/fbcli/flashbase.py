from os.path import join as path_join

import config
from log import logger
from net import get_ssh, ssh_execute


# deprecated
class Flashbase(object):
    """This is for testing class
    """
    def clean(self):
        logger.info('clean')
        host = config.get_master_node()
        client = get_ssh(host)
        command = '''flashbase clean'''
        ssh_execute(client, command)

    def stop(self, force=False):
        logger.info('stop')
        host = config.get_master_node()
        client = get_ssh(host)
        command = '''flashbase stop'''
        if force:
            command += ' --force'
        ssh_execute(client, command)

    def restart(self):
        logger.info('restart')
        command = \
            '''flashbase stop \
&& flashbase clean \
&& flashbase restart --reset --cluster --yes'''
        host = config.get_master_node()
        client = get_ssh(host)
        ssh_execute(client, command)

    def start(self):
        logger.info('restart')
        command = '''flashbase start'''
        host = config.get_master_node()
        client = get_ssh(host)
        ssh_execute(client, command)

    def ready_iris(self):
        repo_path = config.get_root_of_cli_config()
        iris = path_join(repo_path, 'data/iris')
        command = \
            '''tsr2-tools insert \
            -d {iris}/load/ \
            -s "," \
            -t {iris}/json/test.json \
            -p 8 -c 1 -i'''.format(iris=iris)
        logger.info(command)
        host = config.get_master_node()
        client = get_ssh(host)
        ssh_execute(client, command)

    def info(self, detail='all'):
        command = 'flashbase cli info %s' % detail
        host = config.get_master_node()
        client = get_ssh(host)
        ssh_execute(client, command)
