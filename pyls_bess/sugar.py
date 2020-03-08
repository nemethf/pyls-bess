# Copyright (c) 2014-2016, The Regents of the University of California.
# Copyright (c) 2016-2017, Nefeli Networks, Inc.
# Copyright (c) 2020, Felicián Németh
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# * Neither the names of the copyright holders nor the names of their
# contributors may be used to endorse or promote products derived from this
# software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

# based on bess/bessctl/sugar.py

import io
import parser
import re
import tokenize

def is_gate_expr(exp, is_ogate):
    # check if the leading/trailing whitespace characters contains '\n'
    if is_ogate:
        prefix, postfix = '1*', '+1'
    else:
        prefix, postfix = '1+', '*1'

    exp_stripped = exp.strip()
    while len(exp_stripped) > 0 and exp_stripped[-1] == '\\':
        exp_stripped = exp_stripped[:-1].strip()

    try:
        parser.expr('(%s)' % exp_stripped)
        parser.expr('%s%s%s' % (prefix, exp, postfix))
    except SyntaxError:
        return False
    else:
        return True

def replace_rarrows(s):
    # Phase 1: split the string with delimiter "->"
    # (cannot simply use .split() as lexical analysis is required)
    last_token = None
    arrows = []

    try:
        for t in tokenize.generate_tokens(io.StringIO(s).readline):
            token = t[1]
            row, col = t[2]

            if last_token == '-' and token == '>':  # Python 2.x
                # line numbers returned by tokenizer are 1-indexed...
                arrows.append((row - 1, col - 1))
            elif token == '->':  # Python 3
                arrows.append((row - 1, col))

            last_token = token

    except (tokenize.TokenError, IndentationError):
        # Source code has syntax errors, but arrows has been set
        # correctly up until now.
        pass

    segments = []
    curr_seg = []
    arrow_idx = 0

    lines = io.StringIO(s).readlines()
    line_idx = 0
    col_offset = 0

    while line_idx < len(lines):
        line = lines[line_idx]

        if arrow_idx < len(arrows):
            row, col = arrows[arrow_idx]
        else:
            row, col = None, None

        if row is None or line_idx < row:
            curr_seg.append(line[col_offset:])
            line_idx += 1
            col_offset = 0
        elif line_idx == row:
            curr_seg.append(line[col_offset:col])
            segments.append(''.join(curr_seg))
            curr_seg = []
            col_offset = col + 2
            arrow_idx += 1
        else:
            assert False
    segments.append(''.join(curr_seg))

    # Phase 2: transform output gate (:xx ->) and input gate (-> :yy) parts
    for i in range(len(segments) - 1):
        # process output gate
        seg = segments[i]
        colon_pos = seg.rfind(':')
        while colon_pos != -1:
            ogate = seg[colon_pos + 1:]

            if ogate.strip() == '':
                break

            if is_gate_expr(ogate, True):
                segments[i] = seg[:colon_pos] + ',' + ogate
                break

            colon_pos = seg.rfind(':', 0, colon_pos)

        # process input gate
        seg = segments[i + 1]
        colon_pos = seg.find(':')
        while colon_pos != -1:
            igate = seg[:colon_pos]
            if igate.strip() == '':
                break

            if is_gate_expr(igate, False):
                segments[
                    i + 1] = igate + ',' + seg[colon_pos + 1:]
                break

            colon_pos = seg.find(':', colon_pos + 1)

    return '; '.join(segments), arrows

def replace_double_colon(s):
    rows = {}
    text = ''
    for row, line in enumerate(io.StringIO(s).readlines()):
        line, cnt = re.subn(r'::', '= ', line)
        text += line
        if cnt:
            rows[row] = 1
    return text, rows


if __name__ == '__main__':
    s = """

bess.add_tc('main', policy='weighted_fair', resource='bit')

src = Source() -> rr= RoundRobin(gates=[1, 2])

for j in range(i):
    name = 'w_%2s' % j
    bess.add_tc(name,
                parent='main',
                policy='round_robin',
                share=j+1)
    q = Queue()
    q.set_size(size=32)
    q.get_status()['dequeued']
    rr:j->q
    q.attach_task(parent=name)
    q -> Sink()
"""
    print(replace_rarrows(s))
