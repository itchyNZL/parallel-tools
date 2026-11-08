"""
Planting Tool for Vectorworks 2026 / 2027

Copyright (c) 2026 Ian Thrush
Licensed under the MIT License (see LICENSE.md).

Hedges and planting in plan as one path plug-in object, for Architect
(no Landmark). Was Hedge Tool (to 0.6):
- an open path (line) is the hedge's centreline, or one edge, at Width
- a closed path (polygon) is the hedge's outline as drawn
- the edge is roughed up: Billow (cloud arcs of varying size), Fuzzy
  (jagged, like Landmark's Plant Line) or Wavy (smooth wobble)
- the roughness is seeded, so a hedge looks the same every redraw;
  Reshuffle gives it a new look
- Shape Plants draws each plant as a rough circle instead: circles that
  overlap merge (one outline round the outside), spaced ones stand apart

Fill, pen and colour come from the object's attributes (or its class);
Pen fill draws the fill as pencil strokes in the pen colour instead.
Plant centres can sit in their own class, to be filled or turned off apart.
The .vso holds a short loader stub; all logic lives here.
"""

import math
import random
import zlib

import vs

VERSION = '0.11.2'
VERSION_DATE = '2026-11-09'
WEBSITE = 'github.com/itchyNZL/parallel-tools'
TOOL_FOLDER = 'Planting Tool'

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
RESHUFFLE_ID = 3001
ABOUT_WEB_ID = 3002
ABOUT_UPDATE_ID = 3101
RESTART_ID = 3003

OFFSETS = ('Centre', 'Left', 'Right')
SHAPES = ('Band', 'Plants')
FITS = ('Inset', 'Ends', 'Ends and Corners')   # Plant Fit along a line (Inset was Even)
KINK_DEG = 20.0          # a polyline corner turns at least this much
EDGES = ('Billow', 'Fuzzy', 'Wavy')
BILLOW_TYPES = ('Convex', 'Concave')
CENTRE_STYLES = ('Circle', 'Dot', 'Cross')
FILL_STYLES = ('Solid', 'Pen', 'Pen over Solid')
HEDGE_CLASS = 'Landscape-Plant'          # a new hedge goes in this class
PLANT_SIZE_SHARE = 1.25  # Plant Size 0: this times the spacing (they merge, no gaps)
CIRCLE_POINTS = 36       # points round each plant circle
SHADOW_ANGLE = 315.0     # Shadow Angle default: down and right
SHADOW_MM = 0.8          # Shadow Offset default (mm on the sheet, down and right)
SHADOW_RGB = (60 * 257, 60 * 257, 60 * 257)
SHADOW_OPACITY = 45
GUIDE_CLASS = 'Landscape-Plant Guides'    # drawn path and handle labels (tick Non Plot)
LABEL_POINTS = 4         # handle label text size
MAX_STROKES = 4000      # pen strokes, at most (wider spacing beyond this)
MAX_PLANTS = 3000       # plant centres drawn, at most
MAX_ROWS = 5

MAX_SAMPLES = 400       # points read along the path
MIN_SIZE_SHARE = 0.2    # smallest billow, as a share of the default size
MAX_BUMPS = 800         # billows (or fuzzy points) round the outline
ARC_STEP = math.radians(15.0)   # round ends and outside corners
REQUIRED = ('Width', 'Offset', 'EdgeStyle', 'BillowSize', 'BillowHeight', 'Variability',
            'BillowType', 'Seed', 'Version',
            'ShowCentres', 'PlantSpacing', 'Rows', 'CentreStyle', 'CentreSize', 'PlantCount',
            'MarkerClass', 'ControlPoint01X', 'ControlPoint01Y', 'PlantStart', 'State',
            'FillStyle', 'PenSpacing', 'PenAngle', 'CrossHatch', 'PenOpacity',
            'Shape', 'PlantSize', 'Shadow', 'KeepClear',
            'ControlPoint02X', 'ControlPoint02Y', 'ControlPoint03X', 'ControlPoint03Y',
            'ControlPoint04X', 'ControlPoint04Y', 'Zigzag', 'KeepInside',
            'PlantFit', 'RowSpacing', 'RowShift', 'ControlPoint05X', 'ControlPoint05Y',
            'ShadowOffset', 'DrawnSize', 'ShadowAngle')


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


def plant_fit(raw):
    """The Plant Fit option (anything else, such as 0.8's Even: Inset)."""
    return match_choice(raw, FITS, 'Inset')


class Params:
    def __init__(self, h, rec):
        self.h = h
        self.rec = rec
        self.width = max(0.0, self._num('Width', 600.0))
        self.base_width = self.width    # as typed (one row of plants overrides width)
        self.offset = match_choice(self._str('Offset'), OFFSETS, 'Centre')
        self.edge = match_choice(self._str('EdgeStyle'), EDGES, 'Billow')
        self.size = self._num('BillowSize', 0.0)
        self.height = max(0.0, min(100.0, self._num('BillowHeight', 50.0))) / 100.0
        self.var = max(0.0, min(100.0, self._num('Variability', 40.0))) / 100.0
        self.concave = match_choice(self._str('BillowType'), BILLOW_TYPES, 'Convex') == 'Concave'
        self.seed = int(self._num('Seed', 0.0))
        self.centres = self._str('ShowCentres').strip().lower() == 'true'
        self.spacing = self._num('PlantSpacing', 0.0)
        self.rows = max(1, min(MAX_ROWS, int(round(self._num('Rows', 1.0)))))
        self.centre_style = match_choice(self._str('CentreStyle'), CENTRE_STYLES, 'Circle')
        try:
            # in a viewport's annotations, the viewport's scale (as Break Line Tool)
            scale = annotation_scale(h) or vs.GetLScale(vs.GetLayer(h))
        except Exception:
            scale = 1.0
        self.scale = scale if scale and scale > 0 else 1.0
        self.paper = _mm() * self.scale
        self.centre_size = max(0.1, self._num('CentreSize', 1.5)) * self.paper
        self.marker_class = self._str('MarkerClass').strip()
        self.start = self._num('PlantStart', -1.0)
        self.fill = match_choice(self._str('FillStyle'), FILL_STYLES, 'Solid')
        self.pen_spacing = max(0.2, self._num('PenSpacing', 1.0)) * self.paper
        self.pen_angle = self._num('PenAngle', 45.0)
        self.cross = self._str('CrossHatch').strip().lower() == 'true'
        self.pen_opacity = int(max(5.0, min(100.0, self._num('PenOpacity', 80.0))))
        self.plants = match_choice(self._str('Shape'), SHAPES, 'Band') == 'Plants'
        self.plant_size = max(0.0, self._num('PlantSize', 0.0))
        self.shadow = self._str('Shadow').strip().lower() == 'true'
        self.keep_clear = self._str('KeepClear').strip()
        self.shadow_offset = max(0.0, min(20.0, self._num('ShadowOffset', SHADOW_MM))) * self.paper
        # Shadow Angle: the way the shadow falls on the drawing, degrees anticlockwise from
        # right (as Stroke Angle); blank = 315, down and right as before
        self.shadow_angle = self._num('ShadowAngle', SHADOW_ANGLE) % 360.0
        self.zigzag = max(0.0, self._num('Zigzag', 0.0))
        self.keep_inside = self._str('KeepInside').strip().lower() == 'true'
        self.fit = plant_fit(self._str('PlantFit'))
        # closed-shape grid: rows apart and each row's shift, shares of the spacing
        self.row_spacing = max(10.0, min(500.0, self._num('RowSpacing', 86.6))) / 100.0
        self.row_shift = (self._num('RowShift', 50.0) % 100.0) / 100.0
        self.locked = set()     # handle values that come from the style

    def _str(self, name):
        return vs.GetRField(self.h, self.rec, name)

    def _num(self, name, default=0.0):
        text = self._str(name).strip()
        if not text:
            return default
        ok, v = vs.ValidNumStr(text)
        return v if ok else default

    def set(self, name, value):
        if self._str(name) != value:
            vs.SetRField(self.h, self.rec, name, value)

    def set_num(self, name, value):
        self.set(name, '%.6f' % value)


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
    """First redraw of a session: say which parameters the plug-in lacks."""
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
        vs.AlrtDialog('Planting Tool: add these parameters in the Plug-in Manager '
                      '(see README), then restart Vectorworks: ' + ', '.join(missing))


# --------------------------------------------------------------------------
# Geometry (pure Python: object coordinates, lists of (x, y))
# --------------------------------------------------------------------------

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def signed_area(pts):
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                     for i in range(n))


def dedupe(pts, closed, tol=1e-6):
    out = []
    for q in pts:
        if not out or _dist(q, out[-1]) > tol:
            out.append(q)
    if closed and len(out) > 2 and _dist(out[0], out[-1]) <= tol:
        out.pop()
    return out


def _seg_dist(q, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / ll))
    return math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy)


def dist_to_line(q, line):
    return min(_seg_dist(q, line[i], line[i + 1]) for i in range(len(line) - 1))


def _arc_points(c, r, a0, a1, ccw):
    """Points on a circle from angle a0 to a1 (ends included), going
    anticlockwise if ccw."""
    sweep = (a1 - a0) % (2 * math.pi)
    if not ccw:
        sweep -= 2 * math.pi
    if abs(sweep) < 1e-9:
        sweep = 2 * math.pi if ccw else -2 * math.pi
    n = max(1, int(math.ceil(abs(sweep) / ARC_STEP)))
    return [(c[0] + r * math.cos(a0 + sweep * k / n), c[1] + r * math.sin(a0 + sweep * k / n))
            for k in range(n + 1)]


def offset_side(line, d):
    """The open line moved d to its left (negative: right): round on the
    outside of each bend, mitred (then trimmed) on the inside. Points that
    end up closer to the line than d (a bend tighter than the width) are
    dropped, so the hedge edge doesn't loop back on itself."""
    if abs(d) < 1e-9:
        return list(line)
    n = len(line)
    units = []
    for i in range(n - 1):
        a, b = line[i], line[i + 1]
        L = _dist(a, b)
        units.append(((b[0] - a[0]) / L, (b[1] - a[1]) / L))

    def norm(u):
        return (-u[1] * d, u[0] * d)        # left of travel, times d

    out = []
    for i in range(n):
        p = line[i]
        if i == 0 or i == n - 1:
            nv = norm(units[0] if i == 0 else units[-1])
            out.append((p[0] + nv[0], p[1] + nv[1]))
            continue
        u1, u2 = units[i - 1], units[i]
        turn = u1[0] * u2[1] - u1[1] * u2[0]           # > 0: bends left
        n1, n2 = norm(u1), norm(u2)
        outside = (turn < 0) if d > 0 else (turn > 0)
        if outside and abs(turn) > 1e-6:
            a0 = math.atan2(n1[1], n1[0])
            a1 = math.atan2(n2[1], n2[0])
            out += _arc_points(p, abs(d), a0, a1, turn > 0)
        else:
            # mitre: where the two offset edges meet
            dot = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
            half = math.acos(dot) / 2.0
            k = 1.0 / max(math.cos(half), 0.25)
            mx, my = n1[0] + n2[0], n1[1] + n2[1]
            ml = math.hypot(mx, my)
            if ml < 1e-12:
                out.append((p[0] + n1[0], p[1] + n1[1]))
            else:
                s = abs(d) * k / ml
                out.append((p[0] + mx * s, p[1] + my * s))
    if len(line) > 2:
        keep = [q for i, q in enumerate(out)
                if i in (0, len(out) - 1) or dist_to_line(q, line) > abs(d) * 0.98]
        out = keep
    return dedupe(out, False)


