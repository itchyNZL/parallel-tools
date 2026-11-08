# Revision Tool

Drawing revisions for Vectorworks as one object: a revision cloud round the change, a leader, a marker (triangle, circle, square or hexagon) with the revision, and the date and note beside it. It replaces the Revision Cloud object, its record, a Data Tag and the class set-up, and it writes the sheet's revisions into the title block.

By Ian Thrush / Parallel Architecture NZ. MIT licence, see [LICENSE.md](LICENSE.md). Installing: see the [main README](https://github.com/itchyNZL/parallel-tools#installing).

## What it does

- **One object per change.** Cloud, marker, date and note can't drift apart. Three Rev A changes on a sheet are three revisions, each with its own note.
- **Colour from the class.** Each revision goes in `Revision-A`, `Revision-B` and so on. Classes that already exist are used as they are; new ones start dashed, 0.25 mm, A red, B blue, C green and so on, `#` green.
- **One date per revision per sheet.** Every Rev A on sheet A21 has the same date: change it on one and the others follow. Rev A on A22 keeps its own date.
- **Older revisions in grey.** The latest 2 revisions on each sheet (by date) are in colour; older ones are grey with a thin line.
- **`#` for a new sheet** added after the original issue (for example with an RFI response): the note starts as "New sheet".
- **Title block:** one button writes the sheet's revisions into its title block.

## Drawing a revision

Draw on the **sheet layer** (simplest) or in a **viewport's annotations**. In annotations, sizes follow the viewport's scale and the revision counts with the sheet's other revisions.

Use the **Revision** tool. Its tool bar has:

| Tool bar | What it does |
|---|---|
| **Rectangle**, **Ellipse** | Click one corner, then the opposite corner. |
| **Polygon** | Click each corner, double-click to finish. |
| **Freehand** | Drag round the change. |
| **Style** | The revision style for new revisions, or `<Unstyled>`. |
| **Spanner** | Default Settings for new revisions: the Settings window below, and the default Offset. |

The **Revision dialog** then asks for:

- **Revision:** the first is A. After that a new revision starts on the last one you used. Typing a revision fills in the date it already has on this sheet.
- **Date** (dd/mm/yy): today, or the date this revision already has on this sheet.
- **Note:** what changed.
- **Show marker, date and note:** off draws just the cloud (for example several clouds for one change with one tag). It still has its revision and date.
- **Offset (sheet mm):** snap the outline to an object and the cloud is drawn this far outside it, on the printed sheet. The outline stays where you drew it.

## Editing a revision

**Double-click** a revision (or **Edit Revision...** in Object Info) to reopen the Revision dialog. Revision, Date and Note can also be changed in Object Info or a worksheet. A changed date goes to every revision with the same letter on the sheet, and a revision moved to another letter (or pasted onto another sheet) takes that letter's date there.

### Object Info

| Setting | What it does |
|---|---|
| Revision, Date, Note | As in the Revision dialog. |
| Show Marker and Text | Off: the cloud only. |
| Fixed Leader Start | Ticked when you drag the leader start along the cloud; untick to go back to the nearest point. |
| Offset (sheet mm) | How far the cloud sits outside the outline you drew. |
| Sheet | The sheet it is on (read only). |
| Drawn Size | The scale it was drawn at (read only). |
| Edit Revision... | The Revision dialog. |
| Settings... | The Settings window (below). |
| Refresh Sheet | Redraws the revisions on this sheet, for example after deleting one. It doesn't touch the title block. |
| Update Title Block... | Writes this sheet's revisions into its title block (below). |
| About | The tool's version, its GitHub page, and Check for updates.... |

### Settings window

Settings a revision rarely changes. A setting the revision's style controls is greyed.

| Group | Setting | What it does |
|---|---|---|
| Cloud | Outline | A revision cloud, or a plain line. |
| Cloud | Cloud size, Billow height | Scallop size and how far each scallop bulges, on the printed sheet. |
| Cloud | Offset | As in Object Info. |
| Marker | Shape, Size | Triangle, circle, square or hexagon, and its size on the sheet. |
| Leader | Show leader, Shoulder, Setback | The leader, the short level line before the marker, and the gap from the cloud. |
| Text | Show | Date and Note. |
| Text | Wrap (mm) | Wraps the note at this width. 0 is no wrap. Or drag the wrap control point. |
| Text | Line | Under the date: none, as long as the date, or to the end of the text. |
| Text | Note align | Auto (the marker's side), Left or Right. |
| Class | Template | `{Rev}` is replaced: `Revision-{Rev}` gives `Revision-A`. A live preview shows the result. |
| Class | Show latest | How many of a sheet's latest revisions are in colour (default 2; 0 shows them all in colour). One setting per sheet: change it on any revision and the rest of the sheet follows. |

### Control points

- **Knee:** where the leader meets the shoulder. Drag it to move the marker and text.
- **Wrap:** at the far end of the date and note. Drag it sideways to wrap the note at that width (5 mm at least).
- **Leader start:** where the leader leaves the cloud. Drag it along the cloud to fix it there; it stays on the cloud when the cloud is reshaped.

**Font and size:** select revisions and use Text > Format Text, as for any text. The revision letter is bold.

## Older revisions

Revisions are ordered by date on each sheet, so `#` and a Rev 1 after Rev C fall in place (on the same date, by letter). Adding, re-dating or moving a revision redraws the others on the sheet that change colour. Deleting one doesn't: press **Refresh Sheet** on any revision left on that sheet.

## Title block

**Update Title Block...** (Object Info, on any revision) writes the sheet's revisions into the Title Block Border on that sheet.

- One row per revision on the sheet, with its date, a description and a status: *new*, *date differs* or *in title block*. New ones and changed dates start ticked; untick a row to leave it out.
- **Description:** the title block's own if it already has that revision, otherwise the notes of every revision with that letter on the sheet, joined with "; ". Edit it to summarise.
- **By:** one entry for the rows written, remembered for next time.
- A revision already in the title block is updated in place, a new one is added, and revisions only in the title block are kept. All are written latest first, as the Title Block Manager stores them.
- **Set the title block's Numbering to Manual** (Title Block Manager > Document Options > Revision Data). On Auto-Increment the title block renumbers its revisions A, B, C itself, so a `#` would show as A. The dialog warns when it is on Auto.

## Styles

Revisions support plug-in styles. A style holds the look: Outline, Cloud size, Billow height, Marker shape and size, Show leader, Shoulder, Setback, Show date and note, Wrap, Line, Note align, Class template and Show latest. Revision, Date, Note, Offset and the marker position stay with each revision. Colour stays with the class, so one style works for every revision.

## Revision list worksheet

Database row criteria: `=DATABASE((PON='Revision Tool'))`.

| Column | Header | Formula |
|---|---|---|
| A | Sheet | `='Revision Tool'.'Sheet'` |
| B | Rev | `='Revision Tool'.'Rev'` |
| C | Date | `='Revision Tool'.'Date'` |
| D | Note | `='Revision Tool'.'Note'` |

Sort by Sheet, then Rev. Dates are stored ISO (2026-02-17) so they sort, and show as 17/02/26 on the sheet. Line breaks in Note show as `\n`.

## Limits

- No live preview of the marker while placing.
- Deleting a revision doesn't redraw the others on the sheet: use Refresh Sheet.

## Credits

With thanks to the tools and people that inspired this one. The general credits for all the tools (Vectorworks, and the forum threads on plug-in development) are in the main README.

### Inspiration

- **Comment Tool**: revisions were the natural next step from comments. The drawing modes, styles, sheet and viewport handling all came from it.
- **Vectorworks' revision clouds**: the starting point for the cloud.

### Vectorworks forum

The requests, ideas and answers in these threads shaped this tool. Thanks to everyone who posted:

- [Revision Cloud improvements](https://forum.vectorworks.net/topic/122778-revision-cloud-improvements/) (2025): Flair-Studio, Matt Overton, Jonathan Pickup, Tom W., EVM_CAD
- [Redline Tool list of improvements](https://forum.vectorworks.net/topic/125888-redline-tool-list-of-improvements/) (2025): Christiaan, Jonathan Pickup, grant_PD
- [Ability to set Class of Redline Tool](https://forum.vectorworks.net/topic/51280-ability-to-set-class-of-redline-tool/) (2017): Christiaan, markdd, heavy manners, Pat Stanford, E|FA
