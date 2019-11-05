import copy
import datetime
import json
from os.path import join as path_join

import fire
from fire.core import FireExit
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.named_commands import get_by_name
from prompt_toolkit.lexers import PygmentsLexer
from pygments.lexer import RegexLexer, words
from pygments.lexers.sql import SqlLexer
from pygments.token import *
from pyhive import hive

import config
import sql_util
import utils
from cluster import Cluster
from log import logger
from prompt import get_sql_prompt
from rediscli_util import RedisCliUtil
from utils import CommandError, clear_screen, style

TABLE_MAP_KEY = 'table_map'


class MetaManager(object):
    def __init__(self, table_name=None, first=False):
        self.table_name = table_name
        self.biggest_index = -1
        self.prev_cols = None
        if first:
            self._init_first_prev_cols()
        self.cols = None  # {generation, removed:[], added:[], data: []}
        self.options = None

    def get_options_from_db(self):
        """Get options from db(db = cluster 0)

        :return: option data (json type)
        """
        rc = utils.create_cluster_connection_0()
        m = rc.get('%s_options' % self.table_name)
        return json.loads(m)

    def get_columns_from_db(self):
        """Get columns of table from db(db = cluster 0)

        :return: option data (json type)
        """
        return sql_util.get_columns_from_db(self.table_name)

    def get_table_map(self):
        """Get table map

        table_map = { key: { table_id, cluster_id } }
        """
        rc = utils.create_cluster_connection_0()
        m = rc.get(TABLE_MAP_KEY)
        try:
            return json.loads(m)
        except:
            pass
        return {}

    def init_prev_cols(self, prev_cols):
        """Init prev cols

        :param prev_cols: prev cols
        """
        if prev_cols:
            self.prev_cols = copy.deepcopy(prev_cols)
        else:
            self._init_first_prev_cols()

    def update_opt_meta(self, options):
        """Update option meta data
        """
        self.options = options

    def update_col_meta(self, columns):
        """Update col meta data
        """
        assert self.prev_cols is not None
        self.cols = None
        p = self.prev_cols
        generation = p['generation'] + 1
        now = datetime.datetime.now()
        dt = now.strftime("%Y-%m-%d %H:%M:%S")
        all = self.prev_cols['all']
        prev_data = self.prev_cols['data']
        biggest_index = -1
        if all:
            biggest_key = max(all, key=all.get)
            biggest_index = all[biggest_key]
        data = {}
        for col in columns:
            index = self._get_index_and_status(col, all, biggest_index)
            biggest_index = max(index, biggest_index)
            data[col] = index
        added = {k: v for k, v in data.items() if k not in prev_data}
        removed = {k: v for k, v in prev_data.items() if k not in columns}
        all.update(data)
        self.cols = {
            'generation': generation,
            'dt': dt,
            'removed': removed,
            'added': added,
            'all': all,
            'data': data,
        }
        return self.cols

    def save(self):
        """save
        """
        if not self.cols:
            logger.warn('Please update before save')
            return False
        if 'table' not in self.options:
            logger.warn('Table info is not in options')
            logger.warn(self.options)
            return False
        rc = utils.create_cluster_connection_0()
        self._update_table_map(rc)
        key = self.table_name
        rc.set('%s_columns' % key, json.dumps(self.cols))
        rc.set('%s_options' % key, json.dumps(self.options))
        logger.debug('save complete')
        return True

    def save_delete(self):
        """delete
        """
        rc = utils.create_cluster_connection_0()
        key = self.table_name

        table_map = self.get_table_map()
        if key in table_map:
            del table_map[key]
            rc.set(TABLE_MAP_KEY, json.dumps(table_map))
        rc.delete('%s_columns' % key)
        rc.delete('%s_options' % key)
        logger.debug('save_delete complete')
        return True

    def _get_index_and_status(self, col, all, biggest_index):
        if col in all:
            return all[col]
        return biggest_index + 1

    def _update_table_map(self, rc):
        table_map = self.get_table_map()
        assert isinstance(table_map, dict), table_map
        key = self.table_name
        value = self.options['table']
        cluster_id = config.get_cur_cluster_id()
        table_map[key] = {
            'table_id': value,
            'cluster_id': cluster_id,
        }
        rc.set(TABLE_MAP_KEY, json.dumps(table_map))

    def _init_first_prev_cols(self):
        self.prev_cols = {
            'generation': -1,
            'dt': '',
            'removed': {},
            'added': {},
            'all': {},
            'data': {},
        }


