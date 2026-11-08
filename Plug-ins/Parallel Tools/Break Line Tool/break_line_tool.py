"""
Break Line Tool for Vectorworks 2026 / 2027

Copyright (c) 2026 Ian Thrush
Licensed under the MIT License (see LICENSE.md).

A break line as one linear plug-in object, rebuilt from Breaker 11.51
by dbelfm:
- snap the two ends to the thing being broken: the line carries on past them
  by Extend Past Ends
- drag a dot to slide the breaks along the line, each line with its own dot,
  so double break lines don't clash
- the far dot also sets how far apart the lines are, and the mask behind them

The .vso holds a short loader stub; all logic lives here.
"""

import math

import vs

VERSION = '0.5.1'
VERSION_DATE = '2026-11-09'
WEBSITE = 'github.com/itchyNZL/parallel-tools'
TOOL_FOLDER = 'Break Line Tool'

# Vectorworks plug-in events and Object Info properties
kResetEventID = 3
kObjOnInitXProperties = 5
kObjOnWidgetPrep = 41
kObjOnUIButtonHit = 35
kObjXPropHasUIOverride = 8
kObjXHasCustomWidgetVisibilities = 12
kObjPropWidgetGroupMode = 81
kWidgetGroupAutomatic = 2
kWidgetSeparator = 100
kWidgetButton = 12
kObjectEventHandled = -8
kObjXSupportsStyles = 49
kObjOnEditPluginStyle = 60
kObjectEditPluginStyleByDefault = -10   # reply: use the default style dialog
ABOUT_WEB_ID = 3002
ABOUT_UPDATE_ID = 3101

STYLES = ('Straight', 'Curved', 'Arc')
BREAK_MM = 2.0          # break height when Break Height is 0
GAP_MM = 5.0            # mask depth when the parameter is missing
MAX_BREAKS = 50
MAX_SKEW = 80.0         # degrees
REQUIRED = ('Overrun', 'BreakStyle', 'NumBreaks', 'BreakWidth', 'BreakSize', 'BreakRadius',
            'Skew', 'Double', 'Mask',
            'ControlPoint01X', 'ControlPoint01Y', 'ControlPoint02X', 'ControlPoint02Y',
            'LastLength', 'DrawnSize', 'MaskDepth', 'State')


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------


def match_choice(raw, options, default=None):
    """The option a stored pop-up value means: the text (any case), or its
    position number."""
    v = (raw or '').strip().strip('"').strip()
    for o in options:
        if v.lower() == o.lower():
            return o
    if v.isdigit() and 1 <= int(v) <= len(options):
        return options[int(v) - 1]
    return default


class Params:
    def __init__(self, h, rec):
        self.h = h
        self.rec = rec
        try:
            scale = annotation_scale(h) or vs.GetLScale(vs.GetLayer(h))
        except Exception:
            scale = 1.0
        self.scale = scale if scale and scale > 0 else 1.0
        self.paper = _mm() * self.scale

        self.length = max(0.0, self._num('LineLength'))
        self.overrun = max(0.0, self._num('Overrun'))
        self.style = match_choice(self._str('BreakStyle'), STYLES, 'Straight')
        self.breaks = min(MAX_BREAKS, max(0, int(round(self._num('NumBreaks', 1.0)))))
        height_mm = self._num('BreakSize')
        self.height = (height_mm if height_mm > 0 else BREAK_MM) * self.paper
        # Width blank or 0 = as Breaker: as wide as the height
        width_mm = self._num('BreakWidth')
        self.width = width_mm * self.paper if width_mm > 0 else self.height
        # Arc radius blank or 0 = as Breaker: a quarter of the width
        radius_mm = self._num('BreakRadius')
        self.radius = radius_mm * self.paper if radius_mm > 0 else self.width / 4.0
        skew = max(-MAX_SKEW, min(MAX_SKEW, self._num('Skew')))
        self.slope = math.tan(math.radians(skew))
        self.double = self._str('Double').strip().lower() == 'true'
        self.mask = self._str('Mask').strip().lower() != 'false'
        self.last_length = self._num('LastLength')
        # Mask depth: mm on the sheet, either side (negative = the other side)
        depth = self._str('MaskDepth').strip()
        self.depth = (self._num('MaskDepth') if depth else GAP_MM) * self.paper
        self.state = self._str('State').strip()

    def _str(self, name):
        return vs.GetRField(self.h, self.rec, name)

    def _num(self, name, default=0.0):
        ok, v = vs.ValidNumStr(self._str(name).strip())
        return v if ok else default

    def set(self, name, value):
        if self._str(name) != value:
            vs.SetRField(self.h, self.rec, name, value)

    def set_num(self, name, value):
        self.set(name, '%.6f' % value)


ovViewportScale = 1003


def annotation_scale(h):
    """The viewport's scale (5 for 1:5) if h is in a viewport's annotations,
    which are drawn at that scale; else None. Breaker used the sheet's 1:1
    there, so its breaks could come out tiny."""
    vp = _viewport_of(h)
    if not vp:
        return None
    try:
        sc = vs.GetObjectVariableReal(vp, ovViewportScale)
        return sc if sc and sc > 0 else None
    except Exception:
        return None


def _viewport_of(h):
    """The viewport whose annotations hold h, or None (as Revision Tool:
    the parents, then GetVPGroupParent, then every viewport's annotation
    group)."""
    try:
        first = vs.GetParent(h)
    except Exception:
        return None
    if not first:
        return None
    parent = first
    try:
        for _ in range(6):
            if not parent:
                break
            t = vs.GetTypeN(parent)
            if t == 122:                            # viewport
                return parent
            if parent == first and t == 31:         # on a layer: not in annotations
                return None
            parent = vs.GetParent(parent)
    except Exception:
        pass
    try:
        vp = vs.GetVPGroupParent(first)
        if vp and vs.GetTypeN(vp) == 122:
            return vp
    except Exception:
        pass
    found = []

    def look(vp):
        if found:
            return
        for kind in (2, 1, 3, 4):
            try:
                g = vs.GetVPGroup(vp, kind)
            except Exception:
                continue
            if g and g == first:
                found.append(vp)
                return

    try:
        vs.ForEachObject(look, '(T=VIEWPORT)')
    except Exception:
        pass
    return found[0] if found else None


_checked = set()


def check_params(rec):
    """First redraw of a session: say which parameters the plug-in lacks
    (read from its parameter list, as Revision Tool)."""
    if rec in _checked:
        return
    _checked.add(rec)
    try:
        fmt = vs.GetObject(rec)
        names = {vs.GetFldName(fmt, i) for i in range(1, vs.NumFields(fmt) + 1)}
    except Exception:
        return
    missing = [n for n in REQUIRED if n not in names]
    if names and missing:
        vs.AlrtDialog('Break Line Tool: add these parameters in the Plug-in Manager '
                      '(see DEVELOPMENT.md), then restart Vectorworks: ' + ', '.join(missing))


# --------------------------------------------------------------------------
# Geometry (object coordinates: X along the line from the first click)
# --------------------------------------------------------------------------

def break_centres(centre, length, overrun, count, size):
    """Where the breaks go, and the group's centre after keeping them on the
    line. Evenly spaced as in Breaker, as a group round the dot."""
    if count < 1:
        return [], max(-overrun, min(length + overrun, centre))
    spacing = max(length / (count + 1.0), size)
    half = (count - 1) * spacing / 2.0
    low = -overrun + size / 2.0 + half
    high = length + overrun - size / 2.0 - half
    c = length / 2.0 if low > high else max(low, min(high, centre))
    return [c - half + i * spacing for i in range(count)], c


def line_points(start, end, offset, slope, centres, width, height, style):
    """One line as (x, y, kind). kind: 'corner', 'curve' or 'arc'. Each break
    is Breaker's shape: width along the line, height either side of it."""
    peak = 'curve' if style == 'Curved' else 'corner'
    foot = 'arc' if style == 'Arc' else 'corner'
    raw = [(start, 0.0, 'corner')]
    for c in sorted(centres):
        raw += [(c - width / 2.0, 0.0, foot), (c - width / 4.0, height, peak), (c, 0.0, 'corner'),
                (c + width / 4.0, -height, peak), (c + width / 2.0, 0.0, foot)]
    raw.append((end, 0.0, 'corner'))
    return [(x, y + offset + slope * x, k) for x, y, k in raw]


def mask_points(near, far):
    """The area between the two lines, as one closed outline."""
    return near + far[::-1]


def resolve_dots(p, first, x1, x2, y2):
    """The dots as dragged -> (near centre, far centre, gap between the lines).
    The gap is Mask Depth, unless the far dot has moved across the line since
    the last redraw (State holds its last height: a number, so State works as
    a Number or Text parameter): then the dot sets it. A changed length keeps
    the breaks at the same share of the line, so a centred break stays
    centred."""
    if first:
        return p.length / 2.0, p.length / 2.0, p.depth
    ok, last_y = vs.ValidNumStr(p.state)
    dragged = ok and abs(last_y - y2) > 1e-6 * max(1.0, abs(y2))
    gap = y2 - p.slope * x2 if dragged else p.depth
    if p.last_length > 0 and p.last_length != p.length:
        ratio = p.length / p.last_length
        x1 *= ratio
        x2 *= ratio
    return x1, x2, gap


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def _arc_to(x, y, radius):
    """ArcTo takes (x, y, r) or ((x, y), r) depending on the version."""
    try:
        vs.ArcTo(x, y, radius)
    except Exception:
        vs.ArcTo((x, y), radius)


def _curve_through(x, y):
    try:
        vs.CurveThrough(x, y)
    except Exception:
        vs.CurveThrough((x, y))


def draw_poly(points, closed, radius):
    if closed:
        vs.ClosePoly()
    else:
        vs.OpenPoly()
    vs.BeginPoly()
    for x, y, kind in points:
        if kind == 'arc':
            _arc_to(x, y, radius)
        elif kind == 'curve':
            _curve_through(x, y)
        else:
            vs.AddPoint(x, y)
    vs.EndPoly()
    return vs.LNewObj()


def _set_look(h, fill, pen=True):
    """Fill and pen on the drawn shape itself: PenPat / FillPat are
    deprecated (an error in 2027). Fill 1 = solid, 0 = none; no pen = line
    style 0."""
    try:
        vs.SetFPat(h, fill)
        if not pen:
            vs.SetLSN(h, 0)
    except Exception:
        pass


def _short(v):
    """10.0 -> '10', 2.5 -> '2.5'."""
    return ('%.2f' % v).rstrip('0').rstrip('.')


def drawn_size(p):
    """The break as drawn, in the file's units: 'W 10 x H 10 at 1:5', so
    nobody has to work out the sheet size times the scale."""
    text = 'W %s x H %s' % (_short(p.width), _short(p.height))
    if p.style == 'Arc':
        text += ', R %s' % _short(p.radius)
    return '%s at 1:%s' % (text, _short(p.scale))


def reset(h, rec):
    check_params(rec)
    ensure_style_map(h)
    p = Params(h, rec)
    p.set('Version', '%s (%s)' % (VERSION, VERSION_DATE))
    p.set('DrawnSize', drawn_size(p))
    if p.length <= 0:
        return

    first = p.last_length <= 0
    near, far, gap = resolve_dots(p, first, p._num('ControlPoint01X'),
                                  p._num('ControlPoint02X'), p._num('ControlPoint02Y'))
    start, end = -p.overrun, p.length + p.overrun
    near_centres, near = break_centres(near, p.length, p.overrun, p.breaks, p.width)
    far_centres, far = break_centres(far, p.length, p.overrun, p.breaks, p.width)

    near_line = line_points(start, end, 0.0, p.slope, near_centres, p.width, p.height, p.style)
    far_line = line_points(start, end, gap, p.slope, far_centres if p.double else [],
                           p.width, p.height, p.style)

    # The mask is its own shape without a pen, under the lines: the lines stay
    # open (a single line has no second line) and the mask stays solid.
    if p.mask and gap != 0:
        _set_look(draw_poly(mask_points(near_line, far_line), True, p.radius), 1, pen=False)
    _set_look(draw_poly(near_line, False, p.radius), 0)
    if p.double:
        _set_look(draw_poly(far_line, False, p.radius), 0)

    # The near dot stays on its line; the far dot's height is the gap. Written
    # back so a dot dragged off the line returns to where it took effect.
    p.set_num('ControlPoint01X', near)
    p.set_num('ControlPoint01Y', p.slope * near)
    p.set_num('ControlPoint02X', far)
    p.set_num('ControlPoint02Y', gap + p.slope * far)
    p.set_num('LastLength', p.length)
    if abs(gap - p.depth) > 1e-9:
        p.set('MaskDepth', _short(gap / p.paper))
    # As stored, so the next redraw can tell the far dot was dragged
    p.set('State', p._str('ControlPoint02Y').strip())
    try:
        show_far = p.double or p.mask
        vs.SetParameterVisibility(h, 'ControlPoint02X', show_far)
        vs.SetParameterVisibility(h, 'ControlPoint02Y', show_far)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Object Info palette layout (event-based plug-in)
# --------------------------------------------------------------------------

LAYOUT = [
    ('Break Line', ['LineLength', 'Overrun', 'BreakStyle', 'NumBreaks', 'BreakWidth',
                    'BreakSize', 'BreakRadius', 'DrawnSize', 'Skew', 'Double', 'Mask',
                    'MaskDepth']),
    ('About', ['Version']),
]
LABELS = {'LineLength': 'Length', 'Overrun': 'Extend Past Ends', 'BreakStyle': 'Style',
          'NumBreaks': 'Number of Breaks', 'BreakWidth': 'Break Width (sheet mm)',
          'BreakSize': 'Break Height (sheet mm)', 'BreakRadius': 'Arc Radius (sheet mm)',
          'DrawnSize': 'Drawn Size', 'Skew': 'Skew (deg)',
          'Double': 'Double Break Lines', 'Mask': 'Mask Behind', 'MaskDepth': 'Mask Depth (sheet mm)',
          'Version': 'Version'}
READ_ONLY = ('Version', 'DrawnSize')

WIDGET_BASE = 1000
HEADING_BASE = 2000
# Fixed widget IDs: only ever add to the end of these lists.
WIDGET_IDS = ['LineLength', 'Overrun', 'BreakStyle', 'NumBreaks', 'BreakSize', 'Skew',
              'Double', 'Mask', 'Version', 'BreakWidth', 'BreakRadius', 'DrawnSize', 'MaskDepth']
HEADING_IDS = ['Break Line', 'About']


def _widget_ids():
    out = []
    for heading, names in LAYOUT:
        hid = HEADING_BASE + HEADING_IDS.index(heading)
        out.append((hid, heading, [(WIDGET_BASE + WIDGET_IDS.index(n), n) for n in names]))
    return out


def init_layout():
    vs.SetObjPropVS(kObjXPropHasUIOverride, True)
    vs.SetObjPropVS(kObjXHasCustomWidgetVisibilities, True)
    vs.SetObjPropCharVS(kObjPropWidgetGroupMode, chr(kWidgetGroupAutomatic))
    for hid, heading, params in _widget_ids():
        vs.vsoAddWidget(hid, kWidgetSeparator, heading)
        vs.vsoWidgetSetIndLvl(hid, 0)
        for wid, name in params:
            if vs.vsoAddParamWidget(wid, name, LABELS.get(name, '')):
                vs.vsoWidgetSetIndLvl(wid, 1)
        if heading == 'About':
            vs.vsoAddWidget(ABOUT_WEB_ID, kWidgetButton, WEBSITE)
            vs.vsoWidgetSetIndLvl(ABOUT_WEB_ID, 1)
            vs.vsoAddWidget(ABOUT_UPDATE_ID, kWidgetButton, 'Check for updates...')
            vs.vsoWidgetSetIndLvl(ABOUT_UPDATE_ID, 1)
    vs.SetObjPropVS(kObjXSupportsStyles, True)


# Plug-in styles: the look a style shares (By Style). Length, number of
# breaks, skew and the dots stay with each break line (By Instance). Set when
# a style is first used; change it in Edit Style.
STYLE_PARAMS = ('Overrun', 'BreakStyle', 'BreakWidth', 'BreakSize', 'BreakRadius',
                'Double', 'Mask')
kByInstance, kByStyle = 0, 1


def _style_def(h):
    try:
        name = vs.GetPluginStyle(h)
    except Exception:
        return None
    if not name:
        return None
    return vs.GetObject(name) or None


def ensure_style_map(h):
    """First use of a style: STYLE_PARAMS By Style, the rest By Instance. A
    style whose State is already By Instance has been set up: left alone.
    State is internal and never belongs in a style, so setting any real
    field By Style in Edit Style doesn't undo the set-up (0.4.11 checked
    Number of Breaks, which a user could make By Style)."""
    sd = _style_def(h)
    if not sd:
        return
    try:
        if vs.GetParamStyleType(sd, 'State') == kByInstance:
            return
        vs.SetAllStyleParams(sd, kByInstance)
        for name in STYLE_PARAMS:
            try:
                vs.SetParamStyleType(sd, name, kByStyle)
            except Exception:
                pass
    except Exception:
        pass


def widget_prep(h, rec):
    """Arc Radius greyed unless the style is Arc."""
    arc = match_choice(vs.GetRField(h, rec, 'BreakStyle'), STYLES, 'Straight') == 'Arc'
    disabled = set(READ_ONLY) | (set() if arc else {'BreakRadius'})
    for _hid, _heading, params in _widget_ids():
        for wid, name in params:
            vs.vsoWidgetSetEnable(wid, name not in disabled)
    vs.vsoSetEventResult(kObjectEventHandled)


# shared begin common
# --- Common helpers ---------------------------------------------------------
# Logging, units, classes, and the About buttons (website, updates). Uses the
# tool's DEBUG_LOG, TOOL_FOLDER, VERSION and WEBSITE, set at the top of the file.


def _log(*parts):
    """With DEBUG_LOG on, a line in tool_debug.log next to this file (testing)."""
    if not DEBUG_LOG:
        return
    try:
        import os
        import time
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tool_debug.log')
        with open(path, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%H:%M:%S'), ' '.join(str(p) for p in parts)))
    except Exception:
        pass


# A redraw that fails: logged, the object marked, and one alert per session.
_reset_errors = []


def _reset_failed(label):
    """Call from an except block round a redraw. With DEBUG_LOG on the error is
    raised so Vectorworks shows it (testing). Otherwise the object gets a
    locus at its insertion point (shows on screen, does not print) so it can
    still be found and selected, and the first failure in a session says so,
    instead of a Python error for every object in a mass reset."""
    import traceback
    _log('reset failed on', label, traceback.format_exc())
    if DEBUG_LOG:
        raise
    try:
        vs.Locus(0, 0)
    except Exception:
        pass
    _reset_errors.append(label)
    if len(_reset_errors) == 1:
        vs.AlrtDialog('%s %s: an object could not be drawn and is marked with a locus. '
                      'Please report it at %s/issues, with what you were doing.'
                      % (TOOL_FOLDER, VERSION, WEBSITE))


def _mm():
    """Document units per millimetre (1.0 in a mm file, 1/25.4 in an inch file)."""
    try:
        upi = vs.GetPrefReal(152)
    except Exception:
        upi = 0
    return upi / 25.4 if upi and upi > 0 else 1.0


# Classes share Vectorworks' one list of names with layers, symbols, styles
# and other named objects: a class can't be made with a name already in use.
def _class_name_taken(name):
    """True if a layer, symbol, style or other object that isn't a class has
    this name, so no class can be made with it and nothing should go in it."""
    try:
        if not name or vs.Name2Index(name) == 0:
            return False
        o = vs.GetObject(name)
        return bool(o) and vs.GetTypeN(o) != 94
    except Exception:
        return False


def _new_class(name):
    """Make the class, putting the user's active class back even on an error.
    False, and nothing made, if the name is taken by something else."""
    if _class_name_taken(name):
        _log('class name taken by another object', repr(name))
        return False
    active = vs.ActiveClass()
    try:
        vs.NameClass(name)
    finally:
        vs.NameClass(active)
    return True


def _set_class(h, name):
    """vs.SetClass, skipped when the name belongs to something that isn't a class."""
    if not _class_name_taken(name):
        vs.SetClass(h, name)


def _close_rgb(got, want):
    try:
        got = tuple(int(x) for x in got)[:3]
    except Exception:
        return False
    return len(got) == 3 and all(abs(g - w) <= 257 for g, w in zip(got, want))


def _set_class_colour(fn, get_fn, name, rgb):
    """Class pen / fill colour (rgb 0-65535), checked by reading it back:
    the Python call form varies, and a wrong one can set another colour
    without an error (Planting Tool 0.3.1 made a class white). Falls back
    to a colour index."""
    for args in ((name, rgb), (name,) + rgb):
        try:
            getattr(vs, fn)(*args)
            if _close_rgb(getattr(vs, get_fn)(name), rgb):
                return True
        except Exception:
            continue
    try:
        index = vs.RGBToColorIndex(rgb)
        index = index[-1] if isinstance(index, (tuple, list)) else index
        getattr(vs, fn)(name, index)
        return _close_rgb(getattr(vs, get_fn)(name), rgb)
    except Exception as e:
        _log(fn, name, 'colour not set', repr(e))
        return False


def open_url(url):
    """Windows' own opener first, the browser module only if that fails, the
    address in an alert as a last resort. (Trying the browser module first,
    then Windows when it said it hadn't, could open the page twice.)"""
    try:
        import os
        os.startfile(url)               # Windows
        return
    except Exception:
        pass
    try:
        import webbrowser
        if webbrowser.open(url):
            return
    except Exception:
        pass
    vs.AlrtDialog(url)


_web_opened = [0.0]


def open_website():
    """About button: the repo, opened once. A second click within 3 seconds is
    ignored, in case Vectorworks sends the click twice."""
    import time
    now = time.time()
    if now - _web_opened[0] < 3.0:
        return
    _web_opened[0] = now
    open_url('https://' + WEBSITE)


# About: check GitHub for a newer version.
# versions.json at the repo root lists each tool's latest version:
# {"Comment Tool": {"version": "0.22.4", "date": "2026-11-08"}, ...}
VERSIONS_URL = 'https://raw.githubusercontent.com/itchyNZL/parallel-tools/main/versions.json'
RELEASES_URL = 'https://github.com/itchyNZL/parallel-tools/releases'


def _version_tuple(v):
    out = []
    for part in str(v).strip().split('.'):
        digits = ''.join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def latest_version():
    """(version, date) of this tool on GitHub, or None if it can't be read
    (no internet, or the tool isn't listed yet)."""
    try:
        import json
        import urllib.request
        req = urllib.request.Request(VERSIONS_URL, headers={'User-Agent': 'parallel-tools'})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode('utf-8'))
        entry = data.get(TOOL_FOLDER) or {}
        if entry.get('version'):
            return str(entry['version']), str(entry.get('date', ''))
    except Exception:
        pass
    return None


def check_updates():
    """Check for updates button: compares VERSION with GitHub's versions.json."""
    found = latest_version()
    if found is None:
        vs.AlrtDialog('%s %s: could not check for updates (no internet connection, or '
                      'the tool is not on GitHub yet).' % (TOOL_FOLDER, VERSION))
        return
    latest, date = found
    if _version_tuple(latest) <= _version_tuple(VERSION):
        vs.AlrtDialog('%s %s is up to date.' % (TOOL_FOLDER, VERSION))
        return
    when = ' (%s)' % date if date else ''
    if vs.YNDialog('%s %s%s is available. You have %s.\n\nOpen the download page?'
                   % (TOOL_FOLDER, latest, when, VERSION)):
        open_url(RELEASES_URL)
# shared end common


DEBUG_LOG = False      # True writes tool_debug.log next to this file (testing)


def run():
    try:
        event, button = vs.vsoGetEventInfo()
    except Exception:
        event, button = 0, 0
    _log('event', event, button)

    if event == kObjOnInitXProperties:
        init_layout()
        return

    ok, rec, h, _rec_h, _wall_h = vs.GetCustomObjectInfo()
    if not ok:
        return
    if event == kObjOnWidgetPrep:
        widget_prep(h, rec)
    elif event == kObjOnEditPluginStyle:
        vs.vsoSetEventResult(kObjectEditPluginStyleByDefault)
    elif event == kObjOnUIButtonHit:
        if button == ABOUT_WEB_ID:
            open_website()
        elif button == ABOUT_UPDATE_ID:
            check_updates()
    elif event in (kResetEventID, 0):
        try:
            reset(h, rec)
        except Exception:
            _reset_failed(vs.GetName(h))


# --- Breakline tool (the .vst): what its clicks make ------------------------
TOOL_OBJECT = 'Break Line Tool'
TOOL_NAME = 'BreakLine'          # 'Break Line' is taken by a Vectorworks tool
# vstSetPtBehavior 2: two clicks
TOOL_MODES = (('', 2, 'Click the start of the break line, then the end'),)
TOOL_PULLDOWNS = ()
# the spanner: (field, label, 'num' / 'text' / choices)
TOOL_DEFAULTS = (
    ('BreakStyle', 'Style', ('Straight', 'Curved', 'Arc')),
    ('NumBreaks', 'Number of Breaks', 'num'),
    ('Overrun', 'Extend Past Ends', 'num'),
    ('BreakWidth', 'Break Width (sheet mm)', 'num'),
    ('BreakSize', 'Break Height (sheet mm)', 'num'),
    ('Double', 'Double Break Lines', ('True', 'False')),
    ('Mask', 'Mask Behind', ('True', 'False')),
    ('MaskDepth', 'Mask Depth (sheet mm)', 'num'),
)


def tool_complete(mode, pts, h):
    if len(pts) < 2:
        return
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 1e-6:
        return
    obj = new_point_object(x0, y0, math.degrees(math.atan2(y1 - y0, x1 - x0)))
    if obj:
        vs.SetRField(obj, TOOL_OBJECT, 'LineLength', '%.6f' % length)
    styled_new(obj)


# shared begin drawing-tool
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
# shared end drawing-tool