def _cap(a, b, u):
    """Half circle from a to b, bulging along u (the hedge's round end)."""
    c = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    r = _dist(a, b) / 2.0
    if r < 1e-9:
        return [a]
    a0 = math.atan2(a[1] - c[1], a[0] - c[0])
    a1 = math.atan2(b[1] - c[1], b[0] - c[0])
    mid = math.atan2(u[1], u[0])
    ccw = (mid - a0) % (2 * math.pi) < (a1 - a0) % (2 * math.pi)
    return _arc_points(c, r, a0, a1, ccw)


def band_outline(line, width, offset):
    """The closed outline of a hedge `width` wide along an open line:
    centred on it, or to its left or right, with round ends."""
    line = dedupe(line, False)
    if len(line) < 2 or width <= 0:
        return []
    left = left_edge(width, offset)
    right = width - left
    l_side = offset_side(line, left)
    r_side = offset_side(line, -right)
    if len(l_side) < 2 or len(r_side) < 2:
        return []

    def unit(a, b):
        L = _dist(a, b) or 1.0
        return ((b[0] - a[0]) / L, (b[1] - a[1]) / L)

    u_end = unit(line[-2], line[-1])
    u_start = unit(line[1], line[0])
    out = list(l_side)
    out += _cap(l_side[-1], r_side[-1], u_end)[1:-1]
    out += r_side[::-1]
    out += _cap(r_side[0], l_side[0], u_start)[1:-1]
    return dedupe(out, True)


def inset_ring(ring, d):
    """The closed ring moved d inwards: each point along the bisector of
    its two edges (mitre, limited), then points that end up nearer the
    original than d (a part narrower than 2d folding over) dropped."""
    n = len(ring)
    if d <= 0 or n < 3:
        return list(ring)
    sign = 1.0 if signed_area(ring) > 0 else -1.0       # left of travel is inside if ccw
    out = []
    for i in range(n):
        a, p, b = ring[i - 1], ring[i], ring[(i + 1) % n]
        l1, l2 = _dist(a, p), _dist(p, b)
        if l1 < 1e-12 or l2 < 1e-12:
            continue
        n1 = (-(p[1] - a[1]) / l1 * sign, (p[0] - a[0]) / l1 * sign)
        n2 = (-(b[1] - p[1]) / l2 * sign, (b[0] - p[0]) / l2 * sign)
        mx, my = n1[0] + n2[0], n1[1] + n2[1]
        ml = math.hypot(mx, my)
        if ml < 1e-9:
            continue
        cos_half = ml / 2.0
        k = d / max(cos_half, 0.35)
        out.append((p[0] + mx / ml * k, p[1] + my / ml * k))
    edge = ring + [ring[0]]
    keep = [q for q in out if inside(q, ring) and dist_to_line(q, edge) > d * 0.97]
    keep = dedupe(keep, True)
    return keep if len(keep) >= 3 and abs(signed_area(keep)) > 1e-9 else list(ring)


def resample(ring, size, var, rnd, max_n=MAX_BUMPS, mids=False):
    """Points round a closed ring, `size` apart give or take `var` (0..1),
    as (point, outward normal); mids: (point, outward normal, the point on
    the ring halfway to the next one). The last gap is spread over the
    others rather than left short."""
    n = len(ring)
    segs = []
    total = 0.0
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        L = _dist(a, b)
        if L > 1e-12:
            segs.append((total, a, b, L))
            total += L
    if total <= 0:
        return []
    size = max(size, total / max_n)
    steps = []
    s = 0.0
    while True:
        st = size * (1.0 + var * 0.6 * (2.0 * rnd.random() - 1.0))
        if s + st > total - 0.5 * size:
            break
        steps.append(st)
        s += st
    if len(steps) < 3:
        steps = [total / 3.0] * 3
    scale = total / sum(steps) if steps else 1.0
    ccw = signed_area(ring) > 0
    walk = [0]

    def at(s):
        # s only increases: carry on from the last segment
        j = walk[0]
        while j < len(segs) - 1 and segs[j + 1][0] <= s:
            j += 1
        walk[0] = j
        s0, a, b, L = segs[j]
        t = max(0.0, min(1.0, (s - s0) / L))
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nrm = (uy, -ux) if ccw else (-uy, ux)
        return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), nrm

    out = []
    s = 0.0
    for k, st in enumerate([0.0] + steps[:-1]):
        s += st * scale
        q, nrm = at(s)
        if mids:
            m, _n = at(s + steps[k] * scale / 2.0)
            out.append((q, nrm, m))
        else:
            out.append((q, nrm))
    return out


def billows(ring, size, height, var, concave, rnd):
    """Cloud arcs round the ring, each about `size` long, bulging
    out (in if concave) by `height` of its half length, both varied by
    `var`. Each is (start, end, corner, radius): drawn as one arc vertex at
    `corner` (where the arc's end tangents meet), as Revision Tool's cloud.
    The bulge is measured from the ring, not the straight cut between the
    billow's ends: on a curve (a round end, the outside of a bend) the cut
    lies inside the ring, so measured from it the billows there would
    hardly reach past the ring while those along the sides bulge well out."""
    samples = resample(ring, size, var, rnd, mids=True)
    pts = [q for q, _n, _m in samples]
    ccw = signed_area(ring) > 0
    out = []
    m = len(pts)
    for i in range(m):
        a, b = pts[i], pts[(i + 1) % m]
        L = _dist(a, b)
        if L < 1e-9:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = (uy, -ux) if ccw else (-uy, ux)
        if concave:
            nx, ny = -nx, -ny
        r = L / 2.0
        h = height * (1.0 + var * (2.0 * rnd.random() - 1.0))
        h = min(max(h, 0.08), 0.95)
        sag = h * r
        if not concave:
            # how far the ring itself bulges past the cut, halfway along
            half = samples[i][2]
            ring_sag = (half[0] - (a[0] + b[0]) / 2.0) * nx + (half[1] - (a[1] + b[1]) / 2.0) * ny
            sag = min(sag + max(0.0, ring_sag), 0.95 * r)
        R = (r * r + sag * sag) / (2.0 * sag)
        tip = r * math.tan(math.asin(min(1.0, r / R)))
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        out.append((a, b, (mx + nx * tip, my + ny * tip), R))
    return out


def billow_points(arcs, steps=6):
    """Points along the billow arcs (preview and fallback drawing)."""
    out = []
    for s, e, corner, R in arcs:
        r = _dist(s, e) / 2.0
        m = ((s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0)
        tl = _dist(corner, m)
        if tl < 1e-12:
            out.append(s)
            continue
        nx, ny = (corner[0] - m[0]) / tl, (corner[1] - m[1]) / tl
        d = math.sqrt(max(R * R - r * r, 0.0))
        c = (m[0] - nx * d, m[1] - ny * d)
        a0 = math.atan2(s[1] - c[1], s[0] - c[0])
        a1 = math.atan2(e[1] - c[1], e[0] - c[0])
        mid = math.atan2(ny, nx)
        ccw = (mid - a0) % (2 * math.pi) < (a1 - a0) % (2 * math.pi)
        out += _arc_points(c, R, a0, a1, ccw)[:-1]
    return out


def fuzzy(ring, size, height, var, rnd):
    """Points round the ring, each pushed in or out at random by up to
    `height` of `size` (Landmark's Plant Line: segment length and
    thickness)."""
    out = []
    for p, (nx, ny) in resample(ring, size, var, rnd):
        k = size * height * (2.0 * rnd.random() - 1.0) * (0.5 + 0.5 * max(var, 0.2))
        out.append((p[0] + nx * k, p[1] + ny * k))
    return out


def default_size(width, ring):
    """Billow size when the parameter is 0: about two thirds of the width,
    or of the shape's narrow side for a closed path."""
    if width > 0:
        return width * 0.67
    xs = [q[0] for q in ring]
    ys = [q[1] for q in ring]
    return max(min(max(xs) - min(xs), max(ys) - min(ys)) * 0.25, 1e-3)


def point_along(line, d):
    """The point d along an open line (clamped to its ends)."""
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]
        L = _dist(a, b)
        if d <= L or i == len(line) - 2:
            t = 0.0 if L < 1e-12 else max(0.0, min(1.0, d / L))
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        d -= L
    return line[-1]


def line_length(line):
    return sum(_dist(line[i], line[i + 1]) for i in range(len(line) - 1))


def project(line, q):
    """How far along the open line the point nearest q is."""
    best, best_d, run = 0.0, float('inf'), 0.0
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ll = dx * dx + dy * dy
        t = 0.0 if ll == 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / ll))
        d = math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy)
        if d < best_d:
            best, best_d = run + t * math.sqrt(ll), d
        run += math.sqrt(ll)
    return best


def _kink_indices(line, deg=KINK_DEG):
    out = []
    lim = math.radians(deg)
    for i in range(1, len(line) - 1):
        a, b, c = line[i - 1], line[i], line[i + 1]
        t1 = math.atan2(b[1] - a[1], b[0] - a[0])
        t2 = math.atan2(c[1] - b[1], c[0] - b[0])
        turn = abs((t2 - t1 + math.pi) % (2 * math.pi) - math.pi)
        if turn >= lim:
            out.append(i)
    return out


def kinks(line, deg=KINK_DEG):
    """The polyline's corners: vertices where it turns at least `deg`
    (a curve, read as many short straights, has none)."""
    return [line[i] for i in _kink_indices(line, deg)]


