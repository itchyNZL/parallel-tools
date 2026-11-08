"""Copy the shared code blocks into every tool.

Each tool's .py stays one file, so a tool can be handed out on its own. Code
used by more than one tool is kept once in dev/shared/<name>.py and copied into
each tool between these lines:

    # shared begin <name>
    ...
    # shared end <name>

Edit dev/shared/<name>.py, never the copy in a tool, then run:

    python dev/sync_shared.py           write the blocks into every tool
    python dev/sync_shared.py --check   only report tools whose copy differs (exit 1)

build_zips.py runs the check, so a release can't go out with an old copy.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent     # the repo (this file is in dev/)
SHARED = ROOT / 'dev' / 'shared'
PLUGINS = ROOT / 'Plug-ins' / 'Parallel Tools'
BLOCK = re.compile(r'^# shared begin (\S+)\n(.*?)^# shared end \1\n', re.S | re.M)


def masters():
    out = {}
    for p in sorted(SHARED.glob('*.py')):
        text = p.read_text(encoding='utf-8').replace('\r\n', '\n')
        out[p.stem] = text if text.endswith('\n') else text + '\n'
    return out


def tool_files():
    return sorted(PLUGINS.glob('*/*_tool.py'))


def sync(check=False):
    blocks = masters()
    stale, problems = [], []
    for path in tool_files():
        raw = path.read_bytes().decode('utf-8')
        crlf = '\r\n' in raw
        text = raw.replace('\r\n', '\n')
        found = []

        def put(m):
            name = m.group(1)
            found.append(name)
            if name not in blocks:
                problems.append('%s: no dev/shared/%s.py' % (path.relative_to(ROOT), name))
                return m.group(0)
            return '# shared begin %s\n%s# shared end %s\n' % (name, blocks[name], name)

        new = BLOCK.sub(put, text)
        begins = re.findall(r'^# shared begin (\S+)$', text, re.M)
        if sorted(begins) != sorted(found):
            problems.append('%s: a shared begin line has no matching end line'
                            % path.relative_to(ROOT))
            continue
        if new != text:
            stale.append(path)
            if not check:
                out = new.replace('\n', '\r\n') if crlf else new
                tmp = path.with_suffix('.py.tmp')
                tmp.write_bytes(out.encode('utf-8'))
                tmp.replace(path)
        print('%-45s %s%s' % (path.relative_to(PLUGINS), ', '.join(found) or '(no blocks)',
                              '  <- out of date' if new != text else ''))
    for p in problems:
        print('PROBLEM', p)
    return stale, problems


if __name__ == '__main__':
    check = '--check' in sys.argv
    stale, problems = sync(check)
    if problems or (check and stale):
        if check and stale:
            print('Out of date: run python dev/sync_shared.py')
        sys.exit(1)
    print('Checked.' if check else 'Done.')
