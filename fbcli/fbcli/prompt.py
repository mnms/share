from config import get_cur_cluster_id


def get_cli_prompt(user):
    """Return cli prompt

    :param user: user name
    :return: prompt string
    """
    cluster_id = get_cur_cluster_id()
    if cluster_id < 0:
        cluster_id = '-'
    return '{}@flashbase:{}>'.format(user, cluster_id)
    # return '%s@flashbase:%d>' % (user, cluster_id)


def get_sql_prompt(user):
    """Return sql prompt

    :param user: user name
    :return: prompt string
    """
    cluster_id = get_cur_cluster_id()
    if cluster_id < 0:
        cluster_id = '-'
    return '({}){}@flashbase:sql>'.format(cluster_id, user)
    # return '%s@flashbase:sql:%s>' % (user, cluster_id)
