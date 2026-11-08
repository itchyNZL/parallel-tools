"""
Comment Tool for Vectorworks 2026 / 2027

Copyright (c) 2026 Ian Thrush
Licensed under the MIT License (see LICENSE.md).

A drawing review comment as a path plug-in object: an outline (line, cloud
or none) around the area, a leader, and a tag with the comment. A friendlier
alternative to the built-in Redline:
- colour comes from the class (one class per Status), never hardcoded red
- comment types Question / Fix / Note / Nice, so a review is not all faults
- the tag moves and its width changes by dragging two control points
- Show Assignee / Show Author / Show Date defaults are set in the Plug-in
  Manager (Assignee on, Author off out of the box)

The .vso holds a short loader stub; all logic lives here.
"""

import datetime
import math

import vs

VERSION = '0.23.1'
VERSION_DATE = '2026-11-09'
WEBSITE = 'github.com/itchyNZL/parallel-tools'
TOOL_FOLDER = 'Comment Tool'

# Vectorworks plug-in events and Object Info properties
kResetEventID = 3
kObjOnInitXProperties = 5
kObjOnWidgetPrep = 41
kObjXPropHasUIOverride = 8
kObjXHasCustomWidgetVisibilities = 12
kObjPropWidgetGroupMode = 81
kWidgetGroupAutomatic = 2
kWidgetSeparator = 100
kObjectEventHandled = -8
kObjOnSpecialEdit = 7           # double-click / Edit, with kObjXPropSpecialEdit = custom
kObjOnUIButtonHit = 35
kObjXPropSpecialEdit = 3
kObjXPropSpecialEditCustom = 1
kObjectEditResult_DoNothing = 0
kWidgetButton = 12
kObjXSupportsStyles = 49
kObjXPropAcceptStates = 18
kObjXPropAcceptStatesInternal = 19
kObjOnAddState = 44
kObjOnEditPluginStyle = 60
kObjectEditPluginStyleByDefault = -10   # reply: use the default style dialog
EDIT_BUTTON_ID = 3000
SETTINGS_BUTTON_ID = 3002
ABOUT_WEB_ID = 3004
ABOUT_UPDATE_ID = 3101
# 3001 (Leader Attributes...), 3003 (author line) and 3008 are retired: not reused

# Open: comment made. Done: assignee has fixed it, please check.
# Closed: reviewer has checked it.
STATUSES = ('Open', 'Done', 'Closed')
TYPES = ('Fix', 'Note', 'Nice')
AUDIENCES = ('Internal', 'Client')
# How a copy is numbered (Settings > Copies)
COPY_MODES = ('Next number', 'Next free after copied', 'Lowest free')

# One-click buttons in Object Info, each group under its own heading:
# heading -> (field, Params attribute, [(button id, value)]). A click sets
# every selected comment. Buttons have no pressed state, so the current
# value's caption is marked (CURRENT_MARK) at widget prep; no mark when the
# selected comments differ. The buttons never move, so they can be clicked
# from habit.
BUTTON_GROUPS = {
    'Status': ('Status', 'status', [(3005, 'Open'), (3006, 'Done'), (3007, 'Closed')]),
    'Type': ('CommentType', 'type', [(3020 + i, v) for i, v in enumerate(TYPES)]),
    'Audience': ('Audience', 'audience', [(3010 + i, v) for i, v in enumerate(AUDIENCES)]),
}
BUTTON_VALUES = {bid: (field, value) for field, _attr, buttons in BUTTON_GROUPS.values()
                 for bid, value in buttons}
# Filled circles both sides of the current value: the captions are centred,
# so the word stays in place when the mark moves.
CURRENT_MARK = '● %s ●'

# Colour for each Status class when the tool creates it (0-255 RGB). After
# that the class is the office's to change: the tool never sets it again.
STATUS_COLOURS = {
    'Open': (200, 110, 0),         # bright amber: stands out on screen
    'Done': (31, 122, 110),        # teal: waiting for the reviewer
    'Closed': (138, 133, 124),     # warm grey: recedes
}
# Line weight (mils) for a class when the tool creates it: Internal 0.2 mm and
# dashed, Client 0.35 mm and solid; Closed one step thinner (0.13 / 0.18 mm).
# (Before 0.22.1: 0.35 mm for every Open / Done class, 0.18 mm Closed.)
CLASS_WEIGHTS = {False: 8, True: 14}            # client? -> mils
CLOSED_WEIGHTS = {False: 5, True: 7}


def class_weight(status, client):
    return (CLOSED_WEIGHTS if status == 'Closed' else CLASS_WEIGHTS)[bool(client)]

# Paper sizes (mm on the printed sheet), scaled by the layer scale
TAG_WIDTH_MM = 40.0     # tag width when Tag Width is 0 / first placement
TAG_OFFSET_MM = 8.0     # first placement: tag this far up and right of the outline
TEXT_GAP_MM = 0.8       # text clear of the tag line
CLOUD_MM = 6.0          # cloud scallop length when Cloud Size is 0
PIN_MM = 1.2            # pin dot diameter
MIN_WIDTH_MM = 5.0

# Tag Line: the line under the header runs the full tag width, or only as far
# as the header / meta text (the comment below still wraps at the full width)
TAG_LINES = ('Full width', 'Header')


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------


def _today():
    """ISO date (2026-10-13): unambiguous and sorts in worksheets."""
    return datetime.date.today().isoformat()


def iso_date(text):
    """A date typed as dd/mm/yy (or dd/mm/yyyy, dd.mm.yy, dd-mm-yy) -> ISO.
    ISO and anything not read as a date are kept as typed (as Revision Tool)."""
    t = (text or '').strip()
    for sep in ('/', '.', '-'):
        parts = t.split(sep)
        if len(parts) == 3 and all(x.isdigit() for x in parts) and len(parts[0]) <= 2:
            d, m, y = (int(x) for x in parts)
            if y < 100:
                y += 2000
            try:
                return datetime.date(y, m, d).isoformat()
            except ValueError:
                return t
    return t


def _now():
    return datetime.datetime.now().strftime('%H:%M')


def match_choice(raw, options, default=None):
    """The option a stored pop-up / radio-button value means: the text
    (any case), or its position number."""
    v = (raw or '').strip().strip('"').strip()
    for o in options:
        if v.lower() == o.lower():
            return o
    for o in options:
        if v and (o.lower().startswith(v.lower()) or v.lower().startswith(o.lower())):
            return o
    if v.isdigit():
        n = int(v)
        if 1 <= n <= len(options):
            return options[n - 1]
        if n == 0:
            return options[0]
    return default


class Params:
    def __init__(self, h, rec):
        self.h = h
        self.rec = rec
        self.mm = _mm()
        try:
            # In a viewport's annotations the viewport's scale (0.21 used the
            # sheet's 1:1 there, so comments came out tiny)
            scale = annotation_scale(h) or vs.GetLScale(vs.GetLayer(h))
        except Exception:
            scale = 1.0
        self.scale = scale if scale and scale > 0 else 1.0
        self.paper = self.mm * self.scale     # document units per printed mm

        self.note = decode_note(self._str('Note'))
        self.type = self._choice('CommentType', TYPES, 'Note')
        self.status = self._choice('Status', STATUSES, 'Open')
        self.audience = self._choice('Audience', AUDIENCES, 'Internal')
        self.assigned = self._str('To').strip()
        self.author = self._str('From').strip()
        self.show_assignee = self._bool('ShowTo')
        self.show_author = self._bool('ShowFrom')
        self.show_date = self._bool('ShowDate')
        self.show_number = self._bool('ShowNumber')
        self.number = self._str('Number').strip()
        self.created = self._str('CreatedDate').strip()
        self.picked_up = self._str('DoneDate').strip()
        outline = self._str('Outline').strip().lower()
        self.outline = 'cloud' if outline.startswith('cloud') else (
            'none' if outline.startswith('none') else 'line')
        # Cloud Size: scallop length in mm on the printed sheet (0 = 6 mm)
        # Leader Setback: gap between the outline and the leader, mm on paper
        self.setback = max(0.0, self._num('LeaderSetback')) * self.paper
        # Shoulder: text starts this far along the tag line from the leader, mm on paper
        self.shoulder = max(0.0, self._num('Shoulder')) * self.paper
        self.markers = self._str('LeaderMarkers')
        cloud_mm = self._num('CloudSize')
        self.cloud = max(cloud_mm if cloud_mm > 0 else CLOUD_MM, 1.0) * self.paper
        self.tag_width = self._num('TagWidth')
        self.class_template = self._str('ClassTemplate').strip()
        # Use Type / Use Audience (Settings): blank (older comments) = on
        self.use_type = self._str('UseType').strip().lower() != 'false'
        self.use_audience = self._str('UseAudience').strip().lower() != 'false'
        # Number Prefix (blank = '#'); Copies Fill Gaps
        self.prefix = self._str('NumberPrefix').strip() or '#'
        self.copy_mode = match_choice(self._str('CopyNumbering'), COPY_MODES, COPY_MODES[0])
        # Closed comments collapse to the header line (blank = on)
        self.collapse_closed = self._str('CollapseClosed').strip().lower() != 'false'
        # Tag Line (blank = full width, as before)
        self.tag_line = match_choice(self._str('TagLine'), TAG_LINES, TAG_LINES[0])

    def _str(self, name):
        return vs.GetRField(self.h, self.rec, name)

    def _num(self, name, default=0.0):
        ok, v = vs.ValidNumStr(self._str(name).strip())
        return v if ok else default

    def _bool(self, name):
        return self._str(name).strip().lower() == 'true'

    def _choice(self, name, options, default):
        return match_choice(self._str(name), options, default)

    def set(self, name, value):
        if self._str(name) != value:
            vs.SetRField(self.h, self.rec, name, value)

    def set_num(self, name, value):
        vs.SetRField(self.h, self.rec, name, '%.6f' % value)


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------

def outline_points(path):
    """Path vertices as a list of (x, y), read straight from the path.

    Nothing is copied, converted or deleted inside the comment: the old
    duplicate / ConvertToPolygon / delete here could delete the comment's
    own path (0.19.2), leaving it empty and invisible."""
    pts = []
    try:
        n = vs.GetVertNum(path)
        if vs.GetTypeN(path) == 5:                  # polygon
            pts = [tuple(vs.GetPolyPt(path, i))[:2] for i in range(1, n + 1)]
        else:                                       # polyline etc.: its vertices
            for i in range(1, n + 1):
                pt = vs.GetPolylineVertex(path, i)[0]
                pts.append((pt[0], pt[1]))
    except Exception:
        import traceback
        _log(traceback.format_exc())
    # drop a repeated closing point
    if len(pts) > 2 and _dist(pts[0], pts[-1]) < 1e-9:
        pts.pop()
    return pts


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def nearest_on_outline(pts, q):
    """Closest point to q on the closed outline."""
    best, best_d = pts[0], _dist(pts[0], q)
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ll = dx * dx + dy * dy
        t = 0.0 if ll == 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / ll))
        c = (a[0] + t * dx, a[1] + t * dy)
        d = _dist(c, q)
        if d < best_d:
            best, best_d = c, d
    return best


def signed_area(pts):
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                     for i in range(n))


def cloud_points(pts, size):
    """Revision cloud: half-round scallops about `size` long bulging outwards
    along each edge of the closed outline, as a list of points."""
    out = []
    n = len(pts)
    ccw = signed_area(pts) > 0
    # no more than about 400 scallops, however small the size
    perimeter = sum(_dist(pts[i], pts[(i + 1) % n]) for i in range(n))
    size = max(size, perimeter / 400.0)
    steps = 8
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        L = _dist(a, b)
        if L < 1e-9:
            continue
        k = max(1, int(round(L / size)))
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        # outward normal: right of the direction of travel on a CCW outline
        nx, ny = (uy, -ux) if ccw else (-uy, ux)
        seg = L / k
        r = seg / 2.0
        for j in range(k):
            cx = a[0] + ux * (j + 0.5) * seg
            cy = a[1] + uy * (j + 0.5) * seg
            for s in range(steps):
                ang = math.pi * s / steps          # 0 .. 180 deg, start of the scallop
                along = -math.cos(ang) * r
                out_ = math.sin(ang) * r * 0.8
                out.append((cx + ux * along + nx * out_, cy + uy * along + ny * out_))
    return out


