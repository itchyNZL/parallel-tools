# Development

How the tools are built, for anyone rebuilding the plug-in shells or changing the code. To use the tools, see the [README](README.md): the release zips come with the shells ready made.

## How a tool is put together

Each tool is a pair of Vectorworks plug-ins and a code folder, side by side in a `Parallel Tools` folder inside a Plug-ins folder (in this repo, `Plug-ins/Parallel Tools/`):

- **The object** (`<Tool> Tool.vso`): a path, linear or point plug-in object. Its script is `vso_stub.py`.
- **The drawing tool** (`<Name>.vst`): places the object, with the Style list, the tool's own pull-downs and the spanner on the tool bar. Its script is `vst_stub.py`.
- **The code folder** (`<Tool> Tool/`): `<tool>_tool.py` holds all the logic; the stubs find it beside the `.vso` and load it, reloading only when the file has changed. Edit the `.py`, then nudge an object (or Modify > Reset) to redraw: no restart needed, except that Object Info's layout is built once per session.

Object Info's headings, order and labels come from `LAYOUT` and `LABELS` in each tool's code, not the Plug-in Manager. The first redraw in a session lists any parameter missing from the plug-in.

## Shared code

Code used by more than one tool is kept once in `shared/` and copied into each tool's `.py` between marker lines, so every tool stays one file and can be handed out on its own:

```python
# shared begin common
...
# shared end common
```

| Block | What's in it |
|---|---|
| `shared/common.py` | The debug log (`_log`, `_reset_failed`), units (`_mm`), classes (`_new_class`, `_set_class`, `_set_class_colour`), the About buttons (website, Check for updates). Uses each tool's `DEBUG_LOG`, `TOOL_FOLDER`, `VERSION` and `WEBSITE`. |
| `shared/drawing-tool.py` | The drawing tool (`.vst`): modes, the Style list, pull-downs, the spanner, placing. Each tool sets it up with `TOOL_OBJECT`, `TOOL_NAME`, `TOOL_MODES`, `TOOL_PULLDOWNS`, `TOOL_DEFAULTS` and `tool_complete()`, listed at the top of the block. |

Edit the file in `shared/`, never the copy in a tool, then run:

```bash
python sync_shared.py
```

`python sync_shared.py --check` only reports tools whose copy differs, and `build_zips.py` runs it, so a release can't go out with an old copy. A tool can leave a block out (add both marker lines to take one in).

## Making a drawing tool (.vst)

A tool made with Plug-in Manager > New > Tool can't be made event-enabled, and the tool bar needs events. So:

