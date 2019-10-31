from __future__ import unicode_literals

user = ''
host = ''
path = ''

prompt_format = [
    ('class:username', user),
    ('class:at', '@'),
    ('class:host', host),
    ('class:colon', ':'),
    ('class:path', path),
    ('class:pound', '# '),
]

prompt_color = {
    # User input (default text).
    '': '#000000',
    # Prompt.
    'username': '#884444',
    'at': '#00aa00',
    'host': '#00ffff',
    'colon': '#000000',
    'path': 'ansicyan',
    'pound': '#00aa00',
}
