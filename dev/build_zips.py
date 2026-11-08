"""Build the release zips into dist/: one per tool, and one with all of them.

Each zip holds a Parallel Tools folder to copy into a Vectorworks Plug-ins
folder, with only what the tools need to run: the object (.vso), the drawing
tool (.vst) and the tool's .py in its code folder, plus README and LICENSE.
Tool READMEs, changelogs, stubs and icons stay in the repo. The office
folders get the all-tools zip's Parallel Tools folder.
Zips of different tools merge into the same folder. Versions come from each
tool's VERSION and from versions.json, which this script also rewrites. It
stops if a tool's copy of the shared code differs from shared/.

Run with any Python 3, from the repo: python dev/build_zips.py
"""
import datetime
import json
import os
import re
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the repo (this file is in dev/)
PLUGINS = os.path.join(ROOT, 'Plug-ins', 'Parallel Tools')
DIST = os.path.join(ROOT, 'dist')
TOP = 'Parallel Tools'

# tool folder: (code file, object shell, drawing tool shell)
TOOLS = {
    'Comment Tool': ('comment_tool.py', 'Comment Tool.vso', 'Comment.vst'),
    'Revision Tool': ('revision_tool.py', 'Revision Tool.vso', 'Revision.vst'),
    'Break Line Tool': ('break_line_tool.py', 'Break Line Tool.vso', 'Breakline.vst'),
    'Planting Tool': ('planting_tool.py', 'Planting Tool.vso', 'Planting.vst'),
    'HTB Tool': ('htb_tool.py', 'HTB Tool.vso', 'HTB.vst'),
    'Truss Tool': ('truss_tool.py', 'Truss Tool.vso', 'Truss.vst'),
}


def tool_version(folder, py):
    src = open(os.path.join(PLUGINS, folder, py), encoding='utf-8').read()
    v = re.search(r"^VERSION = '([^']+)'", src, re.M).group(1)
    d = re.search(r"^VERSION_DATE = '([^']+)'", src, re.M).group(1)
    return v, d


def tool_files(folder, py, vso, vst):
    """(path on disk, path in the zip) for one tool: only what it needs to
    run, the object (.vso), the drawing tool (.vst) and the code (.py)."""
    out = []
    for shell in (vso, vst):
        p = os.path.join(PLUGINS, shell)
        if not os.path.isfile(p):
            raise SystemExit('missing ' + shell)
        out.append((p, '%s/%s' % (TOP, shell)))
    out.append((os.path.join(PLUGINS, folder, py), '%s/%s/%s' % (TOP, folder, py)))
    return out


def top_files():
    """README and LICENSE, at the top of every zip."""
    return [(os.path.join(ROOT, f), '%s/%s' % (TOP, f)) for f in ('README.md', 'LICENSE')]


def write_zip(name, files):
    path = os.path.join(DIST, name)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for src, arc in files:
            z.write(src, arc)
    print('%-40s %3d files' % (name, len(files)))


def main():
    # every tool's copy of the shared code must match shared/ (sync_shared.py)
    import sync_shared
    stale, problems = sync_shared.sync(check=True)
    if stale or problems:
        raise SystemExit('Shared code out of date: run python dev/sync_shared.py, test, then build.')
    os.makedirs(DIST, exist_ok=True)
    versions, everything = {}, []
    for folder, (py, vso, vst) in TOOLS.items():
        v, d = tool_version(folder, py)
        versions[folder] = {'version': v, 'date': d}
        files = tool_files(folder, py, vso, vst)
        everything += files
        write_zip('%s %s.zip' % (folder, v), files + top_files())
    everything += top_files()
    write_zip('Parallel Tools %s.zip' % datetime.date.today().isoformat(), everything)
    with open(os.path.join(ROOT, 'versions.json'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(versions, indent=2) + '\n')
    print('versions.json updated')


if __name__ == '__main__':
    main()