1. In the Plug-in Manager select **Comment** and **Duplicate** it (the copy keeps Comment's event setting).
2. Rename it (the names below).
3. Edit Script: set the language to **Python** (VectorScript gives "Incorrect angle format"), and replace the script with the tool's `vst_stub.py`.
4. No parameters.
5. Properties > Tooltip Help: the text below.
6. Icon: pick `Plug-ins/Parallel Tools/Icons/<tool>_icon.svg`. Vectorworks finds `<tool>_icon_dark.svg` beside it for dark mode (26 x 20 SVG).

| Drawing tool | Tooltip Help | Object | Tooltip Help |
|---|---|---|---|
| Comment | Draws a review comment: outline, leader and tag. Pick a mode and a Style on the tool bar; the spanner sets the defaults. | Comment Tool | Review comment with status, type and audience, coloured by class. |
| Revision | Draws a revision cloud with its marker. Pick a mode and a Style on the tool bar; the spanner sets the defaults. | Revision Tool | Revision cloud and marker, numbered from the sheet's revisions. |
| BreakLine | Draws a break line: click the start, then the end. Pick a Style on the tool bar. | Break Line Tool | Break line object. |
| Planting | Draws a hedge along a line, or a planting bed in a closed shape. Pick a mode and a Style on the tool bar. | Planting Tool | Hedge or planting bed with plant counts, fills and a shadow. |
| HTB | Places a Height to Boundary point: click on the boundary, then along it to set the rotation. Pick a Style on the tool bar. | HTB Tool | Recession plane from a boundary point. |
| Truss | Places a truss between two clicks. Pick the truss Type and a Style on the tool bar. | Truss Tool | Schematic timber roof truss. |

BreakLine is one word because Vectorworks already has a tool called Break Line.

## Spanner (Default Settings)

The spanner opens Default Settings, set by `TOOL_DEFAULTS` (Break Line, Planting, HTB, Truss), or the tool's own `tool_spanner()` (Comment's and Revision's Preferences). Defaults, the Style and the last mode are saved per user in `%APPDATA%/Nemetschek/Vectorworks/<object name>_prefs.json`; saving merges into the file, so Comment and Revision keep their Preferences in the same file. Tool bar pull-down picks are 0-based.

## Releases

1. Bump `VERSION` and `VERSION_DATE` in the tool's `.py`, and add an entry to the tool's `CHANGELOG.md` for each release.
2. Run `python build_zips.py` (it stops if the shared code needs a sync): one zip per tool and one with all of them in `dist/`, and `versions.json` rewritten from each tool's version. Each zip holds only what's needed to run the tools: a `Parallel Tools` folder with the `.vso`, the `.vst` and each tool's `.py` in its code folder, plus the README and LICENSE. Everything else (tool READMEs, changelogs, stubs, icons) is in this repo.
3. Attach the zips to a GitHub release and push `versions.json`: each tool's About > Check for updates... reads it.

## Developer switch

A file named `vectorworks_tools_dev.txt` in a Vectorworks version's user data folder (for example `%APPDATA%/Nemetschek/Vectorworks/2027/`), holding the path of the development folder that holds the tool folders (in this repo, `Plug-ins/Parallel Tools`), makes that machine load the code from there instead of the installed copy. Without the file nothing changes.

## Setting up each object (.vso)

### Comment Tool

1. Copy `Comment Tool.vso` (once made) and the `Comment Tool` folder side by side into the `Parallel Tools` folder in a Plug-ins folder.
2. Plug-in Manager > New: **Path Object**, name `Comment Tool`.
3. Edit Script: Python, paste `vso_stub.py`.
4. Properties > Execution Options: tick **Event-based plug-in**.
5. Add these parameters in this order. Alternate Name is only a fallback: the Object Info labels and order come from the code.

| Name | Alternate Name | Type | Choices | Default |
|---|---|---|---|---|
| **Comment** | | | | |
| Note | Comment | Text | | |
| Audience | Audience | Pop-up | Internal, Client | Internal |
| Status | Status | Pop-up | Open, Done, Closed | Open |
| CommentType | Type | Pop-up | Fix, Note, Nice | Note |
| From | From | Text | | |
| To | To | Text | | |
| Number | Number | Text | | |
| Location | Location | Text | | |
| CreatedDate | Created | Text | | |
| CreatedTime | Created Time | Text | | |
| DoneDate | Done | Text | | |
| DoneTime | Done Time | Text | | |
| **Settings** | | | | |
| Outline | Outline | Pop-up | Line, Cloud, None | Line |
| CloudSize | Cloud (mm) | Number | | 6 |
| LeaderSetback | Setback (mm) | Number | | 1.5 |
| Shoulder | Shoulder (mm) | Number | | 2 |
| TagWidth | Tag Width | Dimension | | 0 |
| NumberPrefix | Number Prefix | Text | | # |
| CopyNumbering | Copies | Pop-up | Next number, Next free after copied, Lowest free | Next number |
| UseType | Use Type | Boolean | | True |
| UseAudience | Use Audience | Boolean | | True |
| ShowNumber | Show Number | Boolean | | True |
| ShowDate | Show Date | Boolean | | True |
| ShowFrom | Show From | Boolean | | False |
| ShowTo | Show To | Boolean | | True |
| CollapseClosed | Closed Header Only | Boolean | | True |
| TagLine | Tag Line | Pop-up | Full width, Header | Full width |
| ClassTemplate | Class Template | Text | | Notes-Comment-{Audience}-{Status} |
| LeaderMarkers | Leader Markers | Text | | |
| **Internal** | | | | |
| ControlPoint01X | Tag X | X Coordinate | | 0 |
| ControlPoint01Y | Tag Y | Y Coordinate | | 0 |
| ControlPoint02X | Tag End X | X Coordinate | | 0 |
| ControlPoint02Y | Tag End Y | Y Coordinate | | 0 |
| State | State | Text | | |
| Version | Version | Text | | |
| ControlPoint03X | Pin X | X Coordinate | | 0 |
| ControlPoint03Y | Pin Y | Y Coordinate | | 0 |
| DrawnSize | Drawn Size | Text | | |

Notes: From and To for new comments come from Preferences (e.g. your initials in From). Tag Width 0 = 40 mm on paper, Cloud (mm) = scallop size on the printed sheet, 0 = 6 mm. Number, Location and the Created / Done dates and times fill in automatically. State is internal and not shown. Comment text is stored with line breaks as `\n` and a backslash doubled (`\\`), because Vectorworks breaks on a real line break or a lone backslash in a parameter.

### Revision Tool

1. The `Revision Tool` folder goes beside `Revision Tool.vso` in the `Parallel Tools` folder.
2. Plug-in Manager > New: **Path Object**, name `Revision Tool`.
3. Edit Script: Python, paste `vso_stub.py`.
4. Properties > Execution Options: tick **Event-based plug-in**.
5. Add these parameters. The Object Info labels and order come from the code; Alternate Name is only a fallback.

| Name | Alternate Name | Type | Choices | Default |
|---|---|---|---|---|
| **Revision** | | | | |
| Rev | Revision | Text | | |
| Date | Date | Text | | |
| Note | Note | Text | | |
| Sheet | Sheet | Text | | |
| ShowTag | Show Marker and Text | Boolean | | True |
| LeaderFixed | Fixed Leader Start | Boolean | | False |
| CloudOffset | Offset (mm) | Number | | 0 |
| **Settings** | | | | |
| Outline | Outline | Pop-up | Cloud, Line | Cloud |
| CloudSize | Cloud (mm) | Number | | 6 |
| CloudHeight | Billow Height | Pop-up | Low, Medium, High | Medium |
| MarkerShape | Marker | Pop-up | Triangle, Circle, Square, Hexagon | Triangle |
| MarkerSize | Marker (mm) | Number | | 6 |
| ShowLeader | Show Leader | Boolean | | True |
| Shoulder | Shoulder (mm) | Number | | 3 |
| LeaderSetback | Setback (mm) | Number | | 0 |
| ShowDate | Show Date | Boolean | | True |
| ShowNote | Show Note | Boolean | | True |
| NoteWidth | Wrap (mm) | Number | | 0 |
| TextLine | Line | Pop-up | None, Date, Text | Date |
| NoteAlign | Note Align | Pop-up | Auto, Left, Right | Auto |
| ClassTemplate | Class Template | Text | | Revision-{Rev} |
| ShowLatest | Show Latest | Number | | 2 |
| **Internal** | | | | |
| ControlPoint01X | Knee X | X Coordinate | | 0 |
| ControlPoint01Y | Marker Y | Y Coordinate | | 0 |
| ControlPoint02X | Wrap X | X Coordinate | | 0 |
| ControlPoint02Y | Wrap Y | Y Coordinate | | 0 |
| ControlPoint03X | Leader Start X | X Coordinate | | 0 |
| ControlPoint03Y | Leader Start Y | Y Coordinate | | 0 |
| State | State | Text | | |
| Version | Version | Text | | |
| DrawnSize | Drawn Size | Text | | |

Leave the defaults of Rev, Date, Note, Sheet, State, Version and DrawnSize blank (not 0): a new revision fills them from the tool preferences and the dialog. Sizes are mm on the printed sheet. State is internal (the last Rev, Date and Sheet, whether it was drawn in colour and its Show latest, used to share dates and Show latest and to grey older revisions). The first redraw in a session lists any parameter missing from the plug-in. Note text is stored with line breaks as `\n` and a backslash doubled, because Vectorworks breaks on a real line break or a lone backslash in a parameter.

### Break Line Tool

1. The `Break Line Tool` folder goes beside `Break Line Tool.vso` in the `Parallel Tools` folder.
2. Plug-in Manager > New: **Linear Object**, name `Break Line Tool`.
3. Edit Script: Python, paste `vso_stub.py`.
4. Properties > Execution Options: tick **Event-based plug-in**.
   Icon: pick `Icons/break_line_icon.svg` in the Plug-in Manager (Edit Definition > Icon); Vectorworks finds `break_line_icon_dark.svg` beside it for dark mode (the `_dark` suffix) (26 x 20, one line with one break).
5. Add these parameters. The Object Info labels and order come from the code.

| Name | Alternate Name | Type | Choices | Default |
|---|---|---|---|---|
| LineLength | Length | Dimension (built in) | | 1000 |
| Overrun | Extend Past Ends | Dimension | | 20 |
| BreakStyle | Style | Pop-up | Straight, Curved, Arc | Straight |
| NumBreaks | Number of Breaks | Integer | | 1 |
| BreakWidth | Break Width (mm) | Number | | 2 |
| BreakSize | Break Height (mm) | Number | | 2 |
| BreakRadius | Arc Radius (mm) | Number | | 0 |
| Skew | Skew (deg) | Number | | 0 |
| Double | Double Break Lines | Boolean | | False |
| Mask | Mask Behind | Boolean | | True |
| MaskDepth | Mask Depth (mm) | Number | | 5 |
| DrawnSize | Drawn Size | Text | | |
| ControlPoint01X | Near Dot X | X Coordinate | | 0 |
| ControlPoint01Y | Near Dot Y | Y Coordinate | | 0 |
| ControlPoint02X | Far Dot X | X Coordinate | | 0 |
| ControlPoint02Y | Far Dot Y | Y Coordinate | | 0 |
| LastLength | Last Length | Number | | 0 |
| State | State | Text or Number | | |
| Version | Version | Text | | |

Keep LastLength's default at 0 and State's blank: they are internal. 0 is how a new object knows to centre its dots; State is the far dot's last height, so a drag can be told from a typed Mask Depth. The first redraw in a session lists any parameter missing from the plug-in.

### Planting Tool

1. The `Planting Tool` folder goes beside `Planting Tool.vso` in the `Parallel Tools` folder.
2. Plug-in Manager > New: **Path Object**, name `Planting Tool`.
3. Edit Script: Python, paste `vso_stub.py`.
4. Properties > Execution Options: tick **Event-based plug-in**.
5. Add these parameters. The Object Info labels and order come from the code.

| Name            | Alternate Name      | Type         | Choices                       | Default                 |
|-----------------|---------------------|--------------|-------------------------------|-------------------------|
| Width           | Width               | Dimension    |                               | 600                     |
| Offset          | Line Is             | Pop-up       | Centre, Left, Right           | Centre                  |
| EdgeStyle       | Edge                | Pop-up       | Billow, Fuzzy, Wavy           | Billow                  |
| BillowSize      | Billow Size         | Dimension    |                               | 400                     |
| BillowHeight    | Billow Height (%)   | Number       |                               | 50                      |
| Variability     | Variability (%)     | Number       |                               | 40                      |
| BillowType      | Billow Type         | Pop-up       | Convex, Concave               | Convex                  |
| Seed            | Seed                | Integer      |                               | 0                       |
| ShowCentres     | Show Plant Centres  | Boolean      |                               | False                   |
| PlantSpacing    | Spacing (crs)       | Dimension    |                               | 500                     |
| Rows            | Rows                | Integer      |                               | 1                       |
| CentreStyle     | Marker              | Pop-up       | Circle, Dot, Cross            | Circle                  |
| CentreSize      | Marker Size (mm)    | Number       |                               | 1.5                     |
| PlantCount      | Plant Count         | Integer      |                               | 0                       |
| MarkerClass     | Marker Class        | Text         |                               | Landscape-Plant Centres |
| ControlPoint01X | Plant Start X       | X Coordinate |                               | 0                       |
| ControlPoint01Y | Plant Start Y       | Y Coordinate |                               | 0                       |
| PlantStart      | Plant Start         | Number       |                               | -1                      |
| State           | State               | Text         |                               |                         |
| FillStyle       | Fill                | Pop-up       | Solid, Pen, Pen over Solid    | Solid                   |
| PenSpacing      | Stroke Spacing (mm) | Number       |                               | 1                       |
| PenAngle        | Stroke Angle (deg)  | Number       |                               | 45                      |
| CrossHatch      | Cross Hatch         | Boolean      |                               | False                   |
| PenOpacity      | Stroke Opacity (%)  | Number       |                               | 80                      |
| Version         | Version             | Text         |                               |                         |
| Shape           | Shape               | Pop-up       | Band, Plants                  | Band                    |
| PlantSize       | Plant Size (Ø)      | Dimension    |                               | 600                     |
| Shadow          | Shadow              | Boolean      |                               | False                   |
| KeepClear       | Keep Clear of Class | Text         |                               | Landscape-Tree          |
| ControlPoint02X | Width Handle X      | X Coordinate |                               | 0                       |
| ControlPoint02Y | Width Handle Y      | Y Coordinate |                               | 0                       |
| ControlPoint03X | Spacing Handle X    | X Coordinate |                               | 0                       |
| ControlPoint03Y | Spacing Handle Y    | Y Coordinate |                               | 0                       |
| ControlPoint04X | Plant Size Handle X | X Coordinate |                               | 0                       |
| ControlPoint04Y | Plant Size Handle Y | Y Coordinate |                               | 0                       |
| Zigzag          | Zigzag Offset       | Number       |                               | 0                       |
| KeepInside      | Keep Inside Outline | Boolean      |                               | True                    |
| PlantFit        | Plant Fit           | Pop-up       | Inset, Ends, Ends and Corners | Inset                   |
| RowSpacing      | Row Spacing (% crs) | Number       |                               | 86.6                    |
| RowShift        | Row Shift (% crs)   | Number       |                               | 50                      |
| ControlPoint05X | Row Handle X        | X Coordinate |                               | 0                       |
| ControlPoint05Y | Row Handle Y        | Y Coordinate |                               | 0                       |
| ShadowOffset    | Shadow Offset (mm)  | Number       |                               | 0.8                     |
| DrawnSize       | Drawn Size          | Text         |                               |                         |
| ShadowAngle     | Shadow Angle (deg)  | Number       |                               | 315                     |

6. Add the tool to the workspace (Tools > Workspaces > Edit Current Workspace > Tools: Planting Tool is under Miscellaneous; drag it into a tool set).

Keep PlantStart's default at -1 and State's blank: they are internal (-1 = automatic plant layout; State is where the handles were left, so a drag can be told from a reshape). The first redraw in a session lists any parameter missing from the plug-in.

### HTB Tool

1. The `HTB Tool` folder goes beside `HTB Tool.vso` in the `Parallel Tools` folder.
2. Plug-in Manager > New: **Point Object**, name `HTB Tool`. The older `ht2boundary` plug-in can stay installed: objects already in drawings keep working and are replaced as needed. HTB Tool objects only link to other HTB Tool objects (the search is by plug-in name), so replace a whole boundary at once, not half of it.
3. Edit Script: Python, paste `vso_stub.py`.
4. Options > Execution Options: tick **Event-Based**. Icon: pick `Icons/htb_icon.svg` in the Plug-in Manager (Edit Definition > Icon); Vectorworks finds `htb_icon_dark.svg` beside it for dark mode (the `_dark` suffix) (26 x 20: two boundary points, their posts and the plane between).
5. Strings: hint `Click to Insert a Height to Boundary Object`; help `Height to Boundary Object. Place the Object on the Site in Top/Plan view and rotate to match the Boundary. Change the heights on the Object Info Palette.`
6. Add these parameters. The code reads the names exactly, spaces and capitals included (`Point_No` has an underscore).

| Name | Type | Choices | Default |
|---|---|---|---|
| Height at Boundary | Dimension | | 2500 mm |
| Allowable Height | Dimension | | 8000 mm |
| Daylight Angle | Number | | 45 |
| Description | Text | | |
| Profile | Pop-up | Standard, Alternative, Custom | Standard |
| Shelf | Dimension | | 0 |
| Slope 1 to Height | Dimension | | 0 |
| Slope 2 Angle | Number | | 45 |
| Dashed | Boolean | | On |
| Side | Pop-up | North, North East, East, South East, South, South West, West, North West | North |
| Point_No | Integer | | 0 |
| Plane Class | Text | | (blank) |
| Refresh | Boolean | | Off |
| Version | Text | | (blank) |
| State | Text | | (blank) |

Keep Point_No's default at 0: that is how a new object knows to number itself. Keep Plane Class's default blank: the tool writes `Site-HTB-Plane <Profile>` into the field the first time it draws. (A default with a space in it was stored cut at the space, as `Site-HTB-Plane`, in the Plug-in Manager, so the names are held in the code. The tool treats a bare `Site-HTB-Plane` as blank, so an object that has it, or a shell that still has it as the default, follows the Profile all the same.)

Version and State are filled in by the tool (State remembers the Side, so a change of Side redraws the old one too). The first draw in a session lists any parameter the plug-in is missing. Profile, Shelf, Slope 1 to Height and Slope 2 Angle can go anywhere in the list. An object that doesn't have them yet draws as Standard. Object Info may need a Vectorworks restart to show new fields.

#### HTB Tool: Ideas

- **Other regions.** Height in relation to boundary and recession plane rules differ from place to place, and I haven't looked at any beyond Auckland's. A rule that is a vertical line followed by sloping lines, with or without a shelf, can be drawn with Custom now. For one used often, add a preset beside `ALT` in `htb_tool.py` (a new name in `profile_kind` and a case in `profile_points`), so people choose it from Profile with nothing to type.
- **More than two slopes.** Custom stops at a shelf and two slopes. A rule with more could take its lines as a list.
- **The 20 m from the frontage.** The Alternative clause refers to buildings within 20 m of the site frontage. The tool doesn't model that distance: put the Alternative objects along the part of the boundary it applies to.
- **Profile by Side.** A default Profile for each Side, for sites where the street side differs from the rest.

### Truss Tool

1. **Tools > Plug-ins > Plug-in Manager > Custom Plug-ins > New**
2. Name `Truss Tool`, type **Linear Object**.
3. **Edit Script**: set language to **Python**, then paste the contents of `vso_stub.py`.
4. **Properties > Options**: tick **Event-based plug-in** so the Object Info palette shows the group headings (Truss, Geometry, Timber, Soffit, Outriggers, Display, Classes, About). The layout, order and labels come from `LAYOUT` and `LABELS` in `truss_tool.py`, not the Plug-in Manager order or display names. Without it the tool still works, just without headings.
5. **Parameters**: add these exactly (Name and Type matter; the palette label is set by the code).

| Name | Palette label | Type | Default |
|---|---|---|---|
| **Truss** | | | |
| TrussType | Truss Type | Pop-Up: `Rafter Truss (T)` / `Girder Truss (G)` / `Truncated Rafter Truss (TR)` / `Truncated Girder Truss (TG)` / `Gable End Truss (GE)` / `Jack Truss (J)` / `Truncated Jack Truss (TJ)` / `Half Truss (H)` / `Saddle or Valley Truss (S/V)` / `Scissor Truss (SC)` / `Vaulted Truss (VT)` / `Attic Truss (AT)` / `Hip End (HE)` / `Valley Set (VS)` | Rafter Truss (T) |
| IDNumber | ID Number | Text | 1 |
| ID | ID | Text | (automatic) |
| **Geometry** | | | |
| LineLength | Span | Dimension (built in) | 8000 |
| Pitch | Roof Pitch | Angle (or Number) | 25 |
| TwoPitch | Two Pitches | Boolean | False |
| PitchRight | Pitch (Right) | Angle (or Number) | 30 |
| Elevation | Elevation | Dimension | 0 (older trusses only; use the object's Z) |
| HeelHeight | Heel Height | Dimension | 0 (automatic unless Heel Override) |
| HeelHeightRight | Heel (Right) | Dimension | 0 (automatic unless Heel Override) |
| HeelOverride | Heel Override | Boolean | False |
| Overhang | Overhang | Dimension | 450 |
| TwoOverhangs | Two Overhangs | Boolean | False |
| OverhangLeft | Overhang (L) | Dimension | 0 |
| OverhangRight | Overhang (R) | Dimension | 0 |
| WebPattern | Web Pattern | Pop-Up: `4 Web` / `King Post` | 4 Web |
| HalfValley | Half Valley | Boolean | False |
| HighEnd | High End | Pop-Up: `Right` / `Left` | Right |
| Girder | Girder | Pop-Up: `1 Ply` / `2 Ply` / `3 Ply` | 2 Ply |
| WebCentres | Web Centres | Dimension | 0 (1200 girders, 600 gable / valley) |
| AutoOverride | Override Auto | Boolean | False |
| Setback | Setback | Dimension | 0 (automatic) |
| TrussSpacing | Spacing | Dimension | 900 |
| Flip | Flip | Boolean | False |
| HalfAssembly | Half | Boolean | False |
| HalfSide | Side | Pop-Up: `Left` / `Right` | Left |
| CeilingPitch | Ceiling Pitch | Angle (or Number) | 0 (automatic: half the roof pitch) |
| CoveLength | Cove Length | Dimension | 0 (quarter span) |
| CoveGauge | Cove Gauge | Dimension | 190 |
| AtticWidth | Attic Width | Dimension | 0 (half span) |
| CollarHeight | Collar Height | Dimension | 2400 |
| **Timber** | | | |
| Thickness | Thickness | Dimension | 45 |
| TopChord | Top Chord | Dimension | 90 |
| BottomChord | Bottom Chord | Dimension | 90 |
| WebGauge | Webs | Dimension | 70 |
| **Soffit** | | | |
| SoffitBearerSides | Bearers | Pop-Up: `Both` / `Left` / `Right` / `None` | Both |
| SoffitBearerGauge | Bearer Gauge | Dimension | 90 |
| SoffitDrop | Bearer Drop | Dimension | 0 |
| **Outriggers (Gable End)** | | | |
| Outriggers | Outriggers | Boolean | True |
| OutriggerGauge | Gauge | Dimension | 90 |
| OutriggerCentre | Centres | Dimension | 900 |
| OverhangSoffit | Verge | Dimension | 450 |
| DistanceFirstTruss | Back Span | Dimension | 900 |
| OutriggerPlan | Plan Display | Pop-Up: `Solid` / `Line` | Line |
| **Display** | | | |
| PlanDisplay | Plan Display | Pop-Up: `Centre Line` / `Outline` / `None` | Centre Line |
| **Classes** | | | |
| Status | Status | Pop-Up: `Proposed` / `Existing` / `Demolish` | Proposed |
| ClassTruss | Truss | Text | Roof-Truss-{Status}-Object |
| ClassOutrigger | Outrigger | Text | Roof-Truss-{Status}-Outrigger |
| ClassSoffit | Soffit Bearer | Text | Roof-Truss-{Status}-Soffit |
| ClassHip | Hip / Valley | Text | Roof-Truss-{Status}-Hip |
| **About** | | | |
| Version | Version | Text | (automatic) |
| Author | Author | Text (not Integer) | (automatic, not shown) |
| Website | Website | Text | (automatic, not shown) |
| Notice | Note | Text | (automatic, not shown; goes in the IFC description) |

The palette layout, order and labels come from `LAYOUT` and `LABELS` in `truss_tool.py`, so the order in the Plug-in Manager does not matter.

6. Add the tool to your workspace, draw one, and check it.

#### Truss Tool: Truss Type order

Set the TrussType pop-up choices in this order (most used first):

`Rafter Truss (T)`, `Girder Truss (G)`, `Gable End Truss (GE)`, `Half Truss (H)`, `Jack Truss (J)`, `Truncated Rafter Truss (TR)`, `Truncated Girder Truss (TG)`, `Truncated Jack Truss (TJ)`, `Scissor Truss (SC)`, `Vaulted Truss (VT)`, `Attic Truss (AT)`, `Saddle or Valley Truss (S/V)`, `Hip End (HE)`, `Valley Set (VS)`
