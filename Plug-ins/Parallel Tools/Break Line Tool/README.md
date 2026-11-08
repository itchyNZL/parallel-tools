# Break Line Tool

A break line for Vectorworks as one linear object, sized on the printed sheet: straight, curved or arc breaks, one or more of them, single or double lines, with a mask behind. Rebuilt in Python from Breaker 11.51 by dbelfm.

By Ian Thrush / Parallel Architecture NZ. MIT licence, see [LICENSE.md](LICENSE.md). Installing: see the [main README](https://github.com/itchyNZL/parallel-tools#installing).

## What it does

- **Sized on the sheet.** Break width and height are in printed mm, so a break looks the same at 1:5 and 1:100 (in a viewport's annotations it follows the viewport's scale). Drawn Size shows what that is in the drawing, so there is no maths to do.
- **Three break shapes:** Straight (the classic zigzag), Curved or Arc.
- **Any number of breaks,** spaced evenly as a group that you slide along the line.
- **Double break lines** with a mask between them, or a single line with a mask on one side, to hide what's behind.
- **Snap to what's being broken:** the line runs past each end by a set amount.

## Drawing a break line

Use the **BreakLine** tool (Vectorworks already has a tool called Break Line). Click the start, then the end, snapping to what's being broken.

| Tool bar | What it does |
|---|---|
| **Style** | The break line style for new break lines, or `<Unstyled>`. |
| **Spanner** | Default Settings for new break lines: Style, Number of Breaks, Extend Past Ends, Break Width, Break Height, Double, Mask and Mask Depth. Blank or `(as the plug-in)` keeps the plug-in's own default, and a chosen style's values still win. Remembered for each user. |

## Editing a break line

### Object Info

| Setting | What it does |
|---|---|
| Length | The line's length. Changing it keeps the breaks at the same share of the line, so a centred break stays centred. |
| Extend Past Ends | How far the line runs past each end (a real size, in the file's units). |
| Style | **Straight**, **Curved** or **Arc**. |
| Number of Breaks | Spaced evenly as a group round the near control point. 0 gives a plain line. |
| Break Width (sheet mm) | Along the line, on the printed sheet. 0 makes it as wide as it is high (Breaker's shape). |
| Break Height (sheet mm) | Either side of the line, on the printed sheet. |
| Arc Radius (sheet mm) | Rounds the foot of each break (Arc only). 0 gives a quarter of the width. |
| Drawn Size | The break as drawn, in the file's units, for example `W 10 x H 10 at 1:5` (read only). |
| Skew (deg) | Tilts the lines, pivoting on the first end. |
| Double Break Lines | A second line beside the first. |
| Mask Behind | Fills between the lines (or out to the mask depth) with the object's fill colour. |
| Mask Depth (sheet mm) | The depth of the mask, and how far apart double lines are. Negative puts it on the other side. Dragging the far control point sets it. |
| About | The tool's version, its GitHub page, and Check for updates.... |

Line weight and colour come from the class, as usual.

### Control points

- **Near:** on the line. Drag along the line to slide the breaks.
- **Far:** on the second line, or the far edge of the mask. Drag along the line to slide the second line's breaks clear of the first; drag across it to set the gap, on either side.

## Styles

Break lines support plug-in styles. A style holds the look: Extend Past Ends, Style, Break Width, Break Height, Arc Radius, Double Break Lines and Mask Behind. Length, Number of Breaks, Skew, Mask Depth and the control points stay with each break line.

## Credits

With thanks to the tools and people that inspired this one. The general credits for all the tools (Vectorworks, and the forum threads on plug-in development) are in the main README.

### Inspiration

- **Breaker** 11.51 by dbelfm: rebuilt in Python from it, keeping its shape and the mask behind the breaks.
- **Break Poly** by PanzerCAD: an earlier break plug-in used in the office.
- **Vectorworks' Break Line tool**: the built-in version, and the reason this tool's drawing tool is called BreakLine.

### Vectorworks forum

The requests, ideas and answers in these threads shaped this tool. Thanks to everyone who posted:

- [A better Break Line](https://forum.vectorworks.net/topic/14877-a-better-break-line/) (2006): Christiaan, CipesDesign, JC, P Retondo, Ken, islandmon, rDesign
- [Trim to break line](https://forum.vectorworks.net/topic/32415-trim-to-break-line/) (2011): mac@stairworks, bcd, bc, Matt Panzer
- [Break line trim](https://forum.vectorworks.net/topic/40507-break-line-trim/) (2014): VincentCuclair, Kevin McAllister, zoomer, Benson Shaw, bc, Patrick Fritsch, Matt Panzer, Gilbert Osmond, lgoodkind, Jim Smith, Wesley Burrows, Matt Overton, Taproot
- [Break Line Tool](https://forum.vectorworks.net/topic/43898-break-line-tool/) (2016): jmartinarch, Benson Shaw, bc
- [Enhance break line tools](https://forum.vectorworks.net/topic/58546-enhance-break-line-tools/) (2018): Ross Harris, rDesign, twk, BG, Jonathan Pickup, Matt Panzer, Patrick Fritsch, Boh, bc
- [Break Line Tool Defaults](https://forum.vectorworks.net/topic/64386-break-line-tool-defaults/) (2019): JMSarch, markdd, Taproot, Boh, domer1322, Virginia O, Andy Broomell
