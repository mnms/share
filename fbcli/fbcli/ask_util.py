import os
from os.path import join as path_join
import re

from ask import askBool, askInt, askPassword, ask

from log import logger
import config

start_port = 18000
master_offset = 100
slave_offset = 50
port_mn = 18000
port_mx = 65535


def nodes(save=False, default=None):
    logger.debug('ask nodes')
    cli_config = config.get_cli_config()
    if not default:
        default = ['127.0.0.1']
        try:
            d = cli_config['default_nodes']
            if d:
                default = d
        except KeyError:
            pass
    result = ask(
        text='Please type host list. (separate by comma)',
        default=', '.join(default))
    result = map(lambda x: x.strip(), result.split(','))
    if save:
        cli_config['default_nodes'] = result
        config.save_cli_config(cli_config)
    logger.info('OK, {}'.format(result))
    return result


def installer():
    logger.debug('ask installer')
    path_of_cli = config.get_path_of_cli()
    release_path = path_of_cli['release_path']
    if not os.path.exists(release_path):
        os.mkdir(release_path)
    installer_list = os.listdir(release_path)
    installer_list = list(filter(lambda x: x != '.gitignore', installer_list))
    installer_list.sort(reverse=True)

    # format msg
    l = []
    for i, v in enumerate(installer_list):
        l.append('    ({index}) {name}'.format(index=i+1, name=v))
    msg = '''Select installer

    [ INSTALLER LIST ]
{}

Please enter the number or the path of the installer you want to use
you can also add file in list by copy to '$FBPATH/releases/'
    '''.format('\n'.join(l))
    if not installer_list:
        msg = '''Select installer

        [ INSTALLER LIST ]
        (empty)

Please enter the path of the installer you want to use
you can also add file in list by copy to '$FBPATH/releases/'
        '''.format()

    result = ask(msg)
    while True:
        if installer_list and unicode(result, 'utf-8').isdecimal():
            # case: select in list
            result = int(result) - 1
            if result in range(0, len(installer_list)):
                installer_path = path_join(release_path, installer_list[result])
                logger.debug('Select insaller in list: {}'.format(installer_path))
                logger.info('OK, {}'.format(installer_list[result]))
                return installer_path
            msg = [
                'Choose a number ',
                'between 1 and {}'.format(len(installer_list)),
                ', please try again'
            ]
            logger.error(''.join(msg))
        elif result.startswith(('~', '/')):
            # case: type path
            if os.path.isfile(os.path.expanduser(result)):
                logger.debug('Select insaller by path: {}'.format(result))
                logger.info('OK, {}'.format(os.path.basename(result)))
                return result
            msg = [
                "File not existed: '{}'".format(result),
                ', please try again'
            ]
            logger.error(''.join(msg))
        else:
            logger.error("Invalid input: '{}', please try again".format(result))
        result = ask('')
    

def port_range_safe(port):
    if port < port_mn:
        return False
    if port > port_mx:
        return False
    return True


def master_ports(cluster_id):
    logger.debug('ask master ports')
    q = 'How many masters would you like to create on each node?'
    m_count = int(askInt(q, default='1'))
    if m_count <= 0:
        logger.warn("The number of master must be greater than 1. try again.")
        return master_ports(cluster_id)
    logger.info('OK, {}'.format(m_count))

    start_m_ports = start_port + cluster_id * master_offset
    end_m_ports = start_m_ports + m_count - 1
    if start_m_ports == end_m_ports:
        default_m_ports = str(start_m_ports)
    else:
        default_m_ports = '{}-{}'.format(start_m_ports, end_m_ports)
    # q = 'Please type ports. Separated by comma(,) and use hyphen(-) for range.'
    q = 'Please type ports. Use hyphen(-) for range.'

    while True:
        result = ask(''.join(q), default=default_m_ports)
        result = map(lambda x: x.strip(), result.split(','))
        valid = True
        m_ports = set()
        p = re.compile('[0-9]+-[0-9]+')
        for item in result:
            # range number
            m = p.match(item)
            if m:
                s, e = map(int, item.split('-'))
                if s > e:
                    logger.error('Invalid range: {}'.format(item))
                    valid = False
                    break 
                m_ports.update(range(s, e + 1))
                continue
            # single number
            elif unicode(item).isdecimal():
                m_ports.add(int(item))
                continue
            else:
                logger.error('Invalid input: {}'.format(item))
                valid = False
                break
        if not valid:
            continue
        out_of_range = []
        for port in m_ports:
            if not port_range_safe(port):
                out_of_range.append(port)
        if out_of_range:
            logger.error('Use port between {} and {}: {}'.format(port_mn, port_mx, out_of_range))
            continue
        if len(m_ports) != m_count:
            q2 = [
                "You type count '{}' at first, ".format(m_count),
                "but now count is '{}'. ".format(len(m_ports)),
                'try again.'
            ]
            logger.error(''.join(q2))
            continue
        if valid:
            break
    m_ports = sorted(list(m_ports))
    logger.info('OK, {}'.format(result))
    return m_ports, result


