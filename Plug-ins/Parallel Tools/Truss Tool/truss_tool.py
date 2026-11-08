"""
Truss Tool for Vectorworks 2026 / 2027

Copyright (c) 2026 Ian Thrush
Licensed under the MIT License (see LICENSE.md).

Schematic timber roof trusses as a linear plug-in object, using MiTek NZ
terminology (GANG-NAIL Residential Manual, truss types and coding).

Schematic only. Final truss design, sizes and layout are by the truss
fabricator.

The .vso holds a short loader stub; all logic lives here.
"""

import copy
import math
import re

import vs

VERSION = '0.15.1'
VERSION_DATE = '2026-11-09'
AUTHOR = 'Ian Thrush / Parallel Architecture NZ'
WEBSITE = 'github.com/itchyNZL/parallel-tools'
TOOL_FOLDER = 'Truss Tool'
DEBUG_LOG = False      # True writes tool_debug.log next to this file (testing)
NOTICE = 'Schematic only: confirm with truss supplier'

# MiTek truss codes (the code in brackets at the end of the Truss Type choice)
T_RAFTER = 'T'      # Rafter Truss
T_GIRDER = 'G'      # Girder Truss
T_TRUNC = 'TR'      # Truncated Rafter Truss
T_TRUNC_G = 'TG'    # Truncated Girder Truss
T_GABLE = 'GE'      # Gable End Truss
T_JACK = 'J'        # Jack Truss
T_TJACK = 'TJ'      # Truncated Jack Truss
T_HALF = 'H'        # Half Truss
T_VALLEY = 'V'      # Saddle or Valley Truss (S/V)
T_SCISSOR = 'SC'    # Scissor Truss
T_COVE = 'VT'       # Vaulted (Cove) Truss
T_ATTIC = 'AT'      # Attic Truss
T_HIP = 'HE'        # Hip End assembly
T_VSET = 'VS'       # Valley Set assembly

HALF_TYPES = (T_JACK, T_TJACK, T_HALF)
TWO_SIDED = (T_RAFTER, T_GIRDER, T_TRUNC, T_TRUNC_G, T_GABLE, T_SCISSOR, T_COVE, T_ATTIC)
OVERHANG_TYPES = TWO_SIDED + (T_HALF,)      # types with Two Overhangs

# Prefix used for the automatic ID (MiTek coding)
ID_PREFIX = {T_VALLEY: 'V', T_COVE: 'VT', T_ATTIC: 'AT', T_HIP: 'HE', T_VSET: 'VS'}
ASSEMBLIES = (T_HIP, T_VSET)
GIRDER_TYPES = (T_GIRDER, T_TRUNC_G)

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
kObjOnUIButtonHit = 35
kWidgetButton = 12
kObjXSupportsStyles = 49
kObjOnEditPluginStyle = 60
kObjectEditPluginStyleByDefault = -10   # reply: use the default style dialog
ABOUT_WEB_ID = 3002
ABOUT_UPDATE_ID = 3101

BIG = 1.0e7
RIDGE_SETBACK = 100  # mm along the slope from the apex to the top outrigger


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------


CODES = {'T': T_RAFTER, 'G': T_GIRDER, 'TR': T_TRUNC, 'TG': T_TRUNC_G,
         'GE': T_GABLE, 'J': T_JACK, 'TJ': T_TJACK, 'H': T_HALF,
         'S/V': T_VALLEY, 'S': T_VALLEY, 'V': T_VALLEY, 'SC': T_SCISSOR,
         'VT': T_COVE, 'CV': T_COVE, 'AT': T_ATTIC, 'A': T_ATTIC, 'HE': T_HIP, 'VS': T_VSET}


def truss_code(choice):
    """'Truncated Girder Truss (TG)' -> 'TG'. Unknown -> Rafter Truss."""
    m = re.search(r'\(([A-Za-z/]+)\)\s*$', choice.strip())
    return CODES.get(m.group(1).upper(), T_RAFTER) if m else T_RAFTER


class Params:
    def __init__(self, h, rec):
        self.h = h
        self.rec = rec
        self.mm = _mm()

        self.type = truss_code(self._str('TrussType'))

        self.web_pattern = self._str('WebPattern')
        self.span = self._num('LineLength')
        self.elev = self._num('Elevation')
        self.pitch = self._num('Pitch', 25.0)
        # Two Pitches ticked: Pitch (Right) and Heel (Right) apply.
        self.two_pitch = self._bool('TwoPitch') and self.type in (T_RAFTER, T_GIRDER)
        pr = self._num('PitchRight')
        self.pitch_r = pr if (self.two_pitch and 1.0 <= pr <= 75.0) else self.pitch
        # Scissor ceiling pitch: blank, 0 or not less than the roof pitch = half the roof pitch
        self.ceiling_pitch = self._num('CeilingPitch')
        if not (0 < self.ceiling_pitch < self.pitch):
            self.ceiling_pitch = self.pitch / 2.0
        self.heel = self._num('HeelHeight')
        self.heel_r = self._num('HeelHeightRight')
        self.overhang = max(0.0, self._num('Overhang'))
        self.high_overhang = 0.0              # Half Truss: set from Two Overhangs below
        # Two Overhangs ticked: Overhang (R) on the right-hand side (0 = none).
        self.two_overhangs = self._bool('TwoOverhangs') and self.type in OVERHANG_TYPES
        self.overhang_r = max(0.0, self._num('OverhangRight')) if self.two_overhangs else self.overhang
        # Hip End with Two Overhangs: Overhang is the end wall, Overhang (L) and
        # Overhang (R) the side walls at the start and end of the line.
        self.side_overhangs = self._bool('TwoOverhangs') and self.type == T_HIP
        self.overhang_l = self.overhang
        if self.side_overhangs:
            self.overhang_l = max(0.0, self._num('OverhangLeft', self.overhang))
            self.overhang_r = max(0.0, self._num('OverhangRight'))
        self.setback = max(0.0, self._num('Setback'))
        self.spacing = self._pos('TrussSpacing', 900 * self.mm)
        # Flip: Hip End / Valley Set to the other side of the line; Gable End
        # outriggers on the other face.
        self.flip_side = self.flip_outriggers = self._bool('Flip')
        # Half Hip End / Valley Set: only the Side chosen (Left = start of the
        # line, Right = end) gets the hip or valley.
        self.half = self._bool('HalfAssembly')
        self.half_right = self._str('HalfSide').startswith('Right')
        self.high_left = self._str('HighEnd').startswith('Left')
        self.half_valley = self._bool('HalfValley')
        if self.type == T_HALF:
            # Half Truss: Overhang is the low end. With Two Overhangs, Overhang
            # and Overhang (R) are the left and right ends as drawn, so the high
            # end takes the side it is on.
            if self.two_overhangs:
                left, right = self.overhang, self.overhang_r
                self.overhang, self.high_overhang = (right, left) if self.high_left else (left, right)
            self.two_overhangs = False        # no right-hand tail to move on a half truss
        mm = self.mm
        self.thick = self._pos('Thickness', 45 * mm)
        self.plies = self._plies() if self.type in GIRDER_TYPES + (T_HIP,) else 1
        self.tc = self._pos('TopChord', 90 * mm)
        self.bc = self._pos('BottomChord', 90 * mm)
        self.web = self._pos('WebGauge', 70 * mm)
        self.soffit_gauge = self._pos('SoffitBearerGauge', 90 * mm)
        self.soffit_drop = self._num('SoffitDrop')
        self.heel_override = self._bool('HeelOverride')
        self.outriggers = self._bool('Outriggers')
        self.outrigger_gauge = self._pos('OutriggerGauge', 90 * mm)
        self.outrigger_ctr = self._pos('OutriggerCentre', 900 * mm)
        self.verge = max(0.0, self._num('OverhangSoffit'))
        self.dist_first = max(0.0, self._num('DistanceFirstTruss'))
        # Web Centres: 0 = 1200 for girders, 600 for gable end / valley verticals.
        wc = self._num('WebCentres')
        self.vert_ctr = wc if wc > 0 else 600 * mm
        self.girder_ctr = wc if wc > 0 else 1200 * mm
        self.cove_length = max(0.0, self._num('CoveLength'))
        self.cove_gauge = max(self._pos('CoveGauge', 190 * mm), self.tc)
        self.attic_width = max(0.0, self._num('AtticWidth'))
        self.collar_height = self._pos('CollarHeight', 2400 * mm)
        self.plan_display = self._str('PlanDisplay')
        self.outrigger_plan = self._str('OutriggerPlan')
        self.status = self._str('Status').strip()
        self.class_templates = {
            'truss': self._str('ClassTruss'),
            'outrigger': self._str('ClassOutrigger'),
            'soffit': self._str('ClassSoffit'),
            'hip': self._str('ClassHip'),
        }
        # Set only for the trusses inside a Hip End: a half girder may be
        # truncated, and truncated flat tops drop by the rafter depth.
        self.allow_trunc = False
        self.trunc_drop = 0.0

        # Override Auto unticked: Setback, Web Centres, Cove Length, Attic Width
        # and Ceiling Pitch are automatic (the values are written back, greyed).
        self.auto_override = self._bool('AutoOverride')
        if not self.auto_override:
            self.setback = 0.0
            self.vert_ctr, self.girder_ctr = 600 * mm, 1200 * mm
            self.cove_length = self.attic_width = 0.0
            self.ceiling_pitch = self.pitch / 2.0
        self._bearers()

    def _bearers(self):
        """Bearers: Both / Left / Right / None, as drawn. Half trusses are built
        high end on the right and mirrored, so map to their low / high ends."""
        half = self.type in HALF_TYPES
        sides = self._str('SoffitBearerSides').strip().lower() or 'both'
        left = sides in ('both', 'left')
        right = sides in ('both', 'right')
        if self.type in ASSEMBLIES:
            left = right = left or right
        self.bearer_left, self.bearer_right = left, right
        if half:
            self.soffit_bearers = right if self.high_left else left    # low end
            self.high_soffit = left if self.high_left else right       # high end
        else:
            self.soffit_bearers = left
            self.high_soffit = False

    def _str(self, name):
        return vs.GetRField(self.h, self.rec, name)

    def _num(self, name, default=0.0):
        text = self._str(name).replace('\u00b0', '').strip()   # Angle fields: "25°"
        ok, v = vs.ValidNumStr(text)
        return v if ok else default

    def _plies(self):
        """Girder pop-up ('1 Ply' / '2 Ply' / '3 Ply'); 2 if not set."""
        g = self._str('Girder').strip()
        digits = ''.join(ch for ch in g if ch.isdigit())
        return max(1, int(digits)) if digits else 2

    def _pos(self, name, default):
        """Sizes and spacings: 0 or blank falls back to a sensible default."""
        v = self._num(name)
        return v if v > 0 else default

    def _bool(self, name):
        return self._str(name).strip().lower() == 'true'

    def set(self, name, value):
        vs.SetRField(self.h, self.rec, name, value)


