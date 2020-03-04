### pyls_bess --- bess plugin for pyls      -*- coding: utf-8; -*-

## Copyright (C) 2019-2020 Felicián Németh
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import collections
import functools
import gzip
import inspect
import json
import logging
import os
import re
from pyls import hookimpl, uris
from pyls.config import config as pyls_config

from .bess_conf import BessConfig
from .sugar import replace_rarrows

log = logging.getLogger(__name__)

# Monkey patch :(
# But this way it's easier to sync with upstream, and
# config variable `bess.source_directory` can be used.
from pyls.workspace import Workspace
old_source_roots = Workspace.source_roots
def new_source_roots(self, document_path):
    path = []

    log.debug('bess new_source_roots %s', self.bess_dir)
    if self.bess_dir:
        path.append(self.bess_dir)

    path.extend(old_source_roots(self, document_path))
    return path
Workspace.source_roots = new_source_roots

from pyls.workspace import Document
old_source = Document.source
@property
def new_source(self):
    '''
    Return the source without the syntactic sugar of the bess language.

    The code returned, however, is not a .bess to .py transformation.
    It is more or less a syntactically correct python file, where
    important column and line position are not altered.  So, instead
    of transforming 'a->y:b' to 'a.connect(next_mod=b, igate=y)', it
    transforms into 'a; y,b'.
    '''

    src = old_source.fget(self)
    if not self.filename.endswith('.bess'):
        return src

    # Workspace.apply_change has this line:
    #  self._source = self.source + text
    # which modifies _source if we return the transformed source here.
    stack = inspect.stack()
    if stack[2].function == 'apply_change':
        return src

    import_line = 'from pyls_bess.bess_doc.mclass import *'
    if getattr(self, 'prepend_import_to_source', False):
        # Insert an extra line and adjust line numbers later with
        # fix_offset().
        src = import_line + "\n" + src
    elif not src.startswith(import_line):
        # Modify the first line, because we cannot adjust the line
        # numbers later (e.g. in case of mypy.)  This might result in
        # incorrect column numbers for the first line.
        src = import_line + '; ' + src
    src = re.sub(r'\$\w(\w*)!', "'\\1'+", src)
    src = src.replace('::', '= ')
    src = replace_rarrows(src)
    return src
Document.source = new_source

old_jedi_script = Document.jedi_script
def new_jedi_script(self, position=None):
    try:
        new_position = position
        if self.filename.endswith('.bess'):
            self.prepend_import_to_source = True
            if position:
                new_position = position.copy()
                new_position['line'] += 1
        return old_jedi_script(self, new_position)
    finally:
        self.prepend_import_to_source = False
Document.jedi_script = new_jedi_script

###########################################################################

@hookimpl
def pyls_settings(config):
    default = pyls_config.DEFAULT_CONFIG_SOURCES
    sources = config._settings.get('configurationSources', default)
    sources.append('bess')
    config._settings['configurationSources'] = sources

    config._config_sources['bess'] = BessConfig(config._root_path)

    # We cannot set the defaults in config.py, because that
    # would overwrite user level configuration.  See:
    # ../config/config.py:107
    return {'plugins': {'bess': {}}}

@hookimpl
def pyls_initialize(config, workspace):
    workspace.bess_dir = get_spath(config)
    log.debug('pyls_initialize bess_dir: %s', workspace.bess_dir)

@hookimpl(hookwrapper=True)
def pyls_definitions(config, document, position):
    outcome = yield
    process_refs(config, document, 'definitions', outcome)

@hookimpl(hookwrapper=True)
def pyls_references(config, document, position, exclude_declaration=False):
    outcome = yield
    process_refs(config, document, 'references', outcome)

@hookimpl(hookwrapper=True)
def pyls_document_highlight(config, document, position):
    outcome = yield
    process_refs(config, document, 'highlight', outcome)

def fix_offset(d, document=None):
    if d.get('uri', document.uri).endswith('.bess'):
        d['range']['start']['line'] -= 1
        d['range']['end']['line'] -= 1
    return d

def process_refs(config, document, goto_kind, outcome):
    defs = []
    try:
        result = outcome.get_result()
    except Exception as e:
        log.warn("No results: %s, %s", e, outcome.excinfo)
        return

    for l in result:
        defs.extend( [fix_offset(d, document) for d in l] )

    if goto_kind != 'highlight':
        defs = insert_bess_refs(config, document, goto_kind, defs)

    outcome.force_result([defs])

