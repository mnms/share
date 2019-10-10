import os
from subprocess import call

EDITOR = os.environ.get('EDITOR', 'vim')


def edit(f, syntax=None):
    """Open editor

    :param f: file name
    """
    cmd = '{} {}'.format(EDITOR, f)
    if syntax and EDITOR == 'vim':
        cmd = '{} -c "set syntax={}"'.format(cmd, syntax)
    call(cmd, shell=True)
