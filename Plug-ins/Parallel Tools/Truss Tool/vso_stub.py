# Truss Tool loader. Paste this into the plug-in's script (Plug-in Manager > Edit Script).
# It finds the "Truss Tool" folder next to the .vso (user or workgroup Plug-ins) and runs
# truss_tool.py from it, reloading the module only when the file has changed.
# A vectorworks_tools_dev.txt file in the user data folder points it at a development copy.
import os
import sys
import importlib
import vs


DEV_FILE = 'vectorworks_tools_dev.txt'


def _dev_folder():
    # Dev switch: a file named vectorworks_tools_dev.txt in this Vectorworks version's user
    # data folder (or its Plug-ins folder) holding the path of the development Plug-ins
    # folder makes this machine load the code from there instead of the office copy.
    # Only the developer's machine has the file; everyone else is unaffected.
    try:
        base = str(vs.GetFolderPath(-2)).rstrip('\\/')
    except Exception:
        return None
    for d in (os.path.dirname(base), base):
        f = os.path.join(d, DEV_FILE)
        if not os.path.isfile(f):
            continue
        try:
            with open(f, encoding='utf-8-sig') as fh:
                root = fh.readline().strip().strip('"')
        except Exception:
            return None
        cand = os.path.join(root, 'Truss Tool')
        if os.path.isfile(os.path.join(cand, 'truss_tool.py')):
            return cand
    return None


def _truss_folder():
    roots = []
    for name in ('Truss Tool.vso', 'truss_tool.py'):
        ok, path = vs.FindFileInPluginFolder(name)
        if ok and path:
            roots.append(os.path.dirname(path))
    roots += list(sys.path)
    for code in (-2, 2):
        try:
            roots.append(vs.GetFolderPath(code))
        except Exception:
            pass
    for root in roots:
        for cand in (os.path.join(str(root), 'Truss Tool'), str(root)):
            if os.path.isfile(os.path.join(cand, 'truss_tool.py')):
                return cand
    return None


def _run():
    tt = sys.modules.get('truss_tool')
    if tt is None:
        folder = _dev_folder() or _truss_folder()
        if folder is None:
            vs.AlrtDialog('Truss Tool: cannot find the "Truss Tool" folder (with truss_tool.py) '
                          'next to Truss Tool.vso.')
            return
        if folder not in sys.path:
            sys.path.insert(0, folder)
        import truss_tool as tt
        tt._loaded_mtime = os.path.getmtime(tt.__file__)
    else:
        # Reload only when truss_tool.py has been edited since it was loaded.
        mtime = os.path.getmtime(tt.__file__)
        if mtime != getattr(tt, '_loaded_mtime', None):
            # Vectorworks can reset sys.path between runs: put the module's
            # folder back first, or reload cannot find it.
            folder = os.path.dirname(tt.__file__)
            if folder not in sys.path:
                sys.path.insert(0, folder)
            tt = importlib.reload(tt)
            tt._loaded_mtime = mtime
    tt.run()


_run()