def offset_corners(line, d):
    """The corners of the line moved d to its left (as offset_side): the
    middle of the round on the outside of a bend, the mitre point on the
    inside. (The drawn corner itself is the same distance from every point
    of an outside round, so it can't be projected onto the row.)"""
    if abs(d) < 1e-9:
        return kinks(line)
    out = []
    for i in _kink_indices(line):
        a, c, b = line[i - 1], line[i], line[i + 1]
        l1, l2 = _dist(a, c), _dist(c, b)
        if l1 < 1e-12 or l2 < 1e-12:
            continue
        u1 = ((c[0] - a[0]) / l1, (c[1] - a[1]) / l1)
        u2 = ((b[0] - c[0]) / l2, (b[1] - c[1]) / l2)
        mx, my = -u1[1] - u2[1], u1[0] + u2[0]      # left normals added
        ml = math.hypot(mx, my)
        if ml < 1e-9:                               # turns right back
            continue
        turn = u1[0] * u2[1] - u1[1] * u2[0]
        outside = (turn < 0) if d > 0 else (turn > 0)
        dot = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
        k = d if outside else d / max(math.cos(math.acos(dot) / 2.0), 0.25)
        out.append((c[0] + mx / ml * k, c[1] + my / ml * k))
    return out


def fit_positions(L, spacing, stagger, breaks):
    """Distances along a line of length L for Plant Fit Ends: a plant on
    each break (0, L and any corners), each stretch between divided evenly
    at no more than `spacing` (stagger: one in the middle of each gap)."""
    out = []
    for a, b in zip(breaks, breaks[1:]):
        n = max(1, int(math.ceil((b - a) / spacing - 1e-9)))
        step = (b - a) / n
        if stagger:
            out += [a + (i + 0.5) * step for i in range(n)]
        else:
            out += [a + i * step for i in range(n)]
    if not stagger:
        out.append(L)
    return out[:MAX_PLANTS]


def row_centres(line, spacing, stagger=False, start=None, fit='Inset', corners=()):
    """Plants along an open line. start None: best fit at about `spacing`,
    half a space in from each end (stagger: shifted half a space, one
    fewer). start given: exactly `spacing` apart, one plant `start` along
    the line (stagger: half a space on), as far as the ends. fit Ends: a
    plant on each end and spacing a maximum (start ignored); Ends and
    Corners: a plant on each of `corners` too."""
    L = line_length(line)
    if L <= 0 or spacing <= 0:
        return []
    if fit != 'Inset':
        breaks = [0.0]
        if fit == 'Ends and Corners':
            for d in sorted(project(line, c) for c in corners):
                if breaks[-1] + 1e-6 < d < L - 1e-6:
                    breaks.append(d)
        breaks.append(L)
        return [point_along(line, d) for d in fit_positions(L, spacing, stagger, breaks)]
    if start is not None:
        first = (start + (spacing / 2.0 if stagger else 0.0)) % spacing
        n = int((L - first) / spacing + 1e-9) + 1
        return [point_along(line, first + i * spacing) for i in range(min(n, MAX_PLANTS))]
    n = max(1, int(round(L / spacing)))
    step = L / n
    if stagger:
        return [point_along(line, (i + 1) * step) for i in range(n - 1)] or \
            [point_along(line, L / 2.0)]
    return [point_along(line, (i + 0.5) * step) for i in range(n)]


def left_edge(width, offset):
    """How far the hedge's left edge is from the drawn line."""
    return {'Centre': width / 2.0, 'Left': width, 'Right': 0.0}[offset]


def centre_line(line, width, offset):
    """The hedge's true centreline (the drawn line, moved half the width
    when Line Is is Left or Right)."""
    line = dedupe(line, False)
    d = left_edge(width, offset) - width / 2.0
    return offset_side(line, d) if abs(d) > 1e-9 else line


def zigzag_centres(line, spacing, start, zigzag, fit='Inset', corners=()):
    """One row along the line with each plant `zigzag` off it, to one side
    then the other (so 2 x zigzag apart side to side), still `spacing` apart
    along the line."""
    out = []
    L = line_length(line)
    e = max(L * 1e-4, 1e-6)
    for i, q in enumerate(row_centres(line, spacing, start=start, fit=fit, corners=corners)):
        d = project(line, q)
        a, b = point_along(line, max(0.0, d - e)), point_along(line, min(L, d + e))
        t = _dist(a, b)
        if t < 1e-12:
            out.append(q)
            continue
        k = zigzag * (1 if i % 2 == 0 else -1)
        out.append((q[0] - (b[1] - a[1]) / t * k, q[1] + (b[0] - a[0]) / t * k))
    return out


def band_centres(line, width, offset, spacing, rows, start=None, zigzag=0.0, fit='Inset'):
    """Plant centres for a hedge along an open line: `rows` rows spread
    evenly across the width, every other row staggered. start: see
    row_centres (measured along each row). zigzag (one row only): the
    plants step alternately to each side of the centreline. fit: see
    row_centres (the corners are the drawn line's)."""
    line = dedupe(line, False)
    if len(line) < 2 or width <= 0:
        return []
    corners_on = fit == 'Ends and Corners'
    left = left_edge(width, offset)
    if rows == 1 and zigzag > 0:
        d = left - width / 2.0
        return zigzag_centres(centre_line(line, width, offset), spacing, start, zigzag,
                              fit, offset_corners(line, d) if corners_on else ())
    out = []
    for k in range(rows):
        # this row's offset to the left of the drawn line
        d = left - width * (k + 0.5) / rows
        row = offset_side(line, d) if abs(d) > 1e-9 else line
        if len(row) >= 2:
            out += row_centres(row, spacing, stagger=(k % 2 == 1), start=start,
                               fit=fit, corners=offset_corners(line, d) if corners_on else ())
        if len(out) > MAX_PLANTS:
            return out[:MAX_PLANTS]
    return out


def handle_row(pts, p):
    """The row the start dot and the Spacing and Plant Size handles sit
    on, so they are on plants: the middle row, or the one beside the middle
    that isn't staggered (an even number of rows has none on the
    centreline); one zigzag row: the side the first plant steps to.
    (row line, its offset to the left of the drawn line)."""
    line = dedupe(pts, False)
    left = left_edge(p.width, p.offset)
    if p.rows == 1:
        d = left - p.width / 2.0 + p.zigzag
    else:
        k0 = min(range(0, p.rows, 2), key=lambda k: abs(k - (p.rows - 1) / 2.0))
        d = left - p.width * (k0 + 0.5) / p.rows
    return (offset_side(line, d) if abs(d) > 1e-9 else line), d


def single_row_width(p, closed):
    """One row of plants along a line: the hedge is as wide as a plant
    (and the zigzag), so Line Is Left / Right puts the plants' edge on the
    line."""
    if p.plants and p.rows == 1 and not closed:
        sp = p.spacing if p.spacing > 0 else p.base_width
        p.width = max(1.0, p.plant_size if p.plant_size > 0 else sp * PLANT_SIZE_SHARE) + 2.0 * p.zigzag


def inside(q, ring):
    """Point in polygon (even-odd)."""
    x, y = q
    n = len(ring)
    hit = False
    for i in range(n):
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
    return hit


