#!/usr/bin/env python3
from setuptools import setup

setup(
    name='rebalance-lnd',
    version='2.3',
    description='A script that can be used to balance lightning channels of a LND node',
    author='Carsten Otto',
    author_email='bitcoin@c-otto.de',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3'
        ],
    keywords='lightning, lnd, bitcoin',
    python_requires='>=3.6, <4',
    entry_points={
        'console_scripts' : ['rebalance-lnd=rebalance:main']
        },
    project_urls={
        'Source' : 'https://github.com/C-Otto/rebalance-lnd'
        }
)
