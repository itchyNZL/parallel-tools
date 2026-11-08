# Parallel Tools

Python scripted tools for Vectorworks, made to assist office workflow and close gaps in the official software.

## Tools

In daily use in our office.

| Tool | What it does |
|---|---|
| **Comment Tool** | Drawing review comments: an outline (line, revision cloud or pin), a leader and a tag. Colour by class instead of hardcoded red, Status (Open / Done / Closed), Type and Audience, one-click status changes, and a worksheet-ready comment list. A friendlier alternative to the Redline tool. |
| **Revision Tool** | Revision clouds with a marker and number, drawn on the sheet or in a viewport's annotations, with styles and a cloud offset round the object. |
| **Break Line Tool** | A break line as one linear object, sized on the sheet: straight, curved or arc breaks, single or double, with a mask behind. |
| **Planting Tool** | Hedges and planting beds as one 2D object: plants along a line or over an area, plant counts, fills, strokes and a shadow. |
| **HTB Tool** | Height to Boundary: the recession plane from a boundary by height at boundary and daylight angle (Standard, Alternative or Custom profiles). Points on the same side link up into one plane. |
| **Truss Tool** | Schematic timber roof trusses as one linear plug-in object, for documentation and visualisation: 14 truss types and assemblies. Terminology follows the MiTek NZ GANG-NAIL Residential Manual. |

Each tool has a README (how to use it and its settings) and a CHANGELOG.

## Installing

Every tool comes as a pair: a drawing tool (`.vst`) that places the object, and the object itself (`.vso`).