# --------------------------------------------------------------------------
# Classes
# --------------------------------------------------------------------------

def class_name(p):
    tmpl = p.class_template
    if not tmpl:
        return ''
    if not getattr(p, 'use_audience', True):
        # Audience not used: {Audience} drops out (Notes-Comment-Open)
        for token in ('-{Audience}', '{Audience}-', '{Audience}', '-{audience}', '{audience}-'):
            tmpl = tmpl.replace(token, '')
    name = tmpl.replace('{Status}', p.status).replace('{status}', p.status)
    name = name.replace('{Type}', p.type).replace('{type}', p.type)
    name = name.replace('{Audience}', p.audience).replace('{audience}', p.audience)
    return name.strip()[:63]


def client_class(p, audience):
    """True if the class is a Client one of its own: Audience tracked and
    in the template. Client classes are solid, Internal ones dashed."""
    return (audience == 'Client' and getattr(p, 'use_audience', True)
            and '{audience}' in (p.class_template or '').lower())


def class_set(p):
    """Every class the template can give: all Audience / Status (/ Type)
    combinations, with the status of each and whether it is a Client class."""
    tmpl = p.class_template
    if not tmpl:
        return []
    out = []
    for aud in AUDIENCES:
        for status in STATUSES:
            for typ in (TYPES if '{type}' in tmpl.lower() else (p.type,)):
                q = type('P', (), {})()
                q.class_template, q.audience, q.status, q.type = tmpl, aud, status, typ
                q.use_audience = p.use_audience
                out.append((class_name(q), status, client_class(p, aud)))
    return out


def ensure_class_set(p):
    """First use of a template: create all its classes at once, coloured,
    so viewport and sheet class visibility can be set once."""
    for name, status, client in class_set(p):
        _ensure_class(name, status, client)


ovViewportScale = 1003


def annotation_scale(h):
    """The viewport's scale (50 for 1:50) if h is in a viewport's
    annotations, which are drawn at that scale; else None."""
    vp = _viewport_of(h)
    if not vp:
        return None
    try:
        sc = vs.GetObjectVariableReal(vp, ovViewportScale)
        return sc if sc and sc > 0 else None
    except Exception as e:
        _log('viewport scale', repr(e))
        return None


# Which GetVPGroup kind is a viewport's annotation group: found by the
# viewport search in _viewport_of (2 is the guess until then)
_vp_kind = {'annotations': 2}


def _viewport_of(h):
    """The viewport whose annotations hold h, or None (as Revision Tool):
    the parents (an annotation group may not give its viewport as parent),
    then GetVPGroupParent, then every viewport in the file, matching its
    annotation group to h's parent."""
    try:
        first = vs.GetParent(h)
    except Exception:
        return None
    if not first:
        return None
    chain = []
    parent = first
    try:
        for _ in range(6):
            if not parent:
                break
            t = vs.GetTypeN(parent)
            chain.append(t)
            if t == 122:                            # viewport
                return parent
            parent = vs.GetParent(parent)
    except Exception as e:
        chain.append(repr(e))
    if chain and chain[0] in (31,):                 # on a layer: not in annotations
        return None
    try:
        vp = vs.GetVPGroupParent(first)
        if vp and vs.GetTypeN(vp) == 122:
            return vp
    except Exception as e:
        chain.append('GetVPGroupParent: %r' % e)
    found = []

    def look(vp):
        if found:
            return
        for kind in (_vp_kind['annotations'], 2, 1, 3, 4):
            try:
                g = vs.GetVPGroup(vp, kind)
            except Exception:
                continue
            if g and g == first:
                found.append(vp)
                _vp_kind['annotations'] = kind
                return

    try:
        vs.ForEachObject(look, '(T=VIEWPORT)')
    except Exception as e:
        chain.append('viewport search: %r' % e)
    if found:
        return found[0]
    _log('no viewport found; parent types', chain)
    return None


def show_class(h, name):
    """A new comment's class is turned on if it is off or greyed, so placing
    a comment never looks like nothing happened. In a viewport's annotations
    the viewport's class visibility is the one that counts."""
    if not name:
        return
    vp = _viewport_of(h)
    try:
        vis = vs.GetVPClassVisibility(vp, name) if vp else vs.GetCVis(name)
    except Exception:
        vis = None                                  # unknown: turn it on anyway
    if vis == 0:                                    # 0 = visible
        return
    try:
        if vp:
            vs.SetVPClassVisibility(vp, name, 0)
        else:
            vs.ShowClass(name)
        _log('class turned on', name, 'in viewport' if vp else '')
    except Exception as e:
        _log('show class', name, repr(e))


def _read_rgb(fn, name):
    try:
        v = getattr(vs, fn)(name)
        return tuple(int(x) for x in v)[:3]
    except Exception:
        return None


LINE_TYPE_RESOURCE = 96         # resource list type for line types


def _dash_line_style():
    """A dashed line type in this file, as a class line style value
    (negative resource index), or None to leave the class solid. Takes a
    plain dash (name has 'dash' but not 'dot'), shortest name first."""
    try:
        list_id, n = vs.BuildResourceList(LINE_TYPE_RESOURCE, 0, '')
        names = [vs.GetNameFromResourceList(list_id, i) for i in range(1, n + 1)]
    except Exception as e:
        _log('line types', repr(e))
        return None
    dashes = sorted((x for x in names if x and 'dash' in x.lower() and 'dot' not in x.lower()),
                    key=len)
    for name in dashes:
        index = vs.Name2Index(name)
        if index:
            return -index
    return None


def _style_class(name, status, client=False):
    """Status colour for pen and fill, no fill pattern, Use at Creation,
    line weight (class_weight), and a dashed line for Internal (solid for a
    Client class, or if the file has no dash)."""
    r, g, b = STATUS_COLOURS.get(status, STATUS_COLOURS['Open'])
    rgb = (r * 257, g * 257, b * 257)
    _set_class_colour('SetClPenFore', 'GetClPenFore', name, rgb)
    _set_class_colour('SetClFillFore', 'GetClFillFore', name, rgb)
    dash = None if client else _dash_line_style()
    calls = [lambda: vs.SetClFPat(name, 0), lambda: vs.SetClUseGraphic(name, True),
             lambda: vs.SetClLW(name, class_weight(status, client))]
    if dash is not None:
        calls.append(lambda: vs.SetClLSN(name, dash))
    for call in calls:
        try:
            call()
        except Exception as e:
            _log('class setting failed', name, repr(e))


def _unconfigured(name):
    """A class still to colour: black with Use at Creation off. Anything
    else is the office's own: left alone."""
    pen = _read_rgb('GetClPenFore', name)
    try:
        if vs.GetClUseGraphic(name):
            return False
    except Exception:
        return False
    return pen in ((0, 0, 0), None)


def _ensure_class(name, status, client=False):
    """Create the class if missing (or finish one made by an older
    version), coloured for its status."""
    if not name:
        return
    if vs.Name2Index(name) == 0:
        if not _new_class(name):
            return
    elif not _unconfigured(name):
        return
    _style_class(name, status, client)


# Object variable 800 on: text the script creates uses the comment's own
# Text > Format Text settings (font, size, style). Alignment is not kept, so
# the script sets it on each text.
ovUsePIOTextAttributes = 800


# LeaderMarkers: "byclass|start|end|2", each marker
# "style,angle,length,width,basis,thickness,shown" (lengths in page inches).
# Shown applies with class markers too (the class gives the style, the tick
# says whether that end has one). The trailing 2 marks that format: older
# text with class markers ignored the ticks, so it reads as both shown.
DEFAULT_MARKER = (0, 15, 0.125, 0.0625, 0, 0.0)


def _default_marker():
    try:
        m = vs.GetDefaultBeginningMarker()
        if m and m[0]:
            return tuple(m[1:7])
    except Exception:
        pass
    return DEFAULT_MARKER


def read_markers(text):
    """(by_class, (start marker, shown), (end marker, shown))."""
    parts = (text or '').split('|')
    by_class = parts[0].strip() == '1'
    old_class = by_class and (len(parts) < 4 or parts[3].strip() != '2')

    def one(i):
        try:
            v = [float(x) for x in parts[i].split(',')]
            m = (int(v[0]), int(v[1]), v[2], v[3], int(v[4]), v[5])
            shown = bool(int(v[6]))
        except Exception:
            m, shown = _default_marker(), False
        return m, (True if old_class else shown)

    return by_class, one(1), one(2)


def write_markers(by_class, start, end):
    def one(mv):
        m, shown = mv
        return ','.join(['%d' % m[0], '%d' % m[1], '%g' % m[2], '%g' % m[3], '%d' % m[4],
                         '%g' % m[5], '1' if shown else '0'])
    return '|'.join(['1' if by_class else '0', one(start), one(end), '2'])


def no_markers(h):
    """Hide both markers on a line drawn inside the comment."""
    for get, put in (('GetObjBeginningMarker', 'SetObjBeginningMarker'),
                     ('GetObjEndMarker', 'SetObjEndMarker')):
        try:
            m = getattr(vs, get)(h)
            if m and m[0] and m[7]:
                getattr(vs, put)(h, *(tuple(m[1:7]) + (False,)))
        except Exception:
            pass


def start_marker_shown(h):
    """True if the leader h ended up with a visible start marker (its own or
    the class's): then the pin dot is not drawn, the marker is the pin."""
    try:
        m = vs.GetObjBeginningMarker(h)
        return bool(m and m[0] and m[7])
    except Exception:
        return False


class Painter:
    """Puts each new object in the comment's class, attributes by class."""

    def __init__(self, p):
        self.cls = class_name(p)
        if self.cls and (vs.Name2Index(self.cls) == 0 or _unconfigured(self.cls)):
            ensure_class_set(p)
        _ensure_class(self.cls, p.status, client_class(p, p.audience))
        # The comment itself goes in the same class, so Object Info shows it
        # and turning the class off hides the whole comment.
        if self.cls:
            try:
                if vs.GetClass(p.h) != self.cls:
                    _set_class(p.h, self.cls)
            except Exception:
                pass

    def finish(self, h):
        if self.cls:
            _set_class(h, self.cls)
        for fn in ('SetLSByClass', 'SetLWByClass', 'SetPenColorByClass',
                   'SetFillColorByClass', 'SetFPatByClass'):
            try:
                getattr(vs, fn)(h)
            except Exception:
                pass
        return h

    def poly(self, pts, closed=True):
        if closed:
            vs.ClosePoly()
        else:
            vs.OpenPoly()
        vs.BeginPoly()
        for x, y in pts:
            vs.AddPoint(x, y)
        vs.EndPoly()
        return self.finish(vs.LNewObj())

    def leader(self, a, b, p):
        """Leader with the comment's Leader Attributes markers (or the class
        markers). Start = outline / pin end, end = tag end."""
        vs.MoveTo(a[0], a[1])
        vs.LineTo(b[0], b[1])
        h = self.finish(vs.LNewObj())
        by_class, start, end = read_markers(p.markers)
        try:
            if by_class:
                vs.SetMarkerByClass(h)
                if not (start[1] and end[1]):
                    # class style, but an end ticked off: copy what the class
                    # gave and hide that end
                    for get, put, shown in (('GetObjBeginningMarker', 'SetObjBeginningMarker', start[1]),
                                            ('GetObjEndMarker', 'SetObjEndMarker', end[1])):
                        m = getattr(vs, get)(h)
                        if m and m[0]:
                            getattr(vs, put)(h, *(tuple(m[1:7]) + (bool(m[7]) and shown,)))
            else:
                vs.SetObjBeginningMarker(h, *(tuple(start[0]) + (start[1],)))
                vs.SetObjEndMarker(h, *(tuple(end[0]) + (end[1],)))
        except Exception as e:
            _log('leader markers', repr(e))
        return h

    def line(self, a, b):
        vs.MoveTo(a[0], a[1])
        vs.LineTo(b[0], b[1])
        h = self.finish(vs.LNewObj())
        no_markers(h)
        return h

    def dot(self, c, d):
        r = d / 2.0
        vs.Oval(c[0] - r, c[1] + r, c[0] + r, c[1] - r)
        h = self.finish(vs.LNewObj())
        try:
            vs.SetFPat(h, 1)          # solid, in the class colour
        except Exception:
            pass
        return h

    def text(self, p, origin, s, valign, wrap=None, just=1):
        vs.TextOrigin(origin[0], origin[1])
        vs.CreateText(s)
        h = vs.LNewObj()
        self.finish(h)
        vs.SetTextJust(h, just)             # 1 left, 3 right
        vs.SetTextVerticalAlign(h, valign)      # 1 top, 5 bottom
        if wrap:
            vs.SetTextWrap(h, True)
            vs.SetTextWidth(h, wrap)
        try:
            vs.SetFPat(h, 0)                # no background behind the text
        except Exception:
            pass
        return h


