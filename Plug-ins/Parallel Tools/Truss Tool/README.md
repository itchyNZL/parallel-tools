# Truss Tool

Schematic timber roof trusses for Vectorworks, as one linear object: 14 truss types and assemblies (hip ends and valley sets), drawn in plan and modelled in 3D so sections and elevations come from the model. Terminology follows the MiTek NZ GANG-NAIL Residential Manual.

**Schematic only.** Truss Tool draws trusses for documentation and visualisation. Truss design, layout, sizes and connections are always by the truss supplier or fabricator.

By Ian Thrush / Parallel Architecture NZ. MIT licence, see [LICENSE.md](LICENSE.md). Installing: see the [main README](https://github.com/itchyNZL/parallel-tools#installing).

## What it does

- **14 types** from the MiTek manual: rafter, girder, truncated, gable end, jack, half, saddle or valley, scissor, vaulted and attic trusses, plus hip end and valley set assemblies.
- **Draws by span:** outside of wall to outside of wall. Heel height, setbacks and web centres are worked out for you.
- **Real members in 3D:** every member is an extrude, girders show each ply, and IFC export marks each truss as a truss assembly.
- **Classes per part and per status** (Proposed, Existing, Demolish), so members, outriggers, soffit bearers and hip lines can be styled and turned off separately.

## Drawing a truss

Use the **Truss** tool. Click one end of the span (the outside face of one wall), then the other.

| Tool bar | What it does |
|---|---|
| **Style** | The truss style for new trusses, or `<Unstyled>`. |
| **Type** | The truss type. Pick it before drawing. |
| **Spanner** | Default Settings for new trusses: Roof Pitch, Overhang, Web Pattern, Girder, Plan Display and Status. Blank or `(as the plug-in)` keeps the plug-in's own default, and a chosen style's values still win. Remembered for each user. |

Set the truss height (top of wall plate) with the object's **Z** in Object Info.

**Left and right:** left is the start of the line, the first point you click (Vectorworks shows "insertion point" when you hover over it). Right is the end. Two Overhangs, Bearers, High End and Half all use this.

## Truss types

The code in brackets at the end of each type is what the tool reads.

| Type | Notes |
|---|---|
| Rafter Truss (T) | Web Pattern: 4 Web or King Post. Tick Two Pitches for a different Pitch (Right) and Heel (Right); the apex sits where the roof lines meet. |
| Girder Truss (G) | Verticals at equal panels, no more than Web Centres apart, with diagonals. 2 or 3 ply (Girder). |
| Truncated Rafter Truss (TR) | A flat top from the Setback (0 gives a quarter of the span). |
| Truncated Girder Truss (TG) | As TR, with verticals along the flat top at Web Centres, and 2 or 3 ply. Carries hip end jacks. |
| Gable End Truss (GE) | Vertical webs at set centres, top chord dropped for outriggers. |
| Jack Truss (J) | A short half truss carried by a girder: end post, one vertical, one diagonal. |
| Truncated Jack Truss (TJ) | Top cut short at the Setback (0 gives half the span), with a flat chord below the rafter seat. |
| Half Truss (H) | A mono truss, High End Left or Right. Overhang is the low end; tick Two Overhangs to set each end. |
| Saddle or Valley Truss (S/V) | A triangle with vertical webs, no overhang, sitting on the main roof. Tick Half Valley for a mono valley truss. |
| Scissor Truss (SC) | A pitched bottom chord at Ceiling Pitch (0 gives half the roof pitch). |
| Vaulted Truss (VT) | A deeper cove member from the tail over the wall to Cove Length (0 gives a quarter of the span), then a flat ceiling chord. |
| Attic Truss (AT) | Knee-wall studs Attic Width apart with a diagonal web outside each, and a collar tie at Collar Height above the floor. |
| Hip End (HE) | The whole hip in the MiTek pattern (below). |
| Valley Set (VS) | Saddle or valley trusses where a wing roof meets a main roof (below). |

**Hip End:** draw along the end wall. The roof runs away from the line on its left (start to end); tick **Flip** to swap. You get the girder (TG, or G at the apex), main jacks, side jacks, corner jacks and hip rafters. Setback is the girder setback: 0 is automatic (a full girder at the apex for end walls up to 7.4 m; beyond that a truncated girder one Spacing short of the apex). Overhang is every eave; tick Two Overhangs to set the end wall (Overhang) and the side walls (Overhang L and R) apart, for example 0 on a boundary.

**Valley Set:** draw along the main wall face across the wing, internal corner to internal corner. The valley trusses step up the main roof to the left of the line (or right with Flip) at Spacing, each sized to land in the wing roof, until they run out at the wing ridge. Valley lines are drawn in plan. Place the wing's rafter trusses outwards from the line.

**Half** (Hip End and Valley Set): tick Half and pick the Side for an L corner, then draw from the corner to the ridge line. Only that half is drawn.

## Editing a truss

Object Info shows only the settings the truss type uses. Settings indented under another are greyed until it is ticked.

### Truss

| Setting | What it does |
|---|---|
| Truss Type | As on the tool bar. |
| Span | Outside of wall to outside of wall. Or drag the end control points. |
| Roof Pitch | Degrees. |
| Two Pitches, Pitch (Right) | A different pitch on the right (Rafter Truss). |
| Heel Height, Heel (Right) | Top of wall plate to the top of the top chord, at the outside of the wall (MiTek's definition). Worked out from the top chord and pitch, and greyed. |
| Heel Override | Enter your own heel height. A raised heel adds heel posts. |
| Overhang | The eave, past the wall. |
| Two Overhangs, Overhang (L), (R) | A different overhang at each end. |
| Web Pattern | 4 Web or King Post (Rafter Truss). |
| Half Valley | A mono valley truss. |
| High End | Left or Right (Half Truss, Half Valley). |
| Girder | 1, 2 or 3 Ply. Each ply is drawn, so sections show the laminations. |
| Spacing | Truss centres, for hip ends and valley sets. |
| Flip | Which side of the line a hip end or valley set runs. |
| Half, Side | Half a hip end or valley set, and which half. |
| Collar Height | Attic Truss: the collar tie above the floor. |
| Override Auto | Unticked, Setback, Web Centres, Ceiling Pitch, Cove Length and Attic Width are worked out, shown and greyed. Tick to edit them, starting from the automatic value. |
| Setback, Web Centres, Ceiling Pitch, Cove Length, Attic Width | As in Truss types above. |

### Member Sizes

| Setting | What it does |
|---|---|
| Thickness | Timber thickness (default 45). |
| Top Chord, Bottom Chord, Webs | Member depths. |
| Cove Member | The vaulted truss's deeper member. |
| Soffit Bearer, Outrigger | Their depths. |

### Soffit

| Setting | What it does |
|---|---|
| Bearers | Soffit bearers at Both ends, Left, Right or None. They sit beside the top chord tail, underside level with the bottom of the tail at the fascia. |
| Bearer Drop | Lowers them. |

### Outriggers

Gable End Truss only.

| Setting | What it does |
|---|---|
| Outriggers | On or off. |
| Centres | Outrigger spacing. |
| Verge | How far they run past the gable. |
| Back Span | How far they run back, to the first truss. |
| Plan Display | Solid (outlines) or Line (centre lines). |

### Display

| Setting | What it does |
|---|---|
| Plan Display | Centre Line, Outline or None. The line style comes from the class. |

### ID & Classes

| Setting | What it does |
|---|---|
| ID Number | The number in the truss mark. |
| ID | The truss mark: the MiTek code plus ID Number (T1, TG2, J3), filled in automatically. The tool doesn't draw it: show it with a Data Tag reading the ID field. |
| Status | Proposed, Existing or Demolish. Goes into the class names and the IFC description. |
| Truss, Outrigger, Soffit Bearer, Hip / Valley | The class for each part (below). |

### About

The tool's version, its GitHub page, and Check for updates....

## Classes

Each part goes in its own class and takes that class's line, weight, colour and fill:

| Part | Setting | Default |
|---|---|---|
| Truss members, hip end jacks and rafters | Truss | `Roof-Truss-{Status}-Object` |
| Gable outriggers | Outrigger | `Roof-Truss-{Status}-Outrigger` |
| Soffit bearers | Soffit Bearer | `Roof-Truss-{Status}-Soffit` |
| Hip and valley lines in plan | Hip / Valley | `Roof-Truss-{Status}-Hip` |

`{Status}` becomes the Status and `{Type}` the truss code (T, TG and so on). Classes are made if they don't exist. A blank class setting leaves that part in the object's own class.

## IFC

Each truss exports as **IfcElementAssembly** with PredefinedType **TRUSS**: Name and Tag are its ID, ObjectType its truss type, AssemblyPlace FACTORY, and Description its Status plus the schematic notice (for example "Proposed. Schematic only: confirm with truss supplier"). IFC settings you have changed by hand are kept.

## Styles

Trusses support plug-in styles. A style holds the member sizes, the plan displays and the class names. Truss type, span, pitch, heights, overhangs, ID and the rest stay with each truss.

## Limits

- Schematic only: not a truss design.
- Older trusses may show an Elevation setting. Set it to 0 and use the object's Z instead.

## Credits

With thanks to the tools and people that inspired this one. The general credits for all the tools (Vectorworks, and the forum threads on plug-in development) are in the main README.

### Inspiration

- **Schematic Wood Truss** by David Hamer (2023): an earlier schematic truss plug-in.
- **Truss Gable End** and **Truss Standard 4 Web** by John Greaney: the earlier truss plug-ins used in the office.
- **MiTek NZ GANG-NAIL Residential Manual**: the truss types and terms.

### Vectorworks forum

The requests, ideas and answers in these threads shaped this tool. Thanks to everyone who posted:

- [Roof Trusses](https://forum.vectorworks.net/topic/44922-roof-trusses/) (2016): Mitchell (the other one), AlanW, CipesDesign, trussgrp
- [Roof Truss tool](https://forum.vectorworks.net/topic/51129-roof-truss-tool/) (2017): Rico2surf, AlanW, BG, The Hamma
- [Schematic Wood Truss](https://forum.vectorworks.net/topic/107674-schematic-wood-truss/) (2023): The Hamma, TomKen
- [Wood Truss Tool](https://forum.vectorworks.net/topic/118417-wood-truss-tool/) (2024): Sam Combs, The Hamma
