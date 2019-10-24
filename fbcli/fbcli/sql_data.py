"""(deprecated) This is temp test data
"""
from __future__ import unicode_literals

drop_table_operation = 'drop table if exists iris'

select_operation = \
    'SELECT sepal_length, sepal_width FROM iris WHERE sepal_length > 0'

create_table_operation2 = '''
/*
this is multiline comment
*/
CREATE TABLE iris (
    sepal_length FLOAT,
    sepal_width FLOAT,
    petal_length FLOAT,
    petal_width FLOAT,
    species STRING) USING R2 OPTIONS (
    table '101', 
    host 'localhost',
    port '18101',
    partitions 'sepal_length sepal_width',
    mode 'nvkvs',
    group_size '5',
    query_result_partition_cnt_limit '40000',
    query_result_task_row_cnt_limit '10000',
    query_result_total_row_cnt_limit '100000000',
    transformations '[
    {
    "index": "sepal_length",
    "value": "$(sepal_length).length()<12? \\"000000000000\\" :$(sepal_length).substring(0, 11).concat( \\"0\\" )"
    },
    {
    "index": "petal_length",
    "value": "$(petal_length).length() != 0 && $(petal_length).substring(0, 2).equals(\\"T1\\")?\\"T1\\": \\"O\\""
    },
    {
    "index": "species",
    "value": "fnvHash(petal_width, 10)"
    }
    ]'
) 
'''

create_table_operation = '''
/*
this is multiline comment
*/
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
    "value": "$(0).length()<12? \\"000000000000\\" :$(0).substring(0, 11).concat( \\"0\\" )"
    },
    {
    "index": 34,
    "value": "$(7).length() != 0 && $(7).substring(0, 2).equals(\\"T1\\")?\\"T1\\": \\"O\\""
    },
    {
    "index": 35,
    "value": "fnvHash(7, 10)"
    }
    ]'
) 
'''

# [{generation, biggest_index, removed:[], added:[], data: []}]
create0 = '''
CREATE TABLE iris (
    my_col_0 FLOAT)
USING R2 OPTIONS (
    table '101'
)
'''

cols0_expected = {
    "generation": 0,
    "dt": "2018-12-04 08:00:00",
    "removed": {},
    "added": {"my_col_0": 0},
    "all": {
        "my_col_0": 0
    },
    "data": {
        "my_col_0": 0
    },
}

create1 = '''
CREATE TABLE iris (
    my_col_0 FLOAT,
    my_col_1 FLOAT)
USING R2 OPTIONS (
    table '101'
)
'''

cols1_expected = {
    "generation": 1,
    "dt": "2018-12-04 08:00:01",
    "removed": {},
    "added": {"my_col_1": 1},
    "all": {
        "my_col_0": 0,
        "my_col_1": 1
    },
    "data": {
        "my_col_0": 0,
        "my_col_1": 1
    },
}

create2 = '''
CREATE TABLE iris (
    my_col_0 FLOAT,
    my_col_2 FLOAT,
    my_col_1 FLOAT,
    my_col_3 FLOAT)
USING R2 OPTIONS (
    table '101'
) 
'''

cols2_expected = {
    "generation": 2,
    "dt": "2018-12-04 08:00:02",
    "removed": {},
    "added": {"my_col_2": 2, "my_col_3": 3},
    "all": {
        "my_col_0": 0,
        "my_col_1": 1,
        "my_col_2": 2,
        "my_col_3": 3,
    },
    "data": {
        "my_col_0": 0,
        "my_col_1": 1,
        "my_col_2": 2,
        "my_col_3": 3,
    },
}

create3 = '''
CREATE TABLE iris (
    my_col_0 FLOAT,
    my_col_4 FLOAT,
    my_col_1 FLOAT) USING R2 OPTIONS (
    table '101',
    host 'localhost',
    port '18101',
    partitions 'sepal_length',
    mode 'nvkvs',
    group_size '5',
    query_result_partition_cnt_limit '40000',
    query_result_task_row_cnt_limit '10000',
    query_result_total_row_cnt_limit '100000000',
    /*
    If you want to use " inside value, use \\"
    */
    transformations '[
    {
    "index": 33,
    "value": "$(0).length()<12? \\"000000000000\\" :$(0).substring(0, 11).concat( \\"0\\" )"
    },
    {
    "index": 34,
    "value": "$(7).length() != 0 && $(7).substring(0, 2).equals(\\"T1\\")?\\"T1\\": \\"O\\""
    },
    {
    "index": 35,
    "value": "fnvHash(7, 10)"
    }
    ]'
) 
'''

cols3_expected = {
    "generation": 3,
    "dt": "2018-12-04 08:00:02",
    "removed": {
        "my_col_2": 2,
        "my_col_3": 3,
    },
    "added": {"my_col_4": 4},
    "all": {
        "my_col_0": 0,
        "my_col_1": 1,
        "my_col_2": 2,
        "my_col_3": 3,
        "my_col_4": 4,
    },
    "data": {
        "my_col_0": 0,
        "my_col_1": 1,
        "my_col_4": 4,
    },
}