# --------------------------------------------------------------------------
# Comment data
# --------------------------------------------------------------------------

def _bbox_x(h):
    """(left, right) of an object, or None."""
    try:
        r = vs.GetBBox(h)
    except Exception:
        return None
    nums = []

    def flat(v):
        if isinstance(v, (tuple, list)):
            for n in v:
                flat(n)
        elif isinstance(v, (int, float)):
            nums.append(float(v))
    flat(r)
    if len(nums) < 4:
        return None
    return (min(nums[0], nums[2]), max(nums[0], nums[2]))


def _record_name(rec):
    """GetCustomObjectInfo gives the plug-in (record) name as a string."""
    return rec if isinstance(rec, str) and rec else 'Comment Tool'


def location(p):
    """Where the comment is: 'A101 [Floor Plan]' on a sheet layer, the layer
    name on a design layer."""
    try:
        layer = vs.GetLayer(p.h)
    except Exception as e:
        _log('location: no layer', repr(e))
        return ''
    where = ''
    try:
        where = vs.GetObjectVariableString(layer, 162) or ''    # sheet number [title]
    except Exception:
        pass                                    # design layers have no sheet title
    if not where.strip():
        try:
            where = vs.GetLName(layer) or ''
        except Exception as e:
            _log('location: no layer name', repr(e))
    # apostrophes would break the parameter line Vectorworks writes
    return safe_text(where.strip())


def number_digits(text):
    """12 from '12', '#12', 'C12' or 'A101-12' (older formats)."""
    digits = ''
    for ch in reversed((text or '').strip()):
        if not ch.isdigit():
            break
        digits = ch + digits
    return int(digits) if digits else None


def next_number(p, after=None, lowest=False):
    """Next number in the file (highest + 1). Gaps left by deleted comments
    are not filled; the number of a deleted highest comment is used again.
    after: the next free number after this one instead; lowest: the lowest
    free number (Settings > Copies)."""
    rec_name = _record_name(p.rec)
    used = []

    def collect(h):
        if h == p.h:
            return
        n = number_digits(vs.GetRField(h, rec_name, 'Number'))
        if n is not None:
            used.append(n)

    try:
        vs.ForEachObject(collect, "(R IN ['%s'])" % rec_name)
    except Exception:
        pass
    if lowest:
        after = 0
    if after is not None:
        n = after + 1
        while n in used:
            n += 1
        return str(n)
    return str(max(used) + 1 if used else 1)


def short_date(iso):
    """2026-10-13 -> 13 Oct (the sheet); the record keeps the ISO date."""
    try:
        d = datetime.date.fromisoformat(iso_date(iso))
        return '%d %s' % (d.day, d.strftime('%b'))
    except Exception:
        return iso


def header_text(p):
    """(header line, number length, meta line). Header: number, type,
    status and 'Client' for client comments, the status always spelled out (greyscale prints, colour-blind
    readers). Meta: 'IT to TL   13 Oct', 'By IT', 'To TL'; the date is the
    latest stamp. Closed comments show the header only."""
    number = (p.prefix + p.number if p.number.isdigit() else p.number) \
        if (p.show_number and p.number) else ''
    typ = p.type if p.use_type else ''
    # Client comments say so; Internal is the usual case and stays unmarked
    aud = 'Client' if (p.use_audience and p.audience == 'Client') else ''
    head = '  '.join(x for x in (number, typ, '(%s)' % p.status, aud) if x)
    if p.status == 'Closed' and p.collapse_closed:
        return head, len(number), ''
    author = p.author if p.show_author else ''
    assigned = p.assigned if p.show_assignee else ''
    if author and assigned:
        who = '%s to %s' % (author, assigned)
    elif author:
        who = 'By ' + author
    elif assigned:
        who = 'To ' + assigned
    else:
        who = ''
    stamp = p.picked_up if (p.status != 'Open' and p.picked_up) else p.created
    when = short_date(stamp) if (p.show_date and stamp) else ''
    return head, len(number), '   '.join(x for x in (who, when) if x)


NEWLINE_MARK = '\\n'    # stored in place of a line break: backslash + n


def encode_note(text):
    """Line breaks as \\n in the Note field. Vectorworks writes each parameter
    into the Python script as vs.PNote = '...' without escaping, so a real
    line break, an apostrophe or a stray backslash (C:\\Users, a trailing \\)
    in a parameter stops the plug-in running. A backslash is stored doubled."""
    text = text.replace('\\', '\\\\')
    text = text.replace('\r\n', '\r').replace('\n', '\r').replace('\r', NEWLINE_MARK)
    return text.replace("'", '’')      # typographic apostrophe, same reason


def decode_note(text):
    """\\n typed or stored in the Note field = a new line in the tag; \\\\ = a
    backslash. Any other backslash (older comments) is kept as it is."""
    out = []
    i = 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair == NEWLINE_MARK:
            out.append('\r')
            i += 2
        elif pair == '\\\\':
            out.append('\\')
            i += 2
        else:
            out.append(text[i])
            i += 1
    return ''.join(out)


def safe_text(text):
    """A one-line field typed in a dialog, safe to store: typographic
    apostrophe, forward slash for a backslash (see encode_note)."""
    return text.replace("'", '’').replace('\\', '/')


def _choice_text(r):
    """Text of a GetSelectedChoiceInfo result, whatever its tuple shape."""
    if isinstance(r, tuple):
        for v in reversed(r):
            if isinstance(v, str) and v:
                return v
        return ''
    return r if isinstance(r, str) else ''


class RadioRows:
    """Rows of radio buttons in a layout dialog. Each row sits in its own
    borderless group box, or Vectorworks treats every radio button in the
    window as one set. A row's buttons: [(button id, value, caption)]."""

    def __init__(self, dlg):
        self.dlg = dlg
        self.rows = {}              # group id -> buttons
        self.group_of = {}          # button id -> group id

    def create(self, lid, label, width, gid, buttons):
        vs.CreateStaticText(self.dlg, lid, label, width)
        vs.CreateGroupBox(self.dlg, gid, '', False)
        for bid, _value, text in buttons:
            vs.CreateRadioButton(self.dlg, bid, text)
            self.group_of[bid] = gid
        self.rows[gid] = list(buttons)

    def place(self, lid, gid, gaps=()):
        """The row right of its label, buttons side by side; gaps: extra
        space before the 2nd, 3rd ... button."""
        buttons = self.rows[gid]
        vs.SetRightItem(self.dlg, lid, gid, 0, 0)
        vs.SetFirstGroupItem(self.dlg, gid, buttons[0][0])
        for i, ((left, _v, _t), (bid, _value, _text)) in enumerate(zip(buttons, buttons[1:])):
            vs.SetRightItem(self.dlg, left, bid, gaps[i] if i < len(gaps) else 0, 0)

    def owns(self, item):
        return item in self.group_of

    def pick(self, bid):
        """One button per row: this one on, the rest of its row off."""
        for other, _value, _text in self.rows[self.group_of[bid]]:
            vs.SetBooleanItem(self.dlg, other, other == bid)

    def set(self, gid, value):
        """Turn on the button for value (the row's first if none matches)."""
        buttons = self.rows[gid]
        values = [v for _b, v, _t in buttons]
        self.pick(buttons[values.index(value) if value in values else 0][0])

    def chosen(self, gid):
        for bid, value, _text in self.rows[gid]:
            if vs.GetBooleanItem(self.dlg, bid):
                return value
        return None

    def enable(self, gid, on):
        for bid, _value, _text in self.rows[gid]:
            vs.EnableItem(self.dlg, bid, on)

    def items(self):
        """Every group box and button."""
        return list(self.rows) + list(self.group_of)


