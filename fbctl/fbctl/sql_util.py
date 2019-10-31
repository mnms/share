import json
from os.path import join as path_join

import config
import utils


def get_thrift_addr():
    """Get thrift address from file (thriftserver.properties)
    :return: ip, port info
    """
    cluster_id = config.get_cur_cluster_id()
    path = config.get_repo_cluster_path(cluster_id)
    p = path_join(path, 'tsr2-conf', 'thriftserver.properties')
    ip = None
    port = None
    with open(p, 'r') as fd:
        lines = fd.readlines()
        for line in lines:
            if 'HIVE_HOST' in line:
                ip = line.split('=')[1].strip()
                if '#' in ip:
                    ip = ip.split('#')[0].strip()
            if 'HIVE_PORT' in line:
                port = line.split('=')[1].strip()
                if '#' in port:
                    port = port.split('#')[0].strip()
    return ip, port


def get_columns_from_db(table_name):
    """Get columns from db using 'table name'

    :param table_name: table name
    :return: json type column data
    """
    try:
        rc = utils.create_cluster_connection_0()
        m = rc.get('%s_columns' % table_name)
        return json.loads(m)
    except:
        return None
