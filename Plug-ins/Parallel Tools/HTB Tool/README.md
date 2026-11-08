# HTB Tool

Height to Boundary (the daylight recession plane) for Vectorworks, as one point object. Put one at each ground point along a site boundary: each draws its vertical and angled lines and joins the point before it with a recession plane, so the plane follows the ground at every point. Standard, Auckland Unitary Plan Alternative, and Custom profiles.

By Ian Thrush / Parallel Architecture NZ. MIT licence, see [LICENSE.md](LICENSE.md). Installing: see the [main README](https://github.com/itchyNZL/parallel-tools#installing).

## What it does

- **One object per ground point.** Its height is measured up from its own Z, so set Z to the ground level there.
- **Planes join up automatically.** Points on the same Side link in number order, and a new point links up as soon as it is placed.
- **Three profiles:** Standard (height at boundary, then an angle), the Auckland Unitary Plan Alternative, or your own.
- **Classes per side and per profile,** so a side, or one profile's planes, can be turned off on its own.

## Placing points

Use the **HTB** tool. Click the point on the boundary, then a second point along the boundary to set the rotation. The marker is a T: its stem points into the site, the way the plane leans.

| Tool bar | What it does |
|---|---|
| **Style** | The HTB style (a profile preset) for new points, or `<Unstyled>`. |
| **Side** | North to North West. Pick it before placing; the point takes the next number on that Side. |
| **Spanner** | Default Settings for new points: Profile, Height at Boundary, Allowable Height, Daylight Angle and Dashed. Blank or `(as the plug-in)` keeps the plug-in's own default, and a chosen style's values still win. Remembered for each user. |

Then set each point's Z to the ground level there.

## Editing a point

Object Info shows only the settings the Profile uses.

### Point

| Setting | What it does |
|---|---|
| Side | Points with the same Side join up. |
| Point No | The order along the Side: North 2 draws its plane back to North 1, North 3 back to North 2. The lowest number on a Side has no plane. Gaps are fine. 0 takes the next free number. |
| Description | Notes only. |

**Numbering is automatic.** A new point takes the next free number on its Side. A copy or paste keeps the old number and is renumbered the next time it redraws. Type a free number to set the order yourself, or 0 to renumber.

A small label beside each point says what it links to: `North 3 > 2`, `North 1 (start)`, `North 1 (unlinked)` (alone on its Side), or `(profiles differ)`. The labels are in the class `Site-HTB-Guides`: tick **Non Plot** in that class so they show on screen only.

### Profile

| Setting | What it does |
|---|---|
| Profile | **Standard**, **Alternative** or **Custom** (below). |
| Height at Boundary | The vertical line up from the point. |
| Allowable Height | Where the plane tops out. |
| Daylight Angle (deg) | The plane's angle up from the boundary height (default 45; 0 draws a level line 3 m long). |
| Shelf | Custom: a level run in at the top of the vertical line. 0 is none. |
| Slope 1 to Height | Custom: the Daylight Angle runs up to this height. 0 runs straight to Allowable Height. |
| Slope 2 Angle (deg) | Custom: the angle from Slope 1 to Height up to Allowable Height. |
| Dashed | Dashed lines (200 mm dashes, 100 mm gaps), or solid. |

**The profiles:**

- **Standard:** up Height at Boundary, then Daylight Angle up to Allowable Height.
- **Alternative:** the Auckland Unitary Plan's alternative height in relation to boundary (figure H5.6.6.1), built in: up 3.6 m, a 1 m shelf in, then 73.3° (0.3 m in for every metre up) to 6.9 m, then 45° to 11 m. The 11 m top is read from the figure; the clause text doesn't give it. The height and angle settings are ignored.
- **Custom:** up Height at Boundary, a Shelf, Daylight Angle up to Slope 1 to Height, then Slope 2 Angle up to Allowable Height. Switching to Custom with Shelf and Slope 1 to Height both 0 fills in the Alternative's numbers to start from.

Points joined by a plane should use the same Profile. Sizes are held in millimetres and converted, so any file units work.

### Plane

| Setting | What it does |
|---|---|
| Plane Class | The class the planes go in. Blank follows the Profile: `Site-HTB-Plane Standard`, `Site-HTB-Plane Alternative` or `Site-HTB-Plane Custom`. A name of your own stays whatever the Profile. |
| Refresh Selected | Redraws the selected HTB points. |
| Refresh All | Redraws every HTB point in the file. |

### About

The tool's version, its GitHub page, and Check for updates....

## Classes and lines

- **Points** go in `Site-HTB-<Side>` (for example `Site-HTB-North East`), made if the file hasn't got it, so a side can be turned off on its own. The marker and profile lines take their colour, weight and line type from that class.
- **Planes** take their line, fill, colour and opacity from the Plane Class. A plane is drawn by the higher-numbered point of its pair, and is in that point's class.

## When to refresh

Changing a point redraws the rest of its Side (and its old Side, if you changed it). Two cases need a refresh:

- **After deleting a point:** Vectorworks runs nothing on a delete, so change any point on that Side or press **Refresh All**.
- **After moving a point:** unless Reset on Move is ticked (Options > Execution Options), press **Refresh Selected** or **Refresh All**.

## Styles

HTB points support plug-in styles. A style is a profile preset: Profile, the heights and angles, Shelf and Dashed. Side, Point No and Plane Class stay with each point.

## Limits

- A plane is flat only when both ends have the same angle and rotation; otherwise it is a warped four-point polygon.
- If the two ends have a different number of profile points (different profiles), the plane is one strip from the boundary to the top.
- HTB Tool points only link to other HTB Tool points, not to the older ht2boundary objects, so replace a whole boundary at once.
- Only Auckland's Alternative is built in. Rules elsewhere that are a vertical line followed by sloping lines, with or without a shelf, can be drawn with Custom.
- The Alternative clause's 20 m from the site frontage isn't modelled: put Alternative points along the part of the boundary it applies to.

## Credits

With thanks to the tools and people that inspired this one. The general credits for all the tools (Vectorworks, and the forum threads on plug-in development) are in the main README.

### Inspiration

- **ht2boundary** by Jonathan Pickup, ArchonCAD: the earlier Height to Boundary plug-in this tool replaces.
