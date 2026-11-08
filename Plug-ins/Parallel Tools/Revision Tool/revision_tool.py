"""
Revision Tool for Vectorworks 2026 / 2027

Copyright (c) 2026 Ian Thrush
Licensed under the MIT License (see LICENSE.md).

A drawing revision as one path plug-in object: a revision cloud around the
change, a leader, a marker (triangle, circle or square) with the revision
(A, B, 1, #) and the date and note beside it. Replaces a Revision Cloud
object + record + Data Tag + class:
- colour comes from the class (Revision-A, Revision-B ...), never hardcoded
- one object per change: three Rev A changes on a sheet are three objects,
  each with its own note
- every Rev A on the same sheet shares one date: change it on one and the
  others follow. Rev A on another sheet keeps its own date
- the marker moves by dragging its control point; the text follows it
- Show Latest: the latest revisions on each sheet in colour (2 by default),
  older ones grey with a thin line, cloud kept

Built from the Comment Tool. The .vso holds a short loader stub; all logic
lives here.
"""

import datetime
import math

import vs

VERSION = '0.8.1'
VERSION_DATE = '2026-11-09'
WEBSITE = 'github.com/itchyNZL/parallel-tools'
TOOL_FOLDER = 'Revision Tool'

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
kObjXPropAcceptStatesInternal = 19      # incl. duplicate / paste states
kObjOnAddState = 44
kObjOnEditPluginStyle = 60
kObjectEditPluginStyleByDefault = -10   # reply: use the default style dialog
EDIT_BUTTON_ID = 3000
SETTINGS_BUTTON_ID = 3001
ABOUT_WEB_ID = 3002
ABOUT_UPDATE_ID = 3101
REFRESH_SHEET_ID = 3003
TITLE_BLOCK_ID = 3004

OUTLINES = ('Cloud', 'Line')
MARKERS = ('Triangle', 'Circle', 'Square', 'Hexagon')
# Line under the date: none, as long as the date, or to the end of the text
TEXT_LINES = ('None', 'Date', 'Text')
# Note alignment: Auto = to the marker's side (left when the text is right of
# the marker, right when it is left of it); the date always does that
NOTE_ALIGNS = ('Auto', 'Left', 'Right')
# Billow height: how far each scallop bulges, as a share of its half length
CLOUD_HEIGHTS = {'Low': 0.4, 'Medium': 0.65, 'High': 0.9}
NEW_SHEET = '#'                 # revision for a sheet added after the first issue
NEW_SHEET_NOTE = 'New sheet'

# Colour for each revision class when the tool creates it (0-255 RGB), in
# order A, B, C ... (1, 2, 3 ... the same). After that the class is the
# office's to change: the tool never sets it again.
REV_COLOURS = (
    (210, 35, 35),      # red
    (0, 150, 220),      # blue
    (20, 135, 45),      # green
    (175, 45, 165),     # magenta
    (220, 125, 0),      # orange
    (0, 130, 130),      # teal
    (95, 65, 185),      # purple
    (140, 90, 40),      # brown
)
NEW_SHEET_COLOUR = (20, 135, 45)
CLASS_WEIGHT = 10               # mils: 0.25 mm
# Older revisions (Show Latest): drawn in grey, thin, cloud kept
OLD_COLOUR = (150, 150, 150)
OLD_WEIGHT = 2                  # mils: 0.05 mm (was 0.13 mm, heavier than a 0.05 mm class)
SHOW_LATEST = 2                 # revisions per sheet in colour (0 = all)

# Paper sizes (mm on the printed sheet), scaled by the layer scale
MARKER_MM = 6.0         # marker size when Marker Size is 0
MARKER_OFFSET_MM = 8.0  # first placement: marker this far up and right of the cloud
CLOUD_MM = 6.0          # cloud scallop length when Cloud Size is 0
TEXT_GAP_MM = 1.5       # text clear of the marker
MIN_WRAP_MM = 5.0       # narrowest the wrap dot can make the text
LINE_GAP_MM = 0.6       # date above and note below the marker's centre line, this far off it
MITRE_LIMIT = 3.0       # an offset corner goes at most this many offsets past its vertex


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------


def _today():
    """ISO date (2026-10-20): unambiguous and sorts in worksheets."""
    return datetime.date.today().isoformat()


def iso_date(text):
    """A date typed as dd/mm/yy (or dd/mm/yyyy, dd.mm.yy) -> ISO. ISO and
    anything not read as a date are kept as typed."""
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


def sheet_date(iso):
    """2026-02-17 -> 17/02/26 on the sheet; the record keeps the ISO date."""
    try:
        d = datetime.date.fromisoformat(iso_date(iso))
        return d.strftime('%d/%m/%y')
    except Exception:
        return iso


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


def show_latest(text):
    """Show Latest as a whole number: blank (or not a number) = 2, 0 = all."""
    try:
        return max(0, int(round(float((text or '').strip()))))
    except ValueError:
        return SHOW_LATEST


def clean_rev(text):
    """Revision as stored: trimmed, letters upper case, at most 4 characters."""
    return safe_text((text or '').strip().upper())[:4].replace('|', '')