# --------------------------------------------------------------------------
# 2D geometry helpers (truss elevation: x along span, y up from wall plate)
# --------------------------------------------------------------------------

def clip(poly, a, b, c):
    """Keep the part of poly where a*x + b*y + c >= 0."""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp = a * p[0] + b * p[1] + c
        fq = a * q[0] + b * q[1] + c
        if fp >= 0:
            out.append(p)
        if (fp >= 0) != (fq >= 0):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def clip_under(poly, lines):
    """Clip poly to the region below every line y = m*x + k."""
    for m, k, _x0, _x1 in lines:
        poly = clip(poly, m, -1.0, k)
        if len(poly) < 3:
            return []
    return poly


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def chord(m, k, xa, xb, depth_v):
    """Chord between xa and xb whose top edge is y = m*x + k.
    depth_v is the vertical depth (member depth / cos pitch)."""
    return [(xa, m * xa + k), (xb, m * xb + k),
            (xb, m * xb + k - depth_v), (xa, m * xa + k - depth_v)]


def _hit(ox, oy, ux, uy, line):
    """Distance along the ray (ox, oy) + s*(ux, uy) to line y = m*x + k,
    or None if parallel or outside the line's x range."""
    m, k, x0, x1 = line
    den = uy - m * ux
    if abs(den) < 1e-12:
        return None
    s = (m * ox + k - oy) / den
    x = ox + s * ux
    return s if x0 - 1e-6 <= x <= x1 + 1e-6 else None


def _corner(lines, i, j):
    """Intersection of lines i and j, or None."""
    m1, k1 = lines[i][0], lines[i][1]
    m2, k2 = lines[j][0], lines[j][1]
    if i == j or abs(m1 - m2) < 1e-12:
        return None
    x = (k2 - k1) / (m1 - m2)
    return (x, m1 * x + k1)


def web(p, q, width, bottoms, tops):
    """Web member on centreline p -> q, trimmed to the bottom-chord top
    line(s) it starts on and the first top-chord underside it meets.
    bottoms: a y value (flat bottom chord) or a list of (m, k, xmin, xmax).
    tops: list of (m, k, xmin, xmax) lines."""
    if isinstance(bottoms, (int, float)):
        bottoms = [(0.0, float(bottoms), -BIG, BIG)]
    dx, dy = q[0] - p[0], q[1] - p[1]
    length = math.hypot(dx, dy)
    if length <= 0 or abs(dy) < 1e-9:
        return []
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    ends = []
    for sgn in (1.0, -1.0):
        ox = p[0] + sgn * nx * width / 2.0
        oy = p[1] + sgn * ny * width / 2.0
        hits = [(s, i) for i, ln in enumerate(bottoms)
                for s in [_hit(ox, oy, ux, uy, ln)] if s is not None]
        if not hits:
            return []
        sb, ib = min(hits, key=lambda h: abs(h[0]))
        hits = [(s, i) for i, ln in enumerate(tops)
                for s in [_hit(ox, oy, ux, uy, ln)] if s is not None and s > sb]
        if not hits:
            return []
        st, it = min(hits)
        ends.append(((ox + sb * ux, oy + sb * uy), ib, (ox + st * ux, oy + st * uy), it))

    (b1, ib1, t1, it1), (b2, ib2, t2, it2) = ends
    poly = [b1, t1]
    top_corner = _corner(tops, it1, it2)
    if top_corner:
        poly.append(top_corner)
    poly += [t2, b2]
    bottom_corner = _corner(bottoms, ib1, ib2)
    if bottom_corner:
        poly.append(bottom_corner)
    return poly


def between(poly, x0=None, x1=None):
    """Keep the part of poly with x0 <= x <= x1 (either bound optional)."""
    if poly and x0 is not None:
        poly = clip(poly, 1.0, 0.0, -x0)
    if poly and x1 is not None:
        poly = clip(poly, -1.0, 0.0, x1)
    return poly if poly and len(poly) >= 3 else []


def mirror_x(poly, about):
    return [(2.0 * about - x, y) for x, y in poly]


def under_y(lines, x):
    """Lowest top-chord underside at x."""
    return min(m * x + k for m, k, x0, x1 in lines if x0 - 1e-6 <= x <= x1 + 1e-6)


# --------------------------------------------------------------------------
# Truss geometry
# --------------------------------------------------------------------------

class Geometry:
    def __init__(self):
        self.members = []     # elevation profiles, extruded through truss thickness
        self.outriggers = []  # (profile, z1, z2), extruded perpendicular to truss
        self.bearers = []     # (profile, z1, z2), beside the truss
        self.plan_x = (0.0, 0.0)
        self.plan_outriggers = []  # (x0, x1, y0, y1)

    def add_pair(self, poly, L):
        """poly and its mirror image about the middle of span L."""
        self.add(poly)
        self.add(mirror_x(poly, L / 2.0))

    def add(self, poly):
        if poly and len(poly) >= 3:
            self.members.append(poly)


def heel_minimum(p):
    depth = p.cove_gauge if p.type == T_COVE else p.tc
    return depth / math.cos(math.radians(p.pitch))


def is_dual(p):
    """Rafter or Girder truss with a different pitch or heel on the right."""
    if p.type not in (T_RAFTER, T_GIRDER):
        return False
    return (abs(p.pitch_r - p.pitch) > 0.01 or
            abs(p.heel_r - p.heel) > 0.01 * p.mm)


def build_dual(p):
    """Two-pitch Rafter / Girder truss: Roof Pitch and Heel Height on the left,
    Roof Pitch (Right) and Heel Height (Right) on the right. The apex sits
    where the two roof lines meet."""
    g = Geometry()
    L = p.span
    mm = p.mm
    OH = p.overhang
    tL, cL = math.tan(math.radians(p.pitch)), math.cos(math.radians(p.pitch))
    tR, cR = math.tan(math.radians(p.pitch_r)), math.cos(math.radians(p.pitch_r))
    HL, HR = p.heel, p.heel_r
    xa = (HR - HL + tR * L) / (tL + tR)
    xa = min(max(xa, 0.1 * L), 0.9 * L)
    hw = p.web / 2.0
    bc = p.bc

    lines = [(tL, HL - p.tc / cL, -BIG, xa),
             (-tR, HR + tR * L - p.tc / cR, xa, BIG)]

    def yu(x):
        return under_y(lines, x)

    # ---- chords ----
    g.add(chord(tL, HL, -OH, xa, p.tc / cL))
    g.add(chord(-tR, HR + tR * L, xa, L + OH, p.tc / cR))
    g.add(clip_under(rect(0.0, 0.0, L, bc), lines))

    # ---- raised heel posts ----
    if yu(p.web) - bc > 30 * mm:
        g.add(clip_under(rect(0.0, bc, p.web, BIG), lines))
    if yu(L - p.web) - bc > 30 * mm:
        g.add(clip_under(rect(L - p.web, bc, L, BIG), lines))

    # ---- webs ----
    apex = (xa, yu(xa))
    qL = (xa / 2.0, yu(xa / 2.0))
    qR = (xa + (L - xa) / 2.0, yu(xa + (L - xa) / 2.0))
    if p.type == T_GIRDER:
        ctr = p.girder_ctr
        nl = max(2, int(math.ceil(xa / ctr)))
        nr = max(2, int(math.ceil((L - xa) / ctr)))
        left = [i * xa / nl for i in range(nl + 1)]
        right = [xa + i * (L - xa) / nr for i in range(nr + 1)]
        for x in left[1:] + right[1:-1]:
            if yu(x) - bc > 30 * mm:
                g.add(web((x, bc), (x, yu(x)), p.web, bc, lines))
        for a, b in zip(left[1:-1], left[2:]):
            g.add(between(web((a, bc), (b, yu(b)), p.web, bc, lines), a + hw, b - hw))
        for a, b in zip(right[:-2], right[1:-1]):
            g.add(between(web((b, bc), (a, yu(a)), p.web, bc, lines), a + hw, b - hw))
    elif p.web_pattern.startswith('King'):
        g.add(web((xa, bc), apex, p.web, bc, lines))
        g.add(between(web((xa, bc), qL, p.web, bc, lines), None, xa - hw))
        g.add(between(web((xa, bc), qR, p.web, bc, lines), xa + hw, None))
    else:  # 4 Web
        nL = (xa * 2.0 / 3.0, bc)
        nR = (L - (L - xa) * 2.0 / 3.0, bc)
        g.add(between(web(nL, apex, p.web, bc, lines), None, xa))
        g.add(web(nL, qL, p.web, bc, lines))
        g.add(between(web(nR, apex, p.web, bc, lines), xa, None))
        g.add(web(nR, qR, p.web, bc, lines))

    # ---- soffit bearers, each side to its own pitch and heel ----
    b_left, b_right = p.soffit_bearers, p.bearer_right
    if (b_left or b_right) and OH > 0:
        T = p.thick * p.plies
        sbL, botL = bearer_profile(p, False, HL, tL, cL, OH, L)
        sbR, botR = bearer_profile(p, True, HR, tR, cR, OH, L)
        for sb, on in ((sbL, b_left), (sbR, b_right)):
            if on and len(sb) >= 3:
                g.bearers.append((sb, T / 2.0, T / 2.0 + p.thick))
        if p.soffit_drop < 0:
            cut_tails(g, min(botL, botR))

    g.plan_x = (-OH, L + OH)
    return apply_right_overhang(p, g, tR, HR, cR)


def bearer_profile(p, right, H, t, c, oh, L):
    """Soffit bearer beside a top chord tail: from the wall line out to the
    fascia, underside level with the bottom of the tail at the fascia, lowered
    by Soffit Bearer Drop, never above the roof line. H, t, c: that side's
    heel, tan(pitch) and cos(pitch); oh: that side's overhang."""
    depth = p.cove_gauge if p.type == T_COVE else p.tc
    bottom = H - t * oh - depth / c - p.soffit_drop
    if right:
        poly = clip(rect(L, bottom, L + oh, bottom + p.soffit_gauge), -t, -1.0, H + t * L)
    else:
        poly = clip(rect(-oh, bottom, 0.0, bottom + p.soffit_gauge), t, -1.0, H)
    return poly, bottom


def cut_tails(g, bottom):
    """Negative Soffit Bearer Drop: cut the tails level with the bearer
    underside (never above the wall plate)."""
    cut = min(bottom, 0.0)
    g.members = [m for m in (clip(m, 0.0, 1.0, -cut) for m in g.members) if len(m) >= 3]