class FbLexer(RegexLexer):
    """Lexer for Flashbase CREATE sql statement
    """
    name = 'unused_fb'
    aliases = ['unused_fb']
    filenames = ['*.unused_fb']

    tokens = {
        'root': [
            (r'\s+', Text),
            (r'--.*\n?', Comment.Single),
            (r'/\*', Comment.Multiline, 'comment'),
            (words((
                'CREATE', 'TABLE', 'USING', 'R2', 'OPTIONS',
                'create', 'table', 'using', 'r2', 'options',
            ), suffix=r'\b'), Keyword),
            (r'[+*/<>=~!@#%^&|`?-]', Operator),
            (r'[0-9]+', Number.Integer),
            (r"'(''|[^'])*'", String.Single),
            (r'"(""|[^"])*"', String.Symbol),
            (r'[a-z_A-Z][\w$]*', Name),
            (r'[;:()\[\],.]', Punctuation)
        ],
        'comment': [
            (r'/\*', Comment.Multiline, 'comment'),
            (r'\*/', Comment.Multiline, '#pop'),
            (r'[^/*]+', Comment.Multiline),
            (r'[/*]', Comment.Multiline)
        ]
    }

    def to_text(self, text, options, range):
        tokens = []
        for pair in self.get_tokens(text):
            tokens.append(pair)
        headers = tokens[:range.min_index]
        new_text = ''
        for pair in headers:
            new_text += pair[1]
        new_text += self._options_to_text(options)
        tails = tokens[range.max_index + 1:]
        for pair in tails:
            new_text += pair[1]
        return new_text

    def extract(self, text):
        """Extract meta info from text

        :param text: sql statement
        :return: (columns, options, table_name, options_range)

        - options_range : token range of option section
        """

        tokens = []
        for pair in self.get_tokens(text):
            tokens.append(pair)
        table_name = self._extract_table_name(tokens)
        columns, _ = self._extract_columns(tokens)
        options, options_range = self._extract_options(tokens)
        target_keys = ['transformations']
        for k in options:
            v = options[k]
            if k in target_keys:
                # Check json syntax
                json.loads(v)
        return columns, options, table_name, options_range

    def compile_options(self, options, columns):
        """Compile options

        We change column names in options as index of column.

        :param options: extracted options from text(sql statement)
        :param columns: extracted columns from text(sql statement)
        :return: compiled(modified) options
        """
        col_index_map = columns['data']
        compiles = {
            'transformations': self._compile_transformations,
            # 'partitions': self._compile_partitions,
        }
        # INGING TODO FIXME HERE
        new_options = copy.deepcopy(options)
        for k in compiles:
            func = compiles[k]
            if k in new_options:
                text = new_options[k]
                new_options[k] = func(text, col_index_map)
        return new_options

    def extract_table_name(self, text):
        """Extract table name

        :param text: sql statement
        :return:
        """
        tokens = []
        for pair in self.get_tokens(text):
            tokens.append(pair)
        table_name = self._extract_table_name(tokens)
        return table_name

    def _options_to_text(self, options):
        text = ''
        for k in options:
            v = options[k]
            text += "%s '%s',\n" % (k, v)
        return text[:-2]

    def _compile_transformations(self, text, col_index_map):
        t_map = (json.loads(text))
        new_rows = []
        for row in t_map:
            name = row['index']
            v = row['value']
            for col_key in col_index_map:
                v = v.replace(col_key, str(col_index_map[col_key]))
            new_rows.append({
                'index': col_index_map[name],
                'value': v
            })
        print(new_rows)
        return json.dumps(new_rows)

    def _compile_partitions(self, text, col_index_map):
        names = text.split(' ')
        index_list = map(lambda x: col_index_map[x], names)
        return json.dumps(index_list)

    def _extract_table_name(self, tokens):
        idx = self._find_next_keyword_index(tokens, 'TABLE') + 1
        idx = self._find_next_keyword_or_name_index(tokens, idx)
        v = tokens[idx][1]
        return v

    def _extract_options(self, tokens):
        idx = self._find_next_keyword_index(tokens, 'USING')
        idx = self._find_next_keyword_index(tokens, 'R2', idx)
        idx = self._find_next_keyword_index(tokens, 'OPTIONS', idx)
        start = self._find_next_punctuation_index(tokens, '(', idx) + 1
        end = self._find_next_punctuation_index(tokens, ')', idx) - 1
        cur_index = start
        options = {}
        r = utils.RangeChecker()
        while True:
            if cur_index < 0 or cur_index >= end:
                break
            cur_index = self._find_next_keyword_or_name_index(tokens, cur_index)
            r.check(cur_index)
            k = tokens[cur_index][1]
            cur_index = self._find_next_literal_index(tokens, cur_index)
            r.check(cur_index)
            v = tokens[cur_index][1].strip("'")
            options[k] = v
            cur_index = self._find_next_punctuation_index(
                tokens, ',', cur_index)
        return options, r

    def _extract_columns(self, tokens):
        col_start, col_end = self._get_column_range(tokens)
        columns = []
        cur_index = col_start
        r = utils.RangeChecker()
        while True:
            if cur_index < 0 or cur_index >= col_end:
                break
            cur_index = self._find_next_keyword_or_name_index(tokens, cur_index)
            if cur_index < 0:
                break
            columns.append(tokens[cur_index][1])
            r.check(cur_index)
            cur_index = self._find_next_punctuation_index(
                tokens, ',', cur_index)
        return columns, r

    def _find_next_keyword_or_name_index(self, tokens, start_index=0):
        for index in range(start_index, len(tokens)):
            (t, v) = tokens[index]
            if t == Keyword or t == Name:
                return index
        return -1

    def _find_next_keyword_index(self, tokens, keyword, start_index=0):
        for index in range(start_index, len(tokens)):
            (t, v) = tokens[index]
            if t == Keyword and v.upper() == keyword.upper():
                return index
        assert False
        return -1

    def _find_next_punctuation_index(self, tokens, word, start_index):
        for index in range(start_index, len(tokens)):
            (t, v) = tokens[index]
            if t == Punctuation and v == word:
                return index
        return -1

    def _find_next_literal_index(self, tokens, start_index):
        for index in range(start_index, len(tokens)):
            (t, v) = tokens[index]
            if t == Literal.String.Single:
                return index
        return -1

    def _get_column_range(self, tokens):
        idx = self._find_next_keyword_index(tokens, 'CREATE')
        idx = self._find_next_keyword_index(tokens, 'TABLE', idx)
        start = self._find_next_punctuation_index(tokens, '(', idx) + 1
        end = self._find_next_punctuation_index(tokens, ')', idx) - 1
        return start, end


