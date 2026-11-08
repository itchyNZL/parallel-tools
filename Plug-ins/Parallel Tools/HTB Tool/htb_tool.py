"""
HTB Tool (Height to Boundary) for Vectorworks 2026 / 2027

Copyright (c) 2026 Ian Thrush
Licensed under the MIT License (see LICENSE.md).

A point object that marks one point on a site boundary and draws the daylight
(height in relation to boundary) recession plane for it:
- a vertical line up from the object to Height at Boundary, then a line on the
  Daylight Angle up to Allowable Height, dashed or solid. That is the Standard profile;
  the Profile parameter can also pick Alternative (the Auckland Unitary Plan's alternative
  height in relation to boundary, with its 1 m shelf and two slopes) or Custom (a shelf
  and two slopes of your own)
- objects on the same Side are linked in Point_No order: each one draws the
  recession plane (a 3D polygon, in the Plane Class class) back to the next
  Point_No down on its Side, so the planes follow the ground level at each point
  and a new object links up as soon as it is drawn. The lowest number has no plane.
  Changing an object redraws the rest of its Side (and its old Side, when the Side
  changed), so no plane is left pointing at where a point used to be
- a small label beside each point says what it links to (North 3 > 2, North 1 (start),
  North 1 (unlinked)), in the class Site-HTB-Guides: tick Non Plot in that class
- the object goes in the class Site-HTB-<Side> (Site-HTB-North ...; N, NE ... are read as
  North, North East ...) and the planes in the Plane Class (Site-HTB-Plane <Profile>:
  Standard, Alternative or Custom, when blank), both made if the file hasn't got them.
  The lines take their look from the object's class
- Point_No 0, or a number another object on its Side already has (a copy or paste
  keeps the old number), takes the next free number up on its Side when it draws
- Refresh Selected / Refresh All (Object Info) redraw the selected / every HTB object
- sizes work in any file units (mm, m, inches): fixed sizes are held in mm and converted

The .vso holds a short loader stub; all logic lives here.
"""

import math

import vs

VERSION = '0.5.1'
VERSION_DATE = '2026-11-09'
WEBSITE = 'github.com/itchyNZL/parallel-tools'
TOOL_FOLDER = 'HTB Tool'

DEBUG_LOG = False      # True writes tool_debug.log next to this file (testing)

# True while a draw is redrawing the rest of its Side, so those draws don't do the same
_state = {'propagating': False}

# The planes go in the Plane Class. Left empty it is Site-HTB-Plane <Profile> (Standard,
# Alternative or Custom), written into the field so Object Info shows it and kept in step
# with the Profile; a class typed in by hand is left alone. Each object goes in
# Site-HTB-<Side> (Site-HTB-North ...), so each side can be turned off on its own.
PLANE_CLASS_PREFIX = 'Site-HTB-Plane '
PROFILE_LABELS = {'standard': 'Standard', 'alternative': 'Alternative', 'custom': 'Custom'}
AUTO_PLANE_CLASSES = set(PLANE_CLASS_PREFIX + n for n in PROFILE_LABELS.values())
# A default with a space in it is stored cut at the space by the Plug-in Manager, which turns
# Site-HTB-Plane <Profile> into the bare Site-HTB-Plane: that is treated as empty too
AUTO_PLANE_CLASSES.add(PLANE_CLASS_PREFIX.strip())
SIDE_CLASS_PREFIX = 'Site-HTB-'
SIDE_NAMES = {'N': 'North', 'NE': 'North East', 'E': 'East', 'SE': 'South East',
              'S': 'South', 'SW': 'South West', 'W': 'West', 'NW': 'North West'}
SIDE_CLASSES = set(SIDE_CLASS_PREFIX + n for n in SIDE_NAMES.values())
GUIDE_CLASS = 'Site-HTB-Guides'          # the link labels (tick Non Plot in the class)

# Sizes in mm, converted to the file's units with _mm()
SEGMENT_MM = 200.0      # dash length (on the model)
GAP_MM = 100.0          # dash gap (on the model)
LEVEL_RUN_MM = 3000.0   # Daylight Angle 0: a level line this long
MARKER_MM = 5.0         # marker arm, mm on the printed sheet (500 at 1:100)
LABEL_POINTS = 5        # link label text size