def comment_dialog(h, rec, new=False):
    """The Comment dialog (placing a comment, double-click, Edit Comment...):
    a resizable multi-line text box like the Callout tool, then Status, Type
    and Audience as rows of radio buttons, From and To. Writes the fields;
    True if OK."""
    def get(name):
        return vs.GetRField(h, rec, name)

    cur = {'Note': decode_note(get('Note')),
           'CommentType': match_choice(get('CommentType'), TYPES, 'Note'),
           'Status': match_choice(get('Status'), STATUSES, 'Open'),
           'Audience': match_choice(get('Audience'), AUDIENCES, 'Internal'),
           'To': get('To'), 'From': get('From')}
    # radio rows: (label id, label, field, group id, first button id, values),
    # in the Object Info order; IDs rise down the dialog (the Tab order)
    rows = ((22, 'Status:', 'Status', 90, 60, STATUSES),
            (20, 'Type:', 'CommentType', 91, 70, TYPES),
            (28, 'Audience:', 'Audience', 92, 80, AUDIENCES))
    # rows not tracked, or set by the comment's style, are left out
    rows = tuple(row for row in rows
                 if not (row[2] == 'Audience' and get('UseAudience').strip().lower() == 'false')
                 and not (row[2] == 'CommentType' and get('UseType').strip().lower() == 'false')
                 and not by_style(h, row[2]))
    text_rows = ((24, 'From:', 25, 'From'), (26, 'To:', 27, 'To'))
    result = {}
    try:
        number = get('Number').strip()
        if number:
            number = (get('NumberPrefix').strip() or '#') + number     # as on the tag
        title = 'New Comment' if new else ('Edit Comment ' + number).strip()
        dlg = vs.CreateResizableLayout(title, False, 'OK', 'Cancel', True, True)
        radios = RadioRows(dlg)
        vs.CreateStaticText(dlg, 10, 'Comment:', -1)
        vs.CreateEditTextBox(dlg, 11, cur['Note'].replace('\r', '\r\n'), 50, 8)
        # 'Created 15 Oct 17:24', and Done only once it has a date (the
        # record keeps ISO dates; Location is for the worksheet)
        def stamp(date_field, time_field):
            day = iso_date(get(date_field))
            return ' '.join(x for x in ((short_date(day) if day else ''), get(time_field).strip()) if x)
        info = ['Created ' + (stamp('CreatedDate', 'CreatedTime') or 'now')]
        done = stamp('DoneDate', 'DoneTime')
        if done:
            info.append('Done ' + done)
        vs.CreateStaticText(dlg, 50, '        '.join(info), -1)
        for lid, label, _field, gid, base, values in rows:
            radios.create(lid, label, 13, gid, [(base + i, v, v) for i, v in enumerate(values)])
        for lid, label, fid, field in text_rows:
            vs.CreateStaticText(dlg, lid, label, 13 if lid == text_rows[0][0] else -1)
            vs.CreateEditText(dlg, fid, cur[field], 12)

        vs.SetFirstLayoutItem(dlg, 10)
        vs.SetBelowItem(dlg, 10, 11, 0, 0)
        vs.SetBelowItem(dlg, 11, 50, 0, 0)
        prev = 50
        for lid, _label, _field, gid, _base, _values in rows:
            vs.SetBelowItem(dlg, prev, lid, 0, 1 if prev == 50 else 0)
            radios.place(lid, gid, gaps=(0, 2))     # a little more room before the third column
            prev = lid
        kLeftEdge, kShift = 3, 1
        for buttons in radios.rows.values():
            for col, (bid, _value, _text) in enumerate(buttons):
                if col:                                 # columns line up
                    vs.AlignItemEdge(dlg, bid, kLeftEdge, 100 + col, kShift)
        # From and To side by side on one line
        left = None
        for lid, _label, fid, _field in text_rows:
            if left is None:
                vs.SetBelowItem(dlg, prev, lid, 0, 1)
            else:
                vs.SetRightItem(dlg, left, lid, 1, 0)
            vs.SetRightItem(dlg, lid, fid, 0, 0)
            left = fid
        # The text box grows with the dialog; everything else stays below it.
        vs.SetEdgeBinding(dlg, 11, True, True, True, True)
        below = [50] + [row[0] for row in rows] + radios.items()
        below += [i for lid, _l, fid, _f in text_rows for i in (lid, fid)]
        for item in below:
            vs.SetEdgeBinding(dlg, item, True, False, False, True)

        def handler(item, data):
            if item == 12255:                       # dialog set up
                vs.EnableItem(dlg, 50, False)       # greyed: information only
                for _lid, _label, field, gid, _base, _values in rows:
                    radios.set(gid, cur[field])
            elif radios.owns(item):                 # one button per row
                radios.pick(item)
            elif item == 1:                         # OK
                result['Note'] = vs.GetItemText(dlg, 11)
                for _lid, _label, field, gid, _base, _values in rows:
                    value = radios.chosen(gid)
                    if value:
                        result[field] = value
                for _lid, _label, fid, field in text_rows:
                    result[field] = vs.GetItemText(dlg, fid).strip()
            return item

        vs.RunLayoutDialog(dlg, handler)
    except Exception:
        import traceback
        _log(traceback.format_exc())
        # plain text box instead; an empty answer (Cancel) keeps the text
        result.clear()
        try:
            text = vs.StrDialog('Comment:', cur['Note'])
            if text and text.strip():
                result['Note'] = text
        except Exception:
            pass
    if not result:
        return False
    # Vectorworks text uses returns between lines
    result['Note'] = encode_note(result.get('Note', '').strip())
    for key, value in result.items():
        if key != 'Note':
            value = safe_text(value)
        if value != get(key) and not by_style(h, key):
            vs.SetRField(h, rec, key, value)
    return True


# --------------------------------------------------------------------------
# Tag control points
# --------------------------------------------------------------------------
#
# ControlPoint01 = start of the tag line (where the leader meets the tag,
# drag to move the tag). ControlPoint02 = the other end (drag sideways to
# change the tag width; drag past ControlPoint01 to flip the tag to the
# other side). Tag Width in the Object Info palette is the same value.
# 'State' (not shown) remembers the last tag point and width so the tool can
# tell which of the three was changed.

def _cp(p, n):
    return (p._num('ControlPoint0%dX' % n), p._num('ControlPoint0%dY' % n))


def _set_cp(p, n, pt):
    p.set_num('ControlPoint0%dX' % n, pt[0])
    p.set_num('ControlPoint0%dY' % n, pt[1])


# Dates and times only the tool sets. State keeps its own copy after the tag
# numbers, so an edit made elsewhere (a worksheet, Object Info) is undone.
STAMPED = ('CreatedDate', 'CreatedTime', 'DoneDate', 'DoneTime')


def _read_state(p):
    try:
        x, y, w = (float(v) for v in p._str('State').split('|')[0].split(';'))
        return (x, y), w
    except Exception:
        return None, None


def _saved_stamps(p):
    parts = p._str('State').split('|')
    return parts[1:1 + len(STAMPED)] if len(parts) > len(STAMPED) else None


def _object_id(p):
    try:
        return vs.GetObjectUuid(p.h) or ''
    except Exception:
        return ''


def _saved_id(state):
    """Object ID of the comment that last wrote this State text. A copy
    carries its original's State, so its own ID differs until it is renumbered."""
    parts = (state or '').split('|')
    return parts[1 + len(STAMPED)].strip() if len(parts) > 1 + len(STAMPED) else ''


def _read_pin(p):
    """Last pin point (pin comments), kept after the object ID in State."""
    parts = p._str('State').split('|')
    try:
        x, y = (float(v) for v in parts[2 + len(STAMPED)].split(';'))
        return (x, y)
    except Exception:
        return None


def _write_state(p, cp1, w, pin=None):
    stamps = '|'.join(p._str(f).replace('|', '') for f in STAMPED)
    if pin is None:
        pin = _read_pin(p)
    tail = '|%.6f;%.6f' % pin if pin is not None else ''
    p.set('State', '%.6f;%.6f;%.6f|%s|%s%s' % (cp1[0], cp1[1], w, stamps, _object_id(p), tail))


# A comment just made in Pin mode: the tool writes this into State with the
# tag click as an offset from the pin point. Kept on the object, so it still
# works when Vectorworks runs the first reset after the tool has finished.
PIN_MARK = 'pin:'


def _pin_placement(state):
    """(dx, dy, side) from a PIN_MARK state, or None (no second click)."""
    try:
        dx, dy, side = (float(v) for v in state[len(PIN_MARK):].split(';'))
        return dx, dy, side
    except Exception:
        return None


def make_new_copy(p):
    """A copy is a new comment: next number, created now, Open."""
    _log('copy of', p.number, 'renumbered')
    mode = p.copy_mode
    p.number = next_number(p, number_digits(p.number) if mode == COPY_MODES[1] else None,
                           lowest=(mode == COPY_MODES[2]))
    p.set('Number', p.number)
    p.created = _today()
    p.set('CreatedDate', p.created)
    p.set('CreatedTime', _now())
    p.picked_up = ''
    p.set('DoneDate', '')
    p.set('DoneTime', '')
    p.status = 'Open'
    p.set('Status', 'Open')
    cp1, w = _read_state(p)
    if cp1 is not None:
        _write_state(p, cp1, w)     # lock the copy's own dates, not the original's


def is_copy(p):
    """A duplicate (or a comment pasted in): another comment has the same
    number. Which one is the copy:
    - a comment whose State was written by itself (saved ID = its own ID)
      is the original and is never renumbered;
    - otherwise it is the copy if the other comment is settled (wrote its
      own State) or is the one whose ID this comment's State carries;
    - failing both (older comments, IDs that changed), the later one in the
      drawing is the copy: Vectorworks puts a duplicate after its original.
    Drawing order alone was wrong when a copy was pasted onto an earlier
    layer: the original was renumbered and reopened."""
    mine = number_digits(p.number)
    if mine is None:
        return False
    my_id = _object_id(p)
    my_saved = _saved_id(p._str('State'))
    if my_id and my_saved == my_id:
        return False                                # the original
    rec_name = _record_name(p.rec)
    seen = {'me': False, 'earlier': False, 'original': False}

    def is_me(h, uid):
        return h == p.h or (bool(my_id) and uid == my_id)

    def look(h):
        if seen['original']:
            return
        try:
            uid = vs.GetObjectUuid(h) or ''
        except Exception:
            uid = ''
        if is_me(h, uid):
            seen['me'] = True
            return
        if number_digits(vs.GetRField(h, rec_name, 'Number')) != mine:
            return
        other_saved = _saved_id(vs.GetRField(h, rec_name, 'State'))
        if uid and (uid == other_saved or uid == my_saved):
            seen['original'] = True
        elif not seen['me']:
            seen['earlier'] = True

    try:
        vs.ForEachObject(look, "(R IN ['%s'])" % rec_name)
    except Exception:
        return False
    if seen['original'] or seen['earlier']:
        _log('copy check', p.number, 'original found' if seen['original'] else 'same number earlier')
    return seen['original'] or seen['earlier']


def restore_stamps(p):
    """Put back dates and times changed outside the tool."""
    saved = _saved_stamps(p)
    if not saved:
        return
    for field, value in zip(STAMPED, saved):
        if p._str(field) != value:
            _log('date restored', field, repr(p._str(field)), '->', repr(value))
            p.set(field, value)
    p.created, p.picked_up = iso_date(saved[0]), iso_date(saved[2])


def resolve_tag(p, pts, first, placed=None, pin=None):
    """Tag start point and signed width, keeping the control points, the
    Tag Width field and the stored state in step. pin: the pin point of a
    pin comment (the tag flips round it instead of the outline's centre)."""
    tol = 1e-4 * max(1.0, p.paper)
    min_w = MIN_WIDTH_MM * p.paper
    cp1, cp2 = _cp(p, 1), _cp(p, 2)
    last_cp1, last_w = _read_state(p)

    if first or last_cp1 is None:
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        off = TAG_OFFSET_MM * p.paper
        cp1 = (max(xs) + off, max(ys) + off)
        w = p.tag_width if p.tag_width > 0 else TAG_WIDTH_MM * p.paper
        if placed:
            (sx, sy), (ex, _ey) = placed
            cp1 = (sx, sy)
            dw = ex - sx
            if abs(dw) >= MIN_WIDTH_MM * p.paper:
                w = dw                          # third click: width and side
            else:
                w = math.copysign(abs(w), dw if dw else 1.0)
    else:
        w = last_w if abs(last_w) >= min_w else TAG_WIDTH_MM * p.paper
        typed = abs(p.tag_width)
        if _dist(cp1, last_cp1) > tol:
            # tag moved: keep its width; across the outline's centre line it
            # turns to run away from the outline
            xs = [q[0] for q in pts]
            centre = pin[0] if pin else (min(xs) + max(xs)) / 2.0
            if (cp1[0] - centre) * w < 0:
                w = -w
        elif typed > 0 and abs(typed - abs(w)) > tol:
            w = math.copysign(max(typed, min_w), w)  # Tag Width typed in
        elif _dist(cp2, (cp1[0] + w, cp1[1])) > tol:
            dw = cp2[0] - cp1[0]                    # width point dragged
            w = math.copysign(max(abs(dw), min_w), dw if dw else w)

    _set_cp(p, 1, cp1)
    _set_cp(p, 2, (cp1[0] + w, cp1[1]))
    p.set_num('TagWidth', abs(w))
    _write_state(p, cp1, w, pin)
    return cp1, w


def resolve_pin(p, pts, first):
    """Pin point of a pin comment. ControlPoint03 is the pin's handle: drag
    it to move the point without moving the tag. Starts at the centre of the
    (tiny) outline. Without ControlPoint03 in the Plug-in Manager the pin
    stays at the centre."""
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    centre = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
    has_cp3 = bool(p._str('ControlPoint03X').strip())
    stored = _read_pin(p)
    if first or stored is None:
        pin = centre
    elif has_cp3:
        pin = _cp(p, 3)                 # dragged, or where it was
    else:
        pin = stored
    if has_cp3:
        _set_cp(p, 3, pin)
    return pin


# --------------------------------------------------------------------------
# Reset
# --------------------------------------------------------------------------