def apply_right_overhang(p, g, t_r, h_r, c_r):
    """Two Overhangs: move the right-hand tail ends from Overhang to
    Overhang (R) along the right-hand slope, and rebuild that soffit bearer.
    t_r, h_r, c_r: right-hand tan(pitch), heel and cos(pitch)."""
    if not p.two_overhangs:
        return g
    L, oh, oh_r = p.span, p.overhang, p.overhang_r
    if abs(oh - oh_r) < 0.01 and (oh > 0 or oh_r <= 0):
        return g
    x_end, dy = L + oh, t_r * (oh - oh_r)
    roof_y = h_r + t_r * (L - x_end)          # roof line at the right-hand tail end

    def is_tail(poly):
        """Only the top chord touches the roof line at the tail end; the
        bottom chord and heel post can share the wall line when Overhang is 0."""
        return any(abs(x - x_end) < 0.01 and abs(y - roof_y) < 0.5 for x, y in poly)

    def move(poly):
        if not is_tail(poly):
            return poly
        return [(L + oh_r, y + dy) if abs(x - x_end) < 0.01 else (x, y) for x, y in poly]

    g.members = [m for m in (move(m) for m in g.members) if len(m) >= 3]
    T = p.thick * p.plies
    kept, z = [], (T / 2.0, T / 2.0 + p.thick)
    for b, z1, z2 in g.bearers:
        if min(x for x, _ in b) >= L - 1.0:
            z = (z1, z2)                       # the right-hand bearer: rebuilt below
        else:
            kept.append((b, z1, z2))
    if p.bearer_right and oh_r > 0:
        sb, _bottom = bearer_profile(p, True, h_r, t_r, c_r, oh_r, L)
        if len(sb) >= 3:
            kept.append((sb, z[0], z[1]))
    g.bearers = kept
    g.plan_x = (g.plan_x[0], L + oh_r)
    return g


def default_setback(p):
    """Truncation setback for TR / TG / TJ; 0 in the Setback field picks one."""
    L = p.span
    if p.setback > 0:
        return p.setback
    return L / 2.0 if p.type == T_TJACK else L / 4.0


class Frame:
    """The shared set-out of one single-pitch truss: pitch, heel, overhangs,
    truncation, the top chord underside lines (lines, where webs stop) and
    the bottom chord top lines (bots, where webs land)."""

    def __init__(self, p):
        self.L = L = p.span
        th = math.radians(p.pitch)
        t, c = math.tan(th), math.cos(th)
        self.t, self.c, self.s = t, c, math.sin(th)
        self.H = H = p.heel
        self.mm = mm = p.mm
        self.half = p.type in HALF_TYPES or (p.type == T_VALLEY and p.half_valley)
        self.OH = 0.0 if p.type == T_VALLEY else p.overhang
        # Half truss only: top chord carries on past the high end post.
        self.HOH = p.high_overhang if p.type == T_HALF else 0.0
        self.drop = p.outrigger_gauge if (p.type == T_GABLE and p.outriggers) else 0.0
        under_depth = (p.tc + self.drop) / c
        self.xc = min(p.cove_length or L / 4.0, L / 2.0 - 2 * p.web)    # vaulted cove length

        # ---- truncation (TR / TG / TJ): flat top from the setback inwards ----
        trunc = 0.0
        if p.type in (T_TRUNC, T_TRUNC_G):
            d = default_setback(p)
            trunc = d if 0 < d < L / 2.0 - 10 * mm else 0.0
        elif p.type == T_TJACK:
            d = default_setback(p)
            trunc = d if 0 < d < L - 10 * mm else 0.0
        elif p.type == T_HALF and p.allow_trunc:
            d = p.setback                         # half-hip girder: flat top to the far wall
            trunc = d if 0 < d < L - 10 * mm else 0.0
        self.trunc = trunc
        # Flat top normally continues the roof line. MiTek TJ: flat chord a chord
        # depth below the rafter seat, end post rising to the seat. In a hip end the
        # TG / TR flat tops drop by the rafter depth (trunc_drop).
        self.seat = H + t * trunc - p.tc / c
        self.raised_post = bool(trunc) and p.type == T_TJACK
        if self.raised_post:
            self.y_flat = self.seat - p.tc
        else:
            self.y_flat = H + t * trunc - p.trunc_drop
        x_meet = (self.y_flat - p.tc - H + p.tc / c) / t     # sloped and flat undersides meet
        # Flat chord starts where its top meets the sloped chord underside (or at
        # the truncation point if that is further in); the truncation vertical sits under it.
        self.x_flat = min(trunc, (self.y_flat - H + p.tc / c) / t) if trunc else 0.0

        if self.half and trunc:
            lines = [(t, H - under_depth, -BIG, x_meet),
                     (0.0, self.y_flat - p.tc, x_meet, BIG)]
        elif self.half:
            lines = [(t, H - under_depth, -BIG, BIG)]
        elif trunc:
            lines = [(t, H - under_depth, -BIG, x_meet),
                     (0.0, self.y_flat - p.tc, x_meet, L - x_meet),
                     (-t, H + t * L - under_depth, L - x_meet, BIG)]
        elif p.type == T_COVE:
            # Deep cove member from the tail to the cove length, normal top chord
            # above. The cove member carries on until the top of the ceiling
            # chord meets its underside, so the ceiling chord bears fully against it.
            self.xj = xj = min(self.xc + p.bc / t, L / 2.0 - p.web)
            dcv = p.cove_gauge / c
            lines = [(t, H - dcv, -BIG, xj),
                     (t, H - under_depth, xj, L / 2.0),
                     (-t, H + t * L - under_depth, L / 2.0, L - xj),
                     (-t, H + t * L - dcv, L - xj, BIG)]
        else:
            lines = [(t, H - under_depth, -BIG, L / 2.0),
                     (-t, H + t * L - under_depth, L / 2.0, BIG)]
        self.lines = lines
        self.bots = [(0.0, p.bc, -BIG, BIG)]
        self.bc_top = p.bc

    def yu(self, x):
        """Underside of the top chord at x."""
        return under_y(self.lines, x)

    def yb(self, x):
        """Top of the bottom chord at x."""
        return under_y(self.bots, x)


def build(p):
    if is_dual(p):
        return build_dual(p)
    g = Geometry()
    f = Frame(p)
    L = f.L
    _top_chords(g, p, f)
    heel_posts = _bottom_chord(g, p, f)
    if heel_posts and f.yu(p.web) - f.yb(p.web) > 30 * f.mm:
        m0, k0 = f.bots[0][0], f.bots[0][1]
        post = clip(clip_under(rect(0.0, 0.0, p.web, BIG), f.lines), -m0, 1.0, -k0)
        if f.half:
            g.add(post)
        else:
            g.add_pair(post, L)
    _webs(g, p, f)
    _soffit_bearers(g, p, f)
    if p.type == T_GABLE and p.outriggers and p.outrigger_ctr > 0:
        _gable_outriggers(g, p, f)

    g.plan_x = (-f.OH, L + (f.HOH if f.half else f.OH))
    if not f.half:
        apply_right_overhang(p, g, f.t, f.H, f.c)
    elif p.high_left:
        # half truss high end on the left: mirror everything
        g.members = [mirror_x(m, L / 2.0) for m in g.members]
        g.bearers = [(mirror_x(b, L / 2.0), z1, z2) for b, z1, z2 in g.bearers]
        g.plan_x = (L - g.plan_x[1], L - g.plan_x[0])
    return g


def _top_chords(g, p, f):
    L, t, H, OH, dv = f.L, f.t, f.H, f.OH, p.tc / f.c
    if f.half and f.trunc:
        g.add(chord(t, H, -OH, f.trunc, dv))
        g.add(rect(f.x_flat, f.y_flat - p.tc, L - (p.bc if f.raised_post else 0.0), f.y_flat))
    elif f.half:
        g.add(chord(t, H, -OH, L + f.HOH, dv))
    elif f.trunc:
        g.add_pair(chord(t, H, -OH, f.trunc, dv), L)
        g.add(rect(f.x_flat, f.y_flat - p.tc, L - f.x_flat, f.y_flat))
    elif p.type == T_COVE:
        g.add_pair(chord(t, H, -OH, f.xj, p.cove_gauge / f.c), L)
        g.add_pair(chord(t, H, f.xj, L / 2.0, dv), L)
    elif p.type == T_GABLE and f.drop > 0:
        # outriggers run over the top chord, which drops by their depth
        g.add_pair(clip(chord(t, H - f.drop / f.c, 0.0, L / 2.0, dv), 0, 1, 0), L)
        if OH > 0:
            g.add_pair(chord(t, H, -OH, 0.0, dv), L)
    else:
        g.add_pair(chord(t, H, -OH, L / 2.0, dv), L)


def _bottom_chord(g, p, f):
    """Bottom (ceiling) chord; sets f.bots and f.bc_top. Returns whether the
    truss has raised heel posts."""
    L = f.L
    if p.type == T_SCISSOR:
        cp = math.radians(p.ceiling_pitch)
        tl, cl = math.tan(cp), math.cos(cp)
        f.bots = [(tl, p.bc / cl, -BIG, L / 2.0),
                  (-tl, tl * L + p.bc / cl, L / 2.0, BIG)]
        g.add_pair(clip_under(chord(tl, p.bc / cl, 0.0, L / 2.0, p.bc / cl), f.lines), L)
        return True
    if p.type == T_COVE:
        # Cove member bears on the wall; the flat ceiling chord starts at the
        # cove length, its underside on the cove member underside.
        y_cove = f.H - p.cove_gauge / f.c + f.t * f.xc
        f.bots = [(0.0, y_cove + p.bc, -BIG, BIG)]
        f.bc_top = y_cove + p.bc
        g.add(clip_under(rect(f.xc, y_cove, L - f.xc, y_cove + p.bc), f.lines))
        return False
    g.add(clip_under(rect(0.0, 0.0, L, p.bc), f.lines))
    return True


# ---- webs ----
# Diagonals are trimmed back to the faces of the verticals they meet
# (between(poly, x0, x1) keeps x0 <= x <= x1).

def _webs(g, p, f):
    if f.trunc and not f.half:
        _webs_truncated(g, p, f)
    elif p.type == T_GIRDER:
        # Verticals at panel points and diagonals rising to the centre; the
        # end panels are left to the heel.
        n = max(4, 2 * int(math.ceil(f.L / (2 * p.girder_ctr))))
        _webs_n(g, p, f, [i * f.L / n for i in range(1, n)])
    elif p.type == T_RAFTER or (p.type == T_COVE and f.xc < f.L / 4.0 - 2 * p.web):
        _webs_rafter(g, p, f)
        if p.type == T_COVE:
            _cove_posts(g, p, f)
    elif p.type == T_COVE:
        # Deep cove: king post, plus a post at each end of the ceiling chord.
        g.add(_vertical(p, f, f.L / 2.0))
        _cove_posts(g, p, f)
    elif p.type == T_SCISSOR:
        _webs_scissor(g, p, f)
    elif p.type == T_ATTIC:
        _webs_attic(g, p, f)
    elif p.type == T_VALLEY and f.half:
        _webs_half_valley(g, p, f)
    elif p.type in (T_GABLE, T_VALLEY):
        _webs_gable(g, p, f)
    elif f.half:
        _webs_half(g, p, f)