# Every parameter the code reads or writes (the first draw in a session lists any missing)
REQUIRED = ('Height at Boundary', 'Allowable Height', 'Daylight Angle', 'Description',
            'Profile', 'Shelf', 'Slope 1 to Height', 'Slope 2 Angle', 'Dashed', 'Side',
            'Point_No', 'Plane Class', 'Version', 'State')


def side_name(txt):
    # N -> North, NE -> North East ...; full names pass through, so the Side pop-up can
    # show either, and an object still saying N is on the same side as one saying North.
    t = str(txt).strip()
    return SIDE_NAMES.get(t.upper(), t)


# Vectorworks plug-in events and Object Info properties
kWidgetButton = 12
kWidgetSeparator = 100
kEvInit = 5
kEvButton = 35
kEvReset = 3
kEvAddState = 44
kEvWidgetPrep = 41
kEvEditPluginStyle = 60
kObjectEventHandled = -8
kObjectEditPluginStyleByDefault = -10   # reply: use the default style dialog
kObjXPropHasUIOverride = 8
kObjXHasCustomWidgetVisibilities = 12
kObjXPropAcceptStates = 18
kObjXPropAcceptStatesInternal = 19      # incl. duplicate / paste states
kObjXSupportsStyles = 49
kObjPropWidgetGroupMode = 81
kWidgetGroupAutomatic = 2
kRefreshID = 1001                       # Refresh Selected
REFRESH_ALL_ID = 3001
ABOUT_WEB_ID = 3002
ABOUT_UPDATE_ID = 3101


def read_real(recName, objH, field):
    txt = vs.GetRField(objH, recName, field)
    if txt is None or txt == '':
        return 0.0
    return vs.Str2Num(txt)


def read_bool(recName, objH, field):
    txt = vs.GetRField(objH, recName, field)
    return str(txt).strip().lower() == 'true'


def read_str(recName, objH, field):
    txt = vs.GetRField(objH, recName, field)
    return '' if txt is None else str(txt)


def moveTo(x, y):
    try:
        vs.MoveTo((x, y))
    except TypeError:
        vs.MoveTo(x, y)


def lineTo(x, y):
    try:
        vs.LineTo((x, y))
    except TypeError:
        vs.LineTo(x, y)


def add3DPt(x, y, z):
    try:
        vs.Add3DPt((x, y, z))
    except TypeError:
        vs.Add3DPt(x, y, z)


def createNurbsCurve(x, y, z, byCtrl, degree):
    try:
        return vs.CreateNurbsCurve((x, y, z), byCtrl, degree)
    except TypeError:
        return vs.CreateNurbsCurve(x, y, z, byCtrl, degree)


def addVertex3D(nc, x, y, z):
    try:
        vs.AddVertex3D(nc, (x, y, z))
    except TypeError:
        vs.AddVertex3D(nc, x, y, z)


def run_of(allowH, boundH, angle, mm=1.0):
    if angle == 0:
        return LEVEL_RUN_MM * mm
    return (allowH - boundH) / math.tan(math.radians(angle))


# The Alternative profile: the Auckland Unitary Plan's "Alternative height in relation to
# boundary" (figure H5.6.6.1), in mm. Up 3.6 m at the boundary, 1 m in, then 73.3 degrees
# (0.3 m in for each metre up) to 6.9 m, then 45 degrees to 11 m. The 11 m is read from the
# figure; the text doesn't give it.
ALT = {'h0': 3600.0, 'shelf': 1000.0, 'a1': 73.3, 'h1': 6900.0, 'a2': 45.0, 'top': 11000.0}


def profile_kind(txt):
    t = str(txt).strip().lower()
    if t.startswith('alt'):
        return 'alternative'
    if t.startswith('cust'):
        return 'custom'
    return 'standard'


