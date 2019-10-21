import os

from log import logger
import config
from deploy_util import DeployUtil
import net
import color
import utils


def validate_id(cluster_id):
    if type(cluster_id) is not type(int()):
        return False
    if cluster_id < 1:
        return False
    return True


def get_cluster_list():
    path_of_fb = config.get_path_of_fb(None)
    base_dir = path_of_fb['base_directory']
    buf = os.listdir(base_dir)
    buf = filter(lambda x: x.startswith('cluster_'), buf)
    buf = map(lambda x: int(x[8:]), buf)
    cluster_list = []
    for cluster_id in buf:
        cluster_id = int(cluster_id)
        cluster_dir = 'cluster_{}'.format(cluster_id)
        cluster_path = os.path.join(base_dir, cluster_dir)
        if not os.path.isfile(os.path.join(cluster_path, '.deploy.state')):
            cluster_list.append(cluster_id)
    cluster_list.sort()
    return list(cluster_list)


def convert_list_2_seq(ports):
    logger.debug('ports: {}'.format(ports))
    ret = []
    s = ports[0]
    pre = ports[0] - 1
    for port in ports:
        if pre != port - 1:
            if s != pre:
                ret.append('$(seq {} {})'.format(s, pre))
            else:
                ret.append(s)
            s = port
        pre = port
    if s != pre:
        ret.append('$(seq {} {})'.format(s, pre))
    else:
        ret.append(s)
    logger.debug('converted: {}'.format(ret))
    return ret


def rsync_fb_conf():
    logger.info('Sync conf...')
    cluster_id = config.get_cur_cluster_id()
    if not validate_id(cluster_id):
        logger.warn('Invalid cluster id: {}'.format(cluster_id))
        return
    cluster_list = get_cluster_list()
    if cluster_id not in cluster_list:
        logger.warn('Cluster not exist: {}'.format(cluster_id))
        return
    my_address = config.get_local_ip_list()
    path_of_fb = config.get_path_of_fb(cluster_id)
    props_path = path_of_fb['redis_properties']
    key = 'sr2_redis_master_hosts'
    nodes = config.get_props(props_path, key, [])
    meta = [['HOST', 'RESULT']]
    path_of_fb = config.get_path_of_fb(cluster_id)
    conf_path = path_of_fb['conf_path']
    cluster_path = path_of_fb['cluster_path']
    for node in nodes:
        if net.get_ip(node) in my_address:
            meta.append([node, color.green('OK')])
            continue
        client = net.get_ssh(node)
        if not client:
            meta.append([node, color.red('SSH ERROR')])
            continue
        if not net.is_dir(client, cluster_path):
            meta.append([node, color.red('NO CLUSTER')])
            continue
        net.copy_dir_to_remote(client, conf_path, conf_path)
        meta.append([node, color.green('OK')])
    utils.print_table(meta)
