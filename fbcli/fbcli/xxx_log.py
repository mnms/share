import logging
import sys

from rainbow_logging_handler import RainbowLoggingHandler

formatters = {
    'standard': logging.Formatter('%(message)s'),
    'debug': logging.Formatter(
        '[%(asctime)s] %(filename)s %(funcName)s():%(lineno)d\t%(message)s'),
}

logger = None


def change_log_formatter(name):
    global logger
    logger = logging.getLogger('root')
    logger.handlers = []
    formatter = formatters[name]
    handler = RainbowLoggingHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = 0
    if name == 'debug':
        LogLevel().debug()


change_log_formatter('standard')
logger.setLevel(logging.INFO)


class LogLevel(object):
    """
    LogLevel command
    - Change log level
    """

    def debug(self):
        logger.setLevel(logging.DEBUG)

    def info(self):
        logger.setLevel(logging.INFO)

    def warn(self):
        logger.setLevel(logging.WARN)

    def error(self):
        logger.setLevel(logging.ERROR)