def profile_points(kind, h0, top, a1, shelf, h1, a2, mm=1.0):
    # The profile as (run, height) points: run is how far in from the boundary (along the
    # object's +Y), height is up from its Z. The first point is the top of the vertical line
    # at the boundary (h0). Heights and runs are in the file's units (mm = units per mm).
    # standard:    one slope (a1) from h0 up to top, as it has always been
    # custom:      an optional shelf (a level run in at h0), then slope a1 up to h1 (0 = straight
    #              up to top), then slope a2 up to top. A Slope 1 To Height at or below h0 is
    #              already met: slope 2 starts at h0 (slope 1 goes to the top if there is
    #              no slope 2)
    # alternative: the Auckland figure (ALT, converted from mm)
    # A slope that can't be climbed (top not above where it starts) adds no point, so a
    # profile of one point has nothing to draw above the vertical line.
    if kind == 'alternative':
        h0, shelf, a1, h1, a2, top = (ALT['h0'] * mm, ALT['shelf'] * mm, ALT['a1'],
                                      ALT['h1'] * mm, ALT['a2'], ALT['top'] * mm)
    elif kind == 'standard':
        shelf, h1 = 0.0, 0.0
    pts = [(0.0, h0)]
    run, h = 0.0, h0
    if shelf > 0:
        run += shelf
        pts.append((run, h))
    end1 = h1 if (0 < h1 < top and a1 != 0) else top
    if end1 <= h and not a2 > 0:
        end1 = top                      # no slope 2 to take over: slope 1 to the top
    if end1 > h:
        r1 = run_of(end1, h, a1, mm)
        if r1 > 0:
            run += r1
            h += r1 * math.tan(math.radians(a1))
            pts.append((run, h))
    if end1 < top and a2 > 0 and h < top:
        r2 = run_of(top, h, a2, mm)
        if r2 > 0:
            run += r2
            h += r2 * math.tan(math.radians(a2))
            pts.append((run, h))
    return pts


def seed_custom(recName, objH, mm):
    """A point just switched to Custom with Shelf and Slope 1 To Height both 0 (so it
    would draw just like Standard) starts from the Alternative's numbers, to edit from.
    True if it was filled in."""
    if read_real(recName, objH, 'Shelf') or read_real(recName, objH, 'Slope 1 to Height'):
        return False
    values = (('Height at Boundary', ALT['h0'] * mm), ('Shelf', ALT['shelf'] * mm),
              ('Daylight Angle', ALT['a1']), ('Slope 1 to Height', ALT['h1'] * mm),
              ('Slope 2 Angle', ALT['a2']), ('Allowable Height', ALT['top'] * mm))
    try:
        for field, v in values:
            vs.SetRField(objH, recName, field, '%g' % v)
    except Exception as e:
        _log('seed custom', repr(e))
        return False
    return True


def read_profile(recName, objH, mm):
    # (kind, points) for an object, from its own fields
    kind = profile_kind(read_str(recName, objH, 'Profile'))
    pts = profile_points(kind,
                         read_real(recName, objH, 'Height at Boundary'),
                         read_real(recName, objH, 'Allowable Height'),
                         read_real(recName, objH, 'Daylight Angle'),
                         read_real(recName, objH, 'Shelf'),
                         read_real(recName, objH, 'Slope 1 to Height'),
                         read_real(recName, objH, 'Slope 2 Angle'),
                         mm)
    return kind, pts


def _by_class(h, cls):
    """A line drawn by the object takes its look from cls (the object's own class)."""
    if not h:
        return
    try:
        if cls:
            _set_class(h, cls)
        for fn in ('SetLSByClass', 'SetLWByClass', 'SetPenColorByClass'):
            try:
                getattr(vs, fn)(h)
            except Exception:
                pass
    except Exception:
        pass


def dash_segment(r0, z0, r1, z1, true_length, seg, gap, cls):
    # Dashes along one profile line from (run r0, height z0) to (r1, z1). Standard keeps
    # measuring its dashes along the run (plan); the others along the line itself.
    dr, dz = r1 - r0, z1 - z0
    total = math.hypot(dr, dz) if true_length else dr
    if total <= 0:
        return
    start = 0.0
    while start < total:
        end = min(start + seg, total)
        f0, f1 = start / total, end / total
        nc = createNurbsCurve(0, r0 + f0 * dr, z0 + f0 * dz, True, 1)
        addVertex3D(nc, 0, r0 + f1 * dr, z0 + f1 * dz)
        _by_class(nc, cls)
        start += seg + gap