def _short(v):
    """10.0 -> '10', 2.5 -> '2.5'."""
    return ('%.2f' % v).rstrip('0').rstrip('.')


def drawn_size(p):
    """The sizes set in mm on the sheet, as drawn in the file's units:
    'Cloud 600, tag 4000 wide at 1:100' (as Break Line Tool's Drawn Size)."""
    width = p.tag_width if p.tag_width > 0 else TAG_WIDTH_MM * p.paper
    parts = []
    if p.outline == 'cloud':
        parts.append('Cloud %s' % _short(p.cloud))
    parts.append('tag %s wide' % _short(width))
    text = ', '.join(parts)
    return '%s%s at 1:%s' % (text[0].upper(), text[1:], _short(p.scale))


def _outline_of(h, p):
    """The comment's outline points, or None. Two points drawn (click a
    corner, double-click the opposite corner) make a rectangle on that
    diagonal."""
    path = vs.GetCustomObjectPath(h)
    if not path:
        _log('reset', p.number, 'no path')
        return None
    pts = outline_points(path)
    if len(pts) < 2:
        _log('reset', p.number, 'path has', len(pts), 'points')
        return None
    if len(pts) == 2:
        (ax, ay), (bx, by) = pts
        pts = [(ax, ay), (bx, ay), (bx, by), (ax, by)]
    return pts


def _pin_tag_start(h, rec, p, pts, state):
    """A new pin comment: Outline None, and where its tag starts (the second
    click, running away from the point), or None."""
    vs.SetRField(h, rec, 'Outline', 'None')
    p.outline = 'none'
    tag = _pin_placement(state)
    if not tag:
        return None
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    sx = (min(xs) + max(xs)) / 2.0 + tag[0]
    sy = (min(ys) + max(ys)) / 2.0 + tag[1]
    return ((sx, sy), (sx + tag[2] * 1e-6, sy))


def _start_new(h, rec, p, new_pin):
    """First reset: the Created stamp, and for a new comment (no text yet)
    the Comment tool presets, then the Comment dialog. Returns the Params."""
    if not p.created:
        p.created = _today()
        p.set('CreatedDate', p.created)
        p.set('CreatedTime', _now())
    if p.note:
        return p
    try:
        apply_prefs(h, rec, p.paper)
    except Exception:
        pass
    if new_pin:
        vs.SetRField(h, rec, 'Outline', 'None')     # presets can say Line
    comment_dialog(h, rec, new=True)
    return Params(h, rec)


def _tidy_fields(p, first):
    """Number, Location, a copy made new (or the dates locked), Status and
    Type spelled out, and the Done stamp."""
    if not p.number:
        p.number = next_number(p)
        p.set('Number', p.number)
    where = location(p)
    if where and p._str('Location') != where:
        p.set('Location', where)                    # follows the comment
    if not first and is_copy(p):
        make_new_copy(p)
    elif not first:
        restore_stamps(p)
    if p._str('Status').strip() != p.status:
        p.set('Status', p.status)                   # blank, or typed differently
    if p._str('CommentType').strip() != p.type:
        p.set('CommentType', p.type)
    # Done date: stamped when the comment leaves Open, cleared if reopened
    if p.status == 'Open':
        if p.picked_up:
            p.picked_up = ''
            p.set('DoneDate', '')
            p.set('DoneTime', '')
    elif not p.picked_up:
        p.picked_up = _today()
        p.set('DoneDate', p.picked_up)
        p.set('DoneTime', _now())


def reset(h, rec):
    try:
        vs.SetObjectVariableBoolean(h, ovUsePIOTextAttributes, True)
    except Exception:
        pass
    ensure_style_map(h)
    p = Params(h, rec)
    p.set('Version', '%s (%s)' % (VERSION, VERSION_DATE))
    try:
        p.set('DrawnSize', drawn_size(p))
    except Exception:
        pass                                # parameter not added yet
    pts = _outline_of(h, p)
    if not pts:
        return
    # dates typed by hand (13/10/26) are kept as ISO
    for field in ('CreatedDate', 'DoneDate'):
        old = p._str(field)
        if old.strip() and iso_date(old) != old:
            p.set(field, iso_date(old))
    p.created, p.picked_up = iso_date(p.created), iso_date(p.picked_up)

    state = p._str('State').strip()
    new_pin = state.startswith(PIN_MARK)
    first = not state or new_pin
    placed = _pin_tag_start(h, rec, p, pts, state) if new_pin else None
    if first:
        p = _start_new(h, rec, p, new_pin)
    _tidy_fields(p, first)

    pin = resolve_pin(p, pts, first) if p.outline == 'none' else None
    try:
        # the pin handle only for pin comments
        vs.SetParameterVisibility(h, 'ControlPoint03X', pin is not None)
        vs.SetParameterVisibility(h, 'ControlPoint03Y', pin is not None)
    except Exception:
        pass
    cp1, w = resolve_tag(p, pts, first, placed, pin)
    try:
        vs.vsoStateClear(h)
    except Exception:
        pass
    _draw(h, p, pts, first, pin, cp1, w)


def _draw(h, p, pts, first, pin, cp1, w):
    """Outline, leader and tag. cp1: tag start, w: signed tag width."""
    cp2 = (cp1[0] + w, cp1[1])
    gap = TEXT_GAP_MM * p.paper
    pen = Painter(p)
    if first:
        show_class(h, pen.cls or vs.GetClass(h))

    # Outline
    edge = pts
    if p.outline == 'line':
        # drawn from the points (never a duplicate of the path itself)
        pen.poly(pts, closed=True)
        try:
            vs.SetFPat(vs.LNewObj(), 0)
        except Exception:
            pass
    elif p.outline == 'cloud' and len(pts) >= 3:
        edge = cloud_points(pts, p.cloud)
        pen.poly(edge, closed=True)

    # Leader: from the outline (or the pin) to the nearer end of the tag line.
    if p.outline == 'none':
        start = pin
        end = min((cp1, cp2), key=lambda e: _dist(e, start))
    else:
        s1, s2 = nearest_on_outline(edge, cp1), nearest_on_outline(edge, cp2)
        start, end = (s1, cp1) if _dist(s1, cp1) <= _dist(s2, cp2) else (s2, cp2)
    length = _dist(start, end)
    if p.outline != 'none' and p.setback > 0 and length > 0:
        t = min(p.setback, length) / length       # stop short of the outline
        start = (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)
    leader = pen.leader(start, end, p) if _dist(start, end) > gap else None
    if p.outline == 'none' and not (leader and start_marker_shown(leader)):
        pen.dot(start, PIN_MM * p.paper)        # pin dot unless a start marker is the pin

    _draw_tag(pen, p, cp1, cp2, end, gap)


def _draw_tag(pen, p, cp1, cp2, end, gap):
    """Header and meta above the tag line, comment wrapped below it. The
    text starts Shoulder along the line from the end the leader joins (end)
    and is aligned to that end (right-aligned when the tag runs left)."""
    width = abs(cp2[0] - cp1[0])
    left, right = min(cp1[0], cp2[0]), max(cp1[0], cp2[0])
    shoulder = min(p.shoulder, width * 0.5)
    if abs(end[0] - right) < 1e-9 and abs(end[0] - left) > 1e-9:
        x, just = right - shoulder, 3           # leader joins the right end
    else:
        x, just = left + shoulder, 1
    head, num_len, meta = header_text(p)
    block = head + ('\r' + meta if meta else '')
    t = pen.text(p, (x, cp1[1] + gap), block, 5, just=just)
    try:
        if num_len:
            vs.SetTextStyle(t, 0, num_len, 1)   # number in bold
        if meta:
            size = vs.GetTextSize(t, 0)
            if size and size > 0:               # meta line a little smaller
                vs.SetTextSize(t, len(head) + 1, len(meta), round(size * 0.8, 1))
    except Exception as e:
        _log('tag text style', repr(e))
    a, b = cp1, cp2
    if p.tag_line == 'Header':
        # from the leader's end to the far edge of the header / meta, plus
        # the shoulder again; never past the end handle
        far = cp2 if _dist(end, cp1) <= _dist(end, cp2) else cp1
        a, b = end, far
        edge = _bbox_x(t)
        if edge:
            reach = (x - edge[0]) if just == 3 else (edge[1] - x)
            span = min(width, 2 * shoulder + max(0.0, reach))
            b = (end[0] + math.copysign(span, far[0] - end[0]), end[1])
    pen.line(a, b)
    if p.note and not (p.status == 'Closed' and p.collapse_closed):
        pen.text(p, (x, cp1[1] - gap), p.note, 1, wrap=width - shoulder, just=just)


# --------------------------------------------------------------------------
# Object Info palette layout (event-based plug-in)
# --------------------------------------------------------------------------

# Status, Type and Audience: BUTTON_GROUPS under their own headings
# (init_layout adds the buttons).
LAYOUT = [
    ('Comment', ['From', 'To']),
    ('Status', []),
    ('Type', []),
    ('Audience', []),
    ('Tag', ['NumberPrefix', 'Number', 'DrawnSize']),
    ('About', ['Version']),
]

LABELS = {'From': 'From', 'To': 'To', 'NumberPrefix': 'Prefix', 'Number': 'Number',
          'DrawnSize': 'Drawn Size', 'Version': 'Version'}

READ_ONLY = ('Version', 'DrawnSize')

WIDGET_BASE = 1000
HEADING_BASE = 2000

# Fixed widget IDs: only ever add to the end of these lists.
WIDGET_IDS = [
    'Note', 'CommentType', 'Status', 'To', 'From', 'ShowNumber', 'Number',
    'ShowDate', 'CreatedDate', 'DoneDate', 'ShowTo', 'ShowFrom', 'TagWidth',
    'TextSize', 'TextStyle',              # retired, kept so the IDs below do not move
    'Outline', 'CloudSize', 'ClassTemplate', 'Version',
    'CreatedTime', 'DoneTime', 'Audience', 'LeaderSetback', 'Shoulder',
    'NumberPrefix', 'DrawnSize',
]
HEADING_IDS = ['Comment', 'Tag', 'Outline', 'Class', 'About', 'Status', 'Type', 'Audience']


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
        if heading == 'Comment':
            vs.vsoAddWidget(EDIT_BUTTON_ID, kWidgetButton, 'Edit Comment...')
            vs.vsoWidgetSetIndLvl(EDIT_BUTTON_ID, 1)
        if heading in BUTTON_GROUPS:
            for bid, value in BUTTON_GROUPS[heading][2]:
                vs.vsoAddWidget(bid, kWidgetButton, value)
                vs.vsoWidgetSetIndLvl(bid, 1)
        for wid, name in params:
            label = LABELS.get(name, '')
            if vs.vsoAddParamWidget(wid, name, label):
                vs.vsoWidgetSetIndLvl(wid, 1)
            if heading == 'Tag' and name == 'Number':
                vs.vsoAddWidget(SETTINGS_BUTTON_ID, kWidgetButton, 'Settings...')
                vs.vsoWidgetSetIndLvl(SETTINGS_BUTTON_ID, 1)
        if heading == 'About':
            # where to get it and report issues: a button that opens the repo
            vs.vsoAddWidget(ABOUT_WEB_ID, kWidgetButton, WEBSITE)
            vs.vsoWidgetSetIndLvl(ABOUT_WEB_ID, 1)
            vs.vsoAddWidget(ABOUT_UPDATE_ID, kWidgetButton, 'Check for updates...')
            vs.vsoWidgetSetIndLvl(ABOUT_UPDATE_ID, 1)
    # Double-click (and Edit) opens the comment box instead of reshaping.
    vs.SetObjPropCharVS(kObjXPropSpecialEdit, chr(kObjXPropSpecialEditCustom))
    vs.SetObjPropVS(kObjXSupportsStyles, True)
    # State events: tells the comment it has just been created or copied
    vs.SetPrefInt(590, 1)          # varParametricEnableStateEventing
    vs.SetObjPropVS(kObjXPropAcceptStates, True)
    vs.SetObjPropVS(kObjXPropAcceptStatesInternal, True)   # incl. duplicate states


