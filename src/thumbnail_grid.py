"""Thumbnail grid widget: displays pages and owns drag-and-drop reordering."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDragMoveEvent, QDropEvent, QIcon, QPainter, QPen, QPixmap, QUndoCommand
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QListWidgetItem

from src.image_loader import THUMBNAIL_SIZE
from src.thumbnail_item import PAGE_INDEX_ROLE, ThumbnailItem

ZOOM_FACTORS = (0.5, 0.65, 0.8, 1.0, 1.25, 1.5, 2.0)


class ThumbnailGrid(QListWidget):
    """Grid of page thumbnails with drag-and-drop reordering.

    Order is expressed as a list of original page indices, e.g. [2, 0, 1]
    means the page originally at index 2 is now first.
    """

    order_changed = Signal(list, list)  # old order, new order

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setIconSize(QSize(*THUMBNAIL_SIZE))
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setUniformItemSizes(True)
        self.setSpacing(8)
        self._zoom_index = ZOOM_FACTORS.index(1.0)
        self._drop_indicator_row = -1

    # --- page management -------------------------------------------------

    def set_pages(self, names: list[str]) -> None:
        """Replace contents with placeholder items for the given page names."""
        self.clear()
        placeholder = self._placeholder_icon()
        for index, name in enumerate(names):
            item = ThumbnailItem(index, name)
            item.setIcon(placeholder)
            self.addItem(item)

    def set_thumbnail(self, page_index: int, pixmap: QPixmap) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(PAGE_INDEX_ROLE) == page_index:
                item.setIcon(QIcon(pixmap))
                return

    def current_order(self) -> list[int]:
        return [self.item(row).data(PAGE_INDEX_ROLE) for row in range(self.count())]

    def apply_order(self, order: list[int]) -> None:
        """Rearrange items to the given page-index order. Does not emit order_changed."""
        if order == self.current_order():
            return
        items: dict[int, QListWidgetItem] = {}
        while self.count():
            item = self.takeItem(0)
            items[item.data(PAGE_INDEX_ROLE)] = item
        for page_index in order:
            self.addItem(items.pop(page_index))

    # --- reordering ------------------------------------------------------

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        super().dragMoveEvent(event)
        drop_pos = event.position().toPoint()
        drop_row = self.indexAt(drop_pos).row()
        if drop_row == -1:
            drop_row = self.count()
        self._drop_indicator_row = drop_row
        self.viewport().update()

    def dragLeaveEvent(self, event) -> None:
        super().dragLeaveEvent(event)
        self._drop_indicator_row = -1
        self.viewport().update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._drop_indicator_row >= 0 and self._drop_indicator_row <= self.count():
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor(66, 165, 245), 2))
            if self._drop_indicator_row < self.count():
                rect = self.visualItemRect(self.item(self._drop_indicator_row))
                y = rect.top()
            else:
                y = self.viewport().height()
            painter.drawLine(0, y, self.viewport().width(), y)

    def dropEvent(self, event: QDropEvent) -> None:
        self._drop_indicator_row = -1
        old_order = self.current_order()

        drop_pos = event.position().toPoint()
        index_at_drop = self.indexAt(drop_pos).row()

        if index_at_drop != -1:
            dragged_items = self.selectedItems()
            dragged_rows = sorted(self.row(item) for item in dragged_items)
            if index_at_drop in dragged_rows:
                self.viewport().update()
                return

            dragged_page_indices = [self.item(row).data(PAGE_INDEX_ROLE) for row in dragged_rows]
            remaining_page_indices = [page_index for page_index in old_order if page_index not in dragged_page_indices]

            new_order = []
            for i, page_index in enumerate(remaining_page_indices):
                if i == index_at_drop:
                    new_order.extend(dragged_page_indices)
                new_order.append(page_index)

            if index_at_drop >= len(remaining_page_indices):
                new_order.extend(dragged_page_indices)

            self.apply_order(new_order)
            self._select_pages(dragged_page_indices)
            self._animate_reordered_items(dragged_page_indices)
            self.order_changed.emit(old_order, new_order)
        self.viewport().update()

    def move_selected_to_front(self) -> None:
        self._move_selected(to_front=True)

    def move_selected_to_back(self) -> None:
        self._move_selected(to_front=False)

    def _move_selected(self, to_front: bool) -> None:
        rows = sorted(self.row(item) for item in self.selectedItems())
        if not rows:
            return
        old_order = self.current_order()
        selected = [old_order[row] for row in rows]
        rest = [page for row, page in enumerate(old_order) if row not in set(rows)]
        new_order = selected + rest if to_front else rest + selected
        if new_order == old_order:
            return
        self.apply_order(new_order)
        self._select_pages(selected)
        self._animate_reordered_items(selected)
        self.order_changed.emit(old_order, new_order)

    def _select_pages(self, page_indices: list[int]) -> None:
        wanted = set(page_indices)
        self.clearSelection()
        for row in range(self.count()):
            item = self.item(row)
            if item.data(PAGE_INDEX_ROLE) in wanted:
                item.setSelected(True)

    def _animate_reordered_items(self, page_indices: list[int]) -> None:
        """Briefly highlight reordered items to show they were moved."""
        affected_items = []
        for page_index in page_indices:
            for row in range(self.count()):
                item = self.item(row)
                if item.data(PAGE_INDEX_ROLE) == page_index:
                    affected_items.append(item)
                    item.setBackground(QColor(100, 150, 200, 80))
                    break

        def clear_highlight():
            for item in affected_items:
                item.setBackground(QColor(0, 0, 0, 0))

        QTimer.singleShot(200, clear_highlight)

    # --- zoom ------------------------------------------------------------

    def zoom_in(self) -> None:
        self._set_zoom(self._zoom_index + 1)

    def zoom_out(self) -> None:
        self._set_zoom(self._zoom_index - 1)

    def _set_zoom(self, index: int) -> None:
        index = max(0, min(index, len(ZOOM_FACTORS) - 1))
        if index == self._zoom_index:
            return
        self._zoom_index = index
        factor = ZOOM_FACTORS[index]
        self.setIconSize(QSize(int(THUMBNAIL_SIZE[0] * factor), int(THUMBNAIL_SIZE[1] * factor)))

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _placeholder_icon() -> QIcon:
        pixmap = QPixmap(*THUMBNAIL_SIZE)
        pixmap.fill(QColor(220, 220, 220))
        return QIcon(pixmap)


class ReorderCommand(QUndoCommand):
    """Undoable page reorder; stores index orderings only, not image data."""

    def __init__(self, grid: ThumbnailGrid, old_order: list[int], new_order: list[int]) -> None:
        super().__init__("Reorder pages")
        self._grid = grid
        self._old_order = list(old_order)
        self._new_order = list(new_order)

    def undo(self) -> None:
        self._grid.apply_order(self._old_order)

    def redo(self) -> None:
        self._grid.apply_order(self._new_order)
