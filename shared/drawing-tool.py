# --- Drawing tool (the .vst) ----------------------------------------------
# The object's own tool shows only the spanner, never a Style list, so this
# tool places the object instead, with a Style pull-down on the tool bar (as
# Comment and Revision). Vectorworks collects the clicks and draws the preview
# (vstSetPtBehavior); the tool turns them into an object and gives it the
# chosen style. The spanner sets the values new objects start with; the tool's
# own pull-downs (e.g. HTB's Side) set one of them from the tool bar.
#
# Set up for each tool above this block:
#   TOOL_OBJECT     the object's name (its plug-in and record name)
#   TOOL_NAME       the drawing tool's name, for messages
#   TOOL_MODES      ((icon, vstSetPtBehavior, help text), ...); radio buttons if more than one
#   TOOL_PULLDOWNS  ((label, field, choices), ...): tool bar pull-downs that set a field
#   TOOL_DEFAULTS   ((field, label, 'num' / 'text' / choices), ...): the spanner's
#                   Default Settings window; () for none
#   tool_complete(mode, pts, h)  makes the object from the clicks; the block
#                   deletes the tool's own object h afterwards
# and optionally:
#   TOOL_FIRST_MODE the mode before one has been picked (default 1)
#   tool_spanner()  the tool's own spanner dialog, instead of Default Settings
# The tool's choices are kept in <tool object>_prefs.json beside Vectorworks'
# own settings; saving merges into the file, so a tool's own preferences can
# share it. Event numbers: Vectorworks SDK. Logs with _log (common block).

kToolSetUp = 3
kToolMode = 7
kToolComplete = 104
UNSTYLED = '<Unstyled>'
PREFS_ICON = 'Vectorworks/ModeViewBar/Options.svg'
AS_PLUGIN = '(as the plug-in)'

# Kept while Vectorworks has this module loaded (the loader stub caches it).
# A tool may keep its own entries here too.
_tool = {'mode': 1, 'styles': [UNSTYLED]}

def _tool_prefs_path():
    import os
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    name = TOOL_OBJECT.lower().replace(' ', '_') + '_prefs.json'
    return os.path.join(base, 'Nemetschek', 'Vectorworks', name)


def load_tool_prefs():
    """{'Style': '', 'Mode': 0, 'Defaults': {field: value}}, remembered per
    user between sessions. Mode 0: none picked yet."""
    import json
    prefs = {'Style': '', 'Mode': 0, 'Defaults': {}}
    try:
        with open(_tool_prefs_path(), encoding='utf-8') as f:
            saved = json.load(f)
        for k in prefs:
            if k in saved:
                prefs[k] = saved[k]
    except Exception:
        pass
    if not isinstance(prefs.get('Defaults'), dict):
        prefs['Defaults'] = {}
    return prefs


def save_tool_prefs(prefs):
    """Merged into the file, keeping anything else in it (Comment and
    Revision keep their own preferences in the same file)."""
    import json
    import os
    path = _tool_prefs_path()
    try:
        with open(path, encoding='utf-8') as f:
            saved = json.load(f)
        if not isinstance(saved, dict):
            saved = {}
    except Exception:
        saved = {}
    saved.update(prefs)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(saved, f, indent=1)
    except Exception:
        pass


def plugin_styles():
    """Names of this object's plug-in styles in the file: symbol definitions
    whose object is a TOOL_OBJECT."""
    names = []
    try:
        list_id, n = vs.BuildResourceList(16, 0, '')
    except Exception:
        return names
    for i in range(1, n + 1):
        try:
            name = vs.GetNameFromResourceList(list_id, i)
            sd = vs.GetObject(name)
            obj = vs.FInSymDef(sd) if sd else None
            while obj:
                if vs.GetTypeN(obj) == 86:
                    rec = vs.GetParametricRecord(obj)
                    if rec and vs.GetName(rec) == TOOL_OBJECT:
                        names.append(name)
                    break
                obj = vs.NextObj(obj)
        except Exception:
            continue
    return sorted(names, key=str.lower)


def _style_group():
    # mode groups are numbered in the order added: the radio modes, Style, the
    # tool's own pull-downs (TOOL_PULLDOWNS), then the spanner
    return 2 if len(TOOL_MODES) > 1 else 1


def _pulldown_group(k):
    return _style_group() + 1 + k


def _prefs_group():
    return _style_group() + 1 + len(TOOL_PULLDOWNS)


def menu_pick(msg2, n):
    """The item picked in a tool bar pull-down, counted from 0, or None.
    Vectorworks sends (item shown before << 16) | item picked, both counted
    from 0, and vstSetPDMenuSel counts from 0 too (HTB tool log, 2026-11-08:
    North, the first item, came as 0 and was ignored, and every other pick
    saved the item above it)."""
    if isinstance(msg2, int) and msg2 >= 0:
        i = msg2 & 0xFFFF
        if i < n:
            return i
    return None


def _style_menu():
    styles = [UNSTYLED] + plugin_styles()
    _tool['styles'] = styles
    current = str(load_tool_prefs().get('Style', '')).strip() or UNSTYLED
    vs.vstAddPDMenuMode('Style:')
    for name in styles:
        vs.vstAddPDMenuItem(_style_group(), name)
    vs.vstSetPDMenuSel(_style_group(), styles.index(current) if current in styles else 0)


def _style_chosen(msg2):
    styles = _tool.get('styles') or [UNSTYLED]
    if len(styles) < 2:
        # A new release of this file reloads it mid-session and the list
        # is lost, while Vectorworks keeps the menu: rebuild it as
        # _style_menu did.
        styles = [UNSTYLED] + plugin_styles()
    i = menu_pick(msg2, len(styles))
    if i is not None:
        name = styles[i]
        prefs = load_tool_prefs()
        prefs['Style'] = '' if name == UNSTYLED else name
        save_tool_prefs(prefs)
        _log('style', repr(name))


def tool_defaults():
    """The values new objects start with: the spanner's, and each tool bar
    pull-down's (its first choice until one is picked)."""
    d = dict(load_tool_prefs()['Defaults'])
    for _label, field, choices in TOOL_PULLDOWNS:
        if d.get(field) not in choices:
            d[field] = choices[0]
    return d


def _save_defaults(changes):
    prefs = load_tool_prefs()
    d = dict(prefs['Defaults'])
    for field, value in changes.items():
        if value == '':
            d.pop(field, None)
        else:
            d[field] = value
    prefs['Defaults'] = d
    save_tool_prefs(prefs)


def _pulldown_menus():
    current = tool_defaults()
    for k, (label, field, choices) in enumerate(TOOL_PULLDOWNS):
        g = _pulldown_group(k)
        vs.vstAddPDMenuMode(label)
        for c in choices:
            vs.vstAddPDMenuItem(g, c)
        vs.vstSetPDMenuSel(g, choices.index(current[field]))


def _pulldown_chosen(k, msg2):
    _label, field, choices = TOOL_PULLDOWNS[k]
    i = menu_pick(msg2, len(choices))
    if i is not None:
        _save_defaults({field: choices[i]})
        _log('pull-down', field, '=', choices[i])


def _spanner():
    """What the spanner opens: the tool's own tool_spanner() if it has one,
    otherwise Default Settings when TOOL_DEFAULTS is set, otherwise None (no
    spanner)."""
    own = globals().get('tool_spanner')
    if callable(own):
        return own
    return defaults_dialog if TOOL_DEFAULTS else None


def defaults_dialog():
    """The spanner: what new objects start with. Blank or AS_PLUGIN leaves the
    plug-in's own default; a style's own values still win."""
    if not TOOL_DEFAULTS:
        return
    d = dict(load_tool_prefs()['Defaults'])
    dlg = vs.CreateLayout('%s Default Settings' % TOOL_NAME, False, 'OK', 'Cancel')
    n = len(TOOL_DEFAULTS)
    for i, (field, label, kind) in enumerate(TOOL_DEFAULTS):
        vs.CreateStaticText(dlg, 100 + i, label + ':', 24)
        if isinstance(kind, (tuple, list)):
            vs.CreatePullDownMenu(dlg, 200 + i, 18)
        else:
            vs.CreateEditText(dlg, 200 + i, str(d.get(field, '')), 18)
    vs.CreateStaticText(dlg, 99, "Blank: the plug-in's own default. A style's own values still win.", -1)
    vs.SetFirstLayoutItem(dlg, 100)
    for i in range(n):
        vs.SetRightItem(dlg, 100 + i, 200 + i, 0, 0)
        if i:
            vs.SetBelowItem(dlg, 99 + i, 100 + i, 0, 0)
    vs.SetBelowItem(dlg, 99 + n, 99, 0, 1)
    result = {}

    def options(kind):
        return [AS_PLUGIN] + list(kind)

    def handler(item, data):
        if item == 12255:
            for i, (field, _label, kind) in enumerate(TOOL_DEFAULTS):
                if isinstance(kind, (tuple, list)):
                    opts = options(kind)
                    for j, o in enumerate(opts):
                        vs.AddChoice(dlg, 200 + i, o, j)
                    cur = str(d.get(field, ''))
                    vs.SelectChoice(dlg, 200 + i, opts.index(cur) if cur in opts else 0, True)
        elif item == 1:
            for i, (field, _label, kind) in enumerate(TOOL_DEFAULTS):
                if isinstance(kind, (tuple, list)):
                    opts = options(kind)
                    r = vs.GetSelectedChoiceInfo(dlg, 200 + i, 0)
                    idx = r[0] if isinstance(r, tuple) else r
                    v = opts[idx] if isinstance(idx, int) and 0 <= idx < len(opts) else AS_PLUGIN
                    result[field] = '' if v == AS_PLUGIN else v
                else:
                    txt = vs.GetItemText(dlg, 200 + i).strip()
                    if txt and kind == 'num':
                        ok, num = vs.ValidNumStr(txt)
                        txt = ('%.6f' % num).rstrip('0').rstrip('.') if ok else ''
                    result[field] = txt
        return item

    if vs.RunLayoutDialog(dlg, handler) == 1:
        _save_defaults(result)
        _log('defaults', load_tool_prefs()['Defaults'])


def _tool_mode():
    try:
        v = int(vs.vstGetModeValue(1))
        if 1 <= v <= len(TOOL_MODES):
            _tool['mode'] = v
    except Exception:
        pass
    return _tool['mode']


def _apply_mode(mode):
    _icon, behaviour, help_text = TOOL_MODES[mode - 1]
    vs.vstSetPtBehavior(behaviour)
    vs.vstSetHelpString(help_text)


def _origin_shift():
    """On a sheet layer Vectorworks places what a script creates shifted by
    the file's user origin less the sheet layer's own origin (Comment Tool
    0.20.8); (0, 0) on a design layer."""
    try:
        r = vs.GetSheetLayerUserOrigin(vs.ActLayer())
    except Exception:
        r = None
    if not (r and r[0]):
        return 0.0, 0.0
    dx = dy = 0.0
    for fn in ('GetOriginInDocUnits', 'GetOrigin'):
        try:
            x, y = getattr(vs, fn)()[:2]
            dx, dy = float(x), float(y)
            break
        except Exception:
            continue
    return dx - float(r[1]), dy - float(r[2])


def _clicked_points():
    """Every point clicked with the tool, shifted back by _origin_shift, with
    repeats (a double-click) dropped."""
    pts = []
    try:
        n = int(vs.vstNumPts())
    except Exception:
        n = 0
    sx, sy = _origin_shift()
    for i in range(n):
        try:
            r = vs.vstGetPt2D(i, True)
        except Exception:
            continue
        nums = [v for v in (r if isinstance(r, tuple) else ()) if isinstance(v, float)]
        if len(nums) >= 2:
            q = (nums[0] - sx, nums[1] - sy)
            if not pts or math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) > 1e-9:
                pts.append(q)
    return pts


def _tool_object_points(h):
    """Outline points of the object Vectorworks drew for the tool (freehand)."""
    pts = []
    tmp = None
    try:
        tmp = vs.ConvertToPolygon(h, 32)            # a new polygon; h is kept
        if tmp:
            pts = [tuple(vs.GetPolyPt(tmp, i)) for i in range(1, vs.GetVertNum(tmp) + 1)]
    except Exception:
        pass
    finally:
        if tmp and tmp != h:
            try:
                vs.DelObject(tmp)
            except Exception:
                pass
    if len(pts) > 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-9:
        pts.pop()
    return pts


def styled_new(obj):
    """The tool's defaults and chosen style onto a new object, then its first
    reset. The style comes second, so its own values win."""
    if not obj:
        return obj
    for field, value in tool_defaults().items():
        try:
            vs.SetRField(obj, TOOL_OBJECT, field, str(value))
        except Exception:
            pass
    apply_tool_style(obj, str(load_tool_prefs().get('Style', '')).strip())
    vs.ResetObject(obj)
    return obj


def apply_tool_style(obj, style):
    """The style onto a new object: named, its By Style list set on first
    use, then its By Style values copied across. SetPluginStyle only names
    the style: the object keeps the plug-in's defaults until the style is
    chosen again in Object Info (Planting 0.11.0: a Plants style drew a
    Band), so the values are copied before the first redraw."""
    if not (obj and style):
        return
    try:
        ok = vs.SetPluginStyle(obj, style)
        _log('style', repr(style), ok)
        if ok is False:
            return
        ensure_style_map(obj)
        _copy_style_values(obj, style)
    except Exception:
        import traceback
        _log(traceback.format_exc())


def _style_object(style):
    """The style's symbol definition and the plug-in object inside it."""
    sd = vs.GetObject(style)
    obj = vs.FInSymDef(sd) if sd else None
    while obj:
        if vs.GetTypeN(obj) == 86:
            return sd, obj
        obj = vs.NextObj(obj)
    return sd, None


def _copy_style_values(obj, style):
    """The style's By Style values onto obj."""
    sd, src = _style_object(style)
    if not src:
        _log('style', repr(style), 'has no plug-in object')
        return
    fmt = vs.GetObject(TOOL_OBJECT)
    copied = 0
    for i in range(1, vs.NumFields(fmt) + 1):
        name = vs.GetFldName(fmt, i)
        try:
            if vs.GetParamStyleType(sd, name) != 1:     # 1: By Style
                continue
            value = vs.GetRField(src, TOOL_OBJECT, name)
            if vs.GetRField(obj, TOOL_OBJECT, name) != value:
                vs.SetRField(obj, TOOL_OBJECT, name, value)
                copied += 1
        except Exception:
            continue
    _log('style', repr(style), 'values copied', copied)


def new_point_object(x, y, rot):
    """A new point or linear TOOL_OBJECT at (x, y) turned rot degrees."""
    for args in (((x, y), rot, False), (x, y, rot, False)):
        try:
            h = vs.CreateCustomObjectN(TOOL_OBJECT, *args)
            _log('CreateCustomObjectN', TOOL_OBJECT, args, '->', h)
            if h:
                return h
        except Exception as e:
            _log('CreateCustomObjectN', args, 'failed', repr(e))
            continue
    return None


def new_path_object(pts, closed):
    """A new path TOOL_OBJECT on the polyline (open) or polygon (closed) pts."""
    if closed:
        vs.ClosePoly()
    else:
        vs.OpenPoly()
    vs.BeginPoly()
    for x, y in pts:
        vs.AddPoint(x, y)
    vs.EndPoly()
    poly = vs.LNewObj()
    obj = None
    for nil in (None, vs.Handle(0) if hasattr(vs, 'Handle') else None):
        try:
            obj = vs.CreateCustomObjectPath(TOOL_OBJECT, poly, nil)
            break
        except Exception:
            continue
    # the drawn shape: removed if it was copied rather than used as the path
    try:
        parent = vs.GetParent(poly)
        used = obj and vs.GetCustomObjectPath(obj) == poly
        if parent and vs.GetTypeN(parent) == 31 and not used:
            vs.DelObject(poly)
    except Exception:
        pass
    return obj


def _complete():
    mode = _tool_mode()
    h = None
    try:
        h = vs.vstGetToolObject()
    except Exception:
        pass
    pts = _clicked_points()
    _log('complete mode', mode, 'tool object', h, 'clicked', pts)
    try:
        tool_complete(mode, pts, h)
    except Exception:
        import traceback
        _log(traceback.format_exc())
    finally:
        if h:
            try:
                vs.DelObject(h)
            except Exception:
                pass


def run_tool():
    try:
        info = vs.vstGetEventInfo()
        event, msg1, msg2 = info
    except Exception as e:
        info, event, msg1, msg2 = repr(e), 0, 0, 0
    _log('event', info)
    try:
        _run_tool(event, msg1, msg2)
    except Exception:
        import traceback
        _log(traceback.format_exc())


def _run_tool(event, msg1, msg2):
    if event == 0:
        vs.AlrtDialog('The %s tool needs to be event-enabled.\r\r'
                      'Tools > Plug-ins > Plug-in Manager, select %s, Edit... > '
                      'Properties, tick the event-enabled / event-based option, OK, '
                      'then restart Vectorworks.' % (TOOL_NAME, TOOL_NAME))
        return
    if event == kToolSetUp:
        try:
            m = int(load_tool_prefs().get('Mode', 0))
        except Exception:
            m = 0
        _tool['mode'] = m if 1 <= m <= len(TOOL_MODES) else globals().get('TOOL_FIRST_MODE', 1)
        if len(TOOL_MODES) > 1:
            icons = [icon for icon, _b, _h in TOOL_MODES]
            vs.AddRadioMode(_tool['mode'], len(icons), *(icons + [''] * (6 - len(icons))))
        try:
            _style_menu()
            _pulldown_menus()
        except Exception:
            import traceback
            _log(traceback.format_exc())
        if _spanner():
            vs.AddButtonMode(PREFS_ICON)
        _apply_mode(_tool['mode'])
        _log('setup done, mode', _tool['mode'], 'styles', _tool.get('styles'))
    elif event == kToolMode:
        if msg1 == _style_group():
            _style_chosen(msg2)
        elif msg1 == _prefs_group() and _spanner():
            _spanner()()
        elif _style_group() < msg1 < _prefs_group():
            _pulldown_chosen(msg1 - _style_group() - 1, msg2)
        else:
            mode = _tool_mode()
            _apply_mode(mode)
            prefs = load_tool_prefs()
            prefs['Mode'] = mode
            save_tool_prefs(prefs)
    elif event == kToolComplete:
        _complete()