def get_spath(config, document=None, filename=None):
    document_path = document and document.path
    settings = config.plugin_settings('bess', document_path=document_path)
    bess_dir = os.environ.get('BESS', '')
    bess_dir = settings.get('source_directory', bess_dir)
    bess_dir = os.path.abspath(bess_dir)
    if filename:
        return os.path.join(bess_dir, filename)
    return bess_dir

def get_mpath(filename=None):
    p = os.path
    path = p.realpath(p.join(p.dirname(__file__), 'bess_doc'))
    if filename:
        return p.join(path, filename)
    return path

db = {}
def get_mclass_db():
    global db
    if not db:
        with gzip.open(get_mpath('mclass.min.json.gz')) as f:
            db = json.load(f)
        msg_full = {m['fullName']: m for m in db['msg']}
        msg_short = {m['name']: m for m in db['msg']}
        db['msg'] = msg_short
        db['msg_full'] = msg_full
    return db

def get_ref_types(config, document, goto_kind):
    settings = config.plugin_settings('bess', document_path=document.path)
    ref_types = settings.get(goto_kind)
    if not ref_types:
        # Should keep this synchronized with
        # ../package.json
        defaults = {
            'definitions': [
                "project",
                "cpp_definition",
            ],
            'references': [
                "project",
                "cpp_definition",
                "mclass",
                "protobuf",
                "examples",
            ],
        }
        ref_types = defaults.get(goto_kind, [])
    log.warn("Settings for '%s': %s", goto_kind, ref_types)
    return ref_types

def make_abs_bess_filename(config, document, filename):
    if type(filename) == int:
        db = get_mclass_db()
        if filename == 0:
            filename = get_mpath(db['files'][str(filename)])
        else:
            filename = db['files'][str(filename)]
    if os.path.isabs(filename):
        return filename
    return get_spath(config, document, filename)

def conv_loc(config, document, loc):
    if not loc:
        return
    path = make_abs_bess_filename(config, document, loc['file'])
    return {
        'uri': uris.uri_with(document.uri, path=path),
        'range': {
            'start': {'line': loc['line'] - 1, 'character': 0},
            'end': {'line': loc['line'] - 1, 'character': 0}
        }
    }

def insert_bess_refs(config, document, goto_kind, refs):
    ref_groups = collections.defaultdict(list)
    mclass_uri = uris.uri_with(document.uri,
                               path=get_mpath('mclass.py'))
    db = get_mclass_db()
    for ref in refs:
        if not (ref['uri'] == mclass_uri):
            ref_groups['project'].append(ref)
            continue
        ref_groups['mclass'].append(ref)
        mline = ref['range']['start']['line']
        for mclass in db['mclass']:
            for cmd in [mclass] + mclass['cmds']:
                if mline == cmd.get('line', 0) - 1:
                    break
            else:
                continue

            ref = conv_loc(config, document, cmd['definition'])
            ref_groups['cpp_definition'].append(ref)

            loc = db['msg'].get(cmd['arg'], {})
            ref = conv_loc(config, document, loc)
            ref_groups['protobuf'].append(ref)

            loc = db['msg_full'].get(cmd.get('return'))
            ref = conv_loc(config, document, loc)
            if ref and ref not in ref_groups['protobuf']:
                ref_groups['protobuf'].append(ref)

            for loc in cmd.get('examples', []):
                ref = conv_loc(config, document, loc)
                ref_groups['examples'].append(ref)

    refs = []
    for ref_type in get_ref_types(config, document, goto_kind):
        refs += ref_groups[ref_type]
    return refs


###########################################################################

# Because of the hidden 'import_line', pyflakes_lint becomes quite
# useless.  Fix it by filtering error messages about star import.

try:
    import pyflakes.messages
    PYFLAKES_IGNORED_MESSAGES = (
        pyflakes.messages.ImportStarUsed,
        pyflakes.messages.ImportStarUsage,
    )
except ModuleNotFoundError:
    PYFLAKES_IGNORED_MESSAGES = ()

from pyls.plugins.pyflakes_lint import PyflakesDiagnosticReport as DiagReport
old_flake = DiagReport.flake
def new_flake(self, message):
    if not message.filename.endswith('.bess'):
        return old_flake(self, message)

    for message_type in PYFLAKES_IGNORED_MESSAGES:
        if isinstance(message, message_type):
            break
    else:
        old_flake(self, message)
DiagReport.flake = new_flake