def _vertical(p, f, x):
    """Vertical web at x from the bottom chord up to the top chord."""
    return web((x, f.bc_top), (x, f.yu(x)), p.web, f.bc_top, f.lines)


def _webs_n(g, p, f, nodes):
    """Verticals at the nodes, diagonals rising towards the centre."""
    L, hw = f.L, p.web / 2.0
    for x in nodes:
        if f.yu(x) - f.bc_top > 30 * f.mm:
            g.add(_vertical(p, f, x))
    for a, b in zip(nodes[:-1], nodes[1:]):
        mid = (a + b) / 2.0
        if mid < L / 2.0 - 1:
            w = web((a, f.bc_top), (b, f.yu(b)), p.web, f.bc_top, f.lines)
        elif mid > L / 2.0 + 1:
            w = web((b, f.bc_top), (a, f.yu(a)), p.web, f.bc_top, f.lines)
        else:
            continue
        g.add(between(w, a + hw, b - hw))


def _webs_truncated(g, p, f):
    """Verticals at the truncation points, a diagonal out to each sloped
    chord, N pattern along the flat top (closer panels on a girder)."""
    L, trunc = f.L, f.trunc
    panel = p.girder_ctr if p.type == T_TRUNC_G else 1800 * f.mm
    diag = web((trunc, f.bc_top), (trunc / 2.0, f.yu(trunc / 2.0)), p.web, f.bc_top, f.lines)
    g.add_pair(between(diag, None, trunc - p.web / 2.0), L)
    n = max(1, int(math.ceil((L - 2 * trunc) / panel)))
    _webs_n(g, p, f, [trunc + i * (L - 2 * trunc) / n for i in range(n + 1)])


def _webs_rafter(g, p, f):
    L, bt = f.L, f.bc_top
    apex = (L / 2.0, f.yu(L / 2.0))
    quarter = (L / 4.0, f.yu(L / 4.0))
    if p.type == T_RAFTER and p.web_pattern.startswith('King'):
        g.add(web((L / 2.0, bt), apex, p.web, bt, f.lines))
        strut = web((L / 2.0, bt), quarter, p.web, bt, f.lines)
        g.add_pair(between(strut, None, L / 2.0 - p.web / 2.0), L)
    else:  # 4 Web: webs share the bottom node (plated joint), meet on the centreline
        n1 = (L / 3.0, bt)
        g.add_pair(between(web(n1, apex, p.web, bt, f.lines), None, L / 2.0), L)
        g.add_pair(web(n1, quarter, p.web, bt, f.lines), L)


def _cove_posts(g, p, f):
    """Vaulted truss: a post just inside each end of the ceiling chord,
    where there is height for one."""
    xp = min(f.xc + p.bc / f.t, f.L / 2.0 - p.web) + p.web
    if f.yu(xp) - f.bc_top > 100 * f.mm:
        g.add_pair(_vertical(p, f, xp), f.L)


def _webs_scissor(g, p, f):
    L, hw = f.L, p.web / 2.0
    apex = (L / 2.0, f.yu(L / 2.0))
    b_apex = (L / 2.0, f.yb(L / 2.0))
    centre_post = apex[1] - b_apex[1] > 60 * f.mm
    if centre_post:
        g.add(web(b_apex, apex, p.web, f.bots, f.lines))
    bq = (L / 4.0, f.yb(L / 4.0))
    g.add_pair(web(bq, (L / 4.0, f.yu(L / 4.0)), p.web, f.bots, f.lines), L)
    diag = between(web(bq, apex, p.web, f.bots, f.lines),
                   L / 4.0 + hw, L / 2.0 - (hw if centre_post else 0.0))
    g.add_pair(diag, L)


def _webs_attic(g, p, f):
    """Knee-wall studs either side of the room, collar tie at Collar Height
    above the floor (top of bottom chord), short king post above it."""
    L, bt = f.L, f.bc_top
    room = p.attic_width or L / 2.0
    xs = L / 2.0 - room / 2.0
    if 0 < xs < L / 2.0 and f.yu(xs) - bt > 30 * f.mm:
        g.add_pair(_vertical(p, f, xs), L)
        # Diagonal in the triangle outside each knee wall, from the stud foot
        # out to the top chord, when there is room for one.
        if f.yu(xs) - bt > 600 * f.mm:
            diag = web((xs, bt), (xs / 2.0, f.yu(xs / 2.0)), p.web, bt, f.lines)
            g.add_pair(between(diag, None, xs - p.web / 2.0), L)
    y0 = bt + p.collar_height
    collar = clip_under(rect(0.0, y0, L, y0 + p.bc), f.lines)
    if collar:
        g.add(collar)
        if f.yu(L / 2.0) - (y0 + p.bc) > 30 * f.mm:
            g.add(web((L / 2.0, y0 + p.bc), (L / 2.0, f.yu(L / 2.0)), p.web, y0 + p.bc, f.lines))


def _webs_half_valley(g, p, f):
    """Half valley: end post at the high end, verticals at Web Centres back
    from it."""
    L = f.L
    g.add(clip_under(rect(L - p.web, p.bc, L, BIG), f.lines))
    if p.vert_ctr > 0:
        k = 1
        while L - p.web / 2.0 - k * p.vert_ctr > p.web:
            x = L - p.web / 2.0 - k * p.vert_ctr
            if f.yu(x) - p.bc > 60 * f.mm:
                g.add(_vertical(p, f, x))
            k += 1


def _webs_gable(g, p, f):
    """Gable end and valley trusses: verticals at Web Centres from the centre."""
    L = f.L
    xs = [L / 2.0]
    if p.vert_ctr > 0:
        k = 1
        while L / 2.0 - k * p.vert_ctr > p.web:
            xs += [L / 2.0 - k * p.vert_ctr, L / 2.0 + k * p.vert_ctr]
            k += 1
    for x in xs:
        if f.yu(x) - p.bc > 60 * f.mm:
            g.add(_vertical(p, f, x))


def _webs_half(g, p, f):
    """Jack, truncated jack and half trusses: end post at the high end, then
    verticals and diagonals. Jack: one vertical and one diagonal; half truss:
    panels by span."""
    L, hw, x_flat = f.L, p.web / 2.0, f.x_flat
    end_w = p.bc
    if f.raised_post:
        g.add(rect(L - end_w, p.bc, L, f.seat))
    else:
        g.add(clip_under(rect(L - end_w, p.bc, L, BIG), f.lines))
    n = 2 if p.type in (T_JACK, T_TJACK) else max(2, int(math.ceil(L / (2000 * f.mm))))
    xs = [i * L / n for i in range(1, n)]
    if p.type == T_TJACK and f.trunc:
        xs = [x_flat]          # the panel vertical is the truncation vertical
    verticals = [x for x in xs if f.yu(x) - p.bc > 100 * f.mm]
    if f.trunc and f.yu(x_flat) - p.bc > 30 * f.mm and \
            all(abs(x_flat - x) > p.web for x in xs):
        verticals.append(x_flat)
    for x in verticals:
        g.add(_vertical(p, f, x))
    # Diagonals run from the top of each vertical down to the foot of the
    # next one towards the high end (as on fabricators' jack trusses).
    for i, x in enumerate(xs):
        xn = xs[i + 1] if i + 1 < len(xs) else L - end_w - hw
        lo = x + hw if x in verticals else None
        hi = xn - hw if xn in verticals else (L - end_w if i + 1 == len(xs) else None)
        g.add(between(web((xn, p.bc), (x, f.yu(x)), p.web, p.bc, f.lines), lo, hi))


def _soffit_bearers(g, p, f):
    """Fixed to the side of the top chord tail (inside face on a gable end).
    Default: underside level with the bottom of the tail at the fascia.
    Soffit Bearer Drop lowers it; a negative drop raises it, and the tail is
    then cut level with the bearer underside. The bearer never rises above
    the roof line."""
    L, T = f.L, p.thick * p.plies
    b_left = p.soffit_bearers
    b_right = False if f.half else p.bearer_right
    if (b_left or b_right) and f.OH > 0 and p.type != T_VALLEY:
        sb, bottom = bearer_profile(p, False, f.H, f.t, f.c, f.OH, L)
        if p.type == T_GABLE and p.flip_outriggers:
            z1, z2 = -T / 2.0 - p.thick, -T / 2.0
        else:
            z1, z2 = T / 2.0, T / 2.0 + p.thick
        if len(sb) >= 3:
            if b_left:
                g.bearers.append((sb, z1, z2))
            if b_right:
                g.bearers.append((mirror_x(sb, L / 2.0), z1, z2))
        if p.soffit_drop < 0:
            cut_tails(g, bottom)

    # High end of a half truss: level soffit bearer at the underside of the
    # top chord at the high wall, out to the end of the high overhang.
    if f.HOH > 0 and p.high_soffit:
        hb = f.H + f.t * L - p.tc / f.c - p.soffit_drop - p.soffit_gauge
        g.bearers.append((rect(L, hb, L + f.HOH, hb + p.soffit_gauge), T / 2.0, T / 2.0 + p.thick))


def _gable_outriggers(g, p, f):
    """First outrigger over the outside wall, top one set back from the apex,
    evenly spaced between at no more than Outrigger Centre."""
    L, t, c, s = f.L, f.t, f.c, f.s
    if p.flip_outriggers:
        z1, z2 = -p.dist_first, p.verge
        py0, py1 = -p.verge, p.dist_first
    else:
        z1, z2 = -p.verge, p.dist_first
        py0, py1 = -p.dist_first, p.verge
    w = p.thick
    dO = p.outrigger_gauge
    slope_len = (L / 2.0) / c
    s_top = slope_len - RIDGE_SETBACK * f.mm - w
    n = max(1, int(math.ceil(s_top / p.outrigger_ctr))) if s_top > 0 else 0
    positions = [i * s_top / n for i in range(n + 1)] if n else [0.0]
    for sa in positions:
        xa = sa * c
        xb = xa + w * c
        a, b = (xa, f.H + t * xa), (xb, f.H + t * xb)
        prof = [a, b, (b[0] + dO * s, b[1] - dO * c), (a[0] + dO * s, a[1] - dO * c)]
        g.outriggers.append((prof, z1, z2))
        g.outriggers.append((mirror_x(prof, L / 2.0), z1, z2))
        g.plan_outriggers += [(xa, xb, py0, py1), (L - xb, L - xa, py0, py1)]