def area_centres(ring, spacing, anchor=None, margin=None, row_spacing=math.sqrt(3) / 2.0,
                 row_shift=0.5):
    """Plant centres filling a closed shape: a grid at `spacing` through
    `anchor` (None: the middle of the shape), rows `row_spacing` x spacing
    apart, each row shifted `row_shift` x spacing on from the one below
    (0.866 and 0.5: staggered, triangular; 1 and 0: square), each plant at
    least `margin` (None: a third of a space) in from the edge."""
    if spacing <= 0 or len(ring) < 3:
        return []
    xs = [q[0] for q in ring]
    ys = [q[1] for q in ring]
    dy = spacing * max(0.05, row_spacing)

    def row_off(j):
        return (j * row_shift) % 1.0 * spacing
    nx = int((max(xs) - min(xs)) / spacing) + 2
    ny = int((max(ys) - min(ys)) / dy) + 2
    if nx * ny > MAX_PLANTS * 4:
        return []
    mid = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
    if anchor is None:
        cx, cy = mid
    else:
        # the grid line through the anchor nearest the middle, so the loops
        # below still cover the shape
        j0 = round((mid[1] - anchor[1]) / dy)
        cy = anchor[1] + j0 * dy
        shift0 = row_off(j0)
        cx = anchor[0] + shift0 + round((mid[0] - anchor[0] - shift0) / spacing) * spacing
    edge = ring + [ring[0]]
    if margin is None:
        margin = spacing / 3.0
    out = []
    for j in range(-(ny // 2) - 1, ny // 2 + 2):
        y = cy + j * dy
        shift = row_off(j)
        for i in range(-(nx // 2) - 1, nx // 2 + 2):
            q = (cx + i * spacing + shift, y)
            if inside(q, ring) and dist_to_line(q, edge) >= margin:
                out.append(q)
                if len(out) >= MAX_PLANTS:
                    return out
    if not out:                     # too small for the grid: one in the middle
        c = mid
        if inside(c, ring):
            out.append(c)
    return out


def smooth_ring(pts, steps=4):
    """Points along a closed Catmull-Rom curve through pts: roughly the
    curve Vectorworks draws through CurveThrough vertices (Wavy edge)."""
    n = len(pts)
    out = []
    for k in range(n):
        p0, p1, p2, p3 = pts[k - 1], pts[k], pts[(k + 1) % n], pts[(k + 2) % n]
        for j in range(steps):
            u = j / float(steps)
            out.append(tuple(0.5 * (2 * p1[c] + (-p0[c] + p2[c]) * u +
                                    (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * u * u +
                                    (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * u ** 3)
                       for c in (0, 1)))
    return out


def scan_segments(rings, angle_deg, spacing, var, rnd):
    """Parallel lines at angle_deg, about `spacing` apart (varied by var),
    cut to the inside of the rings (overlapping rings merged): a list of
    (start, end) pairs."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    # rotate so the strokes run along x: v = -x sin + y cos is constant
    rots = [[(x * ca + y * sa, -x * sa + y * ca) for x, y in ring] for ring in rings]
    vs_ = [q[1] for rot in rots for q in rot]
    if not vs_:
        return []
    lo, hi = min(vs_), max(vs_)
    if hi - lo < 1e-9:
        return []
    if (hi - lo) / spacing > MAX_STROKES:
        spacing = (hi - lo) / MAX_STROKES
    spans = [(min(q[1] for q in rot), max(q[1] for q in rot)) for rot in rots]
    out = []
    v = lo + spacing * (0.3 + 0.4 * rnd.random())
    while v < hi:
        runs = []
        for rot, (r0, r1) in zip(rots, spans):
            if not r0 < v < r1:
                continue
            xs = []
            n = len(rot)
            for i in range(n):
                (x1, y1), (x2, y2) = rot[i], rot[(i + 1) % n]
                if (y1 > v) != (y2 > v):
                    xs.append(x1 + (v - y1) * (x2 - x1) / (y2 - y1))
            xs.sort()
            runs += [(xs[k], xs[k + 1]) for k in range(0, len(xs) - 1, 2)]
        runs.sort()
        merged = []
        for u0, u1 in runs:
            if merged and u0 <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], u1)
            else:
                merged.append([u0, u1])
        for u0, u1 in merged:
            out.append(((u0 * ca - v * sa, u0 * sa + v * ca), (u1 * ca - v * sa, u1 * sa + v * ca)))
        v += spacing * (1.0 + var * 0.5 * (2.0 * rnd.random() - 1.0))
    return out


def pen_strokes(rings, angle_deg, spacing, var, rnd, cross=False):
    """Pencil strokes filling the rings (a list): each stroke stops short of the edge
    or runs a little past it, wobbles slightly, and a long one is sometimes
    broken. Each stroke is a list of points."""
    passes = [angle_deg] + ([angle_deg + 90.0] if cross else [])
    out = []
    wob = spacing * (0.08 + 0.25 * var)
    for ang in passes:
        for a, b in scan_segments(rings, ang, spacing, var, rnd):
            L = _dist(a, b)
            if L < spacing * 0.3:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            # each end: in by up to a space, or out by up to a third of one
            s0 = spacing * (rnd.random() * 1.3 - 0.3)
            s1 = spacing * (rnd.random() * 1.3 - 0.3)
            if L - s0 - s1 < spacing * 0.5:
                s0 = s1 = 0.0
            pieces = [(s0, L - s1)]
            if L > spacing * 12 and rnd.random() < 0.5:      # a break in a long stroke
                m = L * (0.3 + 0.4 * rnd.random())
                g = spacing * (0.5 + rnd.random())
                pieces = [(s0, m - g / 2.0), (m + g / 2.0, L - s1)]
            for t0, t1 in pieces:
                if t1 - t0 < spacing * 0.3:
                    continue
                k = max(1, min(4, int((t1 - t0) / (spacing * 6))))
                pts = []
                for j in range(k + 1):
                    t = t0 + (t1 - t0) * j / k
                    off = 0.0 if j in (0, k) else wob * (2.0 * rnd.random() - 1.0)
                    pts.append((a[0] + ux * t - uy * off, a[1] + uy * t + ux * off))
                out.append(pts)
                if len(out) >= MAX_STROKES:
                    return out
    return out


def default_spacing(p, ring, closed):
    """Plant Spacing 0: the hedge width (a closed shape: a quarter of its
    narrow side, as its automatic billow size)."""
    if not closed and p.base_width > 0:
        return p.base_width / p.rows if p.plants else p.base_width
    return default_size(0.0, ring)


def seed_for(p, uuid):
    """Seed 0: from the object's UUID, so each hedge differs and keeps its
    look."""
    if p.seed:
        return p.seed
    return zlib.crc32((uuid or 'hedge').encode('utf-8')) or 1


# --------------------------------------------------------------------------
# Plants shape: a rough circle at each plant, merged where they overlap
# --------------------------------------------------------------------------

class Circle:
    """A rough plant circle: centre c, radius radii[k] at angle 2 pi k / n
    (star shaped about c, so a point is inside if it is nearer c than the
    edge at its angle)."""

    def __init__(self, c, radii):
        self.c = c
        self.radii = radii
        self.rmax = max(radii)

    def radius_at(self, ang):
        n = len(self.radii)
        t = (ang % (2 * math.pi)) / (2 * math.pi) * n
        k = int(t) % n
        f = t - int(t)
        return self.radii[k] * (1.0 - f) + self.radii[(k + 1) % n] * f

    def contains(self, q):
        dx, dy = q[0] - self.c[0], q[1] - self.c[1]
        d = math.hypot(dx, dy)
        return d < self.radius_at(math.atan2(dy, dx)) - 1e-9

    def points(self):
        n = len(self.radii)
        return [(self.c[0] + r * math.cos(2 * math.pi * k / n),
                 self.c[1] + r * math.sin(2 * math.pi * k / n))
                for k, r in enumerate(self.radii)]


def plant_circles(centres, radius, var, edge, rnd, n=CIRCLE_POINTS):
    """A rough circle at each centre. Variability varies the size (up to
    about a quarter); the edge follows Edge: Billow a near circle, Wavy a
    gentle wobble, Fuzzy jagged."""
    out = []
    for c in centres:
        r0 = radius * (1.0 + 0.25 * var * (2.0 * rnd.random() - 1.0))
        if edge == 'Fuzzy':
            radii = [r0 * (1.0 + 0.09 * (2.0 * rnd.random() - 1.0)) for _ in range(n)]
        else:
            amp = 0.07 if edge == 'Wavy' else 0.025
            k1, k2 = rnd.randint(2, 3), rnd.randint(4, 6)
            f1, f2 = rnd.random() * 2 * math.pi, rnd.random() * 2 * math.pi
            radii = [r0 * (1.0 + amp * 0.5 * (math.sin(k1 * a + f1) + math.sin(k2 * a + f2)))
                     for a in (2 * math.pi * k / n for k in range(n))]
        out.append(Circle(c, radii))
    return out


def _neighbours(circles):
    """For each circle, the others that could overlap it (a grid lookup)."""
    if not circles:
        return []
    cell = 2.0 * max(ci.rmax for ci in circles)
    grid = {}
    for i, ci in enumerate(circles):
        grid.setdefault((int(math.floor(ci.c[0] / cell)), int(math.floor(ci.c[1] / cell))), []).append(i)
    out = []
    for i, ci in enumerate(circles):
        gx, gy = int(math.floor(ci.c[0] / cell)), int(math.floor(ci.c[1] / cell))
        near = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    if j != i and _dist(ci.c, circles[j].c) < ci.rmax + circles[j].rmax:
                        near.append(circles[j])
        out.append(near)
    return out


def outer_runs(circles):
    """The outline round the outside of the circles: for each circle, the
    parts of its edge not inside another, as (points, closed). Where an
    edge goes under a neighbour the run ends exactly at the crossing."""
    runs = []
    for ci, near in zip(circles, _neighbours(circles)):
        pts = ci.points()
        n = len(pts)

        def covered(q):
            return any(o.contains(q) for o in near)

        out = [not covered(q) for q in pts]
        if all(out):
            runs.append((pts, True))
            continue
        if not any(out):
            continue

        def crossing(a, b):
            # a covered, b not: bisect for where the edge comes out
            for _ in range(14):
                m = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
                if covered(m):
                    a = m
                else:
                    b = m
            return b

        k0 = out.index(False)
        run = None
        for m in range(1, n + 1):
            k, prev = (k0 + m) % n, (k0 + m - 1) % n
            if out[k] and not out[prev]:
                run = [crossing(pts[prev], pts[k]), pts[k]]
            elif out[k] and run is not None:
                run.append(pts[k])
            elif not out[k] and out[prev] and run is not None:
                run.append(crossing(pts[k], pts[prev]))
                runs.append((run, False))
                run = None
    return runs


def keep_clear_filter(centres, shapes, clearance):
    """Drop plants on a keep-clear shape: ('circle', c, r) or ('poly', pts),
    allowing `clearance` of overlap from the plant's centre."""
    if not shapes:
        return centres
    out = []
    for q in centres:
        hit = False
        for s in shapes:
            if s[0] == 'circle':
                hit = _dist(q, s[1]) < s[2] + clearance
            else:
                ring = s[1]
                hit = inside(q, ring) or dist_to_line(q, ring + [ring[0]]) < clearance
            if hit:
                break
        if not hit:
            out.append(q)
    return out


# --------------------------------------------------------------------------
# Reading the path
# --------------------------------------------------------------------------

def path_closed(path):
    try:
        return bool(vs.IsPolyClosed(path))
    except Exception:
        return vs.GetTypeN(path) == 5


def vertex_points(path):
    """Path vertices (straight lines between them): the fallback."""
    pts = []
    try:
        n = vs.GetVertNum(path)
        if vs.GetTypeN(path) == 5:
            pts = [tuple(vs.GetPolyPt(path, i))[:2] for i in range(1, n + 1)]
        else:
            for i in range(1, n + 1):
                pt = vs.GetPolylineVertex(path, i)[0]
                pts.append((pt[0], pt[1]))
    except Exception:
        pass
    return pts


def corner_vertices(path):
    """The path's corners, which lie on it: every vertex of a polygon, the
    corner vertices of a polyline (not curve or arc control points)."""
    out = []
    try:
        n = vs.GetVertNum(path)
        if vs.GetTypeN(path) == 5:
            return [tuple(vs.GetPolyPt(path, i))[:2] for i in range(1, n + 1)]
        for i in range(1, n + 1):
            v = vs.GetPolylineVertex(path, i)
            pt, vt = v[0], int(v[1])
            rad = float(v[2]) if len(v) > 2 else 0.0
            if vt == 0 or (vt == 3 and rad <= 0):
                out.append((float(pt[0]), float(pt[1])))
    except Exception:
        return []
    return out


def insert_corners(pts, corners, closed, step):
    """The sampled points with the path's corners put back: sampling at
    even steps cuts each corner off with a short chord (two half bends
    either side of it, so Ends and Corners put a plant on each). Each
    corner goes between the two samples either side of it along the path."""
    n = len(pts)
    m = n if closed else n - 1
    if not corners or m < 1:
        return list(pts)
    tol = step * 1.01 + 1e-6

    def fit(i, c):
        a, b = pts[i], pts[(i + 1) % n]
        legs = _dist(a, c) + _dist(c, b)
        return legs - _dist(a, b) if legs <= tol else None

    found = {}
    pos = 0
    for c in corners:
        # corners come in path order: search on from the last one (then
        # round from the start), only as far as the samples either side
        best = None
        for i in list(range(pos, m)) + list(range(0, pos)):
            x = fit(i, c)
            if x is not None:
                if best is None or x < best[1]:
                    best = (i, x)
            elif best is not None:
                break
        if best is not None:
            found.setdefault(best[0], []).append(c)
            pos = best[0]
    out = []
    for i in range(n):
        out.append(pts[i])
        a, b = pts[i], pts[(i + 1) % n]
        for c in sorted(found.get(i, ()), key=lambda q: _dist(a, q)):
            if _dist(c, a) > 1e-6 and _dist(c, b) > 1e-6:
                out.append(c)
    return out


def _numbers(v):
    """All the numbers in a (possibly nested) tuple, in order."""
    out = []
    if isinstance(v, (tuple, list)):
        for x in v:
            out += _numbers(x)
    elif isinstance(v, bool):
        pass
    elif isinstance(v, (int, float)):
        out.append(float(v))
    return out


def _to_local(h):
    """A function from layer coordinates to the object's own (its path's)
    coordinates: undoes the object's offset and rotation."""
    ox = oy = rot = 0.0
    try:
        nums = _numbers(vs.GetEntityMatrix(h))
        if len(nums) >= 6:
            ox, oy, rot = nums[-6], nums[-5], nums[-1]
    except Exception:
        pass
    a = math.radians(-rot)
    ca, sa = math.cos(a), math.sin(a)

    def f(q):
        x, y = q[0] - ox, q[1] - oy
        return (x * ca - y * sa, x * sa + y * ca)
    return f


def keep_clear_shapes(h, cls):
    """Objects in class `cls` on the hedge's layer, in the hedge's
    coordinates: polygons and polylines by their vertices, rectangles by
    their box, anything else (circles, tree symbols, plug-ins) as the circle
    in its box."""
    if not cls:
        return []
    try:
        if vs.Name2Index(cls) == 0:
            return []
        layer = vs.GetLayer(h)
    except Exception:
        return []
    local = _to_local(h)
    found = []

    def look(o):
        try:
            if o == h or vs.GetLayer(o) != layer:
                return
            t = vs.GetTypeN(o)
            if t in (5, 21):
                pts = vertex_points(o)
                if len(pts) >= 3:
                    found.append(('poly', [local(q) for q in pts]))
                    return
            (x1, y1), (x2, y2) = [tuple(q)[:2] for q in vs.GetBBox(o)]
            if t == 3:
                box = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                found.append(('poly', [local(q) for q in box]))
            else:
                c = local(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
                found.append(('circle', c, (abs(x2 - x1) + abs(y2 - y1)) / 4.0))
        except Exception:
            pass
    try:
        vs.ForEachObject(look, "(C='%s')" % cls.replace("'", ""))
    except Exception:
        pass
    return found


def path_points(path, step, closed):
    """Points along the path, about `step` apart, curves included."""
    try:
        length = float(vs.HPerim(path))
    except Exception:
        length = 0.0
    pts = []
    if length > 0:
        n = MAX_SAMPLES // 3 if step <= 0 else math.ceil(length / step)
        n = int(min(MAX_SAMPLES, max(8, n)))
        try:
            for i in range(n + 1):
                ok, pt, _tan = vs.PointAlongPoly(path, length * i / n)
                if not ok:
                    break
                pts.append((pt[0], pt[1]))
        except Exception:
            pts = []
        if len(pts) >= 2:
            pts = insert_corners(pts, corner_vertices(path), closed, length / n)
    if len(pts) < 2:
        pts = vertex_points(path)
    return dedupe(pts, closed)


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

_arcto = {}


def _arc_to(x, y, r):
    """ArcTo takes (x, y, r) or ((x, y), r) depending on the version."""
    form = _arcto.get('form')
    if form is None:
        try:
            vs.ArcTo(x, y, r)
            _arcto['form'] = 0
        except Exception:
            vs.ArcTo((x, y), r)
            _arcto['form'] = 1
    elif form == 0:
        vs.ArcTo(x, y, r)
    else:
        vs.ArcTo((x, y), r)


def _curve_through(x, y):
    try:
        vs.CurveThrough(x, y)
    except Exception:
        vs.CurveThrough((x, y))


def draw_billows(arcs):
    vs.ClosePoly()
    vs.BeginPoly()
    try:
        for s, _e, corner, R in arcs:
            vs.AddPoint(s[0], s[1])
            _arc_to(corner[0], corner[1], R)
        vs.EndPoly()
        return vs.LNewObj()
    except Exception:
        vs.EndPoly()
        h = vs.LNewObj()
        if h:
            vs.DelObject(h)
    return draw_poly(billow_points(arcs))


def draw_smooth(pts):
    """A closed curve through pts (Wavy edge)."""
    vs.ClosePoly()
    vs.BeginPoly()
    for x, y in pts:
        _curve_through(x, y)
    vs.EndPoly()
    return vs.LNewObj()


def _no_fill(h):
    try:
        vs.SetFPat(h, 0)
    except Exception:
        pass


def _no_pen(h):
    for fn in ('SetLSN', 'SetLS'):
        try:
            getattr(vs, fn)(h, 0)
            return
        except Exception:
            continue


def _set_fill_rgb(h, rgb):
    """Solid fill in rgb (0-65535): fore and back, as a solid fill shows
    the back colour. The Python call form varies, so read it back."""
    try:
        vs.SetFPat(h, 1)
    except Exception:
        pass
    for fn, get in (('SetFillBack', 'GetFillBack'), ('SetFillFore', 'GetFillFore')):
        for args in ((h, rgb), (h,) + rgb):
            try:
                getattr(vs, fn)(*args)
                if _close_rgb(getattr(vs, get)(h), rgb):
                    break
            except Exception:
                continue


def _shadowed(o):
    """o made into a shadow: grey, see-through, no pen."""
    _no_pen(o)
    _set_fill_rgb(o, SHADOW_RGB)
    try:
        vs.SetOpacityN(o, 100, SHADOW_OPACITY)
    except Exception:
        try:
            vs.SetOpacity(o, SHADOW_OPACITY)
        except Exception:
            pass


def draw_poly(pts, closed=True):
    if closed:
        vs.ClosePoly()
    else:
        vs.OpenPoly()
    vs.BeginPoly()
    for x, y in pts:
        vs.AddPoint(x, y)
    vs.EndPoly()
    return vs.LNewObj()


def shadow_vector(h, off, angle=SHADOW_ANGLE):
    """(dx, dy) in the object's own coordinates for a shadow that falls at
    `angle` on the drawing (degrees anticlockwise from right; 315 = down and
    right). off is how far across and down it goes at 315, so the default
    looks as before; every angle moves it the same distance (off x 1.41).
    Undoes the object's rotation, so every bed casts its shadow the same way
    however it was rotated."""
    d = off * math.sqrt(2.0)
    a = math.radians(angle)
    to_local = _to_local(h)
    o, s = to_local((0.0, 0.0)), to_local((d * math.cos(a), d * math.sin(a)))
    return (s[0] - o[0], s[1] - o[1])


def draw_plants(circles, fill, shadow, offset):
    """Shadow (optional, offset = (dx, dy) from shadow_vector), then each
    circle's fill with no pen, then the outline round the outside only, so
    overlapping plants read as one."""
    if shadow:
        dx, dy = offset
        for ci in circles:
            pts = [(x + dx, y + dy) for x, y in ci.points()]
            _shadowed(draw_poly(pts))
    if fill:
        for ci in circles:
            _no_pen(draw_poly(ci.points()))
    for pts, closed in outer_runs(circles):
        _no_fill(draw_poly(pts, closed))


def ensure_marker_class(name):
    """Create the plant centres class if missing: black pen, solid black
    fill, Use at Creation. One that exists is left exactly as it is."""
    if not name:
        return
    try:
        if vs.Name2Index(name) != 0:
            return
        if not _new_class(name):
            return
    except Exception:
        return
    for call in (lambda: vs.SetClFPat(name, 1), lambda: vs.SetClUseGraphic(name, True)):
        try:
            call()
        except Exception:
            pass
    _set_class_colour('SetClPenFore', 'GetClPenFore', name, (0, 0, 0))
    _set_class_colour('SetClFillFore', 'GetClFillFore', name, (0, 0, 0))
    # A solid fill shows the fill background colour, so set that too
    _set_class_colour('SetClFillBack', 'GetClFillBack', name, (0, 0, 0))


def _by_class(o, name):
    """Object o in class `name`, every attribute from the class."""
    try:
        _set_class(o, name)
    except Exception:
        return
    for fn in ('SetLSByClass', 'SetLWByClass', 'SetPenColorByClass',
               'SetFillColorByClass', 'SetFPatByClass', 'SetOpacityByClass'):
        try:
            getattr(vs, fn)(o)
        except Exception:
            pass


def draw_centres(h, centres, style, size, cls):
    """A small mark at each plant: a circle, a dot or a cross. size: across,
    in drawing units. cls: the marks' class (pen and fill from it, so it
    can be filled or turned off on its own); none: the hedge's attributes,
    circles unfilled and dots filled in the pen colour."""
    r = size / 2.0
    pen = None
    if style == 'Dot' and not cls:
        try:
            pen = vs.GetPenFore(h)
        except Exception:
            pen = None
    for x, y in centres:
        if style == 'Cross':
            for a, b in (((x - r, y), (x + r, y)), ((x, y - r), (x, y + r))):
                vs.MoveTo(a[0], a[1])
                vs.LineTo(b[0], b[1])
                if cls:
                    _by_class(vs.LNewObj(), cls)
            continue
        try:
            vs.Oval(x - r, y + r, x + r, y - r)
        except Exception:
            vs.Oval((x - r, y + r), (x + r, y - r))
        o = vs.LNewObj()
        if cls:
            _by_class(o, cls)
            if style == 'Dot':                  # solid, in the class's fill colour
                try:
                    vs.SetFPat(o, 1)
                except Exception:
                    pass
        elif style == 'Circle':
            _no_fill(o)
        else:
            try:
                vs.SetFPat(o, 1)
                if pen:
                    vs.SetFillFore(o, pen)
                    vs.SetFillBack(o, pen)
            except Exception:
                pass


def draw_strokes(strokes, opacity):
    """Open polylines in the hedge's pen colour and weight (inherited),
    no fill, at `opacity` %: overlapping strokes build up the colour."""
    for pts in strokes:
        vs.OpenPoly()
        vs.BeginPoly()
        for i, (x, y) in enumerate(pts):
            if 0 < i < len(pts) - 1:
                _curve_through(x, y)
            else:
                vs.AddPoint(x, y)
        vs.EndPoly()
        o = vs.LNewObj()
        _no_fill(o)
        if opacity < 100:
            try:
                vs.SetOpacityN(o, opacity, 100)     # pen first, then fill
            except Exception:
                try:
                    vs.SetOpacity(o, opacity)
                except Exception:
                    pass


def edge_points(edge):
    """The drawn edge as points (for cutting the pen strokes to it)."""
    if edge[0] == 'billow':
        return billow_points(edge[1])
    return smooth_ring(edge[1]) if edge[2] else list(edge[1])


def hedge_outline(p, path_pts, closed):
    """The plain outline: the closed path, or the band along an open one."""
    if closed:
        return path_pts if len(path_pts) >= 3 else []
    return band_outline(path_pts, p.width, p.offset)


def rough_edge(p, ring, rnd, closed):
    """('billow', arcs) or ('points', pts, smooth) for the drawn edge."""
    base = default_size(0.0 if closed else p.width, ring)
    # Billow Size is a real size (mm): a small number (1) would give
    # hundreds of tiny billows, a sandpaper edge. Never under a fifth of
    # the default.
    size = max(p.size, base * MIN_SIZE_SHARE) if p.size > 0 else base
    if p.edge == 'Fuzzy':
        size *= 0.5         # shorter segments, as Landmark's Plant Line
    outline = ring
    # closed shapes only: along a line Width is the hedge's core, billows outside
    keep = p.keep_inside and closed
    if keep and not (p.edge == 'Billow' and p.concave):
        # Keep Inside Outline: move the outline in by about how far the
        # edge bulges, so the hedge finishes within the drawn shape
        if p.edge == 'Billow':
            bulge = min(p.height * (1.0 + 0.5 * p.var), 0.95) * size / 2.0 * (1.0 + 0.3 * p.var)
        else:
            bulge = size * p.height * (0.5 + 0.5 * max(p.var, 0.2))
        ring = inset_ring(ring, bulge)
    if p.edge == 'Billow':
        if keep and not p.concave:
            return 'billow', billows_inside(outline, ring, size, p, rnd)
        return 'billow', billows(ring, size, p.height, p.var, p.concave, rnd)
    return 'points', fuzzy(ring, size, p.height, p.var, rnd), p.edge == 'Wavy'


def billows_inside(outline, ring, size, p, rnd):
    """Billows on the inset ring, checked against the drawn outline: where
    any still bulge past it, the ring goes in by that much more and the
    same billows (same random draws) are made again."""
    state = rnd.getstate()
    edge = outline + [outline[0]]
    arcs = billows(ring, size, p.height, p.var, False, rnd)
    for _ in range(3):
        over = [dist_to_line(q, edge) for q in billow_points(arcs, 4) if not inside(q, outline)]
        worst = max(over) if over else 0.0
        if worst <= size * 0.01:
            break
        ring = inset_ring(ring, worst * 1.1)
        rnd.setstate(state)
        arcs = billows(ring, size, p.height, p.var, False, rnd)
    return arcs


def set_new_class(h):
    """A hedge just drawn goes in HEDGE_CLASS (made if missing), unless
    the active class is already a Landscape one."""
    try:
        if not vs.IsNewCustomObject(TOOL_OBJECT):
            return
        active = vs.ActiveClass()
        if active.lower().startswith('landscape'):
            return
        if vs.Name2Index(HEDGE_CLASS) == 0 and not _new_class(HEDGE_CLASS):
            return
        _set_class(h, HEDGE_CLASS)
    except Exception:
        pass


def _short(v):
    """10.0 -> '10', 2.5 -> '2.5'."""
    return ('%.2f' % v).rstrip('0').rstrip('.')


def drawn_size(p):
    """The sizes set in mm on the sheet, as drawn in the file's units:
    'Markers 150, strokes 100, shadow 80 at 1:100' (as Break Line Tool's
    Drawn Size). Only what this planting shows."""
    parts = []
    if p.centres:
        parts.append('markers %s' % _short(p.centre_size))
    if p.fill != 'Solid':
        parts.append('strokes %s apart' % _short(p.pen_spacing))
    if p.shadow:
        parts.append('shadow %s' % _short(p.shadow_offset))
    text = ', '.join(parts) or 'drawn'
    return '%s%s at 1:%s' % (text[0].upper(), text[1:], _short(p.scale))


def reset(h, rec):
    check_params(rec)
    set_new_class(h)
    ensure_style_map(h)
    p = Params(h, rec)
    p.set('Version', '%s (%s)' % (VERSION, VERSION_DATE))
    p.set('DrawnSize', drawn_size(p))
    path = vs.GetCustomObjectPath(h)
    if not path:
        return
    closed = path_closed(path)
    if p.size > 0 and (closed or p.width <= 0):
        step = p.size / 3.0
    elif p.size > 0:
        size = max(p.size, p.width * 0.67 * MIN_SIZE_SHARE)
        step = min(size / 3.0, p.width / 4.0)
    else:
        step = 0.0 if closed or p.width <= 0 else p.width / 4.0
    pts = path_points(path, step, closed)
    if closed and len(pts) == 2:            # two clicks: a rectangle on the diagonal
        (ax, ay), (bx, by) = pts
        pts = [(ax, ay), (bx, ay), (bx, by), (ax, by)]
    p.locked = style_locked(h)
    single_row_width(p, closed)          # before the drags: the handles' row
    handle_drags(p, pts, closed)
    single_row_width(p, closed)          # a Plant Size drag changes it
    ring = hedge_outline(p, pts, closed)
    if len(ring) < 3:
        p.set('PlantCount', '0')
        return
    try:
        uuid = vs.GetObjectUuid(h)
    except Exception:
        uuid = ''
    seed = seed_for(p, uuid)
    rnd = random.Random(seed)
    spacing = p.spacing if p.spacing > 0 else default_spacing(p, ring, closed)
    radius = (p.plant_size if p.plant_size > 0 else spacing * PLANT_SIZE_SHARE) / 2.0
    clear = keep_clear_shapes(h, p.keep_clear) if p.keep_clear else []

    centres = []
    start = None
    if p.centres or p.plants:
        centre = None if closed else handle_row(pts, p)[0]
        start, anchor = plant_start(p, closed, centre, ring, spacing)
        if closed:
            if p.plants:
                # Keep Inside: whole circles in the shape; else mostly in
                margin = radius * (1.05 if p.keep_inside else 0.6)
            else:
                margin = None
            centres = area_centres(ring, spacing, anchor, margin, p.row_spacing, p.row_shift)
            if start is None and centres:
                # automatic grid: the dot on the plant nearest the middle,
                # not the middle itself (outside an L-shaped bed)
                dot = min(centres, key=lambda q: _dist(q, anchor))
                _set_cp(p, 1, dot)
        else:
            centres = band_centres(pts, p.width, p.offset, spacing, p.rows, start, p.zigzag,
                                   p.fit)
        # a plant may overlap a keep-clear object by half its radius
        centres = keep_clear_filter(centres, clear, radius * 0.5)

    if p.plants:
        circles = plant_circles(centres, radius, p.var, p.edge, rnd)
        draw_plants(circles, p.fill != 'Pen', p.shadow, shadow_vector(h, p.shadow_offset, p.shadow_angle))
        if p.fill != 'Solid':
            strokes = pen_strokes([ci.points() for ci in circles], p.pen_angle, p.pen_spacing,
                                  p.var, random.Random(seed + 1), p.cross)
            draw_strokes(strokes, p.pen_opacity)
    else:
        edge = rough_edge(p, ring, rnd, closed)
        if p.shadow:
            pts_e = edge_points(edge)
            dx, dy = shadow_vector(h, p.shadow_offset, p.shadow_angle)
            _shadowed(draw_poly([(x + dx, y + dy) for x, y in pts_e]))
        if edge[0] == 'billow':
            outline = draw_billows(edge[1])
        else:
            outline = (draw_smooth if edge[2] else draw_poly)(edge[1])
        if p.fill != 'Solid':
            if p.fill == 'Pen':
                _no_fill(outline)
            # own random stream, so changing the pen settings keeps the edge
            strokes = pen_strokes([edge_points(edge)], p.pen_angle, p.pen_spacing, p.var,
                                  random.Random(seed + 1), p.cross)
            draw_strokes(strokes, p.pen_opacity)

    if p.centres:
        cls = p.marker_class
        if cls:
            ensure_marker_class(cls)
        draw_centres(h, centres, p.centre_style, p.centre_size, cls)
    p.set('PlantCount', str(len(centres) if (p.centres or p.plants) else 0))
    draw_guide_path(pts, closed)
    place_handles(h, p, pts, closed, spacing, radius, start, centres)


def _cp(p, i=1):
    return (p._num('ControlPoint%02dX' % i), p._num('ControlPoint%02dY' % i))


def _set_cp(p, i, q):
    p.set_num('ControlPoint%02dX' % i, q[0])
    p.set_num('ControlPoint%02dY' % i, q[1])


def _state_points(p):
    """Where each control point (1 to 5) was left last redraw, None if not
    known. State is 'x1,y1;...;x5,y5' (0.7 had four)."""
    out = [None] * 6
    for i, part in enumerate(p._str('State').split(';')[:5]):
        try:
            x, y = (float(v) for v in part.split(','))
            out[i + 1] = (x, y)
        except Exception:
            pass
    return out


def _state_point(p):
    return _state_points(p)[1]


def _write_state(p):
    p.set('State', ';'.join('%.6f,%.6f' % _cp(p, i) for i in range(1, 6)))


def _moved(p, last, i):
    return last[i] is not None and _dist(_cp(p, i), last[i]) > 1e-4


def handle_drags(p, pts, closed):
    """A dragged handle sets its value: Width (2, the hedge's edge),
    Spacing (3, the next plant from the dot), Plant Size (4, on the dot
    plant's circle) or, on a closed shape, Row Spacing and Row Shift (5, a
    plant in the next row). Reshaping moves no handle, so changes nothing
    here. A value that comes from the style is never set (its handle is
    hidden)."""
    last = _state_points(p)
    line = dedupe(pts, False)
    lk = p.locked
    if _moved(p, last, 2) and not closed and len(line) >= 2 and 'Width' not in lk:
        d = dist_to_line(_cp(p, 2), line)
        w = max(2.0 * d if p.offset == 'Centre' else d, 1.0)
        p.width = p.base_width = w
        p.set_num('Width', w)
    dot = _cp(p, 1)
    if _moved(p, last, 3) and 'PlantSpacing' not in lk:
        if closed:
            sp = _dist(_cp(p, 3), dot)
        elif len(line) >= 2:
            row = handle_row(pts, p)[0]
            sp = abs(project(row, _cp(p, 3)) - project(row, dot))
        else:
            sp = 0.0
        if sp > 1.0:
            p.spacing = sp
            p.set_num('PlantSpacing', sp)
    if _moved(p, last, 4) and 'PlantSize' not in lk:
        size = 2.0 * _dist(_cp(p, 4), dot)
        if size > 1.0:
            p.plant_size = size
            p.set_num('PlantSize', size)
    if _moved(p, last, 5) and closed and p.spacing > 0 and not lk & {'RowSpacing', 'RowShift'}:
        v = (_cp(p, 5)[0] - dot[0], _cp(p, 5)[1] - dot[1])
        if v[1] < 0:                        # on the row below
            v = (-v[0], -v[1])
        rs = v[1] / p.spacing
        if rs >= 0.1:
            p.row_spacing = min(5.0, rs)
            p.row_shift = (v[0] / p.spacing) % 1.0
            p.set_num('RowSpacing', round(p.row_spacing * 100.0, 1))
            p.set_num('RowShift', round(p.row_shift * 100.0, 1) % 100.0)


def _pick_handle(cands, centres, ring, spacing):
    """The first candidate that is a plant, else the first on the bed,
    else the first."""
    tol = max(spacing, 1.0) * 1e-3
    for q in cands:
        if any(_dist(q, c) < tol for c in centres):
            return q
    for q in cands:
        if inside(q, ring):
            return q
    return cands[0]


def place_handles(h, p, pts, closed, spacing, radius, start, centres=()):
    """Put the handles where they belong this redraw, show the ones that
    apply, and remember where they all are (State)."""
    line = dedupe(pts, False)
    plants_on = p.centres or p.plants
    if not closed and len(line) >= 2:
        L = line_length(line)
        m = point_along(line, L / 2.0)
        e = max(L * 0.01, 1e-6)
        a, b = point_along(line, L / 2.0 - e), point_along(line, L / 2.0 + e)
        tl = _dist(a, b)
        if tl > 1e-9:
            nx, ny = -(b[1] - a[1]) / tl, (b[0] - a[0]) / tl     # left of the line
            off = {'Centre': p.width / 2.0, 'Left': p.width, 'Right': -p.width}[p.offset]
            _set_cp(p, 2, (m[0] + nx * off, m[1] + ny * off))
    dot = _cp(p, 1)
    if plants_on and spacing > 0:
        if closed:
            # Spacing: a plant one space from the dot (a Spacing drag reads
            # the distance), along its row first, else round the dot (the
            # staggered grid has six such neighbours), else on the bed
            angles = (0, 180, 60, 120, 240, 300, 90, 270, 30, 150, 210, 330)
            cands = [(dot[0] + spacing * math.cos(math.radians(a)),
                      dot[1] + spacing * math.sin(math.radians(a))) for a in angles]
            _set_cp(p, 3, _pick_handle(cands, centres, line, spacing))
            # row: a plant in the next row up or down (a row drag reads the
            # height and the shift along, so any of them will do)
            v = (p.row_shift * spacing, p.row_spacing * spacing)
            cands = [(dot[0] + v[0], dot[1] + v[1]), (dot[0] + v[0] - spacing, dot[1] + v[1]),
                     (dot[0] - v[0], dot[1] - v[1]), (dot[0] - v[0] + spacing, dot[1] - v[1])]
            _set_cp(p, 5, _pick_handle(cands, centres, line, spacing))
        else:
            centre, d = handle_row(pts, p)
            if len(centre) >= 2 and p.fit != 'Inset':
                corners = offset_corners(line, d) if p.fit == 'Ends and Corners' else ()
                row = row_centres(centre, spacing, fit=p.fit, corners=corners)
                if len(row) >= 2:
                    _set_cp(p, 3, row[1])     # the second plant, as fitted
            elif len(centre) >= 2:
                Lc = line_length(centre)
                s1 = project(centre, dot)
                step = spacing if start is not None else Lc / max(1, int(round(Lc / spacing)))
                pos = s1 + step if s1 + step <= Lc + 1e-9 else s1 - step
                _set_cp(p, 3, point_along(centre, max(0.0, pos)))
    if p.plants:
        k = radius * math.sqrt(0.5)
        _set_cp(p, 4, (dot[0] + k, dot[1] + k))
    lk = p.locked
    width_on = not closed and not (p.plants and p.rows == 1) and 'Width' not in lk
    # Plant Fit Ends pins the plants to the ends: no start to drag
    start_on = plants_on and (closed or p.fit == 'Inset')
    shown = ((1, start_on), (2, width_on), (3, plants_on and 'PlantSpacing' not in lk),
             (4, p.plants and 'PlantSize' not in lk),
             (5, closed and plants_on and not lk & {'RowSpacing', 'RowShift'}))
    for i, show in shown:
        try:
            vs.SetCntrlPtVis(h, i, show)        # the handle on the drawing
        except Exception:
            pass
        for axis in 'XY':
            try:
                vs.SetParameterVisibility(h, 'ControlPoint%02d%s' % (i, axis), show)
            except Exception:
                pass
    labels = {1: 'start', 2: 'W', 3: 'crs', 4: '\u00d8', 5: 'row'}
    draw_handle_labels(p, [(_cp(p, i), labels[i]) for i, show in shown if show])
    _write_state(p)


def ensure_guide_class():
    """The guides' class (the drawn path, the handle labels), made if
    missing (grey). Vectorworks has no script call for a class's Non Plot
    option: tick it once in the class."""
    try:
        if vs.Name2Index(GUIDE_CLASS) != 0:
            return True
        if not _new_class(GUIDE_CLASS):
            return False
    except Exception:
        return False
    grey = (128 * 257, 128 * 257, 128 * 257)
    _set_class_colour('SetClPenFore', 'GetClPenFore', GUIDE_CLASS, grey)
    _set_class_colour('SetClFillFore', 'GetClFillFore', GUIDE_CLASS, grey)
    return True


def draw_guide_path(pts, closed):
    """The path as drawn (the line, or the closed shape), unfilled, in the
    guides class: shows where the hedge was set out from, on screen only
    once the class is Non Plot."""
    if len(pts) < 2 or not ensure_guide_class():
        return
    try:
        o = draw_poly(pts, closed)
        _no_fill(o)
        _set_class(o, GUIDE_CLASS)
        for fn in ('SetLSByClass', 'SetLWByClass', 'SetPenColorByClass'):
            try:
                getattr(vs, fn)(o)
            except Exception:
                pass
    except Exception:
        pass


def draw_handle_labels(p, items):
    """A small label centred on each handle (start, W, crs, diameter, row),
    in the guides' class: on screen only once the class is Non Plot."""
    if not items or not ensure_guide_class():
        return
    for fn, v in (('TextSize', LABEL_POINTS), ('TextJust', 2), ('TextVerticalAlign', 3)):
        try:
            getattr(vs, fn)(v)          # 2: centred across; 3: centred up and down
        except Exception:
            pass
    for (x, y), text in items:
        try:
            vs.TextOrigin(x, y)
            vs.CreateText(text)
            o = vs.LNewObj()
            for fn, v in (('SetTextJust', 2), ('SetTextVerticalAlign', 3)):
                try:
                    getattr(vs, fn)(o, v)
                except Exception:
                    pass
            _set_class(o, GUIDE_CLASS)
            for fn in ('SetPenColorByClass', 'SetFillColorByClass'):
                try:
                    getattr(vs, fn)(o)
                except Exception:
                    pass
        except Exception:
            pass


def plant_start(p, closed, centre, ring, spacing):
    """Where the plants start: (start along each row or None, grid anchor
    or None). The dot (ControlPoint01) marks a plant: drag it to slide the
    rows along the hedge, or the grid across a shape. State holds where the
    dot was left last redraw, so a drag can be told from a reshape. Plant
    Start -1 = automatic (best fit, or the grid centred); Restart sets it
    back."""
    cp = _cp(p)
    last = _state_point(p)
    tol = max(spacing, 1.0) * 1e-6
    dragged = last is not None and _dist(cp, last) > tol
    start = p.start if p.start >= 0 else None
    anchor = None
    if closed:
        if dragged:
            p.set_num('PlantStart', 1.0)
            start = 1.0
        if start is not None:
            anchor = cp
        else:
            xs = [q[0] for q in ring]
            ys = [q[1] for q in ring]
            anchor = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
        dot = anchor
    else:
        if len(centre) < 2:
            return None, None
        L = line_length(centre)
        if p.fit != 'Inset':
            _set_cp(p, 1, centre[0])        # the first plant, on the start
            return None, None
        if dragged:
            start = project(centre, cp)
            p.set_num('PlantStart', start)
        if start is None:
            # best fit: the dot on the first plant of the middle row
            n = max(1, int(round(L / spacing)))
            dot = point_along(centre, 0.5 * L / n)
        else:
            dot = point_along(centre, min(start, L))
    _set_cp(p, 1, dot)
    return start, anchor


# --------------------------------------------------------------------------
# Object Info palette layout (event-based plug-in)
# --------------------------------------------------------------------------

LAYOUT = [
    ('Planting', ['Shape', 'Width', 'Offset', 'KeepInside']),
    ('Plants', ['PlantSpacing', 'PlantSize', 'PlantFit', 'Rows', 'Zigzag', 'RowSpacing',
                'RowShift', 'KeepClear', 'PlantCount']),
    ('Edge', ['EdgeStyle', 'BillowSize', 'BillowHeight', 'Variability', 'BillowType', 'Seed']),
    ('Fill', ['FillStyle', 'PenSpacing', 'PenAngle', 'CrossHatch', 'PenOpacity', 'Shadow',
              'ShadowOffset', 'ShadowAngle']),
    ('Plant Centres', ['ShowCentres', 'CentreStyle', 'CentreSize', 'MarkerClass']),
    ('About', ['Version', 'DrawnSize']),
]
LABELS = {'Width': 'Width', 'Offset': 'Line Is', 'EdgeStyle': 'Edge',
          'BillowSize': 'Billow Size', 'BillowHeight': 'Billow Height (%)',
          'Variability': 'Variability (%)', 'BillowType': 'Billow Type', 'Seed': 'Seed',
          'Version': 'Version', 'ShowCentres': 'Show Plant Centres',
          'PlantSpacing': 'Spacing (crs)', 'Rows': 'Rows', 'CentreStyle': 'Marker',
          'CentreSize': 'Marker Size (sheet mm)', 'PlantCount': 'Plant Count',
          'MarkerClass': 'Marker Class', 'FillStyle': 'Fill',
          'PenSpacing': 'Stroke Spacing (sheet mm)', 'PenAngle': 'Stroke Angle (deg)',
          'CrossHatch': 'Cross Hatch', 'PenOpacity': 'Stroke Opacity (%)',
          'Shape': 'Shape', 'PlantSize': 'Plant Size (\u00d8)', 'Shadow': 'Shadow',
          'ShadowOffset': 'Shadow Offset (sheet mm)', 'ShadowAngle': 'Shadow Angle (deg)',
          'KeepClear': 'Keep Clear of Class', 'Zigzag': 'Zigzag Offset',
          'KeepInside': 'Keep Inside Outline', 'PlantFit': 'Plant Fit',
          'RowSpacing': 'Row Spacing (% crs)', 'RowShift': 'Row Shift (% crs)',
          'DrawnSize': 'Drawn Size'}
READ_ONLY = ('Version', 'PlantCount', 'DrawnSize')

WIDGET_BASE = 1000
HEADING_BASE = 2000
# Fixed widget IDs: only ever add to the end of these lists.
WIDGET_IDS = ['Width', 'Offset', 'EdgeStyle', 'BillowSize', 'BillowHeight', 'Variability',
              'BillowType', 'Seed', 'Version',
              'ShowCentres', 'PlantSpacing', 'Rows', 'CentreStyle', 'CentreSize', 'PlantCount',
              'MarkerClass', 'FillStyle', 'PenSpacing', 'PenAngle', 'CrossHatch', 'PenOpacity',
              'Shape', 'PlantSize', 'Shadow', 'KeepClear', 'Zigzag', 'KeepInside',
              'PlantFit', 'RowSpacing', 'RowShift', 'ShadowOffset', 'DrawnSize', 'ShadowAngle']
HEADING_IDS = ['Planting', 'Edge', 'About', 'Plants', 'Fill', 'Plant Centres']   # was Hedge


def _widget_ids():
    out = []
    for heading, names in LAYOUT:
        hid = HEADING_BASE + HEADING_IDS.index(heading)
        out.append((hid, heading, [(WIDGET_BASE + WIDGET_IDS.index(n), n) for n in names]))
    return out


DEBUG_LOG = False      # True writes tool_debug.log next to this file (testing)


def init_layout():
    _log('init_layout', VERSION, __file__)
    vs.SetObjPropVS(kObjXPropHasUIOverride, True)
    vs.SetObjPropVS(kObjXHasCustomWidgetVisibilities, True)
    vs.SetObjPropCharVS(kObjPropWidgetGroupMode, chr(kWidgetGroupAutomatic))
    for hid, heading, params in _widget_ids():
        vs.vsoAddWidget(hid, kWidgetSeparator, heading)
        vs.vsoWidgetSetIndLvl(hid, 0)
        for wid, name in params:
            ok = vs.vsoAddParamWidget(wid, name, LABELS.get(name, ''))
            if ok:
                vs.vsoWidgetSetIndLvl(wid, 1)
            else:
                _log('  no widget for', name)
        if heading == 'Edge':
            vs.vsoAddWidget(RESHUFFLE_ID, kWidgetButton, 'Reshuffle')
            vs.vsoWidgetSetIndLvl(RESHUFFLE_ID, 1)
        if heading == 'Plants':
            vs.vsoAddWidget(RESTART_ID, kWidgetButton, 'Reset Plant Start')
            vs.vsoWidgetSetIndLvl(RESTART_ID, 1)
        if heading == 'About':
            vs.vsoAddWidget(ABOUT_WEB_ID, kWidgetButton, WEBSITE)
            vs.vsoWidgetSetIndLvl(ABOUT_WEB_ID, 1)
            vs.vsoAddWidget(ABOUT_UPDATE_ID, kWidgetButton, 'Check for updates...')
            vs.vsoWidgetSetIndLvl(ABOUT_UPDATE_ID, 1)
    vs.SetObjPropVS(kObjXSupportsStyles, True)


# Plug-in styles: a style is a kind of hedge (width, edge, fill, plants):
# STYLE_PARAMS By Style. Everything else (Line Is, Seed, the plant start,
# the handles, the read-only fields) stays with each hedge (By Instance).
# Set the first time a style is used; change it in Edit Style.
STYLE_PARAMS = ('Width', 'EdgeStyle', 'BillowSize', 'BillowHeight', 'Variability',
                'BillowType', 'ShowCentres', 'PlantSpacing', 'Rows', 'CentreStyle',
                'CentreSize', 'MarkerClass', 'FillStyle', 'PenSpacing', 'PenAngle',
                'CrossHatch', 'PenOpacity', 'Shape', 'PlantSize', 'Shadow', 'KeepClear',
                'Zigzag', 'KeepInside', 'PlantFit', 'RowSpacing', 'RowShift', 'ShadowOffset',
                'ShadowAngle')
kByInstance, kByStyle = 0, 1
HANDLE_PARAMS = ('Width', 'PlantSpacing', 'PlantSize', 'RowSpacing', 'RowShift')


def _style_def(h):
    try:
        name = vs.GetPluginStyle(h)
    except Exception:
        return None
    if not name:
        return None
    return vs.GetObject(name) or None


def style_locked(h):
    """The handle values (HANDLE_PARAMS) that come from the hedge's style:
    their handles are hidden, so a drag can't override the style."""
    sd = _style_def(h)
    if not sd:
        return set()
    out = set()
    for name in HANDLE_PARAMS:
        try:
            if vs.GetParamStyleType(sd, name) == kByStyle:
                out.add(name)
        except Exception:
            pass
    return out


def ensure_style_map(h):
    """First use of a style: STYLE_PARAMS By Style, the rest By Instance.
    A style whose Seed is already By Instance has been set up: left alone."""
    sd = _style_def(h)
    if not sd:
        return
    try:
        if vs.GetParamStyleType(sd, 'Seed') == kByInstance:
            return
        vs.SetAllStyleParams(sd, kByInstance)
        for name in STYLE_PARAMS:
            try:
                vs.SetParamStyleType(sd, name, kByStyle)
            except Exception:
                pass
    except Exception:
        pass


def hidden_widgets(closed, plants, centres, rows, edge, fill, shadow=True):
    """The Object Info fields that don't apply to this hedge."""
    hidden = set()
    if closed:
        hidden |= {'Width', 'Offset', 'Rows', 'Zigzag', 'PlantFit'}
    else:
        hidden |= {'KeepInside', 'RowSpacing', 'RowShift'}   # no outline, no grid
    if not closed and plants and rows == 1:
        hidden.add('Width')                 # the plant size is the hedge's width
    if rows != 1:
        hidden.add('Zigzag')
    if plants:
        hidden |= {'BillowSize', 'BillowHeight', 'BillowType'}
    else:
        hidden.add('PlantSize')
        if not centres:                     # a band with no plants marked
            hidden |= {'PlantSpacing', 'Rows', 'Zigzag', 'KeepClear', 'PlantCount',
                       'PlantFit', 'RowSpacing', 'RowShift'}
    if edge != 'Billow':
        hidden.add('BillowType')
    if fill == 'Solid':
        hidden |= {'PenSpacing', 'PenAngle', 'CrossHatch', 'PenOpacity'}
    if not centres:
        hidden |= {'CentreStyle', 'CentreSize', 'MarkerClass'}
    if not shadow:
        hidden |= {'ShadowOffset', 'ShadowAngle'}
    return hidden


def widget_prep(h, rec):
    """Fields that don't apply are hidden (a heading too, when all of its
    fields are): see hidden_widgets."""
    def field(name):
        return vs.GetRField(h, rec, name)
    closed = False
    try:
        path = vs.GetCustomObjectPath(h)
        closed = bool(path) and path_closed(path)
    except Exception:
        pass
    plants = match_choice(field('Shape'), SHAPES, 'Band') == 'Plants'
    centres = field('ShowCentres').strip().lower() == 'true'
    try:
        rows = max(1, min(MAX_ROWS, int(round(float(field('Rows').strip() or '1')))))
    except ValueError:
        rows = 1
    hidden = hidden_widgets(closed, plants, centres, rows,
                            match_choice(field('EdgeStyle'), EDGES, 'Billow'),
                            match_choice(field('FillStyle'), FILL_STYLES, 'Solid'),
                            field('Shadow').strip().lower() == 'true')
    for hid, heading, params in _widget_ids():
        shown = False
        for wid, name in params:
            vs.vsoWidgetSetVisible(wid, name not in hidden)
            vs.vsoWidgetSetEnable(wid, name not in READ_ONLY)
            shown = shown or name not in hidden
        vs.vsoWidgetSetVisible(hid, shown)
        if heading == 'Plants':
            # nothing to reset when Plant Fit Ends pins the plants to the ends
            pinned = not closed and plant_fit(field('PlantFit')) != 'Inset'
            vs.vsoWidgetSetVisible(RESTART_ID, shown and not pinned)
    vs.vsoSetEventResult(kObjectEventHandled)


def reshuffle(h, rec):
    """A new random seed: the same hedge with a different rough edge."""
    vs.SetRField(h, rec, 'Seed', str(random.randint(1, 99999)))
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


def run():
    try:
        event, button = vs.vsoGetEventInfo()
    except Exception:
        event, button = 0, 0

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
        if button == RESHUFFLE_ID:
            reshuffle(h, rec)
        elif button == RESTART_ID:
            vs.SetRField(h, rec, 'PlantStart', '-1')
            vs.ResetObject(h)
        elif button == ABOUT_WEB_ID:
            open_website()
        elif button == ABOUT_UPDATE_ID:
            check_updates()
    elif event in (kResetEventID, 0):
        try:
            reset(h, rec)
        except Exception:
            _reset_failed(vs.GetName(h))


# --- Planting tool (the .vst): what its clicks make --------------------------
TOOL_OBJECT = 'Planting Tool'
TOOL_NAME = 'Planting'
TOOL_LINE, TOOL_SHAPE, TOOL_RECT, TOOL_FREEHAND = 1, 2, 3, 4
# (mode icon, vstSetPtBehavior, help): 4 points until double-click, 101 box, 103 freehand
TOOL_MODES = (
    ('Vectorworks/ModeViewBar/Line_Button4.svg', 4,
     'Line (a hedge): click each point, double-click to finish'),
    ('Vectorworks/ModeViewBar/Vertex_Mode.svg', 4,
     'Closed shape (a bed): click each corner, double-click to finish'),
    ('Vectorworks/ModeViewBar/Rectangle_Mode.svg', 101,
     'Rectangle: click one corner, then the opposite corner'),
    ('Vectorworks/ModeViewBar/Freehand_Mode.svg', 103,
     'Freehand: drag around the bed'),
)
TOOL_PULLDOWNS = ()
# the spanner: (field, label, 'num' / 'text' / choices)
TOOL_DEFAULTS = tuple((f, LABELS[f], kind) for f, kind in (
    ('Shape', SHAPES),
    ('Width', 'num'),
    ('Offset', OFFSETS),
    ('EdgeStyle', EDGES),
    ('PlantSpacing', 'num'),
    ('Rows', 'num'),
    ('FillStyle', FILL_STYLES),
    ('Shadow', ('True', 'False')),
    ('ShowCentres', ('True', 'False')),
))


def tool_complete(mode, pts, h):
    if mode == TOOL_LINE:
        if len(pts) >= 2:
            styled_new(new_path_object(pts, False))
        return
    if mode == TOOL_RECT and len(pts) >= 2:
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        ring = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    elif mode == TOOL_FREEHAND or len(pts) < 3:
        ring = _tool_object_points(h) if h else []
    else:
        ring = pts
    if len(ring) >= 3 and abs(signed_area(ring)) > 1e-6:
        styled_new(new_path_object(ring, True))


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