def get_plugin_name(objName):
    # The plug-in's name is also its parameter record's name
    try:
        ok, pName, pRec = vs.GetPluginInfo()
        if ok:
            return pName
    except Exception:
        pass
    return objName


def ensure_class(name):
    # Create the class if the file doesn't have it yet. A class that already exists is
    # left exactly as it is (the active class is put back after making a new one).
    # Returns True if it was made now.
    if not name or vs.Name2Index(name) != 0:
        return False
    if not _new_class(name):
        return False
    made = vs.Name2Index(name)
    _log('class created' if made else 'class NOT created', repr(name), 'len', len(name),
         '-> index now', made)
    return bool(made)


_checked = set()


def check_params(rec):
    """First draw of a session: say which parameters the plug-in lacks."""
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
        # one that is there under a slightly different name (capitals, spaces) is named,
        # so it can be renamed rather than added twice
        def norm(s):
            return ' '.join(str(s).lower().split())
        near = dict((norm(n), n) for n in names)
        lines = []
        for n in missing:
            if norm(n) in near:
                lines.append('%s (it is there as "%s": rename it, capitals and spaces exactly)'
                             % (n, near[norm(n)]))
            else:
                lines.append(n)
        vs.AlrtDialog('HTB Tool: add these parameters in the Plug-in Manager '
                      '(see README), then restart Vectorworks: ' + ', '.join(lines))


# Numbers given out during the current draw (and the redraws it starts): Vectorworks may
# still hand the others the old number until the draw that set it has finished.
_new_numbers = []


def _number_of(recName, h):
    for k, n in _new_numbers:
        if k == h:
            return n
    return read_real(recName, h, 'Point_No')


def others_on_side(recName, mySide, objH, order=False):
    # (handle, Point_No) of every other object of this plug-in on the same Side. With
    # order, (handle, Point_No, earlier): earlier = it comes before objH in the drawing's
    # stacking order, so it is older than objH (a copy or paste goes on top).
    found = []
    want = side_name(mySide)
    seen = []

    def check(h):
        if h == objH:
            seen.append(1)
            return
        if side_name(read_str(recName, h, 'Side')) == want:
            n = _number_of(recName, h)
            found.append((h, n, not seen) if order else (h, n))

    vs.ForEachObject(check, "(PON='" + recName + "')")
    return found


def needs_number(myNo, others):
    """0, or a number an older object on the Side already has: this one is the copy, so
    it takes the next free number and the original keeps its own. (0.3.0 asked only
    whether any other object had the number, so the original could be redrawn first
    and renumber itself.)"""
    return myNo == 0 or any(n == myNo and earlier for _h, n, earlier in others)


def _num_text(n):
    return str(int(n)) if float(n).is_integer() else ('%g' % n)


def link_label(side, myNo, nbrNo, has_above, mismatch=False):
    """What the point links to: 'North 3 > 2', 'North 1 (start)' (lowest of its Side, with
    points above it), 'North 1 (unlinked)' (alone on its Side)."""
    name = '%s %s' % (side or '(no side)', _num_text(myNo))
    if nbrNo is not None:
        text = '%s > %s' % (name, _num_text(nbrNo))
        return text + ' (profiles differ)' if mismatch else text
    return name + (' (start)' if has_above else ' (unlinked)')


def draw_label(text, x, y):
    """The link label, centred on (x, y), in GUIDE_CLASS (made grey if missing; Vectorworks
    has no script call for Non Plot, so tick it once in the class)."""
    try:
        if ensure_class(GUIDE_CLASS):
            grey = (128 * 257, 128 * 257, 128 * 257)
            _set_class_colour('SetClPenFore', 'GetClPenFore', GUIDE_CLASS, grey)
            _set_class_colour('SetClFillFore', 'GetClFillFore', GUIDE_CLASS, grey)
        for fn, v in (('TextSize', LABEL_POINTS), ('TextJust', 2), ('TextVerticalAlign', 3)):
            try:
                getattr(vs, fn)(v)          # 2: centred across; 3: centred up and down
            except Exception:
                pass
        vs.TextOrigin(x, y)
        vs.CreateText(text)
        o = vs.LNewObj()
        _set_class(o, GUIDE_CLASS)
        for fn in ('SetPenColorByClass', 'SetFillColorByClass'):
            try:
                getattr(vs, fn)(o)
            except Exception:
                pass
    except Exception as e:
        _log('label', repr(e))