fb_completer = WordCompleter([], ignore_case=True)


class Table(object):
    """
    Table command
    """

    def info(self, table_name):
        """Command: table info [table_name]

        :param table_name: table name
        """
        print('# table info (meta)')
        table_map = MetaManager().get_table_map()
        if table_name not in table_map:
            print('No table name in map', table_name, table_map)
            return
        table_info = table_map[table_name]
        cluster_id_of_table = table_info['cluster_id']
        self._print_option_meta(table_name)
        self._print_column_meta(table_name)
        self._print_extra_meta(table_name, cluster_id_of_table)

    def list(self):
        """Command: table list"""
        d = MetaManager().get_table_map()
        rows = []
        for k in d:
            v = d[k]
            rows.append((k, v['cluster_id'], v['table_id']))
        utils.tprint_list(rows, ['table_name', 'cluster_id', 'table_id'])

    def __set_tablespace(self, cluster_id_of_table, cols):
        tablespace_lines = RedisCliUtil.command(
            sub_cmd='info tablespace',
            mute=True,
            cluster_id=cluster_id_of_table)
        keywords = ['numPartitionColumns', 'partitionColumns', 'partitions']
        lines = tablespace_lines.splitlines()
        for line in lines:
            for keyword in keywords:
                if keyword in line:
                    left = line.split(keyword + '=')[1]
                    if ',' in left:
                        value = left.split(',')[0]
                        cols[keyword] = value
                    else:
                        cols[keyword] = left

    def __set_ttl(self, cluster_id_of_table, cols):
        def _filter(raw):
            seconds = int(raw)
            return '%s (%s)' % (raw, str(datetime.timedelta(seconds=seconds)))

        key = 'flash-db-ttl'
        try:
            sub_cmd = 'config get "{key}"'.format(key=key)
            v = RedisCliUtil.command(
                sub_cmd=sub_cmd,
                mute=True,
                cluster_id=cluster_id_of_table)
            cols[key] = _filter(v.splitlines()[1])
        except:
            cols[key] = 'error'

    def __set_maxmemory(self, cluster_id_of_table, cols):
        key = 'maxmemory'
        try:
            sub_cmd = 'config get "{key}"'.format(key=key)
            raw = RedisCliUtil.command(
                sub_cmd=sub_cmd,
                mute=True,
                cluster_id=cluster_id_of_table)
            v = int(raw.splitlines()[1])
            cols[key] = '{:,} bytes'.format(v)
        except:
            cols[key] = 'error'

    def _print_extra_meta(self, table_name, cluster_id_of_table):
        cols = {}
        self.__set_tablespace(cluster_id_of_table, cols)
        self.__set_ttl(cluster_id_of_table, cols)
        self.__set_maxmemory(cluster_id_of_table, cols)
        print('## extras')
        utils.tprint(cols, ['key', 'value'])

    def _print_column_meta(self, table_name):
        mm = MetaManager(table_name)
        print('## columns')
        cols = mm.get_columns_from_db()['data']
        utils.tprint(cols, ['column', 'index'])

    def _print_option_meta(self, table_name):
        mm = MetaManager(table_name)
        print('## options')
        data = mm.get_options_from_db()
        utils.tprint(data, ['option', 'value'])


class TableCommand(object):
    """
    Table command
    """

    def __init__(self):
        self.table = Table()


class SqlCluster(object):
    def use(self, cluster_id):
        """Command: cluster use [cluster_id]

        :param cluster_id: cluster #
        """
        Cluster.use(cluster_id)

    def check(self):
        """Command: cluster check

        Check thriftserver address
        """
        print('thrift addr: %s:%s' % sql_util.get_thrift_addr())


class SqlClusterCommand(object):
    def __init__(self):
        self.cluster = SqlCluster()


class FbSql(object):
    def __init__(self, user, print_mode='screen'):
        self.user = user
        self.handler = {
            'create': self._handle_create,
            'drop': self._handle_drop,
            'truncate': self._handle_truncate,
            'select': self._handle_select,
            'table': self._handle_table,
            'others': self._handle_others,
            'cluster': self._handle_sql_cluster,
        }
        self.print_mode = print_mode

    def handle(self, text):
        if text == '':
            return
        if text == 'clear':
            clear_screen()
            return
        try:
            key = text.split(' ')[0].lower()
            if key in self.handler:
                self.handler[key](text)
            else:
                self.handler['others'](text)
        except KeyError as e:
            print('[%s] command fail' % text)
            logger.exception(e)
        except TypeError as e:
            logger.exception(e)
        except CommandError as e:
            logger.exception(e)
        except FireExit as e:
            pass
            # if e.code is not 0:
            #     logger.exception(e)
        except BaseException as ex:
            logger.exception(ex)
            pass

    def run(self):
        """Enter sql cli mode.

        At the first time, you use fbcli mode. If you type 'sql', you enter here.
        If you want to exit here, type 'exit'
        """
        history = path_join(config.get_root_of_cli_config(), 'sql_history')
        session = PromptSession(
            lexer=PygmentsLexer(SqlLexer),
            completer=fb_completer,
            history=FileHistory(history),
            auto_suggest=AutoSuggestFromHistory(),
            style=style)

        bindings = KeyBindings()

        @bindings.add('enter')
        def _(event):
            t = event.app.current_buffer.text.strip()
            if t.endswith(';') or len(t) == 0 or \
                    t.startswith('exit') or t.startswith('help'):
                get_by_name('accept-line')(event)
            else:
                event.current_buffer.newline()

        while True:
            try:
                p = get_sql_prompt()
                text = session.prompt(p, multiline=True, key_bindings=bindings)
                text = text.split(';')[0].strip()
                if text == 'exit':
                    logger.info('Exit sql mode')
                    break
                self.handle(text)
            except KeyboardInterrupt:
                continue
            except EOFError:
                logger.info('Exit sql mode')
                break

    def _handle_help(self):
        print('Start with %s' % self.handler.keys())

    def _execute(self, text):
        ip, port = sql_util.get_thrift_addr()
        conn = hive.Connection(host=ip, port=port)
        cursor = conn.cursor(arraysize=1000)
        result = cursor.execute(text)
        return result, cursor

    def _fire(self, text, component):
        try:
            fire.Fire(
                component=component,
                command=text)
        except KeyError as e:
            print('[%s] command fail' % text)
            logger.exception(e)
        except TypeError as e:
            logger.exception(e)
        except CommandError as e:
            logger.exception(e)
        except FireExit as e:
            pass
        except BaseException as ex:
            logger.exception(ex)

    def _handle_sql_cluster(self, text):
        self._fire(text, SqlClusterCommand)

    def _print(self, text):
        if self.print_mode == 'screen':
            print(text)

    def _handle_create(self, text):
        logger.info('_handle_create')
        fl = FbLexer()
        col, options, table_name, range = fl.extract(text)
        exist = sql_util.get_columns_from_db(table_name)
        first = True
        if exist:
            first = False
        mm = MetaManager(table_name, first)
        prev_cols = mm.get_columns_from_db()
        mm.init_prev_cols(prev_cols)

        cols = mm.update_col_meta(col)
        new_options = fl.compile_options(options, cols)
        mm.update_opt_meta(options)
        mm.update_opt_meta(new_options)  # save compiled json
        new_text = fl.to_text(text, new_options, range)
        print(text)
        print('---')
        print(new_text)
        result, cursor = self._execute(text)
        mm.save()
        print('create table finish')

    def _handle_drop(self, text):
        self._execute(text)
        print('drop table finish')

    def _handle_truncate(self, text):
        fl = FbLexer()
        table_name = fl.extract_table_name(text)
        try:
            result, cursor = self._execute(text)
        except Exception as e:
            logger.exception(e)
        mm = MetaManager(table_name)
        mm.save_delete()
        print('truncate table finish')

    def _handle_select(self, text):
        result, cursor = self._execute(text)
        next_data = cursor.fetchone()
        # cols = len(next_data)
        rows = []
        if self.print_mode == 'screen':
            while next_data:
                rows.append(next_data)
                next_data = cursor.fetchone()
            tr = utils.TableReport([])
            tr.data = rows
            tr.print_out()
        else:
            while next_data:
                print(','.join(map(str, next_data)))
                next_data = cursor.fetchone()

    def _handle_table(self, text):
        self._fire(text, TableCommand)

    def _handle_others(self, text):
        if len(text.strip()) > 0:
            self._handle_help()


def fbsql(user):
    """Enter sql mode

    :param user: username
    """
    FbSql(user).run()
