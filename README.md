# Parallel Tools

Python scripted tools for Vectorworks, made to assist office workflow and close gaps in the official software.

## Tools (coming soon)

The tools are in use and testing in our office and will be added here shortly.

| Tool | What it does |
|---|---|
| **Comment Tool** | Drawing review comments: an outline (line, revision cloud or pin), a leader and a tag. Colour by class instead of hardcoded red, Status (Open / Done / Closed), Type and Audience, one-click status changes, and a worksheet-ready comment list. A friendlier alternative to the Redline tool. |
| **Revision Tool** | Revision clouds with a marker and number, drawn on the sheet or in a viewport's annotations, with styles and a cloud offset round the object. |
| **Break Line Tool** | A break line as one linear object, sized on the sheet: straight, curved or arc breaks, single or double, with a mask behind. |
| **Planting Tool** | Hedges and planting beds as one 2D object: plants along a line or over an area, plant counts, fills, strokes and a shadow. |
| **HTB Tool** | Height to Boundary: the recession plane from a boundary by height at boundary and daylight angle (Standard, Alternative or Custom profiles). Points on the same side link up into one plane. |
| **Truss Tool** | Schematic timber roof trusses as one linear plug-in object, for documentation and visualisation: 14 truss types and assemblies. Terminology follows the MiTek NZ GANG-NAIL Residential Manual. |

Each tool will come with a README (setup and parameters) and a CHANGELOG.

## Installing

Every tool comes as a pair: a drawing tool (`.vst`) that places the object, and the object itself (`.vso`).

1. **Add them to your Plug-ins folder.** Download a zip from [Releases](https://github.com/itchyNZL/parallel-tools/releases): one per tool, or one with all of them. Each zip holds a `Parallel Tools` folder (the `.vso`, the `.vst` and each tool's code folder): copy it into your Vectorworks user Plug-ins folder, or a workgroup folder's `Plug-ins`, so the tools stay together and apart from other plug-ins. Adding another tool later? Copy its folder over the one already there. Restart Vectorworks.

   To find your user folder: Vectorworks Preferences > User Folders > Explore, then open `Plug-ins`.
2. **Add the drawing tools to your workspace.** Tools > Workspaces > Edit Current Workspace, Tools tab: drag the drawing tools below into a tool set. The objects don't need to be in the workspace: the drawing tools place them and you edit them in the Object Info palette.

| Drawing tool (add to your workspace) | Object it places | Tool bar |
|---|---|---|
| **Comment** | Comment Tool | Ellipse, Rectangle, Polygon, Freehand and Pin modes; Style; spanner |
| **Revision** | Revision Tool | Ellipse, Rectangle, Polygon and Freehand modes; Style; spanner |
| **BreakLine** | Break Line Tool | Style; spanner |
| **Planting** | Planting Tool | Line, Closed shape, Rectangle and Freehand modes; Style; spanner |
| **HTB** | HTB Tool | Style; Side; spanner |
| **Truss** | Truss Tool | Style; Type; spanner |

The spanner sets the default settings for new objects.

## Requirements

Tested on Windows 11 with Vectorworks 2027, and some with Vectorworks 2026. Not tested on Mac. If you hit a problem with a particular version or platform, please say which in [GitHub Issues](https://github.com/itchyNZL/parallel-tools/issues).

## Credits

### General

- **Vectorworks** (Vectorworks, Inc.): the Python plug-in system, scripting reference and developer forum that make these tools possible. Not affiliated with or endorsed by Vectorworks.
- **Jesse Cogswell**: his forum answer on custom tool and plug-in icons (light and dark, SVG) sorted out the tool icons.
- **The Vectorworks forum** threads on plug-in development:
  - [Custom tool and PIO icons](https://forum.vectorworks.net/topic/116204-custom-tool-and-pio-icons/)
  - [Event enabled noob questions](https://forum.vectorworks.net/topic/104429-event-enabled-noob-questions/)
  - [Plug-in and object events](https://forum.vectorworks.net/topic/108107-plug-in-and-object-events/)
  - [Python plug-in with widgets, basic example](https://forum.vectorworks.net/topic/81852-python-plug-in-with-widgets-basic-example/)
  - [Plug-in object control points, OIP and text handling](https://forum.vectorworks.net/topic/81778-plug-in-object-control-pts-oip-and-text-handling-qs/)
  - [Formatting PIO text on the fly](https://forum.vectorworks.net/topic/111781-formatting-pio-text-on-the-fly/)
  - [Adding mode bar buttons](https://forum.vectorworks.net/topic/126471-adding-mode-bar-buttons/) and [Adding button to the mode bar](https://forum.vectorworks.net/topic/43527-adding-button-to-the-mode-bar/)
  - [Change tool modes](https://forum.vectorworks.net/topic/19406-change-tool-modes/)
  - [There should be a button for plug-in options in the OIP](https://forum.vectorworks.net/topic/89343-there-should-be-a-button-for-plug-in-options-in-the-oip/)

### Specific tools

Each tool's README (added with the tool) credits the plug-ins that came before it and the forum threads that shaped it, with everyone who posted. In brief:

- **Comment Tool**: Vectorworks' Redline tool, and the Redline Wishlist threads.
- **Revision Tool**: a natural progression from Comment Tool, and the Revision Cloud Wishlist thread.
- **Break Line Tool**: Breaker by dbelfm, Break Poly by PanzerCAD, Vectorworks' Break Line tool, and six break line threads from 2006 on.
- **HTB Tool**: ht2boundary by Jonathan Pickup (ArchonCAD).
- **Truss Tool**: Schematic Wood Truss by David Hamer, John Greaney's truss plug-ins, and four roof truss threads.
- **Planting Tool**: the hedge threads.

## Feedback

Bug reports and feature suggestions: [GitHub Issues](https://github.com/itchyNZL/parallel-tools/issues).

Known issues are tracked in GitHub Issues too. **Check for updates...**, in the About section of each tool's Object Info, compares your version with the latest here.

## Disclaimer

Use at your own risk. The tools are provided as is, without warranty of any kind (see the LICENSE). Check what they draw before you issue it: they are documentation aids, not design or compliance tools. Truss Tool's trusses are schematic, not a truss design, and HTB Tool's recession planes don't replace checking the planning rules that apply to your site.

## Licence

MIT, see [LICENSE](LICENSE). Not affiliated with or endorsed by Vectorworks.