# Plug-in styles: the settings a style shares (By Style). Everything else -
# the comment itself, its status, people, dates, number, tag position - stays
# By Instance. Set when a style is first used; change it in Edit Style.
STYLE_PARAMS = ('Outline', 'CloudSize', 'LeaderSetback', 'Shoulder', 'ShowNumber', 'ShowDate',
                'ShowTo', 'ShowFrom', 'ClassTemplate', 'UseType', 'UseAudience',
                'NumberPrefix', 'CopyNumbering', 'CollapseClosed', 'TagLine')
kByInstance, kByStyle = 0, 1


def _style_def(h):
    try:
        name = vs.GetPluginStyle(h)
    except Exception:
        return None
    if not name:
        return None
    sd = vs.GetObject(name)
    return sd or None


def ensure_style_map(h):
    """First use of a style: Note etc. By Instance, STYLE_PARAMS By Style.
    A style whose Note is already By Instance has been set up: left alone."""
    sd = _style_def(h)
    if not sd:
        return
    try:
        if vs.GetParamStyleType(sd, 'Note') == kByInstance:
            return
        vs.SetAllStyleParams(sd, kByInstance)
        for name in STYLE_PARAMS:
            # one at a time: a parameter missing from the .vso skips only itself
            try:
                vs.SetParamStyleType(sd, name, kByStyle)
            except Exception as e:
                _log('style map', name, repr(e))
        _log('style map set for', vs.GetPluginStyle(h))
    except Exception:
        import traceback
        _log(traceback.format_exc())


def by_style(h, field):
    """True if this comment's style controls the field."""
    sd = _style_def(h)
    if not sd:
        return False
    try:
        return vs.GetParamStyleType(sd, field) == kByStyle
    except Exception:
        return False


SETTINGS_FIELDS = ('Outline', 'CloudSize', 'LeaderSetback', 'Shoulder', 'NumberPrefix', 'CopyNumbering',
                   'UseType', 'UseAudience', 'ShowNumber', 'ShowDate', 'ShowFrom', 'ShowTo',
                   'ClassTemplate', 'LeaderMarkers', 'CollapseClosed', 'TagLine')


def settings_form(title, get, styled, tag_mm, status='Open', sample=None):
    """Comment Settings: the window for one comment (Settings...) and for
    the defaults (Preferences > Default Settings...). get(field) gives the
    current value as text (sizes in mm on the sheet); styled(field) greys a
    field a style controls. status / sample (audience, type) feed the class
    preview. Returns {field: text, 'TagWidthMM': mm} or None.

    Grouped Outline, Tag, Numbering, Class, Leader. Item IDs rise down the
    window, so Tab follows the layout."""
    by_class, start, end = read_markers(get('LeaderMarkers'))
    SHAPES, CLOSED, LINES, MARKERS = 112, 213, 219, 502      # radio rows (group ids)
    # number rows: (label id, label, field id, field, hint id, hint)
    outline_nums = ((106, 'Cloud (sheet mm):', 107, 'CloudSize', 108, 'scallop size on the sheet'),
                    (109, 'Setback (sheet mm):', 110, 'LeaderSetback', 111, 'gap from the outline to the leader'))
    shows = ((208, 'Number', 'ShowNumber'), (209, 'Date', 'ShowDate'),
             (210, 'From', 'ShowFrom'), (211, 'To', 'ShowTo'))
    audience, ctype = sample or (match_choice(get('Audience'), AUDIENCES, AUDIENCES[0]),
                                 match_choice(get('CommentType'), TYPES, 'Note'))
    has_tag_line = bool(get('TagLine').strip())     # blank: parameter not in the .vso yet

    # Cloud and Width show the real size: a stored 0 (older comments and
    # presets) is the built-in default, shown as that number
    shown_default = {'CloudSize': CLOUD_MM}

    def number(field):
        ok, v = vs.ValidNumStr(get(field).strip())
        return '%g' % (v if ok and v > 0 else shown_default.get(field, 0))

    dlg = vs.CreateLayout(title, False, 'OK', 'Cancel')
    radios = RadioRows(dlg)
    for gid, heading in ((100, 'Outline'), (200, 'Tag'), (300, 'Numbering'), (400, 'Class'), (500, 'Leader')):
        vs.CreateGroupBox(dlg, gid, heading, True)
    hints = []

    def num_row(lid, label, fid, value, hid, hint):
        vs.CreateStaticText(dlg, lid, label, 14)
        vs.CreateEditText(dlg, fid, value, 8)
        vs.CreateStaticText(dlg, hid, hint, -1)
        hints.append(hid)

    # Outline
    radios.create(101, 'Shape:', 14, SHAPES, [(102, 'Line', 'Line'), (103, 'Cloud', 'Cloud'),
                                              (104, 'None', 'None')])
    for lid, label, fid, field, hid, hint in outline_nums:
        num_row(lid, label, fid, number(field), hid, hint)
    # Tag
    num_row(201, 'Shoulder (sheet mm):', 202, number('Shoulder'), 203, 'where the text starts along the tag line')
    num_row(204, 'Width (sheet mm):', 205, '%g' % (round(tag_mm, 1) if tag_mm else TAG_WIDTH_MM), 206,
            'tag width on the sheet')
    vs.CreateStaticText(dlg, 207, 'Show:', 14)
    for cid, label, _field in shows:
        vs.CreateCheckBox(dlg, cid, label)
    radios.create(212, 'When closed:', 14, CLOSED, [(214, 'False', 'Full tag'), (215, 'True', 'Header only')])
    radios.create(216, 'Line:', 14, LINES, [(217, 'Full width', 'Full width'), (218, 'Header', 'Header')])
    # Numbering
    vs.CreateStaticText(dlg, 301, 'Prefix:', 14)
    vs.CreateEditText(dlg, 302, get('NumberPrefix').strip() or '#', 8)
    vs.CreateStaticText(dlg, 303, 'Copies get:', 14)
    vs.CreatePullDownMenu(dlg, 304, 22)
    vs.CreateStaticText(dlg, 305, 'the number a copied comment takes', -1)
    hints.append(305)
    # Class
    vs.CreateStaticText(dlg, 401, 'Template:', 14)
    vs.CreateEditText(dlg, 402, get('ClassTemplate'), 40)
    vs.CreateStaticText(dlg, 403, '{Audience} {Status} {Type} are replaced', -1)
    hints.append(403)
    vs.CreateStaticText(dlg, 404, ' ' * 60, 44)     # live class preview, filled in below
    # Leader
    radios.create(501, 'Markers:', 14, MARKERS, [(503, True, 'From class'), (504, False, 'Custom')])
    vs.CreateStaticText(dlg, 505, 'Start:', 14)
    vs.CreateMarkerPopup(dlg, 506)
    vs.CreateCheckBox(dlg, 507, 'Show')
    vs.CreateStaticText(dlg, 508, 'End (tag):', 14)
    vs.CreateMarkerPopup(dlg, 509)
    vs.CreateCheckBox(dlg, 510, 'Show')

    # layout
    def below(prev, lid, fid=None, hid=None):
        vs.SetBelowItem(dlg, prev, lid, 0, 0)
        if fid:
            vs.SetRightItem(dlg, lid, fid, 0, 0)
        if hid:
            vs.SetRightItem(dlg, fid, hid, 0, 0)

    vs.SetFirstLayoutItem(dlg, 100)
    vs.SetFirstGroupItem(dlg, 100, 101)
    radios.place(101, SHAPES)
    below(101, 106, 107, 108)
    below(106, 109, 110, 111)
    vs.SetBelowItem(dlg, 100, 200, 0, 1)
    vs.SetFirstGroupItem(dlg, 200, 201)
    vs.SetRightItem(dlg, 201, 202, 0, 0)
    vs.SetRightItem(dlg, 202, 203, 0, 0)
    below(201, 204, 205, 206)
    vs.SetBelowItem(dlg, 204, 207, 0, 0)
    left = 207
    for cid, _label, _field in shows:
        vs.SetRightItem(dlg, left, cid, 0, 0)
        left = cid
    vs.SetBelowItem(dlg, 207, 212, 0, 0)
    radios.place(212, CLOSED)
    vs.SetBelowItem(dlg, 212, 216, 0, 0)
    radios.place(216, LINES)
    vs.SetBelowItem(dlg, 200, 300, 0, 1)
    vs.SetFirstGroupItem(dlg, 300, 301)
    vs.SetRightItem(dlg, 301, 302, 0, 0)
    below(301, 303, 304)
    vs.SetBelowItem(dlg, 304, 305, 0, 0)            # description under the pull-down
    vs.SetBelowItem(dlg, 300, 400, 0, 1)
    vs.SetFirstGroupItem(dlg, 400, 401)
    vs.SetRightItem(dlg, 401, 402, 0, 0)
    vs.SetBelowItem(dlg, 401, 403, 0, 0)
    vs.SetBelowItem(dlg, 403, 404, 0, 0)
    vs.SetBelowItem(dlg, 400, 500, 0, 1)
    vs.SetFirstGroupItem(dlg, 500, 501)
    radios.place(501, MARKERS)
    below(501, 505, 506)
    vs.SetRightItem(dlg, 506, 507, 0, 0)
    below(505, 508, 509)
    vs.SetRightItem(dlg, 509, 510, 0, 0)
    # every group box stretched to the widest, so the right edges line up
    kRightEdge, kResize = 1, 0
    for gid in (100, 200, 300, 400, 500):
        vs.AlignItemEdge(dlg, gid, kRightEdge, 900, kResize)

    result = {}

    def outline_enable():
        """Cloud only for a cloud outline, Setback not for a pin."""
        shape = radios.chosen(SHAPES) or 'Line'
        vs.EnableItem(dlg, 107, shape == 'Cloud' and not styled('CloudSize'))
        vs.EnableItem(dlg, 110, shape != 'None' and not styled('LeaderSetback'))

    def markers_enable():
        """The marker pickers only for Custom; the Show ticks always (with
        From class they turn the class marker at that end on or off)."""
        free = not styled('LeaderMarkers')
        own = radios.chosen(MARKERS) is False and free
        for item in (506, 509):
            vs.EnableItem(dlg, item, own)
        for item in (505, 507, 508, 510):
            vs.EnableItem(dlg, item, free)

    def class_preview():
        """The class this template gives (catches typos before they make
        stray classes)."""
        q = type('P', (), {})()
        q.class_template = vs.GetItemText(dlg, 402).strip()
        q.status, q.audience, q.type = status, audience, ctype
        q.use_audience = get('UseAudience').strip().lower() != 'false'
        name = class_name(q)
        vs.SetItemText(dlg, 404, ('→ ' + name) if name else 'Blank: the comment keeps its own class')

    def handler(item, data):
        if item == 12255:
            radios.set(SHAPES, match_choice(get('Outline'), OUTLINES, 'Line'))
            radios.set(CLOSED, 'False' if get('CollapseClosed').strip().lower() == 'false' else 'True')
            radios.set(LINES, match_choice(get('TagLine'), TAG_LINES, TAG_LINES[0]))
            radios.set(MARKERS, by_class)
            for cid, _label, field in shows:
                vs.SetBooleanItem(dlg, cid, get(field).strip().lower() == 'true')
            mode = match_choice(get('CopyNumbering'), COPY_MODES, COPY_MODES[0])
            for i, o in enumerate(COPY_MODES):
                vs.AddChoice(dlg, 304, o, i)
            vs.SelectChoice(dlg, 304, COPY_MODES.index(mode), True)
            for pid, cid, (m, shown) in ((506, 507, start), (509, 510, end)):
                vs.SetMarkerValue(dlg, pid, *m)
                vs.SetBooleanItem(dlg, cid, shown)
            # what a style controls is greyed
            for gid, field in ((SHAPES, 'Outline'), (CLOSED, 'CollapseClosed'), (MARKERS, 'LeaderMarkers'),
                               (LINES, 'TagLine')):
                radios.enable(gid, not styled(field))
            if not has_tag_line:
                vs.EnableItem(dlg, 216, False)
                radios.enable(LINES, False)
            for fid, field in ((202, 'Shoulder'), (205, 'TagWidth'), (302, 'NumberPrefix'),
                               (304, 'CopyNumbering'), (402, 'ClassTemplate')):
                vs.EnableItem(dlg, fid, not styled(field))
            for cid, _label, field in shows:
                vs.EnableItem(dlg, cid, not styled(field))
            for hid in hints:
                vs.EnableItem(dlg, hid, False)      # greyed: descriptions only
            outline_enable()
            markers_enable()
            class_preview()
        elif radios.owns(item):
            radios.pick(item)
            outline_enable()
            markers_enable()
        elif item == 402:
            class_preview()
        elif item == 1:
            shape = radios.chosen(SHAPES)
            if shape:
                result['Outline'] = shape
            for fid, field in ((107, 'CloudSize'), (110, 'LeaderSetback'), (202, 'Shoulder')):
                ok, v = vs.ValidNumStr(vs.GetItemText(dlg, fid).strip() or '0')
                if ok:
                    result[field] = '%g' % max(0.0, v)
            ok, mm = vs.ValidNumStr(vs.GetItemText(dlg, 205).strip() or '0')
            result['TagWidthMM'] = max(0.0, mm) if ok else 0.0
            for cid, _label, field in shows:
                result[field] = 'True' if vs.GetBooleanItem(dlg, cid) else 'False'
            result['CollapseClosed'] = radios.chosen(CLOSED) or 'True'
            if has_tag_line:
                result['TagLine'] = radios.chosen(LINES) or TAG_LINES[0]
            result['NumberPrefix'] = safe_text(vs.GetItemText(dlg, 302).strip()) or '#'
            picked = _choice_text(vs.GetSelectedChoiceInfo(dlg, 304, 0))
            if picked:
                result['CopyNumbering'] = picked
            result['ClassTemplate'] = safe_text(vs.GetItemText(dlg, 402).strip())
            result['LeaderMarkers'] = write_markers(
                radios.chosen(MARKERS) is not False,
                (tuple(vs.GetMarkerValue(dlg, 506)), vs.GetBooleanItem(dlg, 507)),
                (tuple(vs.GetMarkerValue(dlg, 509)), vs.GetBooleanItem(dlg, 510)))
        return item

    if vs.RunLayoutDialog(dlg, handler) != 1 or not result:
        return None
    return result


