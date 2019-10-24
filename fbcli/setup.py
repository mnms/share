from setuptools import setup, find_packages

setup(
    name='fbcli',
    version='0.0.1',
    description='flashbase cli',
    author='',
    author_email='',
    url='',
    download_url='',
    install_requires=[],
    packages=find_packages(exclude=['docs, tests*']),
    python_requires='~=2.7',
    entry_points={
        'console_scripts': [
            'fbcli = fbcli.cli_main:main',
        ]
    },
    classifiers=[
        'Programming Language :: Python :: 2.7'
    ]
)