def replicas(default=2):
    logger.debug('ask replicas')
    default = str(default)
    result = askInt('How many replicas would you like to create on each master?', default=default)
    if int(result) < 0:
        logger.warn("The number of master must be greater than 0. try again.")
        return replicas()
    logger.info('OK, {}'.format(result))
    return int(result)


def slave_ports(cluster_id, m_count, replicas):
    logger.debug('ask slave ports')
    s_count = m_count * replicas
    start_s_ports = start_port + cluster_id * master_offset + slave_offset
    end_s_ports = start_s_ports + s_count - 1
    if start_s_ports == end_s_ports:
        default_s_ports = str(start_s_ports)
    else:
        default_s_ports = '{}-{}'.format(start_s_ports, end_s_ports)
    # q = 'Please type ports. Separated by comma(,) and use hyphen(-) for range.'
    q = 'Please type ports. Use hyphen(-) for range.'

    while True:
        result = ask(q, default=default_s_ports)
        result = map(lambda x: x.strip(), result.split(','))
        valid = True
        s_ports = set()
        p = re.compile('[0-9]+-[0-9]+')
        for item in result:
            # range number
            m = p.match(item)
            if m:
                s, e = map(int, item.split('-'))
                if s > e:
                    logger.error('Invalid range: {}'.format(item))
                    valid = False
                    break
                s_ports.update(range(s, e + 1))
                continue
            # single number
            elif unicode(item).isdecimal():
                s_ports.add(int(item))
                continue
            else:
                logger.error('Invalid input: {}'.format(item))
                valid = False
                break
        out_of_range = []
        for port in s_ports:
            if not port_range_safe(port):
                out_of_range.append(port)
        if out_of_range:
            logger.error('Use port between {} and {}: {}'.format(port_mn, port_mx, out_of_range))
            continue
        if len(s_ports) != s_count:
            msg = [
                "You type replicas '{}' at first, ".format(replicas),
                "but now count is '{}'. ".format(len(s_ports) / float(m_count)),
                'try again.'
            ]
            logger.error(''.join(msg))
            continue
        if valid:
            break
    s_ports = sorted(list(s_ports))
    logger.info('OK, {}'.format(result))
    return s_ports, result


def ssd_count(save=True, default=3):
    logger.debug('ask ssd count')
    cli_config = config.get_cli_config()
    try:
        d = cli_config['default_ssd']
        if d:
            default = d
    except KeyError:
        pass
    default = str(default)
    result = askInt('How many sdd would you like to use?', default=default)
    if int(result) <= 0:
        logger.warn("The number of ssd must be greater than 1. try again.")
        return ssd_count(save=save)
    if save:
        cli_config['default_ssd'] = int(result)
        config.save_cli_config(cli_config)
    logger.info('OK, {}'.format(result))
    return result


def base_directory(default='~/tsr2'):
    logger.debug('ask base directory')
    result = ask('Type base directory of flashbase', default=default)
    if not result.startswith(('~', '/')):
        logger.error("Invalid path: '{}', try again".format(result))
        return base_directory()
    logger.info('OK, {}'.format(result))
    cli_config = config.get_cli_config()
    cli_config['base_directory'] = result
    config.save_cli_config(cli_config)
    return result


def prefix_of_rdp(save=True, default='~/ssd_'):
    logger.debug('ask redis data path')
    cli_config = config.get_cli_config()
    try:
        d = cli_config['prefix_redis_data_path']
        if d:
            default = d
    except KeyError:
        pass
    q = 'Type prefix of {}'
    result = ask(q.format('redis_data_path'), default=default)
    if save:
        cli_config['prefix_redis_data_path'] = result
        config.save_cli_config(cli_config)
    return result


def prefix_of_rdbp(save=True, default='~/ssd_'):
    logger.debug('ask redis db path')
    cli_config = config.get_cli_config()
    try:
        d = cli_config['prefix_redis_db_path']
        if d:
            default = d
    except KeyError:
        pass
    q = 'Type prefix of {}'
    result = ask(q.format('redis_db_path'), default=default)
    if save:
        cli_config['prefix_redis_db_path'] = result
        config.save_cli_config(cli_config)
    return result


def prefix_of_fdbp(save=True, default='~/ssd_'):
    logger.debug('ask flash db path')
    cli_config = config.get_cli_config()
    try:
        d = cli_config['prefix_flash_db_path']
        if d:
            default = d
    except KeyError:
        pass
    q = 'Type prefix of {}'
    result = ask(q.format('flash_db_path'), default=default)
    if save:
        cli_config['prefix_flash_db_path'] = result
        config.save_cli_config(cli_config)
    return result