# --------------------------------------------------------------------------
# Hip end
# --------------------------------------------------------------------------
#
# The object line is the end wall, outside face, corner to corner.
# The roof runs away from the line on its left side (+y), or -y with Flip.
# Half: the line runs from the hipped corner to the ridge line (half the wall).
# Equal pitch on all faces, so hips run at 45 degrees in plan to the hip apex,
# half the span in from the end wall.
#
# Members (MiTek one-truncation hip system):
#   G / TG  girder parallel to the end wall: auto = full girder at the hip
#       apex for end walls up to 7.4 m, else a truncated girder one truss
#       spacing short of the apex (one-truncation system)
#   TR  truncated standards between the girder and the apex (only if the setback
#       is set smaller than auto, giving a 2 or 3 truncation system)
#   J   main jacks from the end wall to the girder, square to the end wall
#   TJ  main jacks that pass the hip line are truncated there and carry the
#       side jacks; corner jacks stop at the hip line on a side jack
#   J/TJ side jacks square to the side walls, landing on the nearest main jack
#   R   hip rafters along the hip lines (Framing Member for anything else)
#
# Standard trusses (T) carry on from half the span in from the end wall.


class HipGeometry:
    def __init__(self):
        self.placed = []      # (profile, z1, z2, rot_z, dx, dy, part)
        self.plan_lines = []  # ((x0, y0), (x1, y1))
        self.plan_polys = []  # [(x, y), ...]
        self.hip_lines = []


def mirror_assembly(hg, L):
    """Mirror a hip end / valley set about the middle of its line."""
    hg.placed = [(prof, z1, z2, 180.0 - rz, L - dx, dy, part)
                 for prof, z1, z2, rz, dx, dy, part in hg.placed]

    def mx(pt):
        return (L - pt[0], pt[1])
    hg.plan_lines = [(mx(a), mx(b)) for a, b in hg.plan_lines]
    hg.plan_polys = [[mx(q) for q in poly] for poly in hg.plan_polys]
    hg.hip_lines = [(mx(a), mx(b)) for a, b in hg.hip_lines]
    return hg


def _sub(p, **kw):
    q = copy.copy(p)
    q.__dict__.update(kw)
    return q


GIRDER_AT_APEX_SPAN = 7400   # mm: MiTek hip end chart (girder at apex, light roof)


def girder_setback(p):
    """Setback 0 = auto: full girder at the hip apex up to a 7.4 m end wall
    (as on the MiTek layouts reviewed), one-truncation system beyond that."""
    L = p.span
    if p.setback > 0:
        return min(p.setback, L / 2.0)
    if L <= GIRDER_AT_APEX_SPAN * p.mm:
        return L / 2.0
    s = L / 2.0 - p.spacing
    return s if s > p.spacing else L / 2.0


def build_hip(p):
    return HipBuilder(p).build()


class HipBuilder:
    """Lays out a hip end, step by step, into a HipGeometry. Built with the
    hip on the left (x from 0 to the end wall length L); a Right half hip is
    mirrored at the end. y runs away from the end wall (negative with Flip)."""

    def __init__(self, p):
        self.p = p
        self.hg = HipGeometry()
        self.half = half = p.half
        # Half: the line runs from the hipped outer corner to the ridge line, so
        # the full end wall is twice the line; only the hipped half is drawn.
        self.L = L = p.span * 2.0 if half else p.span
        th = math.radians(p.pitch)
        self.t, self.c = math.tan(th), math.cos(th)
        self.H = p.heel
        self.OH = p.overhang                  # end wall eave
        self.mm = p.mm
        self.sy = -1.0 if p.flip_side else 1.0
        self.S = girder_setback(_sub(p, span=L))
        self.w = p.thick
        # Side wall overhangs (left = start of the line). Built hip-on-the-left,
        # so a Right half hip takes Overhang (R) on its hipped side wall.
        if p.side_overhangs:
            if half:
                self.ohl, self.ohr = (p.overhang_r if p.half_right else p.overhang_l), 0.0
            else:
                self.ohl, self.ohr = p.overhang_l, p.overhang_r
        else:
            self.ohl = self.ohr = self.OH
        self.xs = set()       # end jack positions along the end wall
        self.jack_len = self.S - self.w * p.plies / 2.0

    def build(self):
        self.girder_and_truncated()
        mains = self.end_jacks()
        self.side_jacks(mains)
        self.infill_rafters()
        self.hip_rafters()
        self.hg.hip_lines = self.plan_hip_lines()
        if self.half and self.p.half_right:
            mirror_assembly(self.hg, self.L / 2.0)
        return self.hg

    # ---- placing members ----

    def place_cross(self, g, y, plies):
        """Truss drawn along x (parallel to the end wall) at distance y."""
        hg, w, sy = self.hg, self.w, self.sy
        T = w * plies
        for i in range(plies):
            z0 = -T / 2.0 + i * w
            for m in g.members:
                hg.placed.append((m, z0, z0 + w, 0.0, 0.0, sy * y, 'truss'))
        for b, z1, z2 in g.bearers:
            hg.placed.append((b, z1, z2, 0.0, 0.0, sy * y, 'soffit'))
        x0, x1 = g.plan_x
        hg.plan_lines.append(((x0, sy * y), (x1, sy * y)))
        hg.plan_polys.append(rect(x0, sy * (y - T / 2.0), x1, sy * (y + T / 2.0)))

    def place_jack(self, g, x):
        """Truss drawn along local x, turned to run square to the end wall at x."""
        hg, w, sy = self.hg, self.w, self.sy
        rz = 90.0 * sy
        for m in g.members:
            hg.placed.append((m, -w / 2.0, w / 2.0, rz, x, 0.0, 'truss'))
        for b, z1, z2 in g.bearers:
            hg.placed.append((b, z1, z2, rz, x, 0.0, 'soffit'))
        u0, u1 = g.plan_x
        hg.plan_lines.append(((x, sy * u0), (x, sy * u1)))
        hg.plan_polys.append(rect(x - w / 2.0, sy * u0, x + w / 2.0, sy * u1))

    def hip_meet(self, x):
        """Distance from the end wall where the jack at x meets a hip line."""
        L = self.L
        if self.half:
            return x if x <= L / 2.0 + 1.0 else BIG
        return min(x, L - x)

    def room(self, span):
        """Whether a jack of this span has height for a truss."""
        p = self.p
        return self.H + self.t * span - p.tc / self.c > p.bc + 20 * self.mm

    def jack(self, span, setback=0.0, **kw):
        """A J (or TJ when truncated at setback) of this span."""
        return build(_sub(self.p, type=T_TJACK if setback else T_JACK, span=span,
                          setback=setback, high_left=False, outriggers=False, plies=1, **kw))

    # ---- layout steps ----

    def girder_and_truncated(self):
        """Girder at the setback, then truncated standards at Truss Spacing up
        to the apex. Flat tops dropped by the rafter depth so the infill and hip
        rafters sit on them; their tails are the side eaves."""
        p, L, S, mm = self.p, self.L, self.S, self.mm
        base = dict(outriggers=False, trunc_drop=p.tc / self.c, overhang=self.ohl,
                    overhang_r=self.ohr, two_overhangs=True)
        if self.half:
            # Half hip: the girder and any truncated standards are half trusses
            # from the hipped wall to the ridge line (flat-topped beyond the
            # setback when truncated).
            Lh = L / 2.0
            base.update(type=T_HALF, allow_trunc=True, high_left=False,
                        high_overhang=0.0, span=Lh)
            girder = dict(base, setback=S if S < Lh - 10 * mm else 0.0)
            standard = dict(base)
        else:
            girder = dict(base, type=T_TRUNC_G if S < L / 2.0 - 10 * mm else T_GIRDER,
                          setback=S)
            standard = dict(base, type=T_TRUNC)
        self.place_cross(build(_sub(p, **girder)), S, p.plies)
        y = S + p.spacing
        while y < L / 2.0 - 10 * mm:
            self.place_cross(build(_sub(p, **dict(standard, setback=y, plies=1))), y, 1)
            y += p.spacing

    def side_jack_positions(self):
        """Side jacks: back from the girder at Truss Spacing (MiTek layout)."""
        p, ys, k = self.p, [], 1
        while self.S - k * p.spacing >= 0.6 * p.spacing:
            ys.append(self.S - k * p.spacing)
            k += 1
        return ys

    def end_jacks(self):
        """Jacks from the centre outwards at spacing, plus one on each side
        wall. Main jacks (clear of the corners) run to the girder, as J or as
        TJ where they pass the hip line, and carry the side jacks. Corner jacks
        stop at the hip line, carried by a side jack. Returns the main jacks."""
        p, L, w = self.p, self.L, self.w
        xs = {L / 2.0}
        k = 1
        while L / 2.0 - k * p.spacing > w:
            xs.update((L / 2.0 - k * p.spacing, L / 2.0 + k * p.spacing))
            k += 1
        xs.update((w / 2.0, L - w / 2.0))
        if self.half:
            xs = {x for x in xs if x <= L / 2.0 + 1.0}
        self.xs = xs
        ys = self.side_jack_positions()
        y_min = min(ys) if ys else BIG
        mains = []
        for x in sorted(xs):
            m = self.hip_meet(x)
            if ys and m <= y_min + 1.0:
                span = m - w / 2.0
                if span > 0 and self.room(span):
                    self.place_jack(self.jack(span), x)
                continue
            if not self.room(min(m, self.jack_len)):
                continue
            self.place_jack(self.jack(self.jack_len, m if m < self.jack_len else 0.0), x)
            mains.append(x)
        return mains

    def side_jacks(self, mains):
        """Square to each side wall, from the eave in to the nearest main end
        jack (truncated where they pass the hip line), each side's overhang."""
        L, w = self.L, self.w
        x_land = min([x for x in mains if x <= L / 2.0] or [L / 2.0])
        span = x_land - w / 2.0
        for y in self.side_jack_positions():
            setback = y if y < span else 0.0
            if span <= 0 or not self.room(min(setback or span, span)):
                continue
            self.place_cross(self.jack(span, setback, overhang=self.ohl), y, 1)
            if not self.half:
                g = self.jack(span, setback, overhang=self.ohr)
                gm = Geometry()
                gm.members = [mirror_x(m, L / 2.0) for m in g.members]
                gm.bearers = [(mirror_x(b, L / 2.0), z1, z2) for b, z1, z2 in g.bearers]
                gm.plan_x = (L - g.plan_x[1], L - g.plan_x[0])
                self.place_cross(gm, y, 1)

    def infill_rafters(self):
        """Carry the jack top chords on over a truncated girder's flat top up
        to the hip lines (or the hip apex at the centre)."""
        p, L, w, sy = self.p, self.L, self.w, self.sy
        if self.S >= L / 2.0 - 10 * self.mm:
            return
        rz = 90.0 * sy
        for x in sorted(self.xs):
            m = self.hip_meet(x)
            if m <= self.jack_len + w or m >= BIG:
                continue
            u1 = m - w / 2.0
            prof = chord(self.t, self.H, self.jack_len, u1, p.tc / self.c)
            self.hg.placed.append((prof, -w / 2.0, w / 2.0, rz, x, 0.0, 'truss'))
            self.hg.plan_lines.append(((x, sy * self.jack_len), (x, sy * u1)))
            self.hg.plan_polys.append(rect(x - w / 2.0, sy * self.jack_len, x + w / 2.0, sy * u1))

    def hip_rafters(self):
        """Along the hip lines, eave corner to the hip apex, stopped just short
        of the apex so the two hips meet without overlapping. With uneven side
        and end overhangs the hip still runs at 45 degrees from the wall corner
        and stops at the nearer eave line; the deeper eave runs on past it to a
        short sloping barge, carried by a fly rafter."""
        p, L, w, sy = self.p, self.L, self.w, self.sy
        r2 = math.sqrt(2.0)
        th_hip = self.t / r2
        hip_end = (L / 2.0 - w / 2.0) * r2
        depth = p.tc * math.sqrt(1 + th_hip * th_hip)
        m_l, m_r = min(self.ohl, self.OH), min(self.ohr, self.OH)
        self.hg.placed.append((chord(th_hip, self.H, -m_l * r2, hip_end, depth),
                               -w / 2.0, w / 2.0, 45.0 * sy, 0.0, 0.0, 'truss'))
        if not self.half:
            self.hg.placed.append((chord(th_hip, self.H, -m_r * r2, hip_end, depth),
                                   -w / 2.0, w / 2.0, 135.0 * sy, L, 0.0, 'truss'))
        self.fly_rafter(self.ohl, False)
        if not self.half:
            self.fly_rafter(self.ohr, True)

    def fly_rafter(self, side_oh, right):
        """Corner where the side and end overhangs differ."""
        p, L, w, OH = self.p, self.L, self.w, self.OH
        if abs(side_oh - OH) < 1.0 * self.mm:
            return
        g = Geometry()
        if OH > side_oh:
            # End eave runs on: rafter square to the end wall on the side eave line.
            g.members = [chord(self.t, self.H, -OH, -side_oh, p.tc / self.c)]
            g.plan_x = (-OH, -side_oh)
            x = -side_oh + w / 2.0
            self.place_jack(g, L - x if right else x)
        else:
            # Side eave runs on: rafter square to the side wall on the end eave line.
            prof = chord(self.t, self.H, -side_oh, -OH, p.tc / self.c)
            g.members = [mirror_x(prof, L / 2.0) if right else prof]
            g.plan_x = (L + OH, L + side_oh) if right else (-side_oh, -OH)
            self.place_cross(g, -OH + w / 2.0, 1)

    def plan_hip_lines(self):
        """Hip lines from the eave corners to the hip apex."""
        L, sy = self.L, self.sy
        m_l, m_r = min(self.ohl, self.OH), min(self.ohr, self.OH)
        apex = (L / 2.0, sy * L / 2.0)
        lines = [((-m_l, -sy * m_l), apex)]
        if not self.half:
            lines.append(((L + m_r, -sy * m_r), apex))
        return lines


# --------------------------------------------------------------------------
# Valley set
# --------------------------------------------------------------------------
#
# A wing roof meeting a main roof at right angles, same pitch. The object line
# is the main wall face across the wing, internal corner to internal corner
# (the span is the wing width). The main roof trusses run through; the wing
# roof over the main roof is formed by saddle / valley trusses (S/V) sitting
# on the main roof, stepping up the main roof slope (left of the line, or
# right with Flip) at Truss Spacing until they run out where the wing
# ridge meets the main roof. Each valley truss is sized so its top chord lands
# in the wing roof plane. Wing rafter trusses carry on outwards from the line.


def build_valley(p):
    hg = HipGeometry()
    half = p.half
    # Half: the line runs from the internal corner to the wing ridge line, so
    # it is half the wing width.
    W = p.span * 2.0 if half else p.span
    th = math.radians(p.pitch)
    t = math.tan(th)
    H = p.heel
    OH = p.overhang
    mm = p.mm
    sy = -1.0 if p.flip_side else 1.0
    w = p.thick

    d = p.spacing
    while True:
        base = H + t * d                      # main roof surface at d up the slope
        span = W - 2.0 * d - 2.0 * H / t      # top chord lands in the wing roof plane
        if span < 4 * p.web + 100 * mm:
            break
        x0 = (W - span) / 2.0
        if half:
            # Half valley truss from the valley line up to the wing ridge.
            span = W / 2.0 - x0
            if span < 2 * p.web + 100 * mm:
                break
        g = build(_sub(p, type=T_VALLEY, span=span, overhang=0.0, half_valley=half,
                       high_left=False, soffit_bearers=False, outriggers=False, plies=1))
        for m in g.members:
            prof = [(x + x0, y + base) for x, y in m]
            hg.placed.append((prof, -w / 2.0, w / 2.0, 0.0, 0.0, sy * d, 'truss'))
        hg.plan_lines.append(((x0, sy * d), (x0 + span, sy * d)))
        hg.plan_polys.append(rect(x0, sy * (d - w / 2.0), x0 + span, sy * (d + w / 2.0)))
        d += p.spacing

    # ---- plan: valley lines from the eave internal corners to where the
    # wing ridge meets the main roof ----
    meet = (W / 2.0, sy * W / 2.0)
    hg.hip_lines = [((-OH, -sy * OH), meet)]
    if not half:
        hg.hip_lines.append(((W + OH, -sy * OH), meet))
    if half and p.half_right:
        # Valley at the end of the line: mirror, then shift back onto the line.
        mirror_assembly(hg, W)
        hg.placed = [(pr, z1, z2, rz, dx - W / 2.0, dy, part)
                     for pr, z1, z2, rz, dx, dy, part in hg.placed]
        sh = lambda pt: (pt[0] - W / 2.0, pt[1])
        hg.plan_lines = [(sh(a), sh(b)) for a, b in hg.plan_lines]
        hg.plan_polys = [[sh(q) for q in poly] for poly in hg.plan_polys]
        hg.hip_lines = [(sh(a), sh(b)) for a, b in hg.hip_lines]
    return hg


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

def class_names(p):
    """Class for each part, from the Class parameters. {Status} and {Type}
    are replaced; a blank field leaves that part in the object's own class."""
    status = p.status or 'Proposed'
    out = {}
    for key, tmpl in p.class_templates.items():
        name = tmpl.replace('{Status}', status).replace('{status}', status)
        name = name.replace('{Type}', p.type).replace('{type}', p.type)
        out[key] = name.strip()[:63]
    return out


def _ensure_class(name):
    if name and vs.Name2Index(name) == 0:
        _new_class(name)


class Painter:
    """Puts each new object in its class, with attributes by class."""

    def __init__(self, p):
        self.classes = class_names(p)
        for name in set(self.classes.values()):
            _ensure_class(name)

    def finish(self, h, part):
        name = self.classes.get(part)
        if name:
            _set_class(h, name)
        for fn in ('SetLSByClass', 'SetLWByClass', 'SetPenColorByClass',
                   'SetFillColorByClass', 'SetFPatByClass'):
            try:
                getattr(vs, fn)(h)
            except Exception:
                pass

    def poly(self, pts, part):
        vs.ClosePoly()
        vs.BeginPoly()
        for x, y in pts:
            vs.AddPoint(x, y)
        vs.EndPoly()
        self.finish(vs.LNewObj(), part)

    def line(self, a, b, part):
        vs.MoveTo(a[0], a[1])
        vs.LineTo(b[0], b[1])
        self.finish(vs.LNewObj(), part)

    def extrude(self, profile, z1, z2, elev, part, rot_z=0.0, dx=0.0, dy=0.0):
        vs.BeginXtrd(z1, z2)
        vs.ClosePoly()
        vs.BeginPoly()
        for x, y in profile:
            vs.AddPoint(x, y)
        vs.EndPoly()
        vs.EndXtrd()
        h = vs.LNewObj()
        # Profile is drawn in XY; stand it up so profile Y becomes world Z,
        # then turn it in plan and move it into place.
        vs.Set3DRot(h, 90, 0, 0, 0, 0, 0)
        if rot_z:
            vs.Set3DRot(h, 0, 0, rot_z, 0, 0, 0)
        vs.Move3DObj(h, dx, dy, elev)
        self.finish(h, part)


def _plan_mode(p):
    d = p.plan_display
    if d.startswith('Outline'):
        return 'outline'
    if d.startswith('None'):
        return 'none'
    return 'line'


def _outrigger_mode(p):
    """Outrigger Plan: Solid (outline) or Line (centre line)."""
    return 'outline' if p.outrigger_plan.startswith('Solid') else 'line'


def draw_hip(p, hg):
    pt = Painter(p)
    mode = _plan_mode(p)
    if mode == 'outline':
        for poly in hg.plan_polys:
            pt.poly(poly, 'truss')
    elif mode == 'line':
        for a, b in hg.plan_lines:
            pt.line(a, b, 'truss')
    if mode != 'none':
        for a, b in hg.hip_lines:
            pt.line(a, b, 'hip')
    for prof, z1, z2, rz, dx, dy, part in hg.placed:
        pt.extrude(prof, z1, z2, p.elev, part, rz, dx, dy)


def draw(p, g):
    pt = Painter(p)
    T = p.thick * p.plies
    x0, x1 = g.plan_x

    # ---- plan ----
    mode = _plan_mode(p)
    if mode == 'outline':
        for i in range(p.plies):
            y0 = -T / 2.0 + i * p.thick
            pt.poly(rect(x0, y0, x1, y0 + p.thick), 'truss')
    elif mode == 'line':
        pt.line((x0, 0), (x1, 0), 'truss')

    if mode != 'none':
        omode = _outrigger_mode(p)
        for ox0, ox1, oy0, oy1 in g.plan_outriggers:
            if omode == 'outline':
                pt.poly(rect(ox0, oy0, ox1, oy1), 'outrigger')
            else:
                xm = (ox0 + ox1) / 2.0
                pt.line((xm, oy0), (xm, oy1), 'outrigger')

    # ---- 3D ----
    # Each ply is its own extrude, so a girder reads as 2/90x45 in section.
    for i in range(p.plies):
        z0 = -T / 2.0 + i * p.thick
        for m in g.members:
            pt.extrude(m, z0, z0 + p.thick, p.elev, 'truss')
    for prof, z1, z2 in g.outriggers:
        pt.extrude(prof, z1, z2, p.elev, 'outrigger')
    for prof, z1, z2 in g.bearers:
        pt.extrude(prof, z1, z2, p.elev, 'soffit')


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