def redraw_side(recName, side, objH):
    """Redraw every other object on side (their planes may have pointed at this one, or
    at where it was). Those draws don't redraw in turn (_state['propagating'])."""
    if _state['propagating'] or not side_name(side):
        return
    _state['propagating'] = True
    try:
        for h, _n in others_on_side(recName, side, objH):
            vs.ResetObject(h)
    finally:
        _state['propagating'] = False


def draw_object():
    ok, objName, objH, _rec, _wall = vs.GetCustomObjectInfo()
    if not ok or not objH:
        return
    recName = get_plugin_name(objName)
    check_params(recName)
    ensure_style_map(objH)
    stamp = '%s (%s)' % (VERSION, VERSION_DATE)
    if read_str(recName, objH, 'Version') != stamp:
        vs.SetRField(objH, recName, 'Version', stamp)

    mm = _mm()
    try:
        scale = vs.GetLScale(vs.GetLayer(objH))
    except Exception:
        scale = 1.0
    paper = mm * (scale if scale and scale > 0 else 1.0)    # file units per printed mm

    # State: 'Side|profile' as of the last draw (0.3.0 held the Side alone)
    oldSide, _bar, oldKind = read_str(recName, objH, 'State').partition('|')
    oldSide = side_name(oldSide)
    kind, pts = read_profile(recName, objH, mm)
    if kind == 'custom' and oldKind != 'custom' and seed_custom(recName, objH, mm):
        kind, pts = read_profile(recName, objH, mm)
    heightAtBoundary = pts[0][1]
    dashed = read_bool(recName, objH, 'Dashed')
    mySide = read_str(recName, objH, 'Side')
    planeClass = read_str(recName, objH, 'Plane Class')
    # An empty Plane Class, or one of the Site-HTB-Plane <Profile> names, follows the Profile
    # (written into the field so Object Info shows it). A class typed in by hand stays.
    # The Plug-in Manager stored a default with a space in it cut at the space, so this
    # isn't a parameter default.
    autoClass = PLANE_CLASS_PREFIX + PROFILE_LABELS[kind]
    if planeClass == '' or planeClass in AUTO_PLANE_CLASSES:
        if planeClass != autoClass:
            try:
                vs.SetRField(objH, recName, 'Plane Class', autoClass)
            except Exception as e:
                _log('plane class', repr(e))
        planeClass = autoClass
    cls = planeClass
    ensure_class(cls)

    # The object itself goes in Site-HTB-<Side>. Only an object with no class, or one in
    # another side's class (its Side was changed), is moved: a class chosen by hand stays.
    if side_name(mySide):
        sideClass = SIDE_CLASS_PREFIX + side_name(mySide)
        ensure_class(sideClass)
        try:
            current = vs.GetClass(objH)
            if current != sideClass and (current in ('', 'None') or current in SIDE_CLASSES):
                _set_class(objH, sideClass)
        except Exception as e:
            _log('object class', repr(e))
    try:
        lineClass = vs.GetClass(objH)
    except Exception:
        lineClass = ''

    myNo = read_real(recName, objH, 'Point_No')
    # Number it when it has none (0) or when another object on this Side already has
    # the same number (a copy or paste keeps the old number): next free number up.
    top = not _state['propagating']
    if top:
        del _new_numbers[:]
    ordered = others_on_side(recName, mySide, objH, order=True)
    others = [(h, n) for h, n, _e in ordered]
    taken = [n for h, n in others]
    if needs_number(myNo, ordered):
        myNo = max(taken + [0]) + 1
        vs.SetRField(objH, recName, 'Point_No', str(int(myNo)))
        _new_numbers.append((objH, myNo))

    # The marker: a T, the stem pointing into the site (+Y), sized on the sheet
    arm = MARKER_MM * paper
    moveTo(-arm, 0)
    lineTo(arm, 0)
    _by_class(vs.LNewObj(), lineClass)
    moveTo(0, 0)
    lineTo(0, arm)
    _by_class(vs.LNewObj(), lineClass)

    seg, gap = SEGMENT_MM * mm, GAP_MM * mm
    if dashed:
        # the vertical line at the boundary, then each line of the profile
        dash_segment(0.0, 0.0, 0.0, heightAtBoundary, True, seg, gap, lineClass)
        for i in range(len(pts) - 1):
            dash_segment(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], kind != 'standard',
                         seg, gap, lineClass)
    elif len(pts) > 1:
        nc = createNurbsCurve(0, 0, 0, True, 1)
        for r, z in pts:
            addVertex3D(nc, 0, r, z)
        _by_class(nc, lineClass)

    # ---- the plane runs back to the object below: same Side, next Point_No down.
    # A number equal to ours is skipped.
    nbr = None
    nbrNo = -1
    has_above = False
    for h, n in others:
        if n < myNo and n > nbrNo:
            nbrNo = n
            nbr = h
        elif n > myNo:
            has_above = True

    mismatch = False
    if nbr is not None:
        ax, ay, az = vs.GetSymLoc3D(objH)
        bx, by, bz = vs.GetSymLoc3D(nbr)
        rotA = math.radians(vs.GetSymRot(objH))
        dRot = math.radians(vs.GetSymRot(nbr)) - rotA

        dx = bx - ax
        dy = by - ay
        dz = bz - az
        bxL = dx * math.cos(rotA) + dy * math.sin(rotA)
        byL = -dx * math.sin(rotA) + dy * math.cos(rotA)

        kindB, ptsB = read_profile(recName, nbr, mm)
        mismatch = len(pts) != len(ptsB)
        if len(pts) > 1 and len(ptsB) > 1:
            # One quad for each line of the profile, from this object's points to the one
            # below's. If the two profiles have a different number of points, one quad from
            # the boundary to the top.
            if len(pts) == len(ptsB):
                strips = [((i, i), (i + 1, i + 1)) for i in range(len(pts) - 1)]
            else:
                strips = [((0, 0), (len(pts) - 1, len(ptsB) - 1))]

            def mine(i):
                return (0, pts[i][0], pts[i][1])

            def below(i):
                run, z = ptsB[i]
                return (bxL - run * math.sin(dRot), byL + run * math.cos(dRot), dz + z)

            vs.PushAttrs()
            for (a0, b0), (a1, b1) in strips:
                vs.BeginPoly3D()
                add3DPt(*mine(a0))
                add3DPt(*below(b0))
                add3DPt(*below(b1))
                add3DPt(*mine(a1))
                add3DPt(*mine(a0))
                vs.EndPoly3D()
                planeH = vs.LNewObj()

                _set_class(planeH, cls)
                vs.SetLWByClass(planeH)
                vs.SetPenColorByClass(planeH)
                vs.SetFPatByClass(planeH)
                vs.SetFillColorByClass(planeH)
                vs.SetOpacityByClass(planeH)
            vs.PopAttrs()

    # The link label, just outside the boundary (below the T's bar)
    draw_label(link_label(side_name(mySide), myNo, nbrNo if nbr is not None else None,
                          has_above, mismatch),
               0, -1.5 * arm)

    # Redraw the rest of this Side (a plane above may have pointed at this object or at
    # where it was), and the Side it was on before if that changed (State holds it). Not
    # when this draw was itself started that way, so it can't run on.
    newSide = side_name(mySide)
    state = '%s|%s' % (newSide, kind)
    if read_str(recName, objH, 'State') != state:
        vs.SetRField(objH, recName, 'State', state)
    if not _state['propagating']:
        if oldSide and oldSide != newSide:
            redraw_side(recName, oldSide, objH)
        redraw_side(recName, newSide, objH)


def on_add_state(stateId):
    # State event (moved, pasted, duplicated ...). Vectorworks sends these for a copy but
    # doesn't redraw it, so the copy would keep the original's number: redraw it here when
    # its number is 0 or another object on its Side has it, and the draw renumbers it.
    # A second state message for the same copy comes after the first redraw; if the
    # renumber didn't stick, the clash is still there and it is redrawn again.
    ok, objName, objH, _rec, _wall = vs.GetCustomObjectInfo()
    if not ok:
        return
    try:
        vs.vsoSetEventResult(vs.vsoStateAddCurrent(objH, stateId))
    except Exception as e:
        _log('add state', repr(e))
    try:
        recName = get_plugin_name(objName)
        mySide = read_str(recName, objH, 'Side')
        myNo = read_real(recName, objH, 'Point_No')
        ordered = others_on_side(recName, mySide, objH, order=True)
        if needs_number(myNo, ordered):
            vs.ResetObject(objH)
            vs.ReDrawAll()
    except Exception:
        import traceback
        _log(traceback.format_exc())


def refresh(pluginName, selected_only):
    def reset_one(h):
        vs.ResetObject(h)
    crit = "(PON='" + pluginName + "')"
    if selected_only:
        crit = "(%s & (SEL=TRUE))" % crit
        vs.ForEachObject(reset_one, crit)
        return
    # Refresh All: every object is redrawn here, so none needs to redraw its Side too
    _state['propagating'] = True
    try:
        vs.ForEachObject(reset_one, crit)
    finally:
        _state['propagating'] = False


