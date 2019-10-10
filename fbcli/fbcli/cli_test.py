from ask import askInt

from log import logger
from redistrib2 import command as trib
import ask_util

def cluster_create():
    logger.info('create cluster test start')
    cluster_id = askInt('cluster id')
    ask_util.master_ports(int(cluster_id))
    # print('>>> Creating cluster')
    # self._update_ip_port()
    # targets = get_ip_port_tuple_list(self.ip_list, self.master_port_list)
    # logger.debug('create_master_cluster.')
    # trib.create(targets, max_slots=16384)
    # # if len(self.slave_port_list) > 0:
    # #     self._replicate()
    # logger.info('create_cluster complete.')
    logger.info('create cluster test end')
    exit(0)