"""(deprecated) This is temp unittest file
"""
from __future__ import unicode_literals

import json

from pyhive import hive
from rediscluster import StrictRedisCluster

import config
import sql_data as sd
import utils
from sql import FbLexer, MetaManager

host = '10.1.1.234'
# host = 'localhost'
port = 13000
cursor_array_size = 1000


def test_redis_cluster():
    cluster_id = 0
    ip_list = config.get_node_ip_list(cluster_id)
    port_list = config.get_master_port_list(cluster_id)
    startup_nodes = utils.get_ip_port_dict_list(ip_list, port_list)
    rc = StrictRedisCluster(startup_nodes=startup_nodes, decode_responses=True)
    d = {
        'k': {
            'k2': [1, 2, 3]
        }
    }
    # s = json.dumps(d)
    rc.set('cols', d)
    print(rc.get('cols'))


def test_lexer():
    fl = FbLexer()
    col0, opt0, table_name, range = fl.extract(sd.create_table_operation2)
    mm = MetaManager(table_name=table_name, first=True)

    col_meta = mm.update_col_meta(col0)
    fl.compile_options(opt0, col_meta)
    mm.update_opt_meta(opt0)


def test_sql():
    conn = hive.Connection(host=host, port=port)
    cursor = conn.cursor(arraysize=cursor_array_size)
    result = cursor.execute(sd.drop_table_operation)
    print('after drop table:', result)
    result = cursor.execute(sd.create_table_operation)
    print('after create table:', result)
    cursor.execute(sd.select_operation)
    next_data = cursor.fetchone()
    print('select result(first row):', next_data)
    while next_data:
        # print(tuple(map(lambda x: [x], next_data)))
        next_data = cursor.fetchone()


def _update_cols(prev_cols, statement):
    mm = MetaManager(table_name='iris')
    fl = FbLexer()
    mm.init_prev_cols(prev_cols)
    col, opt, _, _ = fl.extract(statement)
    cols = mm.update_col_meta(col)
    mm.update_opt_meta(opt)
    mm.save()
    return cols


def _check_cols(actual, expected):
    assert actual['generation'] == expected['generation']
    assert actual['removed'] == expected['removed']
    assert actual['added'] == expected['added']
    assert actual['all'] == expected['all']
    assert actual['data'] == expected['data']


def test_cols():
    fl = FbLexer()
    col0, opt0, table_name, range = fl.extract(sd.create0)
    assert table_name == 'iris'
    mm = MetaManager(table_name=table_name, first=True)
    cols0 = mm.update_col_meta(col0)
    mm.update_opt_meta(opt0)
    cols1 = _update_cols(cols0, sd.create1)
    cols2 = _update_cols(cols1, sd.create2)
    cols3 = _update_cols(cols2, sd.create3)
    _check_cols(cols0, sd.cols0_expected)
    _check_cols(cols1, sd.cols1_expected)
    _check_cols(cols2, sd.cols2_expected)
    _check_cols(cols3, sd.cols3_expected)

    mm = MetaManager(table_name)
    print('table_map:', mm.get_table_map())
    print('iris_columns:', utils.get_meta_data('iris_columns'))
    opt = json.loads(utils.get_meta_data('iris_options'))
    print('iris_options:', opt)
    tr = opt['transformations']
    print('transformations:', json.loads(tr))


inside_fbsql_create_statement = '''
# create table
CREATE TABLE iris (
    sepal_length FLOAT,
    sepal_width FLOAT,
    petal_length FLOAT,
    petal_width FLOAT,
    species STRING) USING R2 OPTIONS (
    table '101', 
    host 'localhost',
    port '18101',
    partitions 'sepal_length',
    mode 'nvkvs',
    group_size '5',
    query_result_partition_cnt_limit '40000',
    query_result_task_row_cnt_limit '10000',
    query_result_total_row_cnt_limit '100000000',
    transformations '[
    {
    "index": 33,
    "value": "$(0).length()<12? \"000000000000\" :$(0).substring(0, 11).concat( \"0\" )"
    },
    {
    "index": 35,
    "value": "fnvHash(7, 10)"
    }
    ]'
);

# select table
SELECT sepal_length, sepal_width FROM iris WHERE sepal_length > 0;

# drop TABLE 
drop table iris;

# data load
tsr2-tools insert -d /root/local-cli/.flashbase/data/iris/load/ -s "," -t /root/local-cli/.flashbase/data/iris/json/test.json -p 8 -c 1 -i
'''
