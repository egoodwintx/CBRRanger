"""Main application window: menus, toolbar, status bar, signal wiring."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QUndoStack
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from src import comic_file
from src.comic_file import ComicArchive, ComicFileError, EmptyArchiveError
from src.image_loader import ImageLoader
from src.thumbnail_grid import ReorderCommand, ThumbnailGrid

APP_NAME = "CBRRanger"
OPEN_FILTER = "Comic archives (*.cbz *.cbr *.zip *.rar);;All files (*)"
SAVE_FILTER = "Comic Book ZIP (*.cbz)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._comic: ComicArchive | None = None
        self._save_path: str | None = None  # current CBZ target; None until a CBR is saved as CBZ

        self._undo_stack = QUndoStack(self)
        self._undo_stack.cleanChanged.connect(self._update_title)

        self._grid = ThumbnailGrid(self)
        self._grid.order_changed.connect(self._on_order_changed)
        self.setCentralWidget(self._grid)

        self._loader = ImageLoader(self)
        self._loader.thumbnail_ready.connect(self._grid.set_thumbnail)
        self._loader.thumbnail_failed.connect(self._on_thumbnail_failed)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self.statusBar().showMessage("Open a CBZ or CBR file to begin")

        self.resize(1000, 700)
        self._update_title()
        self._update_actions()

    # --- UI construction --------------------------------------------------

    def _create_actions(self) -> None:
        self._open_action = QAction("&Open...", self)
        self._open_action.setShortcut(QKeySequence("Ctrl+O"))
        self._open_action.triggered.connect(self.open_file)

        self._save_action = QAction("&Save", self)
        self._save_action.setShortcut(QKeySequence("Ctrl+S"))
        self._save_action.triggered.connect(self.save)

        self._save_as_action = QAction("Save &As...", self)
        self._save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._save_as_action.triggered.connect(self.save_as)

        self._quit_action = QAction("&Quit", self)
        self._quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._quit_action.triggered.connect(self.close)

        self._select_all_action = QAction("Select &All", self)
        self._select_all_action.setShortcut(QKeySequence("Ctrl+A"))
        self._select_all_action.triggered.connect(self._grid.selectAll)

        self._move_front_action = QAction("Move to &Front", self)
        self._move_front_action.triggered.connect(self._grid.move_selected_to_front)

        self._move_back_action = QAction("Move to &Back", self)
        self._move_back_action.triggered.connect(self._grid.move_selected_to_back)

        self._undo_action = self._undo_stack.createUndoAction(self, "&Undo")
        self._undo_action.setShortcut(QKeySequence("Ctrl+Z"))

        self._redo_action = self._undo_stack.createRedoAction(self, "&Redo")
        self._redo_action.setShortcut(QKeySequence("Ctrl+Y"))

        self._zoom_in_action = QAction("Zoom +", self)
        self._zoom_in_action.setShortcut(QKeySequence("Ctrl+="))
        self._zoom_in_action.triggered.connect(self._grid.zoom_in)

        self._zoom_out_action = QAction("Zoom -", self)
        self._zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        self._zoom_out_action.triggered.connect(self._grid.zoom_out)

        self._about_action = QAction("&About", self)
        self._about_action.triggered.connect(self._show_about)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self._open_action)
        file_menu.addSeparator()
        file_menu.addAction(self._save_action)
        file_menu.addAction(self._save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self._quit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self._select_all_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._move_front_action)
        edit_menu.addAction(self._move_back_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self._about_action)

    def _create_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.addAction(self._open_action)
        toolbar.addAction(self._save_action)
        toolbar.addAction(self._save_as_action)
        toolbar.addSeparator()
        toolbar.addAction(self._zoom_out_action)
        toolbar.addAction(self._zoom_in_action)

    # --- file handling ----------------------------------------------------

    def open_file(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Comic", "", OPEN_FILTER)
        if path:
            self.load_comic(path)

    def load_comic(self, path: str) -> None:
        try:
            comic = comic_file.load_comic(path)
        except EmptyArchiveError as exc:
            QMessageBox.warning(self, "No pages found", str(exc))
            return
        except ComicFileError as exc:
            QMessageBox.critical(self, "Could not open file", str(exc))
            return

        self._comic = comic
        suffix = Path(path).suffix.lower()
        self._save_path = path if suffix in comic_file.ZIP_SUFFIXES else None
        self._undo_stack.clear()
        self._loader.cancel()
        self._grid.set_pages(comic.names)
        self._loader.load_thumbnails(comic.pages)
        self.statusBar().showMessage(f"Loaded {len(comic.pages)} pages from {Path(path).name}")
        self._update_title()
        self._update_actions()

    def save(self) -> None:
        if self._comic is None:
            return
        if self._save_path is None:
            # Input was CBR; saving requires choosing a CBZ target.
            self.save_as()
            return
        self._write(self._save_path)

    def save_as(self) -> None:
        if self._comic is None:
            return
        suggested = str(Path(self._comic.path).with_suffix(".cbz"))
        path, _ = QFileDialog.getSaveFileName(self, "Save As CBZ", suggested, SAVE_FILTER)
        if not path:
            return
        if not path.lower().endswith(".cbz"):
            path += ".cbz"
        self._write(path)

    def _write(self, path: str) -> None:
        assert self._comic is not None
        order = self._grid.current_order()
        pages = [self._comic.pages[i] for i in order]
        names = [self._comic.names[i] for i in order]
        try:
            comic_file.safe_save(path, pages, names, self._comic.comic_info)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", f"Could not save {path}:\n{exc}")
            return
        self._save_path = path
        self._undo_stack.setClean()
        self.statusBar().showMessage(f"Saved {len(pages)} pages to {Path(path).name}")
        self._update_title()

    # --- state ------------------------------------------------------------

    def _on_order_changed(self, old_order: list[int], new_order: list[int]) -> None:
        self._undo_stack.push(ReorderCommand(self._grid, old_order, new_order))

    def _on_thumbnail_failed(self, index: int, message: str) -> None:
        self.statusBar().showMessage(f"Could not render page {index + 1}: {message}")

    def _update_title(self, *_args) -> None:
        if self._comic is None:
            self.setWindowTitle(APP_NAME)
            return
        name = Path(self._save_path or self._comic.path).name
        star = "" if self._undo_stack.isClean() else "*"
        self.setWindowTitle(f"{name}{star} — {APP_NAME}")

    def _update_actions(self) -> None:
        loaded = self._comic is not None
        for action in (
            self._save_action,
            self._save_as_action,
            self._select_all_action,
            self._move_front_action,
            self._move_back_action,
        ):
            action.setEnabled(loaded)

    def _confirm_discard(self) -> bool:
        """Return True if it is safe to discard the current document."""
        if self._comic is None or self._undo_stack.isClean():
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            "The current file has unsaved changes. Save them?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            self.save()
            return self._undo_stack.isClean()
        return answer == QMessageBox.StandardButton.Discard

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br>"
            "Rearrange pages in CBR/CBZ comic book archives.<br><br>"
            "Drag and drop thumbnails to reorder, then save as CBZ.",
        )