# --------------------------------------------------------------------------
# Object Info palette layout (as the other tools: headings, labels, About)
# --------------------------------------------------------------------------

LAYOUT = [
    ('Point', ['Side', 'Point_No', 'Description']),
    ('Profile', ['Profile', 'Height at Boundary', 'Allowable Height', 'Daylight Angle',
                 'Shelf', 'Slope 1 to Height', 'Slope 2 Angle', 'Dashed']),
    ('Plane', ['Plane Class']),
    ('About', ['Version']),
]
LABELS = {'Side': 'Side', 'Point_No': 'Point No', 'Description': 'Description',
          'Profile': 'Profile', 'Height at Boundary': 'Height at Boundary',
          'Allowable Height': 'Allowable Height', 'Daylight Angle': 'Daylight Angle (deg)',
          'Shelf': 'Shelf', 'Slope 1 to Height': 'Slope 1 to Height',
          'Slope 2 Angle': 'Slope 2 Angle (deg)', 'Dashed': 'Dashed',
          'Plane Class': 'Plane Class', 'Version': 'Version'}
READ_ONLY = ('Version',)

WIDGET_BASE = 1100      # 1001 is Refresh Selected
HEADING_BASE = 2000
# Fixed widget IDs: only ever add to the end of these lists. '' marks the retired Refresh
# tick box, so the IDs after it stay where they were.
WIDGET_IDS = ['Side', 'Point_No', 'Description', 'Profile', 'Height at Boundary',
              'Allowable Height', 'Daylight Angle', 'Shelf', 'Slope 1 to Height',
              'Slope 2 Angle', 'Dashed', 'Plane Class', '', 'Version']
HEADING_IDS = ['Point', 'Profile', 'Plane', 'About']


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
        if heading == 'Plane':
            vs.vsoAddWidget(kRefreshID, kWidgetButton, 'Refresh Selected')
            vs.vsoWidgetSetIndLvl(kRefreshID, 1)
            vs.vsoAddWidget(REFRESH_ALL_ID, kWidgetButton, 'Refresh All')
            vs.vsoWidgetSetIndLvl(REFRESH_ALL_ID, 1)
        if heading == 'About':
            vs.vsoAddWidget(ABOUT_WEB_ID, kWidgetButton, WEBSITE)
            vs.vsoWidgetSetIndLvl(ABOUT_WEB_ID, 1)
            vs.vsoAddWidget(ABOUT_UPDATE_ID, kWidgetButton, 'Check for updates...')
            vs.vsoWidgetSetIndLvl(ABOUT_UPDATE_ID, 1)
    vs.SetObjPropVS(kObjXSupportsStyles, True)
    # State events, so a copy or paste can be renumbered (see on_add_state)
    try:
        vs.SetPrefInt(590, 1)          # varParametricEnableStateEventing
        vs.SetObjPropVS(kObjXPropAcceptStates, True)
        vs.SetObjPropVS(kObjXPropAcceptStatesInternal, True)
    except Exception as e:
        _log('state events', repr(e))


