import sys
from os.path import expanduser, basename, isdir, dirname, realpath
from os.path import join as path_join
from os import environ, mkdir, system

from logbook import Logger, Processor
from logbook import StreamHandler, RotatingFileHandler
from logbook import DEBUG, INFO, WARNING, ERROR
import color


def get_log_color(level):
    color_by_level = {
        DEBUG: color.ENDC,
        INFO: color.WHITE,
        WARNING: color.YELLOW,
        ERROR: color.RED,
    }
    return color_by_level[level]


def get_log_code(level):
    code = {
        'debug': DEBUG,
        'info': INFO,
        'warn': WARNING,
        'warning': WARNING,
        'error': ERROR,
    }
    return code[level]


formatter = {
    'screen': '' .join([
        '{record.extra[level_color]}',
        '{record.message}',
        '{record.extra[clear_color]}',
    ]),
    'screen_detail': ''.join([
        '{record.time:%Y-%m-%d %H:%M:%S}',
        ' ',
        '[',
        '{record.extra[level_color]}',
        '{record.level_name:<7}',
        '{record.extra[clear_color]}',
        ']',
        ' ',
        '({record.extra[basename]} --- {record.func_name}():{record.lineno})',
        ' : ',
        '{record.extra[level_color]}',
        '{record.message}',
        '{record.extra[clear_color]}',
    ]),
    'file': ''.join([
        '{record.time:%Y-%m-%d %H:%M:%S}',
        ' ',
        '[{record.level_name:<7}]',
        ' ',
        '({record.extra[basename]} --- {record.func_name}():{record.lineno})',
        ' : ',
        '{record.message}',
    ]),
}


def inject_extra(record):
    record.extra['basename'] = basename(record.filename)
    record.extra['level_color'] = get_log_color(record.level)
    record.extra['clear_color'] = color.ENDC


logger = Logger('root')

# extra info
processor = Processor(inject_extra)
processor.push_application()

# for screen log
screen_level = INFO
stream_handler = StreamHandler(sys.stdout, level=screen_level, bubble=True)
stream_handler.format_string = formatter['screen']
stream_handler.push_application()

# for rolling file log
if 'FBPATH' not in environ:
    msg = [
        'To start using fbctl, you should set env FBPATH',
        'ex)',
        'export FBPATH=$HOME/.flashbase'
    ]
    logger.error('\n'.join(msg))
    exit(1)
p = environ['FBPATH']
if not isdir(p):
    system('mkdir -p {}'.format(p))
file_path = expanduser(path_join(p, 'logs'))
if isdir(file_path):
    backup_count = 7
    max_size = 1024 * 1024 * 1024  # 1Gi
    file_level = DEBUG
    each_size = max_size / (backup_count + 1)
    filename = path_join(file_path, 'fbctl-rotate.log')
    rotating_file_handler = RotatingFileHandler(
        filename=filename,
        level=file_level,
        bubble=True,
        max_size=each_size,
        backup_count=backup_count
    )
    rotating_file_handler.format_string = formatter['file']
    rotating_file_handler.push_application()
    logger.debug('start logging on file: {}'.format(filename))
else:
    try:
        mkdir(file_path)
    except Exception:
        logger.error("CreateDirError: {}".format(file_path))
        logger.warn('Could not logging in file. Confirm and restart.')


def set_level(level):
    level_list = ['debug', 'info', 'warning', 'error', 'warn']
    if level not in level_list:
        level_list.remove('warn')
        logger.error("LogLevelError: '{}'. Select in {}".format(
            level,
            level_list
        ))
        return
    code = get_log_code(level)
    stream_handler.level = code
    print(color.white('Changed log level to {}'.format(level)))


def set_mode(mode):
    mode_list = ['debug', 'normal']
    if mode not in mode_list:
        logger.error('ModeError: {}. Select in {}'.format(mode, mode_list))
        return
    if mode == 'debug':
        stream_handler.format_string = formatter['screen_detail']
        set_level('debug')
    if mode == 'normal':
        stream_handler.format_string = formatter['screen']
        set_level('info')