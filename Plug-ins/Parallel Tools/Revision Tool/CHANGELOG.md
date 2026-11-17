# Changelog

## 0.9.0 (2026-11-17)

- New: **Date format** in Settings, styles and the default settings: dd/mm/yy, d Mon yy, yyyy-mm-dd or mm/dd/yy. It is saved with the revision and its style, so it belongs to the drawing; a user's computer settings never change it ([#3](https://github.com/itchyNZL/parallel-tools/issues/3)).
- New: the date is entered as a **Day**, a **Month** picked by name and a **Year**, in the Revision dialog and in Object Info, so it can't be misread whatever date order you are used to. A day past the end of the month becomes its last day ([#3](https://github.com/itchyNZL/parallel-tools/issues/3)).
- New: **Font** and **Text size** in Settings, styles and the default settings. Blank and 0 leave Text > Format Text as before; a font or size set here wins over Format Text ([#2](https://github.com/itchyNZL/parallel-tools/issues/2)).
- Object Info: a note of more than one line is no longer shown there (use Edit Revision). A one-line note still is.
- Fix: Show Latest typed as `inf` raised an error.
- The plug-in object has new parameters (`DateFormat`, `DateDay`, `DateMonth`, `DateYear`, `FontName`, `FontSize`): replace `Revision Tool.vso` as well as the code. Existing revisions keep their dates and their look.

## 0.8.1 (2026-11-09)

- Issued for testing.