def hidden_widgets(kind):
    """Fields a Profile doesn't use."""
    if kind == 'alternative':
        return {'Height at Boundary', 'Allowable Height', 'Daylight Angle', 'Shelf',
                'Slope 1 to Height', 'Slope 2 Angle'}
    if kind == 'standard':
        return {'Shelf', 'Slope 1 to Height', 'Slope 2 Angle'}
    return set()


def widget_prep(h, rec):
    hidden = hidden_widgets(profile_kind(read_str(rec, h, 'Profile')))
    for _hid, _heading, params in _widget_ids():
        for wid, name in params:
            vs.vsoWidgetSetVisible(wid, name not in hidden)
            vs.vsoWidgetSetEnable(wid, name not in READ_ONLY)
    vs.vsoSetEventResult(kObjectEventHandled)


# Plug-in styles: a style is a profile preset (Profile, heights, angles, shelf, Dashed),
# By Style. Side, Point_No, Plane Class and the rest stay with each point (By Instance).
# Set the first time a style is used; change it in Edit Style.
STYLE_PARAMS = ('Profile', 'Height at Boundary', 'Allowable Height', 'Daylight Angle',
                'Shelf', 'Slope 1 to Height', 'Slope 2 Angle', 'Dashed')
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
    style whose Point_No is already By Instance has been set up: left alone."""
    sd = _style_def(h)
    if not sd:
        return
    try:
        if vs.GetParamStyleType(sd, 'Point_No') == kByInstance:
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


def run():
    try:
        theEvent, theData = vs.vsoGetEventInfo()
    except Exception:
        theEvent, theData = 0, 0

    if theEvent == kEvInit:
        init_layout()
    elif theEvent == kEvAddState:
        on_add_state(theData)
    elif theEvent in (kEvReset, 0):
        # 0: the shell isn't event-based; it still draws (no custom Object Info)
        try:
            draw_object()
        except Exception:
            _reset_failed('')
    else:
        ok, objName, objH, _rec, _wall = vs.GetCustomObjectInfo()
        if not ok or not objH:
            return
        pluginName = get_plugin_name(objName)
        if theEvent == kEvWidgetPrep:
            widget_prep(objH, pluginName)
        elif theEvent == kEvEditPluginStyle:
            vs.vsoSetEventResult(kObjectEditPluginStyleByDefault)
        elif theEvent == kEvButton:
            if theData == kRefreshID:
                refresh(pluginName, True)
            elif theData == REFRESH_ALL_ID:
                refresh(pluginName, False)
            elif theData == ABOUT_WEB_ID:
                open_website()
            elif theData == ABOUT_UPDATE_ID:
                check_updates()


# --- HTB tool (the .vst): what its clicks make -------------------------------
TOOL_OBJECT = 'HTB Tool'
TOOL_NAME = 'HTB'
# vstSetPtBehavior 2: two clicks
TOOL_MODES = (('', 2, 'Click the point on the boundary, then a second point along the boundary'),)
# tool bar pull-downs: (label, field, choices; the first until one is picked)
TOOL_PULLDOWNS = (('Side:', 'Side', ('North', 'North East', 'East', 'South East', 'South',
                                      'South West', 'West', 'North West')),)
# the spanner: (field, label, 'num' / 'text' / choices)
TOOL_DEFAULTS = (
    ('Profile', 'Profile', ('Standard', 'Alternative', 'Custom')),
    ('Height at Boundary', 'Height at Boundary', 'num'),
    ('Allowable Height', 'Allowable Height', 'num'),
    ('Daylight Angle', 'Daylight Angle', 'num'),
    ('Dashed', 'Dashed', ('True', 'False')),
)


def tool_complete(mode, pts, h):
    """At the first click, turned to face the second (as a point object's own
    tool), numbered on its first draw like any new HTB object."""
    if not pts:
        return
    (x, y), rot = pts[0], 0.0
    if len(pts) >= 2:
        rot = math.degrees(math.atan2(pts[-1][1] - y, pts[-1][0] - x))
    styled_new(new_point_object(x, y, rot))


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
