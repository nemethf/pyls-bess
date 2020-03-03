#!/usr/bin/env python
#                                             -*- coding: utf-8; -*-
from setuptools import find_packages, setup

README = open('README.md', 'r').read()

setup(
    name='pyls-bess',
    version="0.0.1",
    description='Bess Support for pyls',
    long_description=README,
    long_description_content_type="text/markdown",
    url='https://github.com/nemethf/pyls-bess',
    author='Felicián Németh',
    packages=find_packages(exclude=['resources']),
    install_requires=['python-language-server'],
    extras_require={},
    entry_points={'pyls': ['pyls_bess = pyls_bess.plugin']},
    include_package_data=True,
    package_data={'bess_doc': ['pyls_bess/bess_doc/*']},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
    ],
)
