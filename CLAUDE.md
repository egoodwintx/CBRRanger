# CLAUDE.md — CBRRanger

## Project Overview

A cross-platform desktop application for rearranging pages in digital comic book files (CBR/CBZ). The user opens a comic file, sees all pages as thumbnails in a grid, drags and drops pages to reorder them, and saves the result.

**Primary goal:** Simple, focused, reliable. This tool does one thing well.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| GUI Framework | PySide6 (Qt6 bindings) |
| Image Processing | Pillow (PIL) |
| CBZ support | `zipfile` (stdlib) |
| CBR support | `rarfile` + system `unrar` or `unar` |
| Packaging | PyInstaller (for distributable builds) |

### Why PySide6 over PyQt6
PySide6 is the official Qt binding maintained by The Qt Company, licensed under LGPL. This avoids any GPL licensing concerns for future distribution.

---

## Project Structure

```
CBRRanger/
├── CLAUDE.md                  # This file
├── README.md
├── requirements.txt
├── requirements-dev.txt
├── main.py                    # Entry point
├── src/
│   ├── __init__.py
│   ├── app.py                 # QApplication setup, main window init
│   ├── main_window.py         # MainWindow (QMainWindow subclass)
│   ├── thumbnail_grid.py      # ThumbnailGrid widget (QListWidget subclass)
│   ├── thumbnail_item.py      # ThumbnailItem (QListWidgetItem subclass)
│   ├── comic_file.py          # CBR/CBZ read/write logic (no GUI)
│   ├── image_loader.py        # Threaded thumbnail generation
│   └── utils.py               # Shared helpers
├── tests/
│   ├── __init__.py
│   ├── test_comic_file.py
│   ├── test_image_loader.py
│   └── fixtures/              # Small sample CBZ/CBR files for tests
└── assets/
    └── icon.png
```

---

## Architecture

### Separation of concerns
- **`comic_file.py`** — pure file I/O, no Qt imports. Handles all CBR/CBZ reading and writing. Testable without a display.
- **`image_loader.py`** — thumbnail generation via Pillow, runs in a `QThreadPool` to keep the UI responsive.
- **`thumbnail_grid.py`** — the main interactive widget; owns drag-and-drop reorder logic.
- **`main_window.py`** — orchestrates everything: menu bar, toolbar, status bar, wires signals/slots.

### Data flow
```
File on disk
  → comic_file.py: extract page bytes (in-memory, ordered list)
  → image_loader.py: decode bytes → Pillow Image → QPixmap (thumbnailed)
  → thumbnail_grid.py: display QListWidgetItems with QPixmap icons
  → user drags to reorder
  → thumbnail_grid.py: emits reordered page index list
  → comic_file.py: repack bytes in new order → write to disk
```

### Page representation
Pages are tracked as an **ordered list of raw bytes** (`list[bytes]`), not file paths. This keeps everything in memory and avoids temp file clutter. For very large comics (100+ pages at high resolution), this may need revisiting with lazy loading.

---

## Key Implementation Details

### CBZ (ZIP) — read
```python
import zipfile

def load_cbz(path: str) -> list[bytes]:
    with zipfile.ZipFile(path, 'r') as zf:
        names = sorted(n for n in zf.namelist() if is_image(n))
        return [zf.read(name) for name in names]
```

### CBR (RAR) — read
```python
import rarfile

def load_cbr(path: str) -> list[bytes]:
    with rarfile.RarFile(path, 'r') as rf:
        names = sorted(n for n in rf.namelist() if is_image(n))
        return [rf.read(name) for name in names]
```

### Image filtering
Only include image files; skip metadata files (`__MACOSX/`, `Thumbs.db`, `.DS_Store`, `ComicInfo.xml` — preserve separately):
```python
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}

def is_image(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTENSIONS and not name.startswith('__')
```

### Page sorting
Comic pages inside archives are not always stored in alphabetical order. Always sort by filename using **natural sort** (so `page10.jpg` comes after `page9.jpg`, not after `page1.jpg`):
```python
import re

def natural_sort_key(s: str) -> list:
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]
```

### Saving — always write as CBZ
Writing CBR requires the proprietary `rar` binary, which is not freely redistributable. Always save as CBZ (ZIP). Offer "Save as CBZ" if input was CBR — this is a lossless format change and universally supported.

```python
def save_cbz(path: str, pages: list[bytes], original_names: list[str]) -> None:
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for i, (data, orig_name) in enumerate(zip(pages, original_names)):
            ext = Path(orig_name).suffix
            zf.writestr(f"{i+1:04d}{ext}", data)
```

Rename pages sequentially on save (`0001.jpg`, `0002.jpg`, …) to ensure correct ordering in any reader regardless of metadata.

### Thumbnail generation (threaded)
Generate thumbnails in a `QRunnable` worker, emit a signal with `(index, QPixmap)` when done. Never generate thumbnails on the main thread.

```python
THUMBNAIL_SIZE = (180, 240)  # width, height in pixels
```

### ThumbnailGrid widget
Use `QListWidget` in `IconMode`:
```python
self.setViewMode(QListView.ViewMode.IconMode)
self.setIconSize(QSize(180, 240))
self.setResizeMode(QListView.ResizeMode.Adjust)
self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
self.setDefaultDropAction(Qt.DropAction.MoveAction)
self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
self.setUniformItemSizes(True)
self.setSpacing(8)
```

`InternalMove` drag-and-drop reordering works out of the box with `QListWidget`. No custom `dropEvent` needed for basic reordering.

### ComicInfo.xml preservation
If the archive contains a `ComicInfo.xml` file (ComicRack metadata), preserve it unchanged in the output archive. Do not include it in the page list or reorder it.

---

## UI Layout

