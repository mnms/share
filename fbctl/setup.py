from setuptools import setup, find_packages


setup(
    name='fbctl',
    version='0.1.1',
    description='flashbase command line tool',
    author='dudaji',
    author_email='shhong@dudaji.com',
    url='https://github.com/mnms/share/tree/master/fbcli',
    install_requires=[
        'ask==0.0.8',
        'prompt-toolkit==2.0.7',
        'Pygments==2.3.0',
        'PyYAML==5.1.2',
        'logbook==1.5.2',
        'paramiko==2.5.0',
        'redis-py-cluster==1.3.6',
        'terminaltables==3.1.0',
        'hiredis==0.2.0',
        'retrying==1.3.3',
        'chardet==3.0.4',
        'urllib3==1.25.6',
        'certifi==2019.9.11',
        'requests==2.22.0',
        'Werkzeug==0.16.0',
        'Click==7.0',
        'PyHive==0.6.1',
        'thrift==0.11.0',
        'thrift-sasl==0.3.0',
        'fire==0.1.3'
    ],
    packages=find_packages(exclude=['tests', 'docs', 'sql']),
    python_requires='~=2.7',
    package_data={},
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'fbctl = fbctl.cli_main:main'
        ]
    },
    classifiers=[
        'Programming Language :: Python :: 2.7'
    ]
)