class Params:
    def __init__(self, h, rec):
        self.h = h
        self.rec = rec
        self.mm = _mm()
        try:
            scale = annotation_scale(h) or vs.GetLScale(vs.GetLayer(h))
        except Exception:
            scale = 1.0
        self.scale = scale if scale and scale > 0 else 1.0
        self.paper = self.mm * self.scale     # document units per printed mm

        self.rev = clean_rev(self._str('Rev'))
        self.date = iso_date(self._str('Date'))
        self.note = decode_note(self._str('Note'))
        self.outline = match_choice(self._str('Outline'), OUTLINES, 'Cloud')
        cloud_mm = self._num('CloudSize')
        self.cloud = max(cloud_mm if cloud_mm > 0 else CLOUD_MM, 1.0) * self.paper
        self.cloud_height = CLOUD_HEIGHTS[match_choice(self._str('CloudHeight'),
                                                       tuple(CLOUD_HEIGHTS), 'Medium')]
        self.offset = max(0.0, self._num('CloudOffset')) * self.paper
        self.marker =match_choice(self._str('MarkerShape'), MARKERS, 'Triangle')
        size_mm = self._num('MarkerSize')
        self.marker_size = (size_mm if size_mm > 0 else MARKER_MM) * self.paper
        self.show_leader = self._str('ShowLeader').strip().lower() != 'false'
        self.shoulder = max(0.0, self._num('Shoulder')) * self.paper
        self.setback = max(0.0, self._num('LeaderSetback')) * self.paper
        self.show_date = self._str('ShowDate').strip().lower() != 'false'
        self.show_note = self._str('ShowNote').strip().lower() != 'false'
        # Show Tag off: the cloud only (no marker, leader, date or note)
        self.show_tag = self._str('ShowTag').strip().lower() != 'false'
        self.note_width = max(0.0, self._num('NoteWidth')) * self.paper
        self.text_line = match_choice(self._str('TextLine'), TEXT_LINES, 'None')
        self.note_align = match_choice(self._str('NoteAlign'), NOTE_ALIGNS, 'Auto')
        self.class_template = self._str('ClassTemplate').strip()
        self.show_latest = show_latest(self._str('ShowLatest'))

    def _str(self, name):
        return vs.GetRField(self.h, self.rec, name)

    def _num(self, name, default=0.0):
        ok, v = vs.ValidNumStr(self._str(name).strip())
        return v if ok else default

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
    Nothing inside the object is copied, converted or deleted (see Comment
    Tool 0.19.2: doing so could delete the object's own path)."""
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


def offset_outline(pts, d):
    """The closed outline moved d outwards, with mitred corners, so the cloud
    stands clear of an outline snapped to the object. An edge that an inside
    corner or narrow notch swallows (short ones on a freehand outline) is
    dropped; a very sharp corner stops at MITRE_LIMIT. Returns pts itself if
    d is 0 or the outline has no area."""
    clean = [q for i, q in enumerate(pts) if _dist(q, pts[i - 1]) > 1e-9]
    area = signed_area(clean) if len(clean) >= 3 else 0.0
    if d <= 0 or abs(area) < 1e-9:
        return pts
    ccw = area > 0
    n = len(clean)
    edges = []                  # (start, end, unit direction, outward normal)
    for i in range(n):
        a, b = clean[i], clean[(i + 1) % n]
        L = _dist(a, b)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        edges.append((a, b, (ux, uy), (uy, -ux) if ccw else (-uy, ux)))

    def corner(e1, e2):
        """Where the offset lines of two edges in turn meet, kept near e1's end."""
        ref = e1[1]
        n1, n2 = e1[3], e2[3]
        c1 = n1[0] * e1[0][0] + n1[1] * e1[0][1] + d
        c2 = n2[0] * e2[0][0] + n2[1] * e2[0][1] + d
        det = n1[0] * n2[1] - n1[1] * n2[0]
        if abs(det) < 1e-6:                     # in line (or doubling back)
            return (ref[0] + n1[0] * d, ref[1] + n1[1] * d)
        q = ((c1 * n2[1] - c2 * n1[1]) / det, (c2 * n1[0] - c1 * n2[0]) / det)
        far = _dist(q, ref)
        limit = MITRE_LIMIT * d
        if far > limit:
            q = (ref[0] + (q[0] - ref[0]) * limit / far, ref[1] + (q[1] - ref[1]) * limit / far)
        return q

    while len(edges) >= 3:
        m = len(edges)
        out = [corner(edges[i - 1], edges[i]) for i in range(m)]    # out[i] starts edge i
        # A corner closer to the outline than the offset is in a notch too
        # narrow to follow. Not checked on very long outlines: too slow.
        clear = [n > 500 or _dist(q, nearest_on_outline(clean, q)) > d * 0.99 for q in out]
        keep = []
        for i in range(m):
            j = (i + 1) % m
            q, r = out[i], out[j]
            u = edges[i][2]
            if clear[i] and clear[j] and (r[0] - q[0]) * u[0] + (r[1] - q[1]) * u[1] > 0:
                keep.append(edges[i])
        if len(keep) == m:
            return out
        edges = keep
    return pts


def cloud_scallops(pts, size, height=0.65):
    """Revision cloud: round scallops about `size` long bulging outwards
    along each edge of the closed outline. height: how far a scallop bulges,
    as a share of its half length (under 1: a true arc, less than a half
    circle). Each scallop is (start, end, corner, radius, centre): drawn as
    one arc vertex at `corner` (where the arc's end tangents meet) with that
    radius, so Vectorworks draws a smooth curve (0.3.0; it was 8 straight
    lines a scallop, which looked jagged)."""
    out = []
    n = len(pts)
    ccw = signed_area(pts) > 0
    # no more than about 400 scallops, however small the size
    perimeter = sum(_dist(pts[i], pts[(i + 1) % n]) for i in range(n))
    size = max(size, perimeter / 400.0)
    h = min(max(height, 0.1), 0.95)
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
        r = seg / 2.0                       # half chord
        sag = h * r                         # how far the arc bulges
        R = (r * r + sag * sag) / (2.0 * sag)
        tip = r * math.tan(math.asin(r / R))    # end tangents meet this far out
        for j in range(k):
            s = (a[0] + ux * j * seg, a[1] + uy * j * seg)
            e = (a[0] + ux * (j + 1) * seg, a[1] + uy * (j + 1) * seg)
            mx, my = (s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0
            corner = (mx + nx * tip, my + ny * tip)
            centre = (mx + nx * (sag - R), my + ny * (sag - R))
            out.append((s, e, corner, R, centre))
    return out


def cloud_points(scallops, steps=8):
    """Points along the scallop arcs (for the leader's nearest point)."""
    out = []
    for s, e, _corner, R, c in scallops:
        a0 = math.atan2(s[1] - c[1], s[0] - c[0])
        a1 = math.atan2(e[1] - c[1], e[0] - c[0])
        mid = math.atan2(_corner[1] - c[1], _corner[0] - c[0])
        sweep = (a1 - a0) % (2 * math.pi)
        # go round the side the scallop bulges to (through `mid`)
        if (mid - a0) % (2 * math.pi) > sweep:
            sweep -= 2 * math.pi
        for k in range(steps):
            t = a0 + sweep * k / steps
            out.append((c[0] + R * math.cos(t), c[1] + R * math.sin(t)))
    return out


TRI_H = math.sqrt(3) / 2.0      # equilateral triangle height per side


def marker_shape(shape, c, s):
    """Marker outline points (triangle / square / hexagon), or None for a
    circle. c: centre of the marker's bounding box, s: side / diameter (the
    hexagon's width point to point; flat top and bottom)."""
    cx, cy = c
    r = s / 2.0
    if shape == 'Triangle':
        h = s * TRI_H
        return [(cx - r, cy - h / 2), (cx + r, cy - h / 2), (cx, cy + h / 2)]
    if shape == 'Square':
        return [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
    if shape == 'Hexagon':
        return [(cx + r * math.cos(math.pi * k / 3), cy + r * math.sin(math.pi * k / 3))
                for k in range(6)]
    return None


def marker_text_centre(shape, c, s):
    """Where the revision sits in the marker: a triangle's centroid, which
    is a sixth of its height below the box centre."""
    if shape == 'Triangle':
        return (c[0], c[1] - s * TRI_H / 6.0)
    return c


def marker_reach(shape, s):
    """How far the marker's edge is from its centre along the centre line,
    where the shoulder joins it: a triangle's side at mid height (s / 4; it
    joined at the base corner until 0.4.1, off the line the other shapes
    use), else half the size (a hexagon's point)."""
    return s / 4.0 if shape == 'Triangle' else s / 2.0


def marker_attach(shape, c, s, side):
    """Where the shoulder leaves the marker on side -1 (left) or +1 (right),
    on the marker's centre line."""
    return (c[0] + side * marker_reach(shape, s), c[1])


# --------------------------------------------------------------------------
# Classes
# --------------------------------------------------------------------------

def class_name(template, rev):
    """Revision-{Rev} -> Revision-A. Blank template: the object's own class."""
    if not template:
        return ''
    return template.replace('{Rev}', rev).replace('{rev}', rev).strip()[:63]


def rev_colour(rev):
    """Starting colour of a new revision class: A / 1 red, B / 2 blue ..."""
    r = (rev or '').strip().upper()
    if r == NEW_SHEET or not r:
        return NEW_SHEET_COLOUR
    if r.isdigit():
        i = int(r) - 1
    elif r[0].isalpha():
        i = ord(r[0]) - ord('A')
    else:
        return NEW_SHEET_COLOUR
    return REV_COLOURS[max(i, 0) % len(REV_COLOURS)]


def show_class(h, name):
    """A new revision's class is turned on if it is off or greyed, so placing
    one never looks like nothing happened. In a viewport's annotations the
    viewport's class visibility is the one that counts."""
    if not name:
        return
    vp = _viewport_of(h)
    try:
        vis = vs.GetVPClassVisibility(vp, name) if vp else vs.GetCVis(name)
    except Exception:
        vis = None
    if vis == 0:                                    # 0 = visible
        return
    try:
        if vp:
            vs.SetVPClassVisibility(vp, name, 0)
        else:
            vs.ShowClass(name)
    except Exception as e:
        _log('show class', name, repr(e))


ovViewportScale = 1003


def annotation_scale(h):
    """The viewport's scale (50 for 1:50) if h is in a viewport's
    annotations, which are drawn at that scale; else None. (0.4.3 used the
    sheet's 1:1 there: everything came out 1/50 of its size.)"""
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
    """The viewport whose annotations hold h, or None. Tries, in turn:
    the parents (an annotation group may not give its viewport as parent:
    0.4.4 found none, so annotation revisions drew at 1:1), GetVPGroupParent,
    and last every viewport in the file, matching its annotation group to
    h's parent (this also learns which GetVPGroup kind is the annotations)."""
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
                if _vp_kind['annotations'] != kind:
                    _log('viewport annotations are GetVPGroup kind', kind)
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


LINE_TYPE_RESOURCE = 96         # resource list type for line types


def _dash_line_style():
    """A dashed line type in this file, as a class line style value
    (negative resource index), or None to leave the class solid."""
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


def ensure_class(name, rev):
    """Create the class if missing: revision colour for pen and fill, no
    fill, dashed, Use at Creation. A class that already exists (the office's
    Revision-A etc.) is left exactly as it is."""
    if not name or vs.Name2Index(name) != 0:
        return
    if not _new_class(name):
        return
    r, g, b = rev_colour(rev)
    rgb = (r * 257, g * 257, b * 257)
    _set_class_colour('SetClPenFore', 'GetClPenFore', name, rgb)
    _set_class_colour('SetClFillFore', 'GetClFillFore', name, rgb)
    dash = _dash_line_style()
    calls = [lambda: vs.SetClFPat(name, 0), lambda: vs.SetClUseGraphic(name, True),
             lambda: vs.SetClLW(name, CLASS_WEIGHT)]
    if dash is not None:
        calls.append(lambda: vs.SetClLSN(name, dash))
    for call in calls:
        try:
            call()
        except Exception as e:
            _log('class setting failed', name, repr(e))
    _log('class made', name)


# Object variable 800 on: text the script creates uses the object's own
# Text > Format Text settings (font, size, style). Alignment is not kept, so
# the script sets it on each text.
ovUsePIOTextAttributes = 800


# The call form for a pen / fill colour that worked (index into the forms in
# _set_colour), found on first use and kept while the module is loaded.
_colour_form = {}


def _set_colour(fn, h, rgb):
    """Pen / fill colour on an object, checked by reading it back: the
    Python call form varies, and a wrong one can give black without an
    error (0.2.2: older revisions came out black)."""
    get = 'GetPenFore' if fn == 'SetPenFore' else 'GetFillFore'
    forms = ((h,) + rgb, (h, rgb))
    known = _colour_form.get(fn)
    order = [known] if known is not None else range(len(forms))
    for i in order:
        try:
            getattr(vs, fn)(*forms[i])
        except Exception as e:
            _log(fn, 'form', i, 'failed', repr(e))
            continue
        try:
            got = getattr(vs, get)(h)
        except Exception as e:
            got = repr(e)
        if known is not None or _close_rgb(got, rgb):
            _colour_form[fn] = i
            return
        _log(fn, 'form', i, 'read back', got, 'wanted', rgb)
    # No form read back right: try colour index instead
    try:
        index = vs.RGBToColorIndex(rgb)
        index = index[-1] if isinstance(index, tuple) else index
        getattr(vs, fn)(h, index)
        _log(fn, 'by colour index', index, 'read back', getattr(vs, get)(h))
    except Exception as e:
        _log(fn, 'colour index failed', repr(e))


class Painter:
    """Puts each new object in the revision's class, attributes by class.
    old: an older revision (Show Latest), grey and thin instead; still in
    its class, so turning the class off still hides it."""

    def __init__(self, p, old=False):
        self.old = old
        self.cls = class_name(p.class_template, p.rev)
        ensure_class(self.cls, p.rev)
        # The object itself goes in the same class, so Object Info shows it
        # and turning the class off hides the whole revision.
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
        if self.old:
            # pen and fill both: text takes its colour from one of them,
            # and the fill pattern stays off
            rgb = tuple(c * 257 for c in OLD_COLOUR)
            _set_colour('SetPenFore', h, rgb)
            _set_colour('SetFillFore', h, rgb)
            try:
                vs.SetLW(h, OLD_WEIGHT)
            except Exception:
                pass
        return h

    def solid(self, h):
        """Solid line, class colour and weight: the marker stays crisp when
        the class is dashed."""
        try:
            vs.SetLSN(h, 2)
        except Exception:
            pass
        return h

    def cloud(self, scallops):
        """Closed polyline: a corner at each scallop's start, then one arc
        vertex (smooth). Falls back to points along the arcs if this
        Vectorworks will not take ArcTo."""
        vs.ClosePoly()
        vs.BeginPoly()
        form = _tool.get('arcto')
        ok = True
        for s, _e, corner, R, _c in scallops:
            vs.AddPoint(s[0], s[1])
            if form is None:
                for i, args in enumerate(((corner[0], corner[1], R), (corner, R))):
                    try:
                        vs.ArcTo(*args)
                        form = _tool['arcto'] = i
                        break
                    except Exception as e:
                        _log('ArcTo form', i, repr(e))
                if form is None:
                    ok = False
                    break
            else:
                vs.ArcTo(*((corner[0], corner[1], R), (corner, R))[form])
        vs.EndPoly()
        if not ok:
            vs.DelObject(vs.LNewObj())
            return self.poly(cloud_points(scallops), closed=True)
        h = self.finish(vs.LNewObj())
        try:
            vs.SetFPat(h, 0)
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
        h = self.finish(vs.LNewObj())
        try:
            vs.SetFPat(h, 0)
        except Exception:
            pass
        return h

    def line(self, a, b):
        vs.MoveTo(a[0], a[1])
        vs.LineTo(b[0], b[1])
        return self.finish(vs.LNewObj())

    def circle(self, c, d):
        r = d / 2.0
        vs.Oval(c[0] - r, c[1] + r, c[0] + r, c[1] - r)
        h = self.finish(vs.LNewObj())
        try:
            vs.SetFPat(h, 0)
        except Exception:
            pass
        return h

    def text(self, origin, s, just=1, valign=3, wrap=None):
        vs.TextOrigin(origin[0], origin[1])
        vs.CreateText(s)
        h = vs.LNewObj()
        self.finish(h)
        vs.SetTextJust(h, just)                 # 1 left, 2 centre, 3 right
        vs.SetTextVerticalAlign(h, valign)      # 1 top, 3 centre, 5 bottom
        if wrap:
            vs.SetTextWrap(h, True)
            vs.SetTextWidth(h, wrap)
        try:
            vs.SetFPat(h, 0)                    # no background behind the text
        except Exception:
            pass
        return h


# --------------------------------------------------------------------------
# Revision data
# --------------------------------------------------------------------------

def _record_name(rec):
    """GetCustomObjectInfo gives the plug-in (record) name as a string."""
    return rec if isinstance(rec, str) and rec else OBJECT_NAME


def sheet_of(h):
    """The sheet (layer name, A21) the revision is on: its sheet layer, or
    the sheet of the viewport whose annotations hold it. On a design layer
    this is the layer name."""
    try:
        vp = _viewport_of(h)
        return safe_text((vs.GetLName(vs.GetLayer(vp or h)) or '').strip())
    except Exception as e:
        _log('sheet: no layer', repr(e))
        return ''


def _uuid(h):
    try:
        return vs.GetObjectUuid(h) or ''
    except Exception:
        return ''


def siblings(rec, h, sheet, rev):
    """The other revisions with the same Rev on the same sheet."""
    me = _uuid(h)
    return [o for o, r, _d, _n in sheet_revisions(rec, sheet)
            if r == rev and not (o == h or (me and _uuid(o) == me))]


def sibling_date(rec, h, sheet, rev):
    """The date the other revisions of this Rev on this sheet have, or ''."""
    rec_name = _record_name(rec)
    for o in siblings(rec, h, sheet, rev):
        d = iso_date(vs.GetRField(o, rec_name, 'Date'))
        if d:
            return d
    return ''


# Revisions part-way through their redraw (object IDs). One revision's
# redraw can redraw others (shared date, greying); those must never redraw
# one that is still drawing, or it would run inside itself.
_busy = set()


def redraw(o):
    if _uuid(o) not in _busy:
        vs.ResetObject(o)


def share_date(rec, h, sheet, rev, date):
    """Give every other Rev on this sheet the same date, and redraw them."""
    rec_name = _record_name(rec)
    for o in siblings(rec, h, sheet, rev):
        if iso_date(vs.GetRField(o, rec_name, 'Date')) != date:
            vs.SetRField(o, rec_name, 'Date', date)
            redraw(o)
            _log('date shared', rev, sheet, date)


def sheet_revisions(rec, sheet):
    """Every revision on the sheet: [(handle, rev, date, show latest)]."""
    rec_name = _record_name(rec)
    found = []

    def look(o):
        if sheet_of(o) != sheet:          # the layer it is on now, not the stored name
            return
        rev = clean_rev(vs.GetRField(o, rec_name, 'Rev'))
        if rev:
            found.append((o, rev, iso_date(vs.GetRField(o, rec_name, 'Date')),
                          show_latest(vs.GetRField(o, rec_name, 'ShowLatest'))))

    if sheet:
        try:
            vs.ForEachObject(look, "(R IN ['%s'])" % rec_name)
        except Exception:
            import traceback
            _log(traceback.format_exc())
        # ForEachObject does not look inside viewport annotations
        seen = {_uuid(e[0]) for e in found}
        for o in annotation_revisions(rec_name, sheet):
            uid = _uuid(o)
            if uid and uid in seen:
                continue
            seen.add(uid)
            look(o)
    return found


kViewport, kGroup, kPIO = 122, 11, 86
kVPAnnotations = 2          # GetVPGroup: the annotation group


def annotation_revisions(rec_name, sheet):
    """Revisions inside the annotations of the viewports on a sheet."""
    out = []
    try:
        layer = vs.GetLayerByName(sheet)
    except Exception:
        layer = None
    if not layer:
        return out

    def walk(group, depth=0):
        o = vs.FInGroup(group) if group else None
        while o:
            t = vs.GetTypeN(o)
            if t == kPIO:
                r = vs.GetParametricRecord(o)
                if r and vs.GetName(r) == rec_name:
                    out.append(o)
            elif t == kGroup and depth < 6:
                walk(o, depth + 1)
            o = vs.NextObj(o)

    try:
        o = vs.FInLayer(layer)
        while o:
            if vs.GetTypeN(o) == kViewport:
                walk(vs.GetVPGroup(o, _vp_kind['annotations']))
            o = vs.NextObj(o)
    except Exception:
        import traceback
        _log(traceback.format_exc())
    return out


def latest_revs(entries, n):
    """The n latest revisions on a sheet (all of them for n = 0): ordered
    by date, so # and a Rev 1 after Rev C fall in place; same date by
    revision (B after A, AA after Z)."""
    dates = {}
    for _o, rev, date, _n in entries:
        dates[rev] = max(dates.get(rev, ''), date)
    order = sorted(dates, key=lambda r: (dates[r], len(r), r))
    return set(order if n <= 0 else order[-n:])


def is_current(entries, rev, n):
    return rev in latest_revs(entries, n)


def sheet_show_latest(rec, h, sheet):
    """Show Latest of the other revisions on the sheet, or None."""
    for o, _rev, _date, n in sheet_revisions(rec, sheet):
        if not (o == h or (_uuid(h) and _uuid(o) == _uuid(h))):
            return n
    return None


def share_show_latest(rec, h, sheet, n):
    """Give every other revision on the sheet this Show Latest (not those
    whose style sets it) and redraw them."""
    rec_name = _record_name(rec)
    for o, _rev, _date, other in sheet_revisions(rec, sheet):
        if o == h or (_uuid(h) and _uuid(o) == _uuid(h)) or other == n:
            continue
        if by_style(o, 'ShowLatest'):
            continue
        vs.SetRField(o, rec_name, 'ShowLatest', '%d' % n)
        redraw(o)


def regrey_sheet(rec, h, sheet):
    """Redraw the other revisions on the sheet whose colour / grey has
    changed (a revision added, re-dated, moved or deleted)."""
    entries = sheet_revisions(rec, sheet)
    rec_name = _record_name(rec)
    for o, rev, _date, n in entries:
        if o == h or (_uuid(h) and _uuid(o) == _uuid(h)):
            continue
        parts = vs.GetRField(o, rec_name, 'State').split('|')
        drawn = parts[3] if len(parts) > 3 else ''
        now = '1' if is_current(entries, rev, n) else '0'
        if drawn != now:
            redraw(o)
            _log('regrey', rev, sheet, drawn, '->', now)


NEWLINE_MARK = '\\n'    # stored in place of a line break: backslash + n


def encode_note(text):
    """Line breaks as \\n in the Note field. Vectorworks writes each parameter
    into the Python script without escaping, so a real line break, an
    apostrophe or a lone backslash in a parameter stops the plug-in running.
    A backslash is stored doubled."""
    text = text.replace('\\', '\\\\')
    text = text.replace('\r\n', '\r').replace('\n', '\r').replace('\r', NEWLINE_MARK)
    return text.replace("'", '’')      # typographic apostrophe, same reason


def decode_note(text):
    """\\n in the Note field = a new line; \\\\ = a backslash."""
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
    """A one-line field, safe to store: typographic apostrophe, forward
    slash for a backslash (see encode_note)."""
    return text.replace("'", '’').replace('\\', '/')


def revision_dialog(h, rec, new=False):
    """The Revision dialog (placing a revision, double-click, Edit
    Revision...): Rev and Date on one line, then the note in a resizable
    multi-line box. Changing Rev fills in the date that Rev already has on
    this sheet. Writes the fields; True if OK."""
    def get(name):
        return vs.GetRField(h, rec, name)

    sheet = sheet_of(h)
    # The other revisions on this sheet, looked up once before the dialog
    # opens: rev -> [count, date]. Searching the drawing from inside the
    # dialog (each key typed) is not safe while the object is being made.
    known = {}
    for o, rev, date, _n in sheet_revisions(rec, sheet):
        if o == h or (_uuid(h) and _uuid(o) == _uuid(h)):
            continue
        k = known.setdefault(rev, [0, ''])
        k[0] += 1
        k[1] = k[1] or date
    _log('dialog: other revisions on', sheet, known)
    ok, offset = vs.ValidNumStr(get('CloudOffset').strip())
    cur = {'Rev': clean_rev(get('Rev')), 'Date': iso_date(get('Date')),
           'Note': decode_note(get('Note')),
           'ShowTag': get('ShowTag').strip().lower() != 'false'}
    result = {}
    try:
        title = 'New Revision' if new else ('Edit Revision ' + cur['Rev']).strip()
        dlg = vs.CreateResizableLayout(title, False, 'OK', 'Cancel', True, True)
        vs.CreateStaticText(dlg, 10, 'Revision:', -1)
        vs.CreateEditText(dlg, 11, cur['Rev'], 5)
        vs.CreateStaticText(dlg, 12, 'Date:', -1)
        vs.CreateEditText(dlg, 13, sheet_date(cur['Date']) if cur['Date'] else '', 10)
        vs.CreateStaticText(dlg, 14, 'dd/mm/yy', -1)
        vs.CreateStaticText(dlg, 15, 'Note:', -1)
        vs.CreateEditTextBox(dlg, 16, cur['Note'].replace('\r', '\r\n'), 50, 4)
        vs.CreateStaticText(dlg, 17, ' ' * 70, -1)     # filled in by shared_hint
        vs.CreateCheckBox(dlg, 18, 'Show marker, date and note (off: the cloud only)')
        vs.CreateStaticText(dlg, 19, 'Offset (sheet mm):', -1)
        vs.CreateEditText(dlg, 20, '%g' % max(0.0, offset if ok else 0.0), 8)
        vs.CreateStaticText(dlg, 21, 'clear of the outline you draw', -1)

        vs.SetFirstLayoutItem(dlg, 10)
        vs.SetRightItem(dlg, 10, 11, 0, 0)
        vs.SetRightItem(dlg, 11, 12, 1, 0)
        vs.SetRightItem(dlg, 12, 13, 0, 0)
        vs.SetRightItem(dlg, 13, 14, 0, 0)
        vs.SetBelowItem(dlg, 10, 15, 0, 1)
        vs.SetBelowItem(dlg, 15, 16, 0, 0)
        vs.SetBelowItem(dlg, 16, 17, 0, 0)
        vs.SetBelowItem(dlg, 17, 18, 0, 0)
        vs.SetBelowItem(dlg, 18, 19, 0, 0)
        vs.SetRightItem(dlg, 19, 20, 0, 0)
        vs.SetRightItem(dlg, 20, 21, 0, 0)
        # The note box grows with the dialog; the rest stays below it.
        vs.SetEdgeBinding(dlg, 16, True, True, True, True)
        vs.SetEdgeBinding(dlg, 17, True, False, False, True)
        for item in (18, 19, 20, 21):
            vs.SetEdgeBinding(dlg, item, True, False, False, True)

        def shared_hint(rev):
            others = known.get(rev, [0, ''])[0] if rev else 0
            where = ('on ' + sheet) if sheet else 'on this sheet'
            if others:
                text = 'Date shared with %d other Rev %s %s' % (others, rev, where)
            else:
                text = 'Every Rev %s %s shares this date' % (rev or '?', where)
            vs.SetItemText(dlg, 17, text)

        def handler(item, data):
            if item == 12255:                       # dialog set up
                vs.EnableItem(dlg, 14, False)       # greyed: hints only
                vs.EnableItem(dlg, 17, False)
                vs.EnableItem(dlg, 21, False)
                vs.SetBooleanItem(dlg, 18, cur['ShowTag'])
                shared_hint(cur['Rev'])
            elif item == 11:                        # Rev typed
                rev = clean_rev(vs.GetItemText(dlg, 11))
                d = known.get(rev, [0, ''])[1] if rev else ''
                if d:
                    vs.SetItemText(dlg, 13, sheet_date(d))
                if rev == NEW_SHEET and not vs.GetItemText(dlg, 16).strip():
                    vs.SetItemText(dlg, 16, NEW_SHEET_NOTE)
                shared_hint(rev)
            elif item == 1:                         # OK
                result['Rev'] = clean_rev(vs.GetItemText(dlg, 11))
                result['Date'] = iso_date(safe_text(vs.GetItemText(dlg, 13)))
                result['Note'] = vs.GetItemText(dlg, 16)
                result['ShowTag'] = 'True' if vs.GetBooleanItem(dlg, 18) else 'False'
                good, v = vs.ValidNumStr(vs.GetItemText(dlg, 20).strip() or '0')
                if good:
                    result['CloudOffset'] = '%g' % max(0.0, v)
            return item

        _log('dialog: open')
        vs.RunLayoutDialog(dlg, handler)
        _log('dialog: closed', result)
    except Exception:
        import traceback
        _log(traceback.format_exc())
        result.clear()                          # a failed dialog changes nothing
    if not result:
        return False
    result['Note'] = encode_note(result.get('Note', '').strip())
    for key, value in result.items():
        if value != get(key):
            vs.SetRField(h, rec, key, value)
    return True


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------
#
# ControlPoint01 = the knee: drag to move the marker (the leader and text
# follow). 'State' (not shown) keeps the Rev, Date and Sheet of the
# last redraw, so a redraw can tell what was changed:
# - Date changed (here, in Object Info or a worksheet): every other Rev on
#   this sheet gets it too
# - Rev changed, or moved to another sheet: takes the date that Rev already
#   has there
# The fourth part is 1 if it was drawn in colour, 0 if grey (Show Latest),
# so a sheet only redraws the revisions whose colour changes.
# Blank State = a new revision.

def _pt(text):
    try:
        x, y = (float(v) for v in text.split(';'))
        return (x, y)
    except Exception:
        return None


def read_state(p):
    parts = p._str('State').split('|')
    if len(parts) < 3:
        return None
    return {'rev': parts[0], 'date': parts[1], 'sheet': parts[2],
            'latest': parts[4] if len(parts) > 4 else None,
            'cp1': _pt(parts[5]) if len(parts) > 6 else None,
            'cp2': _pt(parts[6]) if len(parts) > 6 else None,
            'cp3': _pt(parts[7]) if len(parts) > 7 else None}


def write_state(p, sheet, current, cps=None):
    """cps: (knee, wrap dot, leader start) as drawn, so the next redraw can
    tell which was dragged. The last part, k, says ControlPoint01 is the
    knee: no longer read, but kept so a revision opened with a version
    before 0.7.9 is not converted again."""
    parts = [p.rev, p.date, sheet, '1' if current else '0', '%d' % p.show_latest]
    if cps:
        parts += ['%.6f;%.6f' % q if q else '' for q in cps] + ['k']
    p.set('State', '|'.join(x.replace('|', '') for x in parts))


def _cp(p, n=1):
    return (p._num('ControlPoint0%dX' % n), p._num('ControlPoint0%dY' % n))


def moved_alone(p, state, k, n):
    """ControlPoint0n on its own was dragged: the knee did not move but it
    did (moving the whole revision moves every point together)."""
    key = 'cp%d' % n
    if not (state and state['cp1'] and state.get(key)):
        return False
    tol = 1e-4 * max(1.0, p.paper)
    q = _cp(p, n)
    d1 = (k[0] - state['cp1'][0], k[1] - state['cp1'][1])
    dn = (q[0] - state[key][0], q[1] - state[key][1])
    return math.hypot(*d1) <= tol and math.hypot(dn[0] - d1[0], dn[1] - d1[1]) > tol


def wrap_dragged(p, state, c, text_x, away):
    """The wrap dot (ControlPoint02) on its own was dragged: the new wrap
    width (document units), else None. Moving the whole revision moves both
    points together, and dragging the marker moves ControlPoint01: neither
    changes the wrap."""
    if not (state and state['cp1'] and state['cp2']):
        return None
    tol = 1e-4 * max(1.0, p.paper)
    c2 = _cp(p, 2)
    d1 = (c[0] - state['cp1'][0], c[1] - state['cp1'][1])
    d2 = (c2[0] - state['cp2'][0], c2[1] - state['cp2'][1])
    if math.hypot(*d1) > tol or math.hypot(d2[0] - d1[0], d2[1] - d1[1]) <= tol:
        return None
    return max((c2[0] - text_x) * away, MIN_WRAP_MM * p.paper)


def _bbox_x(h):
    """(left, right) of an object, or None."""
    try:
        r = vs.GetBBox(h)
    except Exception:
        return None
    nums = []

    def flat(v):
        if isinstance(v, (tuple, list)):
            for x in v:
                flat(x)
        elif isinstance(v, (int, float)):
            nums.append(float(v))
    flat(r)
    if len(nums) < 4:
        return None
    return (min(nums[0], nums[2]), max(nums[0], nums[2]))


# --------------------------------------------------------------------------
# Parameter check
# --------------------------------------------------------------------------
#
# Every parameter the code reads or writes. A missing or misspelt one in the
# Plug-in Manager fails silently (0.2.3: NoteWIdth, no CloudSize), so the
# first redraw in a session lists any that are missing.

PARAMS = ('Rev', 'Date', 'Note', 'Sheet', 'Outline', 'CloudSize', 'CloudHeight', 'CloudOffset',
          'MarkerShape', 'MarkerSize', 'ShowLeader', 'Shoulder', 'LeaderSetback',
          'ShowDate', 'ShowNote', 'NoteWidth', 'TextLine', 'NoteAlign', 'ClassTemplate',
          'ShowLatest', 'ShowTag',
          'LeaderFixed', 'ControlPoint01X', 'ControlPoint01Y', 'ControlPoint02X',
          'ControlPoint02Y', 'ControlPoint03X', 'ControlPoint03Y',
          'State', 'Version', 'DrawnSize')
_checked = {}


def check_params(rec):
    rec_name = _record_name(rec)
    if _checked.get(rec_name):
        return
    _checked[rec_name] = True
    try:
        fmt = vs.GetObject(rec_name)
        n = vs.NumFields(fmt)
        names = {vs.GetFldName(fmt, i) for i in range(1, n + 1)}
    except Exception as e:
        _log('parameter check', repr(e))
        return
    if not names:
        return
    missing = [x for x in PARAMS if x not in names]
    extra = sorted(x for x in names if x not in PARAMS)
    _log('parameter check: missing', missing, 'not used', extra)
    if missing:
        vs.AlrtDialog('Revision Tool: these parameters are missing from the plug-in '
                      '(Plug-in Manager > Revision Tool > Parameters; names must match '
                      'exactly):\r\r' + ', '.join(missing) +
                      ('\r\rNames there that the tool does not use: ' + ', '.join(extra)
                       if extra else ''))


# --------------------------------------------------------------------------
# Reset
# --------------------------------------------------------------------------

def _short(v):
    """10.0 -> '10', 2.5 -> '2.5'."""
    return ('%.2f' % v).rstrip('0').rstrip('.')


def drawn_size(p):
    """The sizes set in mm on the sheet, as drawn in the file's units:
    'Marker 600, cloud 600 at 1:100' (as Break Line Tool's Drawn Size)."""
    text = 'Marker %s' % _short(p.marker_size)
    if p.outline == 'Cloud':
        text += ', cloud %s' % _short(p.cloud)
    return '%s at 1:%s' % (text, _short(p.scale))


def reset(h, rec):
    me = _uuid(h)
    _busy.add(me)
    try:
        _reset(h, rec)
    finally:
        _busy.discard(me)


def _reset(h, rec):
    """Redraw: read the outline, set up a new revision, keep the sheet in
    step, then draw the cloud, leader and marker, and date and note."""
    _log('reset start', _uuid(h))
    try:
        vs.SetObjectVariableBoolean(h, ovUsePIOTextAttributes, True)
    except Exception:
        pass
    ensure_style_map(h)
    check_params(rec)
    p = Params(h, rec)
    p.set('Version', '%s (%s)' % (VERSION, VERSION_DATE))
    try:
        p.set('DrawnSize', drawn_size(p))
    except Exception:
        pass                                # parameter not added yet

    pts = _drawn_outline(h)
    if not pts:
        _log('reset', p.rev, 'no outline')
        return
    state = read_state(p)
    first = state is None
    sheet = sheet_of(h)
    _log('reset', p.rev, 'sheet', sheet, 'first' if first else state, len(pts), 'points')
    if first:
        p = _new_revision(h, rec, sheet, pts)
    current = _sync_sheet(h, rec, p, state, sheet)

    pen = Painter(p, old=not current)
    _log('reset: drawing, class', pen.cls)
    if first:
        show_class(h, pen.cls or vs.GetClass(h))
    edge = _draw_cloud(pen, p, pts)

    if not p.show_tag:
        # The cloud only: no handles to drag. The State keeps the last marker
        # and wrap points, so turning the tag back on is not read as a drag.
        for cp in ('ControlPoint01X', 'ControlPoint01Y', 'ControlPoint02X', 'ControlPoint02Y',
                   'ControlPoint03X', 'ControlPoint03Y'):
            try:
                vs.SetParameterVisibility(h, cp, False)
            except Exception:
                pass
        if state and state['cp1']:
            write_state(p, sheet, current, (state['cp1'], state['cp2'], state['cp3']))
        _log('reset done (cloud only)', p.rev)
        return
    try:
        vs.SetParameterVisibility(h, 'ControlPoint01X', True)
        vs.SetParameterVisibility(h, 'ControlPoint01Y', True)
    except Exception:
        pass

    k, c, away, start0 = _draw_leader_marker(h, p, pen, state, edge)
    c2 = _draw_text(h, p, pen, state, k, c, away)
    write_state(p, sheet, current, (k, c2, start0))
    _log('reset done', p.rev)


def _drawn_outline(h):
    """The path's points; two points drawn = a rectangle on that diagonal.
    None if there is no path to draw round."""
    path = vs.GetCustomObjectPath(h)
    if not path:
        return None
    pts = outline_points(path)
    if len(pts) < 2:
        return None
    if len(pts) == 2:
        (ax, ay), (bx, by) = pts
        pts = [(ax, ay), (bx, ay), (bx, by), (ax, by)]
    return pts


def _new_revision(h, rec, sheet, pts):
    """First redraw of a new revision: the tool preferences, then the
    Revision dialog; the marker starts up and right of the cloud. A
    parameter default of 0 (Plug-in Manager) counts as blank here.
    Returns the Params as set."""
    p = Params(h, rec)
    for field in ('Rev', 'Date', 'Note', 'Sheet'):
        if p._str(field).strip() == '0':
            p.set(field, '')
    p = Params(h, rec)
    try:
        apply_prefs(h, rec)
    except Exception:
        pass
    if not p.rev:
        p.set('Rev', clean_rev(load_prefs().get('Rev', 'A')) or 'A')
        p = Params(h, rec)
    if not p.date:
        p.set('Date', sibling_date(rec, h, sheet, p.rev) or _today())
    if p.rev == NEW_SHEET and not p.note:
        p.set('Note', NEW_SHEET_NOTE)
    _log('reset: new revision dialog')
    revision_dialog(h, rec, new=True)
    p = Params(h, rec)
    prefs = load_prefs()
    if p.rev and prefs.get('Rev') != p.rev:
        prefs['Rev'] = p.rev                # the next one starts on this Rev
        save_prefs(prefs)
    off = MARKER_OFFSET_MM * p.paper + p.offset
    p.set_num('ControlPoint01X', max(q[0] for q in pts) + off)
    p.set_num('ControlPoint01Y', max(q[1] for q in pts) + off)
    return p


def _sync_sheet(h, rec, p, state, sheet):
    """Keep the sheet in step: one date per Rev per sheet, one Show Latest
    per sheet, and the others redrawn when their colour changes. Writes the
    State (without the control points) and returns whether this revision
    is in colour (current) or grey."""
    first = state is None
    # Stored as typed (17/02/26, a), read as ISO / upper case
    if p._str('Rev') != p.rev:
        p.set('Rev', p.rev)
    if p._str('Date') != p.date:
        p.set('Date', p.date)
    if p._str('Sheet') != sheet:
        p.set('Sheet', sheet)

    # One date per Rev per sheet
    date_changed = first or p.date != state['date']
    moved = not first and (p.rev != state['rev'] or sheet != state['sheet'])
    if moved and not date_changed:
        d = sibling_date(rec, h, sheet, p.rev)
        if d and d != p.date:
            p.date = d
            p.set('Date', d)
    elif date_changed and p.rev:
        _log('reset: share date', p.rev, p.date)
        share_date(rec, h, sheet, p.rev, p.date)

    # Show Latest: the latest revisions on the sheet in colour, older grey.
    # A new, re-dated or moved revision can change the others: redraw them.
    # One Show Latest per sheet: a new revision takes the sheet's; changed on
    # one (Settings, Object Info, a worksheet) it goes to the rest.
    if first and not by_style(h, 'ShowLatest'):
        n = sheet_show_latest(rec, h, sheet)
        if n is not None and n != p.show_latest:
            p.show_latest = n
            p.set('ShowLatest', '%d' % n)
    elif not first and state['latest'] is not None and state['latest'] != '%d' % p.show_latest:
        _log('reset: show latest', state['latest'], '->', p.show_latest)
        share_show_latest(rec, h, sheet, p.show_latest)
    entries = sheet_revisions(rec, sheet)
    me = _uuid(h)
    if not any(o == h or (me and _uuid(o) == me) for o, _r, _d, _n in entries):
        entries.append((h, p.rev, p.date, p.show_latest))   # never left out of its own count
    current = is_current(entries, p.rev, p.show_latest)
    _log('reset: current', current)
    write_state(p, sheet, current)
    if first or date_changed or moved:
        regrey_sheet(rec, h, sheet)
        if not first and state['sheet'] != sheet:
            regrey_sheet(rec, h, state['sheet'])      # the sheet it left
    return current


def _draw_cloud(pen, p, pts):
    """The cloud (or line) round the outline. Offset moves what is drawn
    out from the path, which stays where it was drawn (or snapped).
    Returns the drawn edge, for the leader."""
    pts = offset_outline(pts, p.offset)
    if p.outline == 'Cloud' and len(pts) >= 3:
        scallops = cloud_scallops(pts, p.cloud, p.cloud_height)
        pen.cloud(scallops)
        return cloud_points(scallops)
    pen.poly(pts, closed=True)
    return pts


def _draw_leader_marker(h, p, pen, state, edge):
    """Leader, shoulder and marker. ControlPoint01 = the knee, where the
    leader meets the shoulder: drag it to move the marker and text. The
    marker sits a shoulder past it, on the side away from the cloud.
    ControlPoint03 = where the leader leaves the cloud: the nearest point to
    the knee, or (Fixed Leader Start, set by dragging it) a point of the
    user's, kept on the cloud. Returns (knee, marker centre, away: 1 if the
    marker is right of the knee else -1, leader start)."""
    s = p.marker_size
    reach = marker_reach(p.marker, s)
    k = _cp(p)
    fixed = p._str('LeaderFixed').strip().lower() == 'true'
    if moved_alone(p, state, k, 3):
        fixed = True
        p.set('LeaderFixed', 'True')
        _log('reset: leader start dragged')
    start0 = nearest_on_outline(edge, _cp(p, 3) if fixed else k)
    away = 1 if start0[0] <= k[0] else -1           # the marker is past the knee
    side = -away                                    # the marker side facing the cloud
    c = (k[0] + away * (p.shoulder + reach), k[1])
    if p.show_leader:
        a = marker_attach(p.marker, c, s, side)
        if _dist(a, k) > 1e-6:
            pen.line(a, k)                          # the shoulder
        start = start0
        length = _dist(start, k)
        if p.setback > 0 and length > 0:
            t = min(p.setback, length) / length     # stop short of the cloud
            start = (start[0] + (k[0] - start[0]) * t, start[1] + (k[1] - start[1]) * t)
        if _dist(start, k) > 1e-6:
            pen.line(start, k)
    p.set_num('ControlPoint03X', start0[0])
    p.set_num('ControlPoint03Y', start0[1])
    try:
        vs.SetParameterVisibility(h, 'ControlPoint03X', p.show_leader)
        vs.SetParameterVisibility(h, 'ControlPoint03Y', p.show_leader)
    except Exception:
        pass

    shape = marker_shape(p.marker, c, s)
    pen.solid(pen.poly(shape) if shape else pen.circle(c, s))
    t = pen.text(marker_text_centre(p.marker, c, s), p.rev, just=2, valign=3)
    try:
        vs.SetTextStyle(t, 0, len(p.rev), 1)    # revision in bold
    except Exception:
        pass
    return k, c, away, start0


def _draw_text(h, p, pen, state, k, c, away):
    """Date and note on the side away from the cloud, and the line under
    them. The wrap dot (ControlPoint02) sits at the far end of the text:
    drag it to set the wrap width (Wrap (mm) follows). Returns the wrap
    dot's point."""
    gap = TEXT_GAP_MM * p.paper
    lines = []
    if p.show_date and p.date:
        lines.append(sheet_date(p.date))
    if p.show_note and p.note:
        lines.append(p.note)
    x = c[0] + away * (p.marker_size / 2.0 + gap)
    w = wrap_dragged(p, state, k, x, away) if lines else None
    if w is not None and not by_style(h, 'NoteWidth'):
        p.note_width = w
        p.set('NoteWidth', '%g' % round(w / p.paper, 1))
        _log('reset: wrap dragged to', p._str('NoteWidth'), 'mm')
    # A line out from the marker's centre (not drawn): the date sits on it,
    # the note hangs below it, so the date lines up beside every marker and
    # a longer note only grows downwards. Either one alone is centred on it,
    # unless the line is drawn (Line: Date / Text): then it keeps its side.
    end = x
    just = 1 if away > 0 else 3                 # to the marker's side
    note_just = {'Left': 1, 'Right': 3}.get(p.note_align, just)
    date_text = lines[0] if (p.show_date and p.date) else ''
    note_text = p.note if (p.show_note and p.note) else ''
    drawn_line = p.text_line != 'None' and bool(date_text or note_text)
    split_up = drawn_line or bool(date_text and note_text)
    split = LINE_GAP_MM * p.paper
    date_t = note_t = None
    if date_text:
        date_t = pen.text((x, c[1] + split if split_up else c[1]), date_text,
                          just=just, valign=5 if split_up else 3)
    if note_text:
        note_t = pen.text((x, c[1] - split if split_up else c[1]), note_text,
                          just=note_just, valign=1 if split_up else 3,
                          wrap=p.note_width or None)

    def snap(t):
        """Slide a text sideways so its near edge is at x, the text start:
        whatever its alignment, the block starts the same gap off the
        marker (and wrapped text is not left to Vectorworks' anchoring)."""
        b = _bbox_x(t) if t else None
        if not b:
            return
        dx = x - (b[0] if away > 0 else b[1])
        if abs(dx) > 1e-9:
            try:
                vs.HMove(t, dx, 0)
            except Exception as e:
                _log('snap text', repr(e))

    snap(date_t)
    snap(note_t)

    def far_edge(handles, wrap_end=None):
        """Far end (away from the marker) of these texts, or None."""
        ends = [] if wrap_end is None else [wrap_end]
        for b in (_bbox_x(t) for t in handles if t):
            if b:
                ends.append(b[1] if away > 0 else b[0])
        if not ends:
            return None
        return max(ends) if away > 0 else min(ends)

    wrap_end = x + away * p.note_width if (p.note_width and note_t) else None
    full = far_edge((date_t, note_t), wrap_end)
    if full is not None:
        end = full
    if drawn_line:
        line_end = far_edge((date_t,)) if p.text_line == 'Date' and date_t else full
        if line_end is not None and abs(line_end - x) > 1e-6:
            pen.solid(pen.line((x, c[1]), (line_end, c[1])))
    c2 = (end, c[1])
    p.set_num('ControlPoint02X', c2[0])
    p.set_num('ControlPoint02Y', c2[1])
    try:
        vs.SetParameterVisibility(h, 'ControlPoint02X', bool(lines))
        vs.SetParameterVisibility(h, 'ControlPoint02Y', bool(lines))
    except Exception:
        pass
    return c2


# --------------------------------------------------------------------------
# Title block (Update Title Block...)
# --------------------------------------------------------------------------
#
# The Title Block Border keeps its revision history as records, as the Title
# Block Manager writes them (checked on the office style, 2026-10-21):
# - Title Block Revision Data-1, -2 ...: one per revision, -1 the latest.
#   Fields Number, Date (dd/mm/yyyy), Note (Description), Approval (By),
#   Zone and Recipients (DP Name / DP Reg. in the office style), Publish Date
# - Title Block Revision Data: each field as a list, latest first, every
#   entry ended by chr(8)
# - the title block's own Current Revision Number
# A script-written revision shows in the title block and the Title Block
# Manager like one added there.

TB_OBJECT = 'Title Block Border'
TB_PER = 'Title Block Revision Data-%d'
TB_ALL = 'Title Block Revision Data'
TB_FIELDS = ('Number', 'Date', 'Note', 'Approval', 'Zone', 'Recipients', 'Publish Date')
TB_SEP = chr(8)


def _records_on(h):
    names = []
    try:
        for i in range(1, vs.NumRecords(h) + 1):
            names.append(vs.GetName(vs.GetRecord(h, i)))
    except Exception as e:
        _log('title block records', repr(e))
    return names


def _format_fields(name):
    """Field names of a record format, in order (custom ones included)."""
    fmt = vs.GetObject(name)
    if not fmt:
        return []
    return [vs.GetFldName(fmt, j) for j in range(1, vs.NumFields(fmt) + 1)]


def title_blocks_on(sheet):
    """The Title Block Borders on a sheet layer."""
    found = []

    def look(o):
        try:
            if vs.GetName(vs.GetParametricRecord(o)) != TB_OBJECT:
                return
        except Exception:
            return
        if sheet_of(o) == sheet:
            found.append(o)

    try:
        vs.ForEachObject(look, "(PON='%s')" % TB_OBJECT)
    except Exception:
        import traceback
        _log(traceback.format_exc())
    return found


def tb_read(tb):
    """(revisions latest first as {field: value}, every field name seen)."""
    names = _records_on(tb)
    fields = list(TB_FIELDS)
    revs = []
    k = 1
    while (TB_PER % k) in names:
        own = _format_fields(TB_PER % k) or list(TB_FIELDS)
        fields += [f for f in own if f not in fields]
        revs.append({f: vs.GetRField(tb, TB_PER % k, f) for f in own})
        k += 1
    return revs, fields


def tb_write(tb, revs, fields):
    """Write the revisions (latest first) as the Title Block Manager does,
    then redraw the title block. A record format the file lacks (-3 ...) is
    made like the others."""
    names = _records_on(tb)
    for k, rev in enumerate(revs, 1):
        name = TB_PER % k
        have = _format_fields(name)
        for f in fields:
            if f not in have:
                vs.NewField(name, f, '', 4, 0)          # 4 = text
        if name not in names:
            vs.SetRecord(tb, name)
        for f in fields:
            vs.SetRField(tb, name, f, rev.get(f, ''))
    if TB_ALL not in names:
        vs.SetRecord(tb, TB_ALL)
    for f in fields:
        vs.SetRField(tb, TB_ALL, f, ''.join(r.get(f, '') + TB_SEP for r in revs))
    try:
        prec = vs.GetName(vs.GetParametricRecord(tb))
        vs.SetRField(tb, prec, 'Current Revision Number', revs[0]['Number'] if revs else 'None')
    except Exception as e:
        _log('current revision number', repr(e))
    vs.ResetObject(tb)


def tb_date(iso):
    """2026-10-21 -> 21/10/2026, as the title block stores dates."""
    try:
        return datetime.date.fromisoformat(iso_date(iso)).strftime('%d/%m/%Y')
    except Exception:
        return iso


def _rev_order(rev):
    """Sort key, oldest first: by date, then revision (B after A, AA after Z)."""
    d = iso_date(rev.get('Date', ''))
    n = clean_rev(rev.get('Number', ''))
    return (d if len(d) == 10 and d[4] == '-' else '', len(n), n)


def sheet_summary(rec, sheet):
    """The revisions on a sheet, oldest first: [(rev, iso date, joined
    notes)]. Notes of the same Rev joined with '; ', each once."""
    rec_name = _record_name(rec)
    by_rev = {}
    for o, rev, date, _n in sheet_revisions(rec, sheet):
        r = by_rev.setdefault(rev, {'date': '', 'notes': []})
        r['date'] = max(r['date'], date)
        note = ' '.join(decode_note(vs.GetRField(o, rec_name, 'Note')).split())
        if note and note not in r['notes']:
            r['notes'].append(note)
    rows = [(rev, r['date'], '; '.join(r['notes'])) for rev, r in by_rev.items()]
    rows.sort(key=lambda x: (x[1], len(x[0]), x[0]))
    return rows


def title_block_dialog(sheet, rows, by, auto=False):
    """rows: [(rev, date, description, status, ticked)]. Returns
    ({rev: description} for the ticked rows, by) or None."""
    dlg = vs.CreateLayout('Update Title Block: ' + sheet, False, 'Update', 'Cancel')
    vs.CreateStaticText(dlg, 10, 'Tick the revisions to write to the title block on %s:' % sheet, -1)
    vs.CreateStaticText(dlg, 11, 'Rev', 6)
    vs.CreateStaticText(dlg, 12, 'Date', 11)
    vs.CreateStaticText(dlg, 13, 'Description', 50)
    vs.CreateStaticText(dlg, 14, '', 16)
    for i, (rev, date, desc, status, _tick) in enumerate(rows):
        vs.CreateCheckBox(dlg, 100 + i, rev)
        vs.CreateStaticText(dlg, 200 + i, tb_date(date), 11)
        vs.CreateEditText(dlg, 300 + i, desc, 50)
        vs.CreateStaticText(dlg, 400 + i, status, 16)
    vs.CreateStaticText(dlg, 20, 'By:', -1)
    vs.CreateEditText(dlg, 21, by, 8)
    vs.CreateStaticText(dlg, 22, 'Revisions only in the title block are kept as they are.', -1)
    if auto:
        vs.CreateStaticText(dlg, 23, 'This title block numbers revisions itself (Auto-Increment), so '
                                     'it will renumber these A, B, C... To keep the revisions\' own '
                                     'numbers (#, A ...): Title Block Manager > Document Options > '
                                     'Revision Data > Numbering: Manual.', 70)

    vs.SetFirstLayoutItem(dlg, 10)
    vs.SetBelowItem(dlg, 10, 11, 0, 1)
    vs.SetRightItem(dlg, 11, 12, 0, 0)
    vs.SetRightItem(dlg, 12, 13, 0, 0)
    vs.SetRightItem(dlg, 13, 14, 0, 0)
    above = 11
    kLeftEdge, kShift = 3, 1
    for i in range(len(rows)):
        vs.SetBelowItem(dlg, above, 100 + i, 0, 0)
        vs.SetRightItem(dlg, 100 + i, 200 + i, 0, 0)
        vs.SetRightItem(dlg, 200 + i, 300 + i, 0, 0)
        vs.SetRightItem(dlg, 300 + i, 400 + i, 0, 0)
        above = 100 + i
    # columns line up with their headings
    for col, head in ((200, 12), (300, 13), (400, 14)):
        vs.AlignItemEdge(dlg, head, kLeftEdge, 700 + col // 100, kShift)
        for i in range(len(rows)):
            vs.AlignItemEdge(dlg, col + i, kLeftEdge, 700 + col // 100, kShift)
    vs.SetBelowItem(dlg, above, 20, 0, 1)
    vs.SetRightItem(dlg, 20, 21, 0, 0)
    vs.SetBelowItem(dlg, 20, 22, 0, 0)
    if auto:
        vs.SetBelowItem(dlg, 22, 23, 0, 1)

    result = {}

    def handler(item, data):
        if item == 12255:
            for i, row in enumerate(rows):
                vs.SetBooleanItem(dlg, 100 + i, row[4])
                vs.EnableItem(dlg, 400 + i, False)      # greyed: status only
            vs.EnableItem(dlg, 22, False)
        elif item == 1:
            result['rows'] = {rows[i][0]: safe_text(vs.GetItemText(dlg, 300 + i).strip())
                              for i in range(len(rows)) if vs.GetBooleanItem(dlg, 100 + i)}
            result['by'] = safe_text(vs.GetItemText(dlg, 21).strip())
        return item

    if vs.RunLayoutDialog(dlg, handler) != 1 or 'rows' not in result:
        return None
    return result['rows'], result['by']


def update_title_block(h, rec):
    """Update Title Block... button: write this sheet's revisions into the
    title block on the sheet. Each Rev once, with its shared date and a
    description (the title block's own if it has the Rev, else the notes
    joined); updated in place if the title block has it, else added. Every
    revision is then written latest first."""
    sheet = sheet_of(h)
    tbs = title_blocks_on(sheet)
    if not tbs:
        vs.AlrtDialog('There is no title block on %s.' % (sheet or 'this sheet'))
        return
    if len(tbs) > 1:
        vs.AlrtDialog('%s has %d title blocks: the first one found is updated.' % (sheet, len(tbs)))
    tb = tbs[0]
    existing, fields = tb_read(tb)
    try:
        auto = vs.GetRField(tb, vs.GetName(vs.GetParametricRecord(tb)),
                            'Revision Increment').strip().lower() == 'auto'
    except Exception:
        auto = False
    in_tb = {clean_rev(r.get('Number', '')): r for r in existing}
    rows = []
    for rev, date, notes in sheet_summary(rec, sheet):
        old = in_tb.get(rev)
        if old is None:
            rows.append((rev, date, notes, 'new', True))
        elif iso_date(old.get('Date', '')) != date:
            rows.append((rev, date, old.get('Note', '') or notes, 'date differs', True))
        else:
            rows.append((rev, date, old.get('Note', '') or notes, 'in title block', False))
    if not rows:
        vs.AlrtDialog('There are no revisions on %s.' % sheet)
        return
    prefs = load_prefs()
    got = title_block_dialog(sheet, rows, prefs.get('TBBy', ''), auto)
    if got is None:
        return
    chosen, by = got
    if by != prefs.get('TBBy', ''):
        prefs['TBBy'] = by
        save_prefs(prefs)
    if not chosen:
        return
    dates = {rev: date for rev, date, _d, _s, _t in rows}
    revs = list(existing)
    for rev, desc in chosen.items():
        old = in_tb.get(rev)
        if old is None:
            old = {f: '' for f in fields}
            old['Number'] = rev
            revs.append(old)
        old['Date'] = tb_date(dates[rev])
        old['Note'] = desc
        old['Approval'] = by
    revs.sort(key=_rev_order, reverse=True)       # latest first
    _log('title block', sheet, [(r.get('Number'), r.get('Date')) for r in revs])
    tb_write(tb, revs, fields)


# --------------------------------------------------------------------------
# Object Info palette layout (event-based plug-in)
# --------------------------------------------------------------------------

LAYOUT = [
    ('Revision', ['Rev', 'Date', 'Note', 'ShowTag', 'LeaderFixed', 'CloudOffset', 'Sheet',
                  'DrawnSize']),
    ('About', ['Version']),
]
LABELS = {'Rev': 'Revision', 'Date': 'Date', 'Note': 'Note', 'Sheet': 'Sheet',
          'ShowTag': 'Show Marker and Text', 'LeaderFixed': 'Fixed Leader Start',
          'CloudOffset': 'Offset (sheet mm)', 'DrawnSize': 'Drawn Size',
          'Version': 'Version'}
READ_ONLY = ('Sheet', 'Version', 'DrawnSize')

WIDGET_BASE = 1000
HEADING_BASE = 2000
# Fixed widget IDs: only ever add to the end of these lists.
WIDGET_IDS = ['Rev', 'Date', 'Note', 'Sheet', 'Version', 'ShowTag', 'LeaderFixed', 'CloudOffset',
              'DrawnSize']
HEADING_IDS = ['Revision', 'About']


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
        if heading == 'Revision':
            vs.vsoAddWidget(EDIT_BUTTON_ID, kWidgetButton, 'Edit Revision...')
            vs.vsoWidgetSetIndLvl(EDIT_BUTTON_ID, 1)
        for wid, name in params:
            if vs.vsoAddParamWidget(wid, name, LABELS.get(name, '')):
                vs.vsoWidgetSetIndLvl(wid, 1)
        if heading == 'Revision':
            vs.vsoAddWidget(SETTINGS_BUTTON_ID, kWidgetButton, 'Settings...')
            vs.vsoWidgetSetIndLvl(SETTINGS_BUTTON_ID, 1)
            vs.vsoAddWidget(REFRESH_SHEET_ID, kWidgetButton, 'Refresh Sheet')
            vs.vsoWidgetSetIndLvl(REFRESH_SHEET_ID, 1)
            vs.vsoAddWidget(TITLE_BLOCK_ID, kWidgetButton, 'Update Title Block...')
            vs.vsoWidgetSetIndLvl(TITLE_BLOCK_ID, 1)
        if heading == 'About':
            vs.vsoAddWidget(ABOUT_WEB_ID, kWidgetButton, WEBSITE)
            vs.vsoWidgetSetIndLvl(ABOUT_WEB_ID, 1)
            vs.vsoAddWidget(ABOUT_UPDATE_ID, kWidgetButton, 'Check for updates...')
            vs.vsoWidgetSetIndLvl(ABOUT_UPDATE_ID, 1)
    # Double-click (and Edit) opens the Revision dialog instead of reshaping.
    vs.SetObjPropCharVS(kObjXPropSpecialEdit, chr(kObjXPropSpecialEditCustom))
    vs.SetObjPropVS(kObjXSupportsStyles, True)
    # State events: Vectorworks does not redraw a pasted or duplicated
    # revision, so on its own it would keep the old sheet's date (0.4.1)
    try:
        vs.SetPrefInt(590, 1)          # varParametricEnableStateEventing
        vs.SetObjPropVS(kObjXPropAcceptStates, True)
        vs.SetObjPropVS(kObjXPropAcceptStatesInternal, True)
    except Exception as e:
        _log('state events', repr(e))


# Plug-in styles: the look a style shares (By Style). Rev, Date, Note and
# the marker position stay By Instance. Set when a style is first used;
# change it in Edit Style.
STYLE_PARAMS = ('Outline', 'CloudSize', 'CloudHeight', 'MarkerShape', 'MarkerSize',
                'ShowLeader', 'Shoulder', 'LeaderSetback', 'ShowDate', 'ShowNote',
                'NoteWidth', 'TextLine', 'NoteAlign', 'ClassTemplate', 'ShowLatest')
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
    """First use of a style: Rev etc. By Instance, STYLE_PARAMS By Style.
    A style whose Note is already By Instance has been set up: left alone."""
    sd = _style_def(h)
    if not sd:
        return
    try:
        # Offset is per revision: a style set up by 0.6.0 lets go of it
        if vs.GetParamStyleType(sd, 'CloudOffset') == kByStyle:
            vs.SetParamStyleType(sd, 'CloudOffset', kByInstance)
        if vs.GetParamStyleType(sd, 'Note') == kByInstance:
            return
        vs.SetAllStyleParams(sd, kByInstance)
        for name in STYLE_PARAMS:
            try:
                vs.SetParamStyleType(sd, name, kByStyle)
            except Exception as e:
                _log('style map', name, repr(e))
    except Exception:
        import traceback
        _log(traceback.format_exc())


def by_style(h, field):
    """True if this revision's style controls the field."""
    sd = _style_def(h)
    if not sd:
        return False
    try:
        return vs.GetParamStyleType(sd, field) == kByStyle
    except Exception:
        return False


SETTINGS_FIELDS = STYLE_PARAMS + ('CloudOffset',)    # what the tool's defaults stamp


def settings_form(title, get, styled, rev='A'):
    """Revision Settings: the window for one revision (Settings...) and for
    the defaults (the tool's spanner). get(field) gives the current value as
    text (sizes in mm on the sheet); styled(field) greys a field a style
    controls. Returns {field: text} or None.

    Grouped Cloud, Marker, Leader, Text, Class. Item IDs rise down the
    window, so Tab follows the layout."""
    outlines = (112, [(102, 'Cloud', 'Cloud'), (103, 'Line', 'Line')])
    text_lines = (412, [(408, 'None', 'None'), (409, 'Date', 'Under date'),
                        (410, 'Text', 'Full text')])
    note_aligns = (417, [(414, 'Auto', 'Auto'), (415, 'Left', 'Left'), (416, 'Right', 'Right')])
    markers = (212, [(202 + i, m, m) for i, m in enumerate(MARKERS)])
    radio_groups = (outlines, markers, text_lines, note_aligns)
    group_of = {bid: buttons for _g, buttons in radio_groups for bid, _v, _t in buttons}
    heights = tuple(CLOUD_HEIGHTS)
    # number rows: (label id, label, field id, field, hint id, hint, default)
    nums = {
        'CloudSize': (106, 'Size (sheet mm):', 107, 108, 'scallop length on the sheet', CLOUD_MM),
        'CloudOffset': (111, 'Offset (sheet mm):', 113, 114, 'clear of the outline you draw', 0),
        'MarkerSize': (206, 'Size (sheet mm):', 207, 208, 'triangle side / circle diameter', MARKER_MM),
        'Shoulder': (303, 'Shoulder (sheet mm):', 304, 305, 'flat leg beside the marker', 0),
        'LeaderSetback': (306, 'Setback (sheet mm):', 307, 308, 'gap between the cloud and the leader', 0),
        'NoteWidth': (404, 'Wrap at (sheet mm):', 405, 406, '0 = no wrap', 0),
        'ShowLatest': (505, 'Show latest:', 506, 507, 'revisions per sheet in colour, older grey (0 = all)', 0),
    }
    checks = ((302, 'Show leader', 'ShowLeader'), (402, 'Date', 'ShowDate'), (403, 'Note', 'ShowNote'))

    def number(field):
        if field == 'ShowLatest':
            return '%d' % show_latest(get(field))   # 0 means all, not the default
        ok, v = vs.ValidNumStr(get(field).strip())
        return '%g' % (v if ok and v > 0 else nums[field][5])

    dlg = vs.CreateLayout(title, False, 'OK', 'Cancel')
    for gid, heading in ((100, 'Cloud'), (200, 'Marker'), (300, 'Leader'), (400, 'Text'), (500, 'Class')):
        vs.CreateGroupBox(dlg, gid, heading, True)
    hints = []

    def radio_row(lid, label, group):
        gid, buttons = group
        vs.CreateStaticText(dlg, lid, label, 14)
        vs.CreateGroupBox(dlg, gid, '', False)
        for bid, _value, text in buttons:
            vs.CreateRadioButton(dlg, bid, text)

    def num_row(field):
        lid, label, fid, hid, hint, _d = nums[field]
        vs.CreateStaticText(dlg, lid, label, 14)
        vs.CreateEditText(dlg, fid, number(field), 8)
        vs.CreateStaticText(dlg, hid, hint, -1)
        hints.append(hid)

    # Cloud
    radio_row(101, 'Outline:', outlines)
    num_row('CloudSize')
    vs.CreateStaticText(dlg, 109, 'Billow height:', 14)
    vs.CreatePullDownMenu(dlg, 110, 12)
    num_row('CloudOffset')
    # Marker
    radio_row(201, 'Shape:', markers)
    num_row('MarkerSize')
    # Leader
    vs.CreateCheckBox(dlg, 302, 'Show leader')
    num_row('Shoulder')
    num_row('LeaderSetback')
    # Text
    vs.CreateStaticText(dlg, 401, 'Show:', 14)
    vs.CreateCheckBox(dlg, 402, 'Date')
    vs.CreateCheckBox(dlg, 403, 'Note')
    num_row('NoteWidth')
    radio_row(407, 'Line:', text_lines)
    radio_row(413, 'Note align:', note_aligns)
    # Class
    vs.CreateStaticText(dlg, 501, 'Template:', 14)
    vs.CreateEditText(dlg, 502, get('ClassTemplate'), 30)
    vs.CreateStaticText(dlg, 503, '{Rev} is replaced: Revision-{Rev} -> Revision-A', -1)
    hints.append(503)
    vs.CreateStaticText(dlg, 504, ' ' * 60, 44)     # live class preview
    num_row('ShowLatest')

    def place_radios(lid, group):
        gid, buttons = group
        vs.SetRightItem(dlg, lid, gid, 0, 0)
        vs.SetFirstGroupItem(dlg, gid, buttons[0][0])
        for (left, _v, _t), (bid, _value, _text) in zip(buttons, buttons[1:]):
            vs.SetRightItem(dlg, left, bid, 0, 0)

    def below_num(prev, field):
        lid, _l, fid, hid, _h, _d = nums[field]
        vs.SetBelowItem(dlg, prev, lid, 0, 0)
        vs.SetRightItem(dlg, lid, fid, 0, 0)
        vs.SetRightItem(dlg, fid, hid, 0, 0)
        return lid

    vs.SetFirstLayoutItem(dlg, 100)
    vs.SetFirstGroupItem(dlg, 100, 101)
    place_radios(101, outlines)
    prev = below_num(101, 'CloudSize')
    vs.SetBelowItem(dlg, prev, 109, 0, 0)
    vs.SetRightItem(dlg, 109, 110, 0, 0)
    below_num(109, 'CloudOffset')
    vs.SetBelowItem(dlg, 100, 200, 0, 1)
    vs.SetFirstGroupItem(dlg, 200, 201)
    place_radios(201, markers)
    below_num(201, 'MarkerSize')
    vs.SetBelowItem(dlg, 200, 300, 0, 1)
    vs.SetFirstGroupItem(dlg, 300, 302)
    prev = below_num(302, 'Shoulder')
    below_num(prev, 'LeaderSetback')
    vs.SetBelowItem(dlg, 300, 400, 0, 1)
    vs.SetFirstGroupItem(dlg, 400, 401)
    vs.SetRightItem(dlg, 401, 402, 0, 0)
    vs.SetRightItem(dlg, 402, 403, 0, 0)
    below_num(401, 'NoteWidth')
    vs.SetBelowItem(dlg, 404, 407, 0, 0)
    place_radios(407, text_lines)
    vs.SetBelowItem(dlg, 407, 413, 0, 0)
    place_radios(413, note_aligns)
    vs.SetBelowItem(dlg, 400, 500, 0, 1)
    vs.SetFirstGroupItem(dlg, 500, 501)
    vs.SetRightItem(dlg, 501, 502, 0, 0)
    vs.SetBelowItem(dlg, 501, 503, 0, 0)
    vs.SetBelowItem(dlg, 503, 504, 0, 0)
    below_num(504, 'ShowLatest')
    kRightEdge, kResize = 1, 0              # group boxes the same width
    for gid in (100, 200, 300, 400, 500):
        vs.AlignItemEdge(dlg, gid, kRightEdge, 900, kResize)

    result = {}

    def chosen(group):
        for bid, value, _text in group[1]:
            if vs.GetBooleanItem(dlg, bid):
                return value
        return None

    def pick(bid):
        for other, _value, _text in group_of[bid]:
            vs.SetBooleanItem(dlg, other, other == bid)

    def set_radio(group, value):
        buttons = group[1]
        values = [v for _b, v, _t in buttons]
        pick(buttons[values.index(value) if value in values else 0][0])

    def enable():
        """Cloud size and height only for a cloud; leader sizes only with a
        leader; wrap only with the note shown."""
        cloud = chosen(outlines) == 'Cloud'
        vs.EnableItem(dlg, 107, cloud and not styled('CloudSize'))
        vs.EnableItem(dlg, 110, cloud and not styled('CloudHeight'))
        leader = vs.GetBooleanItem(dlg, 302)
        vs.EnableItem(dlg, 304, leader and not styled('Shoulder'))
        vs.EnableItem(dlg, 307, leader and not styled('LeaderSetback'))
        vs.EnableItem(dlg, 405, vs.GetBooleanItem(dlg, 403) and not styled('NoteWidth'))

    def class_preview():
        name = class_name(vs.GetItemText(dlg, 502).strip(), rev or 'A')
        vs.SetItemText(dlg, 504, ('→ ' + name) if name else 'Blank: the revision keeps its own class')

    def handler(item, data):
        if item == 12255:
            set_radio(outlines, match_choice(get('Outline'), OUTLINES, 'Cloud'))
            set_radio(markers, match_choice(get('MarkerShape'), MARKERS, 'Triangle'))
            set_radio(text_lines, match_choice(get('TextLine'), TEXT_LINES, 'None'))
            set_radio(note_aligns, match_choice(get('NoteAlign'), NOTE_ALIGNS, 'Auto'))
            for i, hname in enumerate(heights):
                vs.AddChoice(dlg, 110, hname, i)
            height = match_choice(get('CloudHeight'), heights, 'Medium')
            vs.SelectChoice(dlg, 110, heights.index(height), True)
            for cid, _label, field in checks:
                vs.SetBooleanItem(dlg, cid, get(field).strip().lower() != 'false')
            # what a style controls is greyed
            for group, field in ((outlines, 'Outline'), (markers, 'MarkerShape'),
                                 (text_lines, 'TextLine'), (note_aligns, 'NoteAlign')):
                for bid, _v, _t in group[1]:
                    vs.EnableItem(dlg, bid, not styled(field))
            for cid, _label, field in checks:
                vs.EnableItem(dlg, cid, not styled(field))
            vs.EnableItem(dlg, 207, not styled('MarkerSize'))
            vs.EnableItem(dlg, 502, not styled('ClassTemplate'))
            vs.EnableItem(dlg, 506, not styled('ShowLatest'))
            for hid in hints:
                vs.EnableItem(dlg, hid, False)      # greyed: descriptions only
            enable()
            class_preview()
        elif item in group_of:
            pick(item)
            enable()
        elif item in (302, 403):
            enable()
        elif item == 502:
            class_preview()
        elif item == 1:
            for group, field in ((outlines, 'Outline'), (markers, 'MarkerShape'),
                                 (text_lines, 'TextLine'), (note_aligns, 'NoteAlign')):
                value = chosen(group)
                if value:
                    result[field] = value
            for field, (_l, _t, fid, _h, _x, _d) in nums.items():
                ok, v = vs.ValidNumStr(vs.GetItemText(dlg, fid).strip() or '0')
                if ok:
                    v = max(0.0, v)
                    result[field] = '%d' % round(v) if field == 'ShowLatest' else '%g' % v
            picked = _choice_text(vs.GetSelectedChoiceInfo(dlg, 110, 0))
            if picked:
                result['CloudHeight'] = picked
            for cid, _label, field in checks:
                result[field] = 'True' if vs.GetBooleanItem(dlg, cid) else 'False'
            result['ClassTemplate'] = safe_text(vs.GetItemText(dlg, 502).strip())
        return item

    if vs.RunLayoutDialog(dlg, handler) != 1 or not result:
        return None
    return result


def _choice_text(r):
    """Text of a GetSelectedChoiceInfo result, whatever its tuple shape."""
    if isinstance(r, tuple):
        for v in reversed(r):
            if isinstance(v, str) and v:
                return v
        return ''
    return r if isinstance(r, str) else ''


def settings_dialog(h, rec):
    """Settings...: the look of one revision (and what a style shares).
    Fields the revision's style controls are greyed. True if OK."""
    def get(name):
        return vs.GetRField(h, rec, name)

    cache = {}

    def styled(field):
        if field not in cache:
            cache[field] = by_style(h, field)
        return cache[field]

    result = settings_form('Revision Settings', get, styled, clean_rev(get('Rev')))
    if result is None:
        return False
    for field, value in result.items():
        if not styled(field) and value != get(field):
            vs.SetRField(h, rec, field, value)
    return True


def edit_revision(h, rec):
    """Edit Revision button / double-click: the Revision dialog with the
    current values. Cancel leaves the revision as it was."""
    if revision_dialog(h, rec):
        vs.ResetObject(h)


def refresh_sheet(h, rec):
    """Refresh Sheet button: redraw every revision on this sheet, e.g. after
    one was deleted (nothing else tells the rest to change colour). Not the
    title block: that is a separate command, still to come."""
    for o, _rev, _date, _n in sheet_revisions(rec, sheet_of(h)):
        vs.ResetObject(o)


def on_add_state(h, rec, state_id):
    """State event (moved, pasted, duplicated ...): record it, and redraw a
    revision whose sheet is not the one it last drew on (pasted or
    duplicated onto another sheet), so it takes that sheet's date and
    Show Latest straight away."""
    try:
        vs.vsoSetEventResult(vs.vsoStateAddCurrent(h, state_id))
    except Exception as e:
        _log('add state', repr(e))
    try:
        p = Params(h, rec)
        state = read_state(p)
        if state and state['sheet'] != sheet_of(h):
            _log('state event: on a new sheet', state['sheet'], '->', sheet_of(h))
            redraw(h)
    except Exception:
        import traceback
        _log(traceback.format_exc())


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


def widget_prep(h, rec):
    for _hid, _heading, params in _widget_ids():
        for wid, name in params:
            vs.vsoWidgetSetEnable(wid, name not in READ_ONLY)
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
        on_add_state(h, rec, _button)
        return
    if event == kObjOnWidgetPrep:
        widget_prep(h, rec)
    elif event == kObjOnSpecialEdit:
        edit_revision(h, rec)
        vs.vsoSetEventResult(kObjectEditResult_DoNothing)
    elif event == kObjOnEditPluginStyle:
        vs.vsoSetEventResult(kObjectEditPluginStyleByDefault)
    elif event == kObjOnUIButtonHit:
        if _button == EDIT_BUTTON_ID:
            edit_revision(h, rec)
        elif _button == SETTINGS_BUTTON_ID:
            if settings_dialog(h, rec):
                vs.ResetObject(h)
        elif _button == ABOUT_WEB_ID:
            open_website()
        elif _button == ABOUT_UPDATE_ID:
            check_updates()
        elif _button == TITLE_BLOCK_ID:
            update_title_block(h, rec)
        elif _button == REFRESH_SHEET_ID:
            refresh_sheet(h, rec)
    elif event in (kResetEventID, 0):
        try:
            reset(h, rec)
        except Exception:
            _reset_failed(vs.GetRField(h, rec, 'Rev'))


# --------------------------------------------------------------------------
# Revision tool (a separate Tool plug-in, "Revision")
# --------------------------------------------------------------------------
#
# Draws the area round the change (Ellipse, Rectangle, Polygon, Freehand, as
# on the Comment tool), then makes it a Revision Tool object. Vectorworks
# collects the points and draws the preview itself (vstSetPtBehavior).
# Event numbers are from the Vectorworks SDK (MiniCadCallBacks.h).

OBJECT_NAME = 'Revision Tool'


MODE_ELLIPSE, MODE_RECT, MODE_POLY, MODE_FREEHAND = 1, 2, 3, 4
MODE_ICONS = ('Vectorworks/ModeViewBar/Oval_Mode.svg',
              'Vectorworks/ModeViewBar/Rectangle_Mode.svg',
              'Vectorworks/ModeViewBar/Vertex_Mode.svg',
              'Vectorworks/ModeViewBar/Freehand_Mode.svg')
# vstSetPtBehavior: 102 ellipse, 101 box, 4 points until double-click, 103 freehand
PT_BEHAVIOUR = {MODE_ELLIPSE: 102, MODE_RECT: 101, MODE_POLY: 4, MODE_FREEHAND: 103}
HELP = {
    MODE_ELLIPSE: 'Ellipse: click one corner, then the opposite corner',
    MODE_RECT: 'Rectangle: click one corner, then the opposite corner',
    MODE_POLY: 'Polygon: click each corner, double-click to finish',
    MODE_FREEHAND: 'Freehand: drag around the area',
}
ELLIPSE_SEGMENTS = 32


# --- Tool preferences (per user, remembered between sessions) -------------

PREF_DEFAULTS = {
    'Outline': 'Cloud', 'CloudSize': CLOUD_MM, 'CloudHeight': 'Medium', 'CloudOffset': 0.0,
    'MarkerShape': 'Triangle', 'MarkerSize': MARKER_MM,
    'ShowLeader': True, 'Shoulder': 3.0, 'LeaderSetback': 0.0,
    'ShowDate': True, 'ShowNote': True, 'NoteWidth': 0.0,
    'ClassTemplate': 'Revision-{Rev}', 'ShowLatest': float(SHOW_LATEST), 'TextLine': 'Date', 'NoteAlign': 'Auto', 'TBBy': '', 'Style': '', 'Rev': 'A',
}


def _prefs_path():
    import os
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'Nemetschek', 'Vectorworks', 'revision_tool_prefs.json')


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
    """The spanner button: the Revision Settings window, saved as the
    default for new revisions. True if OK."""
    prefs = load_prefs()
    got = settings_form('Default Revision Settings', lambda f: _pref_text(prefs.get(f, '')),
                        lambda f: False, clean_rev(prefs.get('Rev', 'A')))
    if not got:
        return False
    for k, v in got.items():
        if isinstance(PREF_DEFAULTS.get(k), bool):
            prefs[k] = (v == 'True')
        elif isinstance(PREF_DEFAULTS.get(k), float):
            ok, num = vs.ValidNumStr(v)
            prefs[k] = num if ok else PREF_DEFAULTS[k]
        else:
            prefs[k] = v
    save_prefs(prefs)
    return True


def apply_prefs(obj, rec=OBJECT_NAME):
    """Stamp the default settings on a new revision (its first reset, before
    the Revision dialog). Fields its style controls are left to the style."""
    prefs = load_prefs()
    for field in SETTINGS_FIELDS:
        if not by_style(obj, field):
            vs.SetRField(obj, rec, field, safe_text(_pref_text(prefs.get(field, ''))))


def shape_points(mode, a, b):
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    if mode == MODE_ELLIPSE:
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        return [(cx + rx * math.cos(2 * math.pi * k / ELLIPSE_SEGMENTS),
                 cy + ry * math.sin(2 * math.pi * k / ELLIPSE_SEGMENTS))
                for k in range(ELLIPSE_SEGMENTS)]
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def create_revision(pts):
    """Make a Revision Tool object on the outline pts."""
    vs.ClosePoly()
    vs.BeginPoly()
    for x, y in pts:
        vs.AddPoint(x, y)
    vs.EndPoly()
    poly = vs.LNewObj()
    _log('create: outline drawn', poly)
    obj = None
    for nil in (None, vs.Handle(0) if hasattr(vs, 'Handle') else None):
        try:
            obj = vs.CreateCustomObjectPath(OBJECT_NAME, poly, nil)
            break
        except Exception as e:
            _log('create: CreateCustomObjectPath', repr(e))
            continue
    _log('create: object', obj)
    # Remove the temporary outline if it was copied rather than used, or if
    # no object was made; never when it is (or might be) the object's path.
    try:
        parent = vs.GetParent(poly)
        used = obj and vs.GetCustomObjectPath(obj) == poly
        on_layer = parent and vs.GetTypeN(parent) == 31
        if on_layer and not used:
            vs.DelObject(poly)
    except Exception:
        pass
    if obj:
        apply_tool_style(obj, load_prefs().get('Style', '').strip())
        _log('create: first redraw')
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
        if tmp and tmp != h:
            try:
                vs.DelObject(tmp)
            except Exception:
                pass
    if len(pts) > 2 and _dist(pts[0], pts[-1]) < 1e-9:
        pts.pop()
    return pts


DEBUG_LOG = False      # True writes tool_debug.log next to this file (testing)


# --- Revision tool (the .vst): what its clicks make -------------------------
TOOL_OBJECT = OBJECT_NAME
TOOL_NAME = 'Revision'
TOOL_MODES = tuple((MODE_ICONS[m - 1], PT_BEHAVIOUR[m], HELP[m]) for m in sorted(HELP))
TOOL_FIRST_MODE = MODE_RECT
TOOL_PULLDOWNS = ()
TOOL_DEFAULTS = ()      # the spanner is the Revision Settings (tool_spanner)


def tool_spanner():
    prefs_dialog()


def tool_complete(mode, clicked, h):
    """Make the revision from the clicks (h, the tool's own object, is
    deleted by the drawing-tool block afterwards)."""
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
        create_revision(pts)


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
