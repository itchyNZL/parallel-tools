# Comment Tool

Drawing review comments for Vectorworks: an outline round the area (a line, a revision cloud or just a pin), a leader, and a tag with the comment. A friendlier alternative to the Redline tool, with comments coloured by class, a Status you can click through (Open, Done, Closed), and a comment list for a worksheet.

By Ian Thrush / Parallel Architecture NZ. MIT licence, see [LICENSE.md](LICENSE.md). Installing: see the [main README](https://github.com/itchyNZL/parallel-tools#installing).

## What it does

- **No hardcoded red.** A comment takes its colour from its class, one class per Status (for example `Notes-Comment-Internal-Open`). New classes start amber (Open), teal (Done) and warm grey (Closed); change them like any other class.
- **Status:** Open (comment made), Done (fixed, please check), Closed (checked). One click in Object Info changes every selected comment.
- **Type:** Fix, Note or Nice, so a reviewed sheet isn't all faults.
- **Audience:** Internal or Client, so client comments can go on their own classes and sheets.
- **Numbered and dated** automatically, with the sheet or layer it is on, ready for a worksheet.
- **Drag the tag** to where it reads best; the leader follows.

## Drawing a comment

Use the **Comment** tool. Its tool bar has:

| Tool bar | What it does |
|---|---|
| **Ellipse**, **Rectangle** | Click one corner, then the opposite corner. |
| **Polygon** | Click each corner, double-click to finish. |
| **Freehand** | Drag round the area. |
| **Pin** | Click the point, then where the note goes. A dot and a leader, no outline. |
| **Style** | The comment style for new comments, or `<Unstyled>`. |
| **Spanner** | Preferences (below). |

You are asked for the comment text when the comment is placed. To turn an existing shape into a comment, select it and use **Modify > Create Objects from Shapes**, then pick Comment Tool.

### Preferences (spanner)

- **New comments start as:** Type and Audience, and From and To (for example your initials in From).
- **Use:** Type and Audience. Turning one off hides it from Object Info, the Comment dialog and the tag.
- **Default Settings...:** the Comment Settings window (below), saved as the starting point for new comments.

## Editing a comment

**Double-click** a comment (or **Edit Comment...** in Object Info) to change its text, Status, Type, Audience, From and To.

### Object Info

| Section | Setting | What it does |
|---|---|---|
| Comment | From, To | Who made the comment, and who it is for. |
| Status | Open, Done, Closed | One-click buttons, applied to every selected comment. The current value is marked ● Open ●. Leaving Open stamps the Done date; reopening clears it. |
| Type | Fix, Note, Nice | As Status. |
| Audience | Internal, Client | As Status. Client comments end their tag header with "Client". |
| Tag | Prefix, Number | The number shown on the tag (for example #12). Blank gives the next number. |
| Tag | Drawn Size | The scale the comment was drawn at (read only). |
| Tag | Settings... | The Comment Settings window (below). |
| About | Version, website, Check for updates... | The tool's version, its GitHub page, and a check for a newer version. |

### Comment Settings window

Settings a comment rarely changes. A setting the comment's style controls is greyed.

| Group | Setting | What it does |
|---|---|---|
| Outline | Outline | **Line** (dashes from the class line type), **Cloud** (a revision cloud) or **None** (a pin dot). |
| Outline | Cloud (mm) | Scallop size on the printed sheet. 0 gives 6 mm. |
| Outline | Setback (mm) | Gap between the outline and the start of the leader. |
| Tag | Shoulder (mm) | The short level line between the leader and the text. |
| Tag | Tag width | Width of the text on the printed sheet. 0 gives 40 mm. Or drag the tag's end control point. |
| Tag | Show | Number, Date, From, To. |
| Tag | Closed header only | A Closed comment shows only its header line. |
| Tag | Tag line | Under the full width of the tag, or under the header only. |
| Numbering | Prefix | Text before the number (default #). |
| Numbering | Copies get | The number a copied comment takes: the next number, the next free after the copied one, or the lowest free. |
| Class | Template | The class the comment goes in. `{Audience}`, `{Status}` and `{Type}` are replaced, so `Notes-Comment-{Type}` colours by type instead. Blank uses the object's own class. A live preview shows the result. |
| Leader markers | Start, End (tag) | Markers from the Vectorworks marker picker. A start marker replaces the pin dot. |

### Control points

- **Tag:** moves the tag.
- **Tag end:** sets the tag width. Drag it past the tag to flip the tag to the other side.
- **Pin** (Pin mode): moves the point; the tag stays put.

**Font and size:** select comments and use Text > Format Text (Ctrl+Shift+T), as for any text.

## Classes

The first comment with a class template creates the whole set of classes (for example every Internal and Client, Open, Done and Closed class), so visibility can be set once. New classes are coloured by Status and lined by Audience:

| Status | Colour | RGB |
|---|---|---|
| Open | Bright amber | 200, 110, 0 |
| Done | Teal | 31, 122, 110 |
| Closed | Warm grey | 138, 133, 124 |

| Audience | Line | Weight (Open, Done) | Weight (Closed) |
|---|---|---|---|
| Internal | Dashed (the first plain dash line type in the file; solid if there is none) | 0.2 mm | 0.13 mm |
| Client | Solid | 0.35 mm | 0.18 mm |

With Audience not used, every class is lined as Internal. After a class is made it is yours: the tool never changes a class you have edited. Use `{Audience}` in the template (for example `Notes-Comment-{Audience}-{Status}`) to show only client comments on client sheets.

## Numbers, dates and location

- **Number:** one running number for the file. A duplicate or pasted copy gets a new number automatically; the original keeps its own. Gaps left by deleted comments are not filled, except that the highest number is used again if that comment is deleted.
- **Location:** filled in by the tool: the sheet number and title, or the layer name.
- **Dates** are ISO (2026-10-13) so they sort in a worksheet. The tool sets them: a date changed by hand goes back on the next redraw.

## Styles

Comments support plug-in styles. A style holds the shared settings: Outline, Cloud, Setback, Shoulder, what the tag shows, the class template, Use Type and Use Audience, the number prefix, Copies and Closed header only. Each comment keeps its own text, Status, Type, Audience, people, dates, number and tag position. Change the split in Edit Style (for example a "Client Markup" style with Audience set by the style to Client). A setting the style controls is left out of the Comment dialog and greyed in Object Info and Settings.

## Comment list worksheet

Database row criteria: Plug-in Object is `Comment Tool` (`=DATABASE((PON='Comment Tool'))`).

| Column | Header | Formula |
|---|---|---|
| A | No. | `='Comment Tool'.'Number'` |
| B | Location | `='Comment Tool'.'Location'` |
| C | Status | `='Comment Tool'.'Status'` |
| D | Type | `='Comment Tool'.'CommentType'` |
| E | Audience | `='Comment Tool'.'Audience'` |
| F | From | `='Comment Tool'.'From'` |
| G | To | `='Comment Tool'.'To'` |
| H | Comment | `='Comment Tool'.'Note'` |
| I | Created | `='Comment Tool'.'CreatedDate'` |
| J | Done | `='Comment Tool'.'DoneDate'` |

- Sort by No. or Created. Wrap text in the Comment column; line breaks show as `\n` (and a backslash as `\\`).
- Only open comments: add `& ('Comment Tool'.'Status'<>'Closed')`. Only client comments: `& ('Comment Tool'.'Audience'='Client')`. One person's: `& ('Comment Tool'.'To'='TL')`.

## Credits

With thanks to the tools and people that inspired this one. The general credits for all the tools (Vectorworks, and the forum threads on plug-in development) are in the main README.

### Inspiration

- **Vectorworks' Redline tool** and its other comment and markup tools: the starting point. The drawing modes and their icons follow Redline's.

### Vectorworks forum

The requests, ideas and answers in these threads shaped this tool. Thanks to everyone who posted:

- [Redline Tool list of improvements](https://forum.vectorworks.net/topic/125888-redline-tool-list-of-improvements/) (2025): Christiaan, Jonathan Pickup, grant_PD
- [Ability to set Class of Redline Tool](https://forum.vectorworks.net/topic/51280-ability-to-set-class-of-redline-tool/) (2017): Christiaan, markdd, heavy manners, Pat Stanford, E|FA
- [The Redline Tool Needs a Ton More Options in the Wrench n' Pencil Preferences Settings](https://forum.vectorworks.net/topic/126746-the-redline-tool-needs-a-ton-more-options-in-the-wrench-n-pencil-preferences-settings/) (2025): Anna Arbetter
- [Redline tool colours](https://forum.vectorworks.net/topic/120123-redline-tool-colours/) (2024): heavy manners
- [Redline tool leader line](https://forum.vectorworks.net/topic/122255-redline-tool-leader-line/) (2025): Jonk, AKieran
- [Redline font size by Text Style and Class](https://forum.vectorworks.net/topic/132112-redline-font-size-by-text-style-and-class/) (2026): Christiaan
