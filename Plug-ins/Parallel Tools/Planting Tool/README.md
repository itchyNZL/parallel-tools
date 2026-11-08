# Planting Tool

Hedges, shrub masses and spaced planting in plan for Vectorworks, as one object. Draw a line for a hedge or a closed shape for a planting bed. Works in Vectorworks Architect: no Landmark needed.

By Ian Thrush / Parallel Architecture NZ. MIT licence, see [LICENSE.md](LICENSE.md). Installing: see the [main README](https://github.com/itchyNZL/parallel-tools#installing).

## What it does

- **Hedge along a line:** at a set width, on the line's centre or along its left or right edge, so you can draw along a boundary and have the hedge sit inside it.
- **Bed in a closed shape:** the shape is the bed's outline.
- **Two looks:** a **Band** (one billowed shape) or **Plants** (a rough circle at each plant, merging into a scalloped mass or standing alone).
- **Plant counts** for a worksheet, with spacing, rows, zigzag and grid layouts.
- **Fills:** the class's solid fill, hand-drawn pen strokes, or strokes over a tint, plus a soft shadow.
- **Keeps clear of trees:** plants that land on a tree are left out.

A style for each species (a Cma hedge, a Lomandra mass, spaced Trachelospermum) keeps each look one click away.

## Drawing planting

Use the **Planting** tool. Its tool bar has:

| Tool bar | What it does |
|---|---|
| **Line** | A hedge: click along the line (straight, arcs or curves), double-click to finish. |
| **Closed shape** | A bed: click each corner, double-click to finish. |
| **Rectangle** | A bed: click one corner, then the opposite corner. |
| **Freehand** | A bed: drag round the area. |
| **Style** | The planting style for new planting, or `<Unstyled>`. |
| **Spanner** | Default Settings for new planting: Shape, Width, Line Is, Edge, Spacing, Rows, Fill, Shadow and Show Plant Centres. Blank or `(as the plug-in)` keeps the plug-in's own default, and a chosen style's values still win. Remembered for each user. |

To turn an existing line, polyline or polygon into planting, select it and use **Modify > Create Objects from Shapes**. Reshape the path with the Reshape tool as usual.

A new planting object goes in the class `Landscape-Plant` (made the first time), unless the active class already starts with Landscape. Set that class's pen and fill so every hedge looks the same.

## Editing planting

Object Info shows only the settings that apply: for example Width only along a line, the billow settings only for a Band, the stroke settings only for a pen fill.

### Planting

| Setting | What it does |
|---|---|
| Shape | **Band:** one billowed shape (see Edge). **Plants:** a rough circle at each plant. |
| Width | How wide the hedge is along a line, with round ends. With Plants in one row there is no Width: the plant is the hedge's width. |
| Line Is | The line is the hedge's **Centre**, or its **Left** or **Right** edge (looking along the line from the first click). |
| Keep Inside Outline | Closed shapes: the billows finish just inside the outline instead of bulging past it, and Plants keep whole circles inside. Along a line, Width is the hedge's core and the billows bulge outside it. |

### Plants

| Setting | What it does |
|---|---|
| Spacing (crs) | Centre to centre, a real size. 0 gives the hedge width (in a closed shape, a quarter of its narrow side). |
| Plant Size (Ø) | Shape Plants: the circle across. Bigger than Spacing and the plants merge into one scalloped shape; smaller and each stands alone. Auto is 1.25 x Spacing. |
| Plant Fit | Along a line. **Inset:** evenly at Spacing, half a space in from each end. **Ends:** a plant on each end, with Spacing as a maximum (a 5000 line at 600 gets 10 plants 556 apart). **Ends and Corners:** also a plant on each corner (a turn of 20° or more). |
| Rows | Along a line: 1 to 5 rows across the width, every other row staggered. |
| Zigzag Offset | With one row: each plant sits this far off the centreline, one side then the other. 0 gives a straight row. |
| Row Spacing, Row Shift (% crs) | Closed shapes: how far apart the grid's rows are, and how far each row shifts along, as a share of Spacing. 86.6 and 50 is a staggered grid, 100 and 0 a square grid. |
| Keep Clear of Class | Plants that land on an object in this class (default `Landscape-Tree`, same layer) are left out. The bed updates when it redraws, not when the tree moves. |
| Plant Count | How many plants are drawn (read only). Use it in a worksheet. |
| Reset Plant Start | Back to the automatic layout after dragging the start control point. |

A closed shape is filled with a grid at Spacing, at least a third of a space in from the edge. Over 3000 plants, none are drawn: increase Spacing.

### Edge

| Setting | What it does |
|---|---|
| Edge | **Billow** (cloud arcs, for a clipped or shrubby hedge), **Fuzzy** (jagged) or **Wavy** (a smooth wobble). For Plants, it sets each circle's outline. |
| Billow Size | How long each billow is, a real size (400 to 500 suits a 600 hedge). 0 is automatic, about two thirds of the width. |
| Billow Height (%) | How far each billow bulges. |
| Variability (%) | How much the billows (or circles) vary. 0 makes them all the same, like a revision cloud. |
| Billow Type | **Convex** (billows outward) or **Concave** (inward, spiky). |
| Seed, Reshuffle | The roughness is random but fixed, so it looks the same every redraw. Seed 0 makes every hedge differ; Reshuffle gives a new look. |

### Fill

| Setting | What it does |
|---|---|
| Fill | **Solid** (the object's fill from Attributes or the class), **Pen** (pencil strokes, no fill) or **Pen over Solid** (strokes over a tint, like coloured pencil). Strokes use the hedge's pen colour and line weight, and look drawn by hand. |
| Stroke Spacing (sheet mm) | Gap between strokes on the printed sheet. |
| Stroke Angle (deg) | 0 is along the x axis. |
| Cross Hatch | A second set of strokes at right angles. |
| Stroke Opacity (%) | So strokes that cross build up the colour. |
| Shadow | A soft grey shadow. |
| Shadow Offset (sheet mm) | How far, on the printed sheet (default 0.8). |
| Shadow Angle (deg) | Which way it falls, anticlockwise from right: 315 (default) is down and right. It keeps its direction however the bed is rotated, so one angle lights a whole plan. |

### Plant Centres

| Setting | What it does |
|---|---|
| Show Plant Centres | A small mark at each plant, like a trunk. |
| Marker | Circle, Dot or Cross. |
| Marker Size (sheet mm) | On the printed sheet. |
| Marker Class | The markers go in this class (default `Landscape-Plant Centres`, made black the first time), so the class sets their look and turning it off hides them. Blank keeps them with the hedge. |

### About

The tool's version, the scale it was drawn at (Drawn Size), its GitHub page, and Check for updates....

### Control points

Each writes its number into Object Info, and typing a number moves it. A control point is hidden when its value comes from the style.

- **Plant start:** a dot on one plant. Drag it to slide the plants along the hedge (or the grid across a bed). Hidden with Plant Fit Ends.
- **Width:** on the hedge's edge, halfway along (lines only).
- **Spacing:** on the next plant from the start.
- **Plant Size:** on the start plant's circle (Shape Plants only).
- **Row:** on a plant in the next row (closed shapes): sets Row Spacing and Row Shift.

**Guides:** the path as drawn and a small label at each control point go in the class `Landscape-Plant Guides`, made grey the first time. Tick **Non Plot** in that class so the guides show on screen and never print.

## Styles

Planting supports plug-in styles: make one for each kind of hedge or bed. A style holds Width, the edge, the fill and the plant settings. Line Is, Seed, the plant start and the read-only fields stay with each object.

## Limits

- A line that doubles back on itself closer than the hedge's width draws a small knot where the two sides cross.
- Sharp corners of a closed shape are rounded slightly by the billows.
- On a Wavy or Fuzzy edge the outer rows of plants can sit just outside the edge where it wanders in.
- Plan only: no 3D yet.

## Credits

With thanks to the tools and people that inspired this one. The general credits for all the tools (Vectorworks, and the forum threads on plug-in development) are in the main README.

### Vectorworks forum

The requests, ideas and answers in these threads shaped this tool. Thanks to everyone who posted:

- [hedge line](https://forum.vectorworks.net/topic/54923-hedge-line/) (2018): beanus, Jonathan Pickup, AlanW
- [Hedge tool to allow multiple species, and staggering of the hedge rows](https://forum.vectorworks.net/topic/63179-hedge-tool-to-allow-multiple-species-and-staggering-of-the-hedge-rows/) (2019): Amanda McDermott, Michal Zarzecki, lisagravy, Hans-Olav, Katarina Ollikainen, Laura Stone