TYPE_NAMES = {
    T_RAFTER: 'Rafter Truss', T_GIRDER: 'Girder Truss', T_TRUNC: 'Truncated Rafter Truss',
    T_TRUNC_G: 'Truncated Girder Truss', T_GABLE: 'Gable End Truss', T_JACK: 'Jack Truss',
    T_TJACK: 'Truncated Jack Truss', T_HALF: 'Half Truss', T_VALLEY: 'Saddle or Valley Truss',
    T_SCISSOR: 'Scissor Truss', T_COVE: 'Vaulted Truss', T_ATTIC: 'Attic Truss',
    T_HIP: 'Hip End', T_VSET: 'Valley Set',
}


def set_ifc(h, p, mark):
    """IFC export data: IfcElementAssembly (TRUSS), Name and Tag = ID,
    ObjectType = truss type, AssemblyPlace = FACTORY, Description = status and
    the schematic notice. The entity is
    only set if the object has none, so manual IFC edits are kept. Never
    allowed to stop the truss drawing."""
    try:
        current = ''
        try:
            r = vs.IFC_GetIFCEntity(h)
            current = r[1] if isinstance(r, tuple) else (r or '')
        except Exception:
            pass
        if not current:
            vs.IFC_SetIFCEntity(h, 'IfcElementAssembly')
            vs.IFC_SetEntityProp(h, 'PredefinedType', 'TRUSS')
        if current in ('', 'IfcElementAssembly'):
            vs.IFC_SetEntityProp(h, 'Name', mark)
            vs.IFC_SetEntityProp(h, 'ObjectType', TYPE_NAMES.get(p.type, 'Truss'))
            vs.IFC_SetEntityProp(h, 'Tag', mark)
            vs.IFC_SetEntityProp(h, 'AssemblyPlace', 'FACTORY')   # prefabricated trusses
            # No common property set for IfcElementAssembly in this IFC
            # version, so the status goes in Description with the notice.
            vs.IFC_SetEntityProp(h, 'Description',
                                 '%s. %s' % ((p.status or 'Proposed').strip(), NOTICE))
    except Exception:
        pass


AUTO_FIELDS = ('Setback', 'WebCentres', 'CoveLength', 'AtticWidth', 'CeilingPitch')


def auto_values(p):
    """The values the tool uses when Override Auto is off, for this type."""
    L, mm = p.span, p.mm
    out = {}
    if p.type in (T_TRUNC, T_TRUNC_G, T_TJACK):
        out['Setback'] = vs.Num2StrF(default_setback(p))
    elif p.type == T_HIP:
        out['Setback'] = vs.Num2StrF(girder_setback(_sub(p, span=L * 2.0 if p.half else L)))
    if p.type in GIRDER_TYPES + (T_HIP,):
        out['WebCentres'] = vs.Num2StrF(1200 * mm)
    elif p.type in (T_GABLE, T_VALLEY, T_VSET):
        out['WebCentres'] = vs.Num2StrF(600 * mm)
    if p.type == T_COVE:
        out['CoveLength'] = vs.Num2StrF(min(L / 4.0, L / 2.0 - 2 * p.web))
    if p.type == T_ATTIC:
        out['AtticWidth'] = vs.Num2StrF(L / 2.0)
    if p.type == T_SCISSOR:
        out['CeilingPitch'] = '%g' % round(p.pitch / 2.0, 2)
    return out


def reset(h, rec):
    p = Params(h, rec)

    stamp = '%s (%s)' % (VERSION, VERSION_DATE)
    upgraded = p._str('Version') != stamp     # first redraw with this version
    for field, value in (('Version', stamp), ('Author', AUTHOR),
                         ('Website', WEBSITE), ('Notice', NOTICE)):
        if p._str(field) != value:
            p.set(field, value)
    # Hiding and greying out is done in widget_prep (event-based palette).
    if upgraded:
        # Clear any hide / grey-out flags stored on this truss by older versions.
        for name in WIDGET_IDS:
            vs.SetParameterVisibility(h, name, True)
            vs.EnableParameter(h, name, True)

    # ID = MiTek code + ID Number (e.g. TG1), filled in and greyed out.
    num = p._str('IDNumber').strip()
    if num.endswith('.0'):
        num = num[:-2]
    mark = ID_PREFIX.get(p.type, p.type) + num
    if p._str('ID') != mark:
        p.set('ID', mark)
    set_ifc(h, p, mark)

    if p.span <= 0:
        return
    if not (1.0 <= p.pitch <= 75.0):
        vs.MoveTo(0, 0)
        vs.LineTo(p.span, 0)
        return

    # Heel Height: calculated from top chord and pitch (shown greyed out),
    # unless Heel Override is ticked. An override below the minimum is raised to it.
    h_min = heel_minimum(p)
    if not p.heel_override or p.heel < h_min - 0.01 * p.mm:
        p.heel = h_min
        if p._str('HeelHeight') != vs.Num2StrF(h_min):
            p.set('HeelHeight', vs.Num2StrF(h_min))

    # Right-hand heel for Two Pitches, same rule against its own pitch.
    if p.two_pitch:
        h_min_r = p.tc / math.cos(math.radians(p.pitch_r))
        if not p.heel_override or p.heel_r < h_min_r - 0.01 * p.mm:
            p.heel_r = h_min_r
            if p._str('HeelHeightRight') != vs.Num2StrF(h_min_r):
                p.set('HeelHeightRight', vs.Num2StrF(h_min_r))
    else:
        p.heel_r = p.heel

    if not p.auto_override:
        for field, value in auto_values(p).items():
            if p._str(field) != value:
                p.set(field, value)

    if p.type == T_HIP:
        draw_hip(p, build_hip(p))
    elif p.type == T_VSET:
        draw_hip(p, build_valley(p))
    else:
        draw(p, build(p))


SHOW_FOR = {
    'WebPattern': (T_RAFTER,),
    'HighEnd': HALF_TYPES,
    'HalfValley': (T_VALLEY,),
    'AutoOverride': (T_TRUNC, T_TRUNC_G, T_TJACK, T_HIP, T_GIRDER, T_GABLE, T_VALLEY,
                     T_VSET, T_COVE, T_ATTIC, T_SCISSOR),
    'TwoPitch': (T_RAFTER, T_GIRDER),
    'PitchRight': (T_RAFTER, T_GIRDER),
    'HeelHeightRight': (T_RAFTER, T_GIRDER),
    'TwoOverhangs': OVERHANG_TYPES + (T_HIP,),
    'OverhangLeft': (T_HIP,),
    'OverhangRight': OVERHANG_TYPES + (T_HIP,),
    'CeilingPitch': (T_SCISSOR,),
    'Setback': (T_TRUNC, T_TRUNC_G, T_TJACK, T_HIP),
    'Girder': (T_GIRDER, T_TRUNC_G, T_HIP),
    'CoveLength': (T_COVE,),
    'CoveGauge': (T_COVE,),
    'AtticWidth': (T_ATTIC,),
    'CollarHeight': (T_ATTIC,),
    'Overhang': tuple(t for t in CODES.values() if t != T_VALLEY),
    'SoffitBearerSides': tuple(t for t in CODES.values() if t not in (T_VALLEY, T_VSET)),
    'Flip': ASSEMBLIES + (T_GABLE,),
    'WebCentres': (T_GIRDER, T_TRUNC_G, T_HIP, T_GABLE, T_VALLEY, T_VSET),
    'TrussSpacing': ASSEMBLIES,
    'HalfAssembly': ASSEMBLIES,
    'HalfSide': ASSEMBLIES,
    'Outriggers': (T_GABLE,),
    'OutriggerGauge': (T_GABLE,),
    'OutriggerCentre': (T_GABLE,),
    'OverhangSoffit': (T_GABLE,),
    'DistanceFirstTruss': (T_GABLE,),
    'OutriggerPlan': (T_GABLE,),
    'ClassOutrigger': (T_GABLE,),
    'ClassHip': ASSEMBLIES,
}


NEEDS_OUTRIGGERS = ('OutriggerGauge', 'OutriggerCentre', 'OverhangSoffit',
                    'DistanceFirstTruss', 'OutriggerPlan', 'ClassOutrigger')

NEEDS_BEARERS = ('SoffitBearerGauge', 'SoffitDrop', 'ClassSoffit')


def visibility(p):
    """Which parameters show for this truss: {name: bool}. Not listed = shown.
    Fields that do not apply to the truss type are hidden; fields that depend
    on a tick box or pop-up are greyed instead (see greyed), as in the
    Vectorworks Fence and Window tools."""
    vis = {}
    for name, types in SHOW_FOR.items():
        vis[name] = p.type in types
    if p.type == T_VALLEY and p.half_valley:
        vis['HighEnd'] = True
    if p.type in (T_VALLEY, T_VSET):
        for name in NEEDS_BEARERS:
            vis[name] = False
    # Elevation: use the object's Z. Only shown while an older truss still has one.
    vis['Elevation'] = abs(p.elev) > 0.001
    vis['TwoDOnly'] = False           # retired: for 2D only, draw a line
    return vis


def greyed(p):
    """Dependent fields greyed out because their controlling setting is off."""
    off = set()
    if not p.two_pitch:
        off |= {'PitchRight', 'HeelHeightRight'}
    if not p.half:
        off.add('HalfSide')
    if not (p._bool('TwoOverhangs') and p.type in OVERHANG_TYPES + (T_HIP,)):
        off |= {'OverhangLeft', 'OverhangRight'}
    if not (p.bearer_left or p.bearer_right):
        off |= set(NEEDS_BEARERS)
    if not p.outriggers:
        off |= set(NEEDS_OUTRIGGERS)
        if p.type == T_GABLE:
            off.add('Flip')
    return off


# Indented one level further under the setting that controls them.
DEPENDENT = ('PitchRight', 'HeelHeightRight', 'OverhangLeft', 'OverhangRight', 'HalfSide',
             'SoffitDrop', 'OutriggerCentre', 'OverhangSoffit', 'DistanceFirstTruss', 'OutriggerPlan',
             'Setback', 'WebCentres', 'CeilingPitch', 'CoveLength', 'AtticWidth')


# --------------------------------------------------------------------------
# Object Info palette layout (event-based plug-in)
# --------------------------------------------------------------------------
#
# Groups with collapsible headings. The order here is the order in the
# Object Info palette, whatever the order in the Plug-in Manager. A heading
# hides when none of its parameters apply to the current truss type.