1. **Add them to your Plug-ins folder.** Download a zip from [Releases](https://github.com/itchyNZL/parallel-tools/releases): one per tool, or one with all of them. Each zip holds a `Parallel Tools` folder (the `.vso`, the `.vst` and each tool's code folder): copy it into your Vectorworks user Plug-ins folder, or a workgroup folder's `Plug-ins`, so the tools stay together and apart from other plug-ins. Adding another tool later? Copy its folder over the one already there. Restart Vectorworks.

   To find your user folder: Vectorworks Preferences > User Folders > Explore, then open `Plug-ins`. By default it is `%APPDATA%\Nemetschek\Vectorworks\2027\Plug-ins` on Windows and `~/Library/Application Support/Vectorworks/2027/Plug-ins` on a Mac (use your version number).
2. **Add the drawing tools to your workspace.** Tools > Workspaces > Edit Current Workspace, Tools tab: find the drawing tools in the **Parallel Tools** category and drag them into a tool set. The objects don't need to be in the workspace: the drawing tools place them and you edit them in the Object Info palette.

| Drawing tool (add to your workspace) | Object it places | Tool bar |
|---|---|---|
| **Comment** | Comment Tool | Ellipse, Rectangle, Polygon, Freehand and Pin modes; Style; spanner |
| **Revision** | Revision Tool | Ellipse, Rectangle, Polygon and Freehand modes; Style; spanner |
| **BreakLine** | Break Line Tool | Style; spanner |
| **Planting** | Planting Tool | Line, Closed shape, Rectangle and Freehand modes; Style; spanner |
| **HTB** | HTB Tool | Style; Side; spanner |
| **Truss** | Truss Tool | Style; Type; spanner |

The spanner sets the default settings for new objects.

No template, record or class set-up is needed: each tool makes the classes it uses the first time it draws.

### Example file

[`parallel-tools examples v27.vwx`](parallel-tools%20examples%20v27.vwx), also on the [Releases](https://github.com/itchyNZL/parallel-tools/releases) page, has examples of each tool, a comment list worksheet and a data tag for HTB Tool, ready to copy into your own files. It is saved in Vectorworks 2027, so it won't open in 2026. Install the tools first, or the objects in it can't be edited.

### Downloading

No GitHub account is needed. For just the tools, download a zip from [Releases](https://github.com/itchyNZL/parallel-tools/releases) (it holds only what the tools need to run). To review everything (code, each tool's README and changelog, icons and the plug-in scripts), use **Code > Download ZIP** on the repository page, or the **Source code** link on the release.

## Updating and uninstalling

- **Updating:** copy the new `Parallel Tools` folder over the old one, then restart Vectorworks. (Vectorworks picks up the code straight away, but the `.vso` and `.vst` only on restart.)
- **Uninstalling:** quit Vectorworks and delete the `Parallel Tools` folder, or just the tool's `.vso`, `.vst` and code folder. Each tool's default settings are in a small `..._prefs.json` file in `%APPDATA%\Nemetschek\Vectorworks` (on a Mac, `Nemetschek/Vectorworks` in your home folder): delete it too if you like.
- **Sharing files:** someone without the tools should see the objects as last drawn, but can't edit them until they install the tools.

## Requirements

Vectorworks 2026 or 2027. Tested on Windows 11 with Vectorworks 2027, and some with Vectorworks 2026; earlier versions and Mac have not been tested. No extra Python packages are needed: the tools use the Python built into Vectorworks. If you hit a problem with a particular version or platform, please say which in [GitHub Issues](https://github.com/itchyNZL/parallel-tools/issues).

### Made in New Zealand

The tools were made for our own work in Auckland, in metric (millimetre) files, so they follow New Zealand practice:

- **Units:** sizes on the printed sheet (cloud scallops, break sizes, tag widths and so on) are set in millimetres, even in an imperial file. The tools convert to the file's units when they draw, so an imperial file should come out at the right size, but this hasn't been tested.
- **HTB Tool:** the Standard profile works anywhere a rule is a height at the boundary then an angle, but the built-in Alternative profile is the Auckland Unitary Plan's.
- **Truss Tool:** truss types and names follow the MiTek NZ GANG-NAIL Residential Manual, and the default timber thickness is 45 mm.
- **Dates:** Revision Tool shows dates day first (17/02/26); worksheets get ISO dates (2026-02-17).

If you use them elsewhere, in imperial or under other rules, we'd like to hear how they work for you in [GitHub Issues](https://github.com/itchyNZL/parallel-tools/issues).

## Troubleshooting

- **A tool isn't in the Workspace Editor:** check the layout in your Plug-ins folder: `Parallel Tools` holding the tool's `.vso`, its `.vst` and its code folder side by side (for example `Comment Tool.vso`, `Comment.vst` and `Comment Tool`). Then restart Vectorworks.
- **"cannot find the ... folder":** the tool's code folder isn't next to its `.vso`. Copy the whole `Parallel Tools` folder from the zip again.
- **"needs to be event-enabled":** the `.vst` has been changed in the Plug-in Manager. Copy it from the zip again, or follow the steps in the message.
- **"an object could not be drawn":** the object is marked with a locus so you can find it. Please report it in [GitHub Issues](https://github.com/itchyNZL/parallel-tools/issues) with what you were doing.
- **Start the defaults again:** delete the tool's `..._prefs.json` file (see Uninstalling above).

## How they're made

I'm a designer, not a programmer. I don't know Python, but I know what I want from a tool, so I built these with Claude (Anthropic's AI) writing the code. I describe what the tool should do, test it in Vectorworks on our own projects, and keep refining it until it works the way we draw. I've learnt the rest along the way.

Ian Thrush, Parallel Architecture

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

Each tool's README credits the plug-ins that inspired it and the forum threads that shaped it, with everyone who posted. In brief:

- **Comment Tool**: Vectorworks' Redline tool, and the Redline Wishlist threads.
- **Revision Tool**: a natural progression from Comment Tool, and the Revision Cloud Wishlist thread.
- **Break Line Tool**: Breaker by dbelfm, Break Poly by PanzerCAD, Vectorworks' Break Line tool, and six break line threads from 2006 on.
- **HTB Tool**: ht2boundary by Jonathan Pickup (ArchonCAD).
- **Truss Tool**: Schematic Wood Truss by David Hamer, John Greaney's truss plug-ins, and four roof truss threads.
- **Planting Tool**: the hedge threads.

## Feedback

Bug reports and feature suggestions: [GitHub Issues](https://github.com/itchyNZL/parallel-tools/issues) (a free GitHub account is needed to post).

Known issues are tracked in GitHub Issues too. **Check for updates...**, in the About section of each tool's Object Info, compares your version with the latest here. It only connects when you click it, reads the list of versions on GitHub, and sends nothing else.

## Contributing

The tools are open source so they can get better together. Ideas, bug reports and fixes are welcome, in [GitHub Issues](https://github.com/itchyNZL/parallel-tools/issues) or as a pull request (see [DEVELOPMENT.md](DEVELOPMENT.md) for how the tools are built). If you improve a tool, please share it back here rather than releasing a separate copy, so everyone gets the fix. And please don't repackage the tools and sell them: they're free, and should stay that way.

## Disclaimer

Use at your own risk. The tools are provided as is, without warranty of any kind (see the LICENSE). Check what they draw before you issue it: they are documentation aids, not design or compliance tools. Truss Tool's trusses are schematic, not a truss design, and HTB Tool's recession planes don't replace checking the planning rules that apply to your site.

## Licence

MIT, see [LICENSE](LICENSE). Not affiliated with or endorsed by Vectorworks.