def settings_dialog(h, rec):
    """Settings...: what a comment rarely changes (and a style shares).
    Fields the comment's style controls are greyed. True if OK."""
    def get(name):
        return vs.GetRField(h, rec, name)

    paper = Params(h, rec).paper
    ok, tw = vs.ValidNumStr(get('TagWidth').strip())
    tag_mm = tw / paper if ok and tw > 0 and paper > 0 else 0.0
    styled_cache = {}

    def styled(field):
        if field not in styled_cache:
            styled_cache[field] = by_style(h, field)
        return styled_cache[field]

    result = settings_form('Comment Settings', get, styled, tag_mm, status=Params(h, rec).status)
    if result is None:
        return False
    mm = result.pop('TagWidthMM', 0.0)
    # the window shows the width to 0.1 mm: unchanged, the exact width stays
    if mm > 0 and not (tag_mm and abs(mm - round(tag_mm, 1)) < 1e-6):
        result['TagWidth'] = '%.6f' % (mm * paper)
    for field, value in result.items():
        if not styled(field) and value != get(field):
            vs.SetRField(h, rec, field, value)
    return True


def edit_note(h, rec):
    """Edit Comment button / double-click: the Comment dialog with the
    current values. Cancel leaves the comment as it was."""
    if comment_dialog(h, rec):
        vs.ResetObject(h)


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


def selected_comments(rec, h):
    """The selected comments Object Info is showing: those beside h (its
    layer, or the viewport annotations / group it is in). Comments left
    selected on other layers are not touched."""
    found = []
    try:
        parent = vs.GetParent(h)
        on_layer = vs.GetTypeN(parent) == 31
        # Object Info refreshes often (widget prep): on a layer, skip the walk
        # when h is the only selected object, and stop once every selected
        # object there has been seen.
        left = vs.NumSObj(parent) if on_layer else -1
        if left == 1 and vs.Selected(h):
            return [h]
        o = vs.FInLayer(parent) if on_layer else vs.FInGroup(parent)
        while o:
            if vs.Selected(o):
                if vs.GetTypeN(o) == 86:
                    r = vs.GetParametricRecord(o)
                    if r and vs.GetName(r) == rec:
                        found.append(o)
                left -= 1
                if left == 0:
                    break
            o = vs.NextObj(o)
    except Exception:
        import traceback
        _log(traceback.format_exc())
    return found


def widget_prep(h, rec):
    p = Params(h, rec)
    disabled = set(READ_ONLY)
    # Audience / Type not used: hidden
    hidden = set()
    if not p.use_audience:
        hidden.add('Audience')
    if not p.use_type:
        hidden.add('CommentType')
    for hid, heading, params in _widget_ids():
        for wid, name in params:
            vs.vsoWidgetSetVisible(wid, name not in hidden)
            vs.vsoWidgetSetEnable(wid, name not in disabled)
        group = BUTTON_GROUPS.get(heading)
        vs.vsoWidgetSetVisible(hid, not group or group[0] not in hidden)
    # Buttons: the current value marked; no mark when the selected comments differ.
    others = [Params(o, rec) for o in selected_comments(rec, h) if o != h]
    for field, attr, buttons in BUTTON_GROUPS.values():
        values = {getattr(q, attr) for q in [p] + others}
        current = values.pop() if len(values) == 1 else None
        styled = by_style(h, field)                 # the style sets it: greyed
        for bid, value in buttons:
            vs.vsoWidgetSetVisible(bid, field not in hidden)
            vs.vsoWidgetSetEnable(bid, not styled)
            vs.vsoWidgetSetText(bid, (CURRENT_MARK % value) if value == current else value)
    vs.vsoSetEventResult(kObjectEventHandled)


def run():
    try:
        event, _button = vs.vsoGetEventInfo()
    except Exception:
        event = 0

    if event == kObjOnInitXProperties:
        init_layout()
        return

    ok, rec, h, _rec_h, _wall_h = vs.GetCustomObjectInfo()
    if not ok:
        return
    if event == kObjOnAddState:
        _log('state event', _button, 'on', vs.GetRField(h, rec, 'Number'))
        try:
            vs.vsoSetEventResult(vs.vsoStateAddCurrent(h, _button))
        except Exception as e:
            _log('add state', repr(e))
        # Duplicating sends state events but no redraw: a copy (same number
        # as an earlier comment) is made a new comment here and redrawn.
        try:
            p = Params(h, rec)
            if is_copy(p):
                make_new_copy(p)
                _tool['redraw'] = p.number
                vs.ResetObject(h)
                vs.ReDrawAll()
            elif _tool.get('redraw') and _tool['redraw'] == p.number:
                _tool['redraw'] = None      # second duplicate message: redraw again
                vs.ResetObject(h)
                vs.ReDrawAll()
        except Exception:
            import traceback
            _log(traceback.format_exc())
        return
    if event == kObjOnWidgetPrep:
        widget_prep(h, rec)
    elif event == kObjOnSpecialEdit:
        edit_note(h, rec)
        vs.vsoSetEventResult(kObjectEditResult_DoNothing)
    elif event == kObjOnEditPluginStyle:
        vs.vsoSetEventResult(kObjectEditPluginStyleByDefault)
    elif event == kObjOnUIButtonHit:
        if _button == EDIT_BUTTON_ID:
            edit_note(h, rec)
        elif _button == SETTINGS_BUTTON_ID:
            if settings_dialog(h, rec):
                vs.ResetObject(h)
        elif _button == ABOUT_WEB_ID:
            open_website()
        elif _button == ABOUT_UPDATE_ID:
            check_updates()
        else:
            if _button in BUTTON_VALUES:
                field, value = BUTTON_VALUES[_button]
                # Vectorworks sends the click to one comment: set them all,
                # except where the comment's style sets the field
                for other in selected_comments(rec, h) or [h]:
                    if vs.GetRField(other, rec, field) != value and not by_style(other, field):
                        vs.SetRField(other, rec, field, value)
                        vs.ResetObject(other)
    elif event in (kResetEventID, 0):
        try:
            reset(h, rec)
        except Exception:
            _reset_failed(vs.GetRField(h, rec, 'Number'))


# --------------------------------------------------------------------------
# Comment tool (a separate Tool plug-in, "Comment")
# --------------------------------------------------------------------------
#
# Draws a comment's outline with the same modes as the Vectorworks Redline
# tool (Ellipse, Rectangle, Polygon, Freehand), then makes it a Comment Tool
# object. Vectorworks collects the points and draws the preview itself
# (vstSetPtBehavior); the tool only turns the result into a comment.
# Event numbers are from the Vectorworks SDK (MiniCadCallBacks.h).

OBJECT_NAME = 'Comment Tool'


MODE_ELLIPSE, MODE_RECT, MODE_POLY, MODE_FREEHAND, MODE_PIN = 1, 2, 3, 4, 5
MODE_ICONS = ('Vectorworks/ModeViewBar/Oval_Mode.svg',
              'Vectorworks/ModeViewBar/Rectangle_Mode.svg',
              'Vectorworks/ModeViewBar/Vertex_Mode.svg',
              'Vectorworks/ModeViewBar/Freehand_Mode.svg',
              'Vectorworks/ModeViewBar/Callout_Mode3.svg')
# vstSetPtBehavior: 102 ellipse, 101 box, 4 points until double-click, 103 freehand
PT_BEHAVIOUR = {MODE_ELLIPSE: 102, MODE_RECT: 101, MODE_POLY: 4, MODE_FREEHAND: 103,
                MODE_PIN: 2}
HELP = {
    MODE_ELLIPSE: 'Ellipse: click one corner, then the opposite corner',
    MODE_RECT: 'Rectangle: click one corner, then the opposite corner',
    MODE_POLY: 'Polygon: click each corner, double-click to finish',
    MODE_FREEHAND: 'Freehand: drag around the area',
    MODE_PIN: 'Pin: click the point, then where the note goes',
}
ELLIPSE_SEGMENTS = 32


# --- Tool preferences (per user, remembered between sessions) -------------

OUTLINES = ('Line', 'Cloud', 'None')
# Presets: the new-comment values plus everything in Settings, stored by the
# comment's own field names (sizes in mm on the sheet).
NEW_COMMENT_FIELDS = ('Audience', 'CommentType', 'From', 'To')
PREF_DEFAULTS = {
    'Audience': 'Internal', 'CommentType': 'Note', 'From': '', 'To': '',
    'Outline': 'Line', 'CloudSize': CLOUD_MM, 'LeaderSetback': 1.5, 'Shoulder': 2.0, 'TagWidthMM': TAG_WIDTH_MM,
    'NumberPrefix': '#', 'CopyNumbering': 'Next number', 'UseType': True, 'UseAudience': True,
    'ShowNumber': True, 'ShowDate': True, 'ShowFrom': False, 'ShowTo': True,
    'CollapseClosed': True, 'TagLine': 'Full width',
    'ClassTemplate': 'Notes-Comment-{Audience}-{Status}', 'LeaderMarkers': '', 'Style': '',
}