```
┌─────────────────────────────────────────────────────┐
│  Menu: File | Edit | Help                           │
├─────────────────────────────────────────────────────┤
│  Toolbar: [Open] [Save] [Save As] | [Zoom -] [Zoom +]│
├─────────────────────────────────────────────────────┤
│                                                     │
│   ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐ ┌───┐             │
│   │   │ │   │ │   │ │   │ │   │ │   │             │
│   │ 1 │ │ 2 │ │ 3 │ │ 4 │ │ 5 │ │ 6 │  ...        │
│   └───┘ └───┘ └───┘ └───┘ └───┘ └───┘             │
│                                                     │
│   (drag and drop to reorder)                        │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Status: "Loaded 24 pages from my_comic.cbz"        │
└─────────────────────────────────────────────────────┘
```

### Menu structure
```
File
  Open...             Ctrl+O
  ─────────────────
  Save                Ctrl+S
  Save As...          Ctrl+Shift+S
  ─────────────────
  Quit                Ctrl+Q

Edit
  Select All          Ctrl+A
  ─────────────────
  Move to Front
  Move to Back
  ─────────────────
  Undo                Ctrl+Z
  Redo                Ctrl+Y

Help
  About
```

---

## Undo/Redo

Implement a simple undo stack using `QUndoStack`. Each drag-and-drop reorder pushes a `ReorderCommand` onto the stack. Keep it lightweight — just store the before/after page index ordering (not the image data itself).

```python
class ReorderCommand(QUndoCommand):
    def __init__(self, grid: ThumbnailGrid, old_order: list[int], new_order: list[int]):
        ...
    def undo(self): self.grid.apply_order(self.old_order)
    def redo(self): self.grid.apply_order(self.new_order)
```

---

## Unsaved Changes Tracking

- Track a `dirty` flag (set to `True` on any reorder, `False` after save).
- Show `*` in the window title when there are unsaved changes: `"my_comic.cbz* — Comic Reorder"`.
- Prompt to save on close if dirty.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| File not found | `QMessageBox.critical` with clear message |
| Corrupt ZIP/RAR | Show error, do not crash |
| `unrar`/`unar` not installed | Detect at startup; show a one-time warning that CBR support requires `unrar` to be installed |
| Save fails (permissions, disk full) | Show error, do not overwrite original until write succeeds (write to temp file first, then rename) |
| Empty archive / no images found | Show warning dialog |

### Safe save pattern
Always write to a temp file first, then atomically rename:
```python
import tempfile, os, shutil

def safe_save(target_path: str, pages: list[bytes], names: list[str]) -> None:
    dir_ = Path(target_path).parent
    with tempfile.NamedTemporaryFile(dir=dir_, delete=False, suffix='.cbz') as tmp:
        tmp_path = tmp.name
    try:
        save_cbz(tmp_path, pages, names)
        shutil.move(tmp_path, target_path)
    except Exception:
        os.unlink(tmp_path)
        raise
```

---

## Platform Notes

### Linux
- Install `unrar` or `unar` via package manager for CBR support.
- `rarfile` auto-detects which backend is available.
- Qt6 requires `libxcb` and related X11/Wayland libs — document in README.

### BSD (FreeBSD / OpenBSD)
- PySide6 may need to be built from ports or installed via `pip` with a compatible Qt6.
- `unrar` available via ports (`archivers/unrar`).
- Test on Wayland and X11.

### Windows / macOS (future)
- No extra steps for CBZ.
- On macOS, use `unar` (available via Homebrew) instead of `unrar`.
- Consider `.app` bundle (macOS) and `.exe` installer (Windows) via PyInstaller.

---

## Dependencies

### requirements.txt
```
PySide6>=6.6.0
Pillow>=10.0.0
rarfile>=4.1
```

### requirements-dev.txt
```
pytest>=7.0
pytest-qt>=4.3
black
ruff
```

### System dependencies (document in README)
- **CBR support:** `unrar` or `unar` must be installed separately
  - Debian/Ubuntu: `sudo apt install unrar`
  - Fedora: `sudo dnf install unrar`
  - FreeBSD: `pkg install unrar`
  - Arch: `sudo pacman -S unrar`

---

## Testing

- Unit test `comic_file.py` with small fixture ZIP files (no GUI needed).
- Use `pytest-qt` for widget tests.
- Test natural sort with edge cases: `page9`, `page10`, `page09`, mixed filenames.
- Test CBZ round-trip: load → reorder → save → reload → verify page order matches.
- Do **not** commit real copyrighted comic files; generate minimal test fixtures programmatically.

```python
# Generate a minimal test CBZ fixture
def make_test_cbz(path, num_pages=5):
    with zipfile.ZipFile(path, 'w') as zf:
        for i in range(num_pages):
            img = Image.new('RGB', (100, 150), color=(i*40, 100, 200))
            buf = io.BytesIO()
            img.save(buf, format='JPEG')
            zf.writestr(f"page{i+1:02d}.jpg", buf.getvalue())
```

---

## Development Conventions

- **Python style:** Black formatting, `ruff` for linting. Line length 100.
- **Qt signals/slots:** Always use the new-style signal syntax (`signal.connect(slot)`).
- **No business logic in widgets:** Keep `comic_file.py` and `image_loader.py` free of Qt imports where possible.
- **String literals:** Use f-strings. No `%` formatting.
- **Type hints:** Use throughout. Run `mypy` on `src/` before PRs.
- **No global state:** Pass dependencies explicitly; avoid module-level mutable state.

---

## Out of Scope (for now)

- Viewing/reading pages at full size (this is a *reorder* tool, not a reader)
- Editing page metadata or ComicInfo.xml fields
- Splitting or merging multiple comic files
- Converting between image formats
- PDF comic support
- Cloud sync or remote files
- Any mobile platform