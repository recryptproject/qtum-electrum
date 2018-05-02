#!/usr/bin/env python3

# python setup.py sdist --format=zip,gztar

import argparse
import imp
import os
import platform
import sys
from setuptools import setup

with open('./requirements.txt') as f:
    requirements = f.read().splitlines()

version = imp.load_source('version', 'lib/version.py')

if sys.version_info[:3] < (3, 4, 0):
    sys.exit("Error: Electrum requires Python version >= 3.4.0...")

data_files = []

if platform.system() in ['Linux', 'FreeBSD', 'DragonFly']:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root=', dest='root_path', metavar='dir', default='/')
    opts, _ = parser.parse_known_args(sys.argv[1:])
    usr_share = os.path.join(sys.prefix, "share")
    icons_dirname = 'pixmaps'
    if not os.access(opts.root_path + usr_share, os.W_OK) and \
       not os.access(opts.root_path, os.W_OK):
        icons_dirname = 'icons'
        if 'XDG_DATA_HOME' in os.environ.keys():
            usr_share = os.environ['XDG_DATA_HOME']
        else:
            usr_share = os.path.expanduser('~/.local/share')
    data_files += [
        (os.path.join(usr_share, 'applications/'), ['recrypt-electrum.desktop']),
        (os.path.join(usr_share, icons_dirname), ['icons/electrum.png'])
    ]

setup(
    name="Recrypt Electrum",
    version=version.ELECTRUM_VERSION,
    install_requires=requirements,
    packages=[
        'recrypt_electrum',
        'recrypt_electrum_gui',
        'recrypt_electrum_gui.qt',
        'recrypt_electrum_plugins',
        'recrypt_electrum_plugins.audio_modem',
        'recrypt_electrum_plugins.email_requests',
        'recrypt_electrum_plugins.greenaddress_instant',
        'recrypt_electrum_plugins.hw_wallet',
        'recrypt_electrum_plugins.keepkey',
        'recrypt_electrum_plugins.labels',
        'recrypt_electrum_plugins.ledger',
        'recrypt_electrum_plugins.trezor',
        'recrypt_electrum_plugins.digitalbitbox',
        'recrypt_electrum_plugins.trustedcoin',
        'recrypt_electrum_plugins.virtualkeyboard',
    ],
    package_dir={
        'recrypt_electrum': 'lib',
        'recrypt_electrum_gui': 'gui',
        'recrypt_electrum_plugins': 'plugins',
    },
    package_data={
        'recrypt_electrum': [
            'currencies.json',
            'www/index.html',
            'wordlist/*.txt',
            'locale/*/LC_MESSAGES/electrum.mo',
            'servers.json',
            'servers_testnet.json',
        ]
    },
    scripts=['recrypt-electrum'],
    data_files=data_files,
    description="Lightweight Recrypt Wallet",
    author="CodeFace",
    author_email="codeface@recrypt.org",
    license="MIT Licence",
    url="https://recrypt.org",
    long_description="""Lightweight Recrypt Wallet"""
)