def _prefs_path():
    import os
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'Nemetschek', 'Vectorworks', 'comment_tool_prefs.json')


def load_prefs():
    import json
    prefs = dict(PREF_DEFAULTS)
    try:
        with open(_prefs_path(), encoding='utf-8') as f:
            saved = json.load(f)
        for k, v in saved.items():
            if k in PREF_DEFAULTS:
                prefs[k] = v
    except Exception:
        pass
    return prefs


def save_prefs(prefs):
    """Merged into the file, keeping what the drawing tool keeps there too
    (its Mode; same file, see save_tool_prefs)."""
    import json
    import os
    path = _prefs_path()
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


def _pref_text(v):
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, float):
        return '%g' % v
    return str(v)


def prefs_dialog():
    """The spanner button: how new comments start (Type, Audience, From,
    To), what the office tracks (Type, Audience), and Default Settings...
    (the Comment Settings window, saved as the defaults). True if OK."""
    prefs = load_prefs()
    defaults = {}                       # from Default Settings..., saved on OK

    def pref_get(field):
        return _pref_text(defaults.get(field, prefs.get(field, '')))

    TYPE_ROW, AUD_ROW = 602, 607        # radio rows (group ids)
    # (label id, label, field, group id, buttons)
    rows = ((601, 'Type:', 'CommentType', TYPE_ROW, [(603 + i, t, t) for i, t in enumerate(TYPES)]),
            (606, 'Audience:', 'Audience', AUD_ROW, [(608 + i, a, a) for i, a in enumerate(AUDIENCES)]))
    # Use ticks: (tick id, caption, field, the row it greys)
    tracks = ((702, 'Type', 'UseType', rows[0]), (703, 'Audience', 'UseAudience', rows[1]))

    dlg = vs.CreateLayout('Comment Preferences', False, 'OK', 'Cancel')
    radios = RadioRows(dlg)
    for gid, heading in ((600, 'New comments start as'), (700, 'Tracking'), (800, 'Appearance')):
        vs.CreateGroupBox(dlg, gid, heading, True)
    for lid, label, _field, gid, buttons in rows:
        radios.create(lid, label, 12, gid, buttons)
    vs.CreateStaticText(dlg, 610, 'From:', 12)
    vs.CreateEditText(dlg, 611, pref_get('From'), 12)
    vs.CreateStaticText(dlg, 612, 'To:', -1)
    vs.CreateEditText(dlg, 613, pref_get('To'), 12)
    vs.CreateStaticText(dlg, 701, 'Use:', 12)
    for cid, label, _field, _row in tracks:
        vs.CreateCheckBox(dlg, cid, label)
    vs.CreateStaticText(dlg, 704, 'Off hides that row from the palette, dialog and tag', -1)
    vs.CreateStaticText(dlg, 801, 'Defaults:', 12)
    vs.CreatePushButton(dlg, 802, 'Default Settings...')
    vs.CreateStaticText(dlg, 803, 'The Comment Settings window, saved as the default', -1)

    vs.SetFirstLayoutItem(dlg, 600)
    vs.SetFirstGroupItem(dlg, 600, 601)
    prev = None
    for lid, _label, _field, gid, _buttons in rows:
        if prev:
            vs.SetBelowItem(dlg, prev, lid, 0, 0)
        radios.place(lid, gid)
        prev = lid
    vs.SetBelowItem(dlg, prev, 610, 0, 0)
    vs.SetRightItem(dlg, 610, 611, 0, 0)
    vs.SetRightItem(dlg, 611, 612, 1, 0)
    vs.SetRightItem(dlg, 612, 613, 0, 0)
    vs.SetBelowItem(dlg, 600, 700, 0, 1)
    vs.SetFirstGroupItem(dlg, 700, 701)
    vs.SetRightItem(dlg, 701, 702, 0, 0)
    vs.SetRightItem(dlg, 702, 703, 0, 0)
    vs.SetBelowItem(dlg, 701, 704, 0, 0)
    vs.SetBelowItem(dlg, 700, 800, 0, 1)
    vs.SetFirstGroupItem(dlg, 800, 801)
    vs.SetRightItem(dlg, 801, 802, 0, 0)
    vs.SetBelowItem(dlg, 801, 803, 0, 0)
    kRightEdge, kResize = 1, 0              # group boxes the same width
    for gid in (600, 700, 800):
        vs.AlignItemEdge(dlg, gid, kRightEdge, 901, kResize)

    result = {}

    def track_enable():
        """A row that is not tracked is greyed."""
        for cid, _label, _field, (lid, _l, _f, gid, _b) in tracks:
            used = vs.GetBooleanItem(dlg, cid)
            vs.EnableItem(dlg, lid, used)
            radios.enable(gid, used)

    def handler(item, data):
        if item == 12255:
            for _lid, _label, field, gid, buttons in rows:
                values = [v for _b, v, _t in buttons]
                radios.set(gid, match_choice(pref_get(field), values, values[0]))
            for cid, _label, field, _row in tracks:
                vs.SetBooleanItem(dlg, cid, pref_get(field).strip().lower() != 'false')
            for hid in (704, 803):
                vs.EnableItem(dlg, hid, False)      # greyed: descriptions only
            track_enable()
        elif radios.owns(item):
            radios.pick(item)
        elif item in (702, 703):
            track_enable()
        elif item == 802:
            # the same window as Settings..., filled from the defaults
            got = settings_form('Default Comment Settings', pref_get, lambda f: False,
                                float(defaults.get('TagWidthMM', prefs.get('TagWidthMM')) or 0),
                                sample=(radios.chosen(AUD_ROW) or AUDIENCES[0],
                                        radios.chosen(TYPE_ROW) or TYPES[0]))
            if got:
                defaults.update(got)
        elif item == 1:
            for _lid, _label, field, gid, _buttons in rows:
                value = radios.chosen(gid)
                if value:
                    result[field] = value
            result['From'] = safe_text(vs.GetItemText(dlg, 611).strip())
            result['To'] = safe_text(vs.GetItemText(dlg, 613).strip())
            for cid, _label, field, _row in tracks:
                result[field] = 'True' if vs.GetBooleanItem(dlg, cid) else 'False'
        return item

    if vs.RunLayoutDialog(dlg, handler) != 1 or not result:
        return False
    result.update(defaults)
    for k, v in result.items():
        if k == 'TagWidthMM':
            prefs[k] = float(v)
        elif isinstance(PREF_DEFAULTS.get(k), bool):
            prefs[k] = (v == 'True')
        elif isinstance(PREF_DEFAULTS.get(k), float):
            ok, num = vs.ValidNumStr(v)
            prefs[k] = num if ok else PREF_DEFAULTS[k]
        else:
            prefs[k] = v
    save_prefs(prefs)
    return True


def apply_prefs(obj, rec=OBJECT_NAME, paper=1.0):
    """Stamp the presets on a new comment (done in its first reset, before
    the Comment dialog). paper = document units per printed mm. Fields the
    comment's style controls are left to the style."""
    prefs = load_prefs()

    def put(field, value):
        if not by_style(obj, field):
            try:
                vs.SetRField(obj, rec, field, value)
            except Exception as e:
                _log('preset', field, repr(e))

    for field in NEW_COMMENT_FIELDS + SETTINGS_FIELDS:
        put(field, safe_text(_pref_text(prefs.get(field, ''))))
    mm = float(prefs.get('TagWidthMM') or 0)
    if mm > 0:
        put('TagWidth', '%.6f' % (mm * paper))


def shape_points(mode, a, b):
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    if mode == MODE_ELLIPSE:
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        return [(cx + rx * math.cos(2 * math.pi * k / ELLIPSE_SEGMENTS),
                 cy + ry * math.sin(2 * math.pi * k / ELLIPSE_SEGMENTS))
                for k in range(ELLIPSE_SEGMENTS)]
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def create_comment(pts, state=''):
    """Make a Comment Tool object on the outline pts. state: written into
    State before the first reset (PIN_MARK for a pin)."""
    vs.ClosePoly()
    vs.BeginPoly()
    for x, y in pts:
        vs.AddPoint(x, y)
    vs.EndPoly()
    poly = vs.LNewObj()
    obj = None
    for nil in (None, vs.Handle(0) if hasattr(vs, 'Handle') else None):
        try:
            obj = vs.CreateCustomObjectPath(OBJECT_NAME, poly, nil)
            break
        except Exception:
            continue
    # Remove the temporary outline if it was copied rather than used, or if
    # no comment was made; never when it is (or might be) the comment's path.
    try:
        parent = vs.GetParent(poly)
        used = obj and vs.GetCustomObjectPath(obj) == poly
        on_layer = parent and vs.GetTypeN(parent) == 31
        _log('placed: path is the drawn shape', bool(used), '| shape still on layer', bool(on_layer))
        if on_layer and not used:
            vs.DelObject(poly)
    except Exception:
        pass
    if obj:
        apply_tool_style(obj, load_prefs().get('Style', '').strip())
        if state and not vs.GetRField(obj, OBJECT_NAME, 'State').strip():
            vs.SetRField(obj, OBJECT_NAME, 'State', state)
        vs.ResetObject(obj)
    _log('created', obj, len(pts), 'points')
    return obj


def _object_points(h):
    """Outline points of the object Vectorworks drew for the tool."""
    pts = []
    tmp = None
    try:
        tmp = vs.ConvertToPolygon(h, ELLIPSE_SEGMENTS)      # a new polygon; h is kept
        if tmp:
            pts = [tuple(vs.GetPolyPt(tmp, i)) for i in range(1, vs.GetVertNum(tmp) + 1)]
    except Exception:
        import traceback
        _log(traceback.format_exc())
    finally:
        if tmp and tmp != h:                # never the tool object itself (deleted by _complete)
            try:
                vs.DelObject(tmp)
            except Exception:
                pass
    if len(pts) > 2 and _dist(pts[0], pts[-1]) < 1e-9:
        pts.pop()
    return pts


DEBUG_LOG = False      # True writes tool_debug.log next to this file (testing)


# --- Comment tool (the .vst): what its clicks make --------------------------
TOOL_OBJECT = OBJECT_NAME
TOOL_NAME = 'Comment'
TOOL_MODES = tuple((MODE_ICONS[m - 1], PT_BEHAVIOUR[m], HELP[m]) for m in sorted(HELP))
TOOL_FIRST_MODE = MODE_RECT
TOOL_PULLDOWNS = ()
TOOL_DEFAULTS = ()      # the spanner is the Comment Preferences (tool_spanner)


def tool_spanner():
    prefs_dialog()


def tool_complete(mode, clicked, h):
    """Make the comment from the clicks (h, the tool's own object, is deleted
    by the drawing-tool block afterwards)."""
    if mode == MODE_PIN and clicked:
        # a tiny square round the point: no outline is drawn, just the dot
        (x, y), e = clicked[0], 0.005
        # The tag click goes on the object as an offset from the point (the
        # first reset can run after this returns, see PIN_MARK).
        state = PIN_MARK
        if len(clicked) >= 2:
            (tx, ty) = clicked[-1]
            side = 1.0 if tx >= x else -1.0
            state += '%.6f;%.6f;%g' % (tx - x, ty - y, side)
        create_comment([(x - e, y - e), (x + e, y - e), (x + e, y + e), (x - e, y + e)], state)
        return
    pts = []
    if mode in (MODE_RECT, MODE_ELLIPSE) and len(clicked) >= 2:
        pts = shape_points(mode, clicked[0], clicked[-1])
    if not pts and h:
        pts = _object_points(h)
    if not pts and len(clicked) >= 3:
        pts = clicked
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if len(pts) >= 3 and max(xs) - min(xs) > 1e-6 and max(ys) - min(ys) > 1e-6:
        create_comment(pts)


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
