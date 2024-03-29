import os
from os.path import join as path_join
import re

from ask import askBool, askInt, askPassword, ask

from log import logger
import config

START_PORT = 18000
MASTER_OFFSET = 100
SLAVE_OFFSET = 50
PORT_MININUM = 18000
PORT_MAXIMUM = 65535


def nodes(save, default=None):
    logger.debug('ask hosts')
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
        text='Please type host list separated by comma(,)',
        default=', '.join(default))
    result = map(lambda x: x.strip(), result.split(','))
    if save:
        cli_config['default_nodes'] = result
        config.save_cli_config(cli_config)
    logger.info('OK, {}'.format(result))
    return result


def hosts(save, default=None):
    logger.debug('ask host')
    deploy_history = config.get_deploy_history()
    if not default:
        default = deploy_history['hosts']
    q = 'Please type host list separated by comma(,)'
    result = ask(q, default=', '.join(default))
    result = map(lambda x: x.strip(), result.split(','))
    if save:
        deploy_history['hosts'] = result
        config.save_deploy_history(deploy_history)
    logger.info('OK, {}'.format(result))
    return result


def installer():
    '''
    Select installer from list of '$FBPATH/releases'
    or input absolute path of file directly
    return installer path
    '''
    logger.debug('ask installer')
    path_of_cli = config.get_path_of_cli(None)
    release_path = path_of_cli['release_path']
    if not os.path.exists(release_path):
        os.mkdir(release_path)
    installer_list = os.listdir(release_path)
    installer_list = list(filter(lambda x: x != '.gitignore', installer_list))
    installer_list.sort(reverse=True)

    # formatting msg
    formatted = []
    for i, name in enumerate(installer_list):
        formatted.append('    ({index}) {name}'.format(index=i+1, name=name))
    msg = [
        'Select installer',
        '',
        '    [ INSTALLER LIST ]',
        '{}\n'.format('\n'.join(formatted)),
        'Please enter the number or the path of the installer you want to use',
        "you can also add file in list by copy to '$FBPATH/releases/'",
    ]
    if not installer_list:
        msg = [
            'Select installer',
            '',
            '    [ INSTALLER LIST ]',
            '    (empty)\n\n'
            'Please enter the path of the installer you want to use',
            "you can also add file in list by copy to '$FBPATH/releases/'",
        ]

    result = ask('\n'.join(msg))
    while True:
        if installer_list and result.decode('utf-8').isdecimal():
            # case: select in list
            result = int(result) - 1
            if result in range(0, len(installer_list)):
                ret = path_join(release_path, installer_list[result])
                logger.debug('Select insaller in list: {}'.format(ret))
                logger.info('OK, {}'.format(installer_list[result]))
                return os.path.expanduser(ret)
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
                return os.path.expanduser(result)
            msg = [
                "File not existed: '{}'".format(result),
                ', please try again'
            ]
            logger.error(''.join(msg))
        else:
            msg = [
                "Invalid input: '{}', ".format(result),
                "please try again",
            ]
            logger.error(''.join(msg))
        result = ask('')


def port_range_safe(port):
    if port < PORT_MININUM:
        return False
    if port > PORT_MAXIMUM:
        return False
    return True


def master_ports(save, cluster_id, default_count=None):
    logger.debug('ask master ports')
    deploy_history = config.get_deploy_history()
    if not default_count:
        default_count = deploy_history['master_count']
    q = 'How many masters would you like to create on each host?'
    m_count = int(askInt(q, default=str(default_count)))
    if m_count <= 0:
        logger.warn("The number of master must be greater than 0. try again.")
        return master_ports(cluster_id, default_count)
    logger.info('OK, {}'.format(m_count))
    if save:
        deploy_history['master_count'] = m_count
        config.save_deploy_history(deploy_history)

    start_m_ports = START_PORT + cluster_id * MASTER_OFFSET
    end_m_ports = start_m_ports + m_count - 1
    if start_m_ports == end_m_ports:
        default_m_ports = str(start_m_ports)
    else:
        default_m_ports = '{}-{}'.format(start_m_ports, end_m_ports)

    q = [
        'Please type ports separate with comma(,) ',
        'and use hyphen(-) for range.',
    ]
    while True:
        result = ask(''.join(q), default=default_m_ports)
        result = map(lambda x: x.strip(), result.split(','))
        valid = True
        m_ports = set()
        pattern = re.compile('[0-9]+-[0-9]+')
        for item in result:
            # range number
            matched = pattern.match(item)
            if matched:
                s, e = map(int, item.split('-'))
                if s > e:
                    logger.error('Invalid range: {}'.format(item))
                    valid = False
                    break
                m_ports.update(range(s, e + 1))
                continue
            # single number
            elif item.decode('utf-8').isdecimal():
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
            msg = 'Use port between {} and {}: {}'.format(
                PORT_MININUM,
                PORT_MAXIMUM,
                out_of_range,
            )
            logger.error(msg)
            continue
        if valid and len(m_ports) != m_count:
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
    return m_ports