LAYOUT = [
    # Truss type and its geometry first; options for the chosen type at the
    # bottom of the group (automatic ones after Override Auto).
    ('Truss', ['TrussType', 'LineLength', 'Pitch', 'TwoPitch', 'PitchRight', 'Elevation',
               'HeelHeight', 'HeelHeightRight', 'HeelOverride', 'Overhang', 'TwoOverhangs',
               'OverhangLeft', 'OverhangRight', 'WebPattern', 'HalfValley', 'HighEnd', 'Girder',
               'TrussSpacing', 'Flip', 'HalfAssembly', 'HalfSide', 'CollarHeight', 'AutoOverride', 'Setback',
               'WebCentres', 'CeilingPitch', 'CoveLength', 'AtticWidth']),
    ('Member Sizes', ['Thickness', 'TopChord', 'BottomChord', 'WebGauge', 'CoveGauge',
                      'SoffitBearerGauge', 'OutriggerGauge']),
    ('Soffit', ['SoffitBearerSides', 'SoffitDrop']),
    ('Outriggers', ['Outriggers', 'OutriggerCentre', 'OverhangSoffit', 'DistanceFirstTruss',
                    'OutriggerPlan']),
    ('Display', ['PlanDisplay']),
    ('ID & Classes', ['IDNumber', 'ID', 'Status', 'ClassTruss', 'ClassOutrigger', 'ClassSoffit',
                      'ClassHip']),
    ('About', ['Version']),
]

# Object Info labels, set here so none is longer than 'Heel Override' (always
# shown). Vectorworks sizes the label column to the longest label on show, so
# this stops the fields jumping sideways when the truss type changes.
# Parameters not listed use their display name from the Plug-in Manager.
LABELS = {
    'TrussType': 'Truss Type', 'IDNumber': 'ID Number', 'ID': 'ID', 'Status': 'Status',
    'LineLength': 'Span', 'Pitch': 'Roof Pitch', 'TwoPitch': 'Two Pitches',
    'PitchRight': 'Pitch (Right)', 'Elevation': 'Elevation', 'HeelHeight': 'Heel Height',
    'HeelHeightRight': 'Heel (Right)', 'HeelOverride': 'Heel Override', 'Overhang': 'Overhang',
    'TwoOverhangs': 'Two Overhangs',
    'OverhangLeft': 'Overhang (L)', 'OverhangRight': 'Overhang (R)', 'WebPattern': 'Web Pattern',
    'HalfValley': 'Half Valley',
    'HighEnd': 'High End', 'Girder': 'Girder',
    'Setback': 'Setback', 'TrussSpacing': 'Spacing', 'AutoOverride': 'Override Auto',
    'HalfAssembly': 'Half', 'HalfSide': 'Side', 'SoffitBearerSides': 'Bearers',
    'Flip': 'Flip', 'WebCentres': 'Web Centres',
    'CeilingPitch': 'Ceiling Pitch', 'CoveLength': 'Cove Length', 'CoveGauge': 'Cove Member',
    'AtticWidth': 'Attic Width', 'CollarHeight': 'Collar Height',
    'Thickness': 'Thickness', 'TopChord': 'Top Chord', 'BottomChord': 'Bottom Chord',
    'WebGauge': 'Webs',
    'SoffitBearerGauge': 'Soffit Bearer', 'SoffitDrop': 'Bearer Drop',
    'Outriggers': 'Outriggers', 'OutriggerGauge': 'Outrigger', 'OutriggerCentre': 'Centres',
    'OverhangSoffit': 'Verge', 'DistanceFirstTruss': 'Back Span',
    'OutriggerPlan': 'Plan Display',
    'PlanDisplay': 'Plan Display', 'TwoDOnly': '2D Only',
    'ClassTruss': 'Truss', 'ClassOutrigger': 'Outrigger', 'ClassSoffit': 'Soffit Bearer',
    'ClassHip': 'Hip / Valley',
    'Version': 'Version', 'Author': 'Author', 'Website': 'Website', 'Notice': 'Note',
}

WIDGET_BASE = 1000


# Widget IDs never change, whatever the layout order: each heading and
# parameter keeps its number (retired names stay as placeholders). A palette built by an older version (it is only
# rebuilt when Vectorworks loads the plug-in) then still matches. Only ever
# add to the end of these lists.
WIDGET_IDS = [
    'TrussType', 'IDNumber', 'ID', 'Status', 'WebPattern', 'HalfValley', 'HighEnd', 'Girder',
    'GirderWebCentre', 'Setback', 'TrussSpacing', 'FlipSide', 'CeilingPitch', 'CoveLength',
    'CoveGauge', 'AtticWidth', 'CollarHeight', 'VerticalWebCentre', 'LineLength', 'Pitch',
    'TwoPitch', 'PitchRight', 'Elevation', 'HeelHeight', 'HeelHeightRight', 'HeelOverride',
    'Overhang', 'HighOverhang', 'Thickness', 'TopChord', 'BottomChord', 'WebGauge',
    'SoffitBearers', 'HighSoffitBearer', 'SoffitBearerGauge', 'SoffitDrop', 'Outriggers',
    'OutriggerGauge', 'OutriggerCentre', 'OverhangSoffit', 'DistanceFirstTruss',
    'FlipOutriggers', 'OutriggerPlan', 'PlanDisplay', 'TwoDOnly', 'ClassTruss',
    'ClassOutrigger', 'ClassSoffit', 'ClassHip', 'Version', 'Author', 'Website', 'Notice',
    'HalfAssembly', 'HalfSide', 'TwoOverhangs', 'OverhangRight',
    'SoffitBearerSides', 'Flip', 'WebCentres', 'AutoOverride', 'OverhangLeft',
]
# ('Type Options', 'Geometry', 'Timber' and 'Classes' are no longer used; kept
# so the other IDs do not move.)
HEADING_IDS = ['Truss', 'Type Options', 'Geometry', 'Timber', 'Soffit', 'Outriggers',
               'Display', 'Classes', 'About', 'Member Sizes', 'ID & Classes']
HEADING_BASE = 2000


def _widget_ids():
    """(heading id, heading, [(param id, name)]) per LAYOUT group, fixed IDs."""
    out = []
    for heading, names in LAYOUT:
        hid = HEADING_BASE + HEADING_IDS.index(heading)
        params = [(WIDGET_BASE + WIDGET_IDS.index(n), n) for n in names]
        out.append((hid, heading, params))
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
                vs.vsoWidgetSetIndLvl(wid, 2 if name in DEPENDENT else 1)
        if heading == 'About':
            # as the other tools: Version, then a button that opens the repo
            vs.vsoAddWidget(ABOUT_WEB_ID, kWidgetButton, WEBSITE)
            vs.vsoWidgetSetIndLvl(ABOUT_WEB_ID, 1)
            vs.vsoAddWidget(ABOUT_UPDATE_ID, kWidgetButton, 'Check for updates...')
            vs.vsoWidgetSetIndLvl(ABOUT_UPDATE_ID, 1)
    vs.SetObjPropVS(kObjXSupportsStyles, True)


# Plug-in styles: member sizes, plan display and classes are shared (By
# Style), so a style is e.g. "90 x 45 trusses, centre line". Type, span,
# pitch, heights, ID and the rest stay with each truss (By Instance). Set
# the first time a style is used; change it in Edit Style.
STYLE_PARAMS = ('Thickness', 'TopChord', 'BottomChord', 'WebGauge', 'CoveGauge',
                'SoffitBearerGauge', 'OutriggerGauge', 'PlanDisplay', 'OutriggerPlan',
                'ClassTruss', 'ClassOutrigger', 'ClassSoffit', 'ClassHip')
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
    style whose LineLength is already By Instance has been set up: left alone."""
    sd = _style_def(h)
    if not sd:
        return
    try:
        if vs.GetParamStyleType(sd, 'LineLength') == kByInstance:
            return
        vs.SetAllStyleParams(sd, kByInstance)
        for name in STYLE_PARAMS:
            try:
                vs.SetParamStyleType(sd, name, kByStyle)
            except Exception:
                pass
    except Exception:
        pass


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
    p = Params(h, rec)
    vis = visibility(p)
    disabled = ({'ID', 'Version', 'Author', 'Website', 'Notice'} |
                (set() if p.heel_override else {'HeelHeight', 'HeelHeightRight'}) |
                (set() if p.auto_override else set(AUTO_FIELDS)) |
                greyed(p))
    for hid, heading, params in _widget_ids():
        any_visible = False
        for wid, name in params:
            visible = vis.get(name, True)
            vs.vsoWidgetSetVisible(wid, visible)
            vs.vsoWidgetSetEnable(wid, name not in disabled)
            any_visible = any_visible or visible
        vs.vsoWidgetSetVisible(hid, any_visible)
    vs.vsoSetEventResult(kObjectEventHandled)


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
        if button == ABOUT_WEB_ID:
            open_website()
        elif button == ABOUT_UPDATE_ID:
            check_updates()
    elif event in (kResetEventID, 0):
        # Event 0: plug-in not event-based (no custom layout).
        try:
            ensure_style_map(h)
            reset(h, rec)
        except Exception:
            _reset_failed(vs.GetName(h))


# --- Truss tool (the .vst): what its clicks make ---------------------------
TOOL_OBJECT = 'Truss Tool'
TOOL_NAME = 'Truss'
# vstSetPtBehavior 2: two clicks
TOOL_MODES = (('', 2, 'Click one end of the truss, then the other'),)
# tool bar pull-downs: (label, field, choices; the first until one is picked)
TOOL_PULLDOWNS = (('Type:', 'TrussType', (
    'Rafter Truss (T)', 'Girder Truss (G)', 'Truncated Rafter Truss (TR)',
    'Truncated Girder Truss (TG)', 'Gable End Truss (GE)', 'Jack Truss (J)',
    'Truncated Jack Truss (TJ)', 'Half Truss (H)', 'Saddle or Valley Truss (S/V)',
    'Scissor Truss (SC)', 'Vaulted Truss (VT)', 'Attic Truss (AT)', 'Hip End (HE)',
    'Valley Set (VS)')),)
# the spanner: (field, label, 'num' / 'text' / choices)
TOOL_DEFAULTS = (
    ('Pitch', 'Roof Pitch', 'num'),
    ('Overhang', 'Overhang', 'num'),
    ('WebPattern', 'Web Pattern', ('4 Web', 'King Post')),
    ('Girder', 'Girder', ('1 Ply', '2 Ply', '3 Ply')),
    ('PlanDisplay', 'Plan Display', ('Centre Line', 'Outline', 'None')),
    ('Status', 'Status', ('Proposed', 'Existing', 'Demolish')),
)


def tool_complete(mode, pts, h):
    """Span from the first click to the second, as the object's own tool."""
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
