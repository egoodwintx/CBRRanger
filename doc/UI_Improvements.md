# CBRRanger UI Improvement Suggestions

## High Impact / Quick Wins

### 1. Page Numbers on Thumbnails
The most critical missing feature for a page reorder tool. There is no way to tell what position a page is currently in or was originally. A small label (current position, e.g. "3") should appear on each thumbnail. The `ThumbnailItem.paint()` method in `thumbnail_grid.py:118` has no text rendering at all.

### 2. Empty State Call-to-Action
The empty state is a plain black rectangle with only a tiny status bar message at the bottom. A centered icon + "Open a CBZ or CBR file to get started" message would be significantly friendlier. Ideally the window would also support drag-and-drop of files to open them directly.

### 3. Theme Split
The menu bar and toolbar render in Qt's light Fusion theme while the grid background is `#1e1e1e`. This light-bar / dark-canvas split looks unintentional. Either style the toolbar to match the dark background, or accept the contrast and add a clear visual separator.

---

## Medium Impact

### 4. Square Thumbnails for Portrait Content
The spec in CLAUDE.md calls for 180×240 (portrait), but the implementation uses a 140×140 square (`THUMB_SIZE = 140` in `thumbnail_grid.py`). Comic pages are almost always portrait. Square cells waste vertical space and distort the natural shape of the content.

### 5. Zoom / Column-Count Control
`zoom_in()`, `zoom_out()`, and `selectAll()` in `thumbnail_grid.py:387-401` are all empty stubs. Even a simple Ctrl+scroll or a toolbar slider to adjust the number of columns would be a meaningful usability improvement.

### 6. Toolbar Icons
The toolbar shows plain text only ("Open", "Save", "Save As"). Qt standard stock icons (`QStyle.StandardPixmap`) could replace or augment these at zero cost and make the toolbar look more polished.

---

## Lower Priority

### 7. Drag-and-Drop File Open
The empty canvas could accept a dragged `.cbz`/`.cbr` file, which is what users expect from modern desktop tools. This pairs naturally with the empty state call-to-action (#2).

### 8. Loading Placeholder Indicator
Gray solid rectangles as placeholders are indistinguishable from a grey-page comic. A subtle spinner or "..." text centered in the placeholder would signal that a thumbnail is still loading.

### 9. Original Page Number Badge
Beyond showing the current position, it can be useful to show the *original* page number (where it started before reordering) alongside the current one, so users can tell at a glance how much they have moved things around.