def replicas(save, default=None):
    logger.debug('ask replicas')
    deploy_history = config.get_deploy_history()
    if not default:
        default = deploy_history['replicas']
    q = 'How many replicas would you like to create on each master?'
    result = int(askInt(q, default=str(default)))
    if result < 0:
        msg = [
            'The number of master must be greater than or equal to 0.',
            'try again.',
        ]
        logger.error(' '.join(msg))
        return replicas(save, default=default)
    if save:
        deploy_history['replicas'] = result
        config.save_deploy_history(deploy_history)
    logger.info('OK, {}'.format(result))
    return result


def slave_ports(cluster_id, m_count, replicas_count):
    logger.debug('ask slave ports')
    if replicas_count <= 0:
        logger.debug('return empty list')
        return []
    s_count = m_count * replicas_count
    start_s_ports = START_PORT + (cluster_id * MASTER_OFFSET) + SLAVE_OFFSET
    end_s_ports = start_s_ports + s_count - 1
    if start_s_ports == end_s_ports:
        default_s_ports = str(start_s_ports)
    else:
        default_s_ports = '{}-{}'.format(start_s_ports, end_s_ports)
    q = [
        'Please type ports separate with comma(,) ',
        'and use hyphen(-) for range.',
    ]

    while True:
        result = ask(''.join(q), default=default_s_ports)
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
            elif item.decode('utf-8').isdecimal():
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
            logger.error('Use port between {} and {}: {}'.format(PORT_MININUM, PORT_MAXIMUM, out_of_range))
            continue
        if valid and len(s_ports) != s_count:
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
    return s_ports


def ssd_count(save, default=None):
    logger.debug('ask ssd count')
    deploy_history = config.get_deploy_history()
    if not default:
        default = deploy_history['ssd_count']
    q = 'How many sdd would you like to use?'
    result = int(askInt(q, default=str(default)))
    if result <= 0:
        logger.warn("The number of ssd must be greater than 0. try again.")
        return ssd_count(save=save, default=default)
    if save:
        deploy_history['ssd_count'] = result
        config.save_deploy_history(deploy_history)
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


def prefix_of_rd(save, default=None):
    logger.debug('ask redis data path')
    deploy_history = config.get_deploy_history()
    if not default:
        default = deploy_history['prefix_of_rd']
    q = 'Type prefix of {}'
    result = ask(q.format('redis_data'), default=default)
    if save:
        deploy_history['prefix_of_rd'] = result
        config.save_deploy_history(deploy_history)
    logger.info('OK, {}'.format(result))
    return result


def prefix_of_rdbp(save, default=None):
    logger.debug('ask redis db path')
    deploy_history = config.get_deploy_history()
    if not default:
        default = deploy_history['prefix_of_rdbp']
    q = 'Type prefix of {}'
    result = ask(q.format('redis_db_path'), default=default)
    if save:
        deploy_history['prefix_of_rdbp'] = result
        config.save_deploy_history(deploy_history)
    logger.info('OK, {}'.format(result))
    return result


def prefix_of_fdbp(save, default=None):
    logger.debug('ask flash db path')
    deploy_history = config.get_deploy_history()
    if not default:
        default = deploy_history['prefix_of_fdbp']
    q = 'Type prefix of {}'
    result = ask(q.format('flash_db_path'), default=default)
    if save:
        deploy_history['prefix_of_fdbp'] = result
        config.save_deploy_history(deploy_history)
    logger.info('OK, {}'.format(result))
    return result


def props(cluster_id, save):
    ret = {}
    ret['hosts'] = hosts(save)
    m_ports = master_ports(save, cluster_id)
    ret['master_ports'] = m_ports
    ret['replicas'] = replicas(save)
    m_count = len(m_ports)
    s_ports = slave_ports(cluster_id, m_count, ret['replicas'])
    ret['slave_ports'] = s_ports
    ret['ssd_count'] = int(ssd_count(save))
    ret['prefix_of_rdp'] = prefix_of_rd(save)
    ret['prefix_of_rdbp'] = prefix_of_rdbp(save)
    ret['prefix_of_fdbp'] = prefix_of_fdbp(save)
    return ret
