"""Thumbnail grid with hover magnification and smooth drag-and-drop reordering."""

from __future__ import annotations

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QPropertyAnimation, QEasingCurve, Signal,
)
from PySide6.QtGui import (
    QPixmap, QPainter, QPainterPath, QColor, QBrush, QPen, QUndoCommand,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsView, QWidget, QLabel, QVBoxLayout,
)

from src.image_loader import decode_full_image

THUMB_SIZE = 140
GRID_SPACING = 24
COLUMNS = 4
HOVER_SCALE = 1.18
HOVER_MS = 160
SLIDE_MS = 220
DROP_MS = 280
CORNER_RADIUS = 10

EDGE_ZONE = 60
MAX_SCROLL_SPEED = 18
SCROLL_INTERVAL_MS = 16

EASING = QEasingCurve.OutCubic
SETTLE_EASING = QEasingCurve(QEasingCurve.OutBack)
SETTLE_EASING.setOvershoot(1.2)


class ImagePopup(QWidget):
    """Full-size image popup window that closes when clicked."""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Viewer")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel()
        label.setCursor(Qt.PointingHandCursor)
        layout.addWidget(label)

        self.setLayout(layout)

        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        max_width = int(screen.width() * 0.9)
        max_height = int(screen.height() * 0.9)

        scaled_pixmap = pixmap.scaled(
            max_width, max_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        label.setPixmap(scaled_pixmap)

        self.resize(scaled_pixmap.width(), scaled_pixmap.height())
        x = (screen.width() - scaled_pixmap.width()) // 2 + screen.x()
        y = (screen.height() - scaled_pixmap.height()) // 2 + screen.y()
        self.move(x, y)

    def mousePressEvent(self, event):
        self.close()


class ThumbnailItem(QGraphicsObject):
    """A thumbnail that magnifies on hover and can be dragged to reorder."""

    def __init__(self, page_index: int, pixmap: QPixmap, size: int = THUMB_SIZE):
        super().__init__()
        self._page_index = page_index
        self._size = size
        self._grid = None
        self._original_pixmap = pixmap
        self._pixmap = pixmap.scaled(
            size, size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        self._was_dragged = False

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setCursor(Qt.OpenHandCursor)
        self.setTransformOriginPoint(size / 2, size / 2)

        self._scale_anim = QPropertyAnimation(self, b"scale", self)
        self._scale_anim.setDuration(HOVER_MS)
        self._scale_anim.setEasingCurve(EASING)
        self._scale_anim.finished.connect(self._on_scale_finished)

        self._pos_anim = QPropertyAnimation(self, b"pos", self)
        self._pos_anim.setEasingCurve(EASING)
        self._pos_target = None

    def page_index(self) -> int:
        return self._page_index

    def update_pixmap(self, pixmap: QPixmap) -> None:
        self._original_pixmap = pixmap
        self._pixmap = pixmap.scaled(
            self._size, self._size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._size, self._size)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = self.boundingRect()

        path = QPainterPath()
        path.addRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
        painter.setClipPath(path)

        px = self._pixmap
        x = (rect.width() - px.width()) / 2
        y = (rect.height() - px.height()) / 2
        painter.drawPixmap(int(x), int(y), px)

        painter.setClipping(False)
        painter.setPen(QPen(QColor(0, 0, 0, 50), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            rect.adjusted(0.5, 0.5, -0.5, -0.5), CORNER_RADIUS, CORNER_RADIUS
        )

    def hoverEnterEvent(self, event):
        self.setZValue(1)
        self._scale_to(HOVER_SCALE)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._scale_to(1.0)
        super().hoverLeaveEvent(event)

    def _scale_to(self, target_scale: float):
        self._scale_anim.stop()
        self._scale_anim.setStartValue(self.scale())
        self._scale_anim.setEndValue(target_scale)
        self._scale_anim.start()

    def _on_scale_finished(self):
        if self.scale() <= 1.0001 and not (
            self._grid and self._grid.dragging is self
        ):
            self.setZValue(0)

    def animate_to_pos(self, target: QPointF, easing=EASING, duration=SLIDE_MS):
        if target == self._pos_target:
            return
        self._pos_target = target
        self._pos_anim.stop()
        self._pos_anim.setDuration(duration)
        self._pos_anim.setEasingCurve(easing)
        self._pos_anim.setStartValue(self.pos())
        self._pos_anim.setEndValue(target)
        self._pos_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._grid:
            self.setCursor(Qt.ClosedHandCursor)
            self._pos_anim.stop()
            self._pos_target = None
            self._grid.begin_drag(self)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self._grid and self._grid.dragging is self:
            self._was_dragged = True
            self._grid.update_drag(self)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        was_click = not self._was_dragged
        self._was_dragged = False

        if self._grid and self._grid.dragging is self:
            self._grid.end_drag(self)
            if was_click:
                self._show_image_popup()
        super().mouseReleaseEvent(event)

    def _show_image_popup(self):
        popup = ImagePopup(self._grid.full_pixmap(self._page_index))
        self._grid._popups.append(popup)
        popup.destroyed.connect(
            lambda: self._grid._popups.remove(popup)
            if popup in self._grid._popups
            else None
        )
        popup.show()


class ThumbnailGrid(QGraphicsView):
    """A scrollable grid of thumbnails with smooth drag-and-drop reordering."""

    order_changed = Signal(list, list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._columns = COLUMNS
        self._cell = THUMB_SIZE + GRID_SPACING
        self._items: list[ThumbnailItem] = []
        self._page_index_to_item: dict[int, ThumbnailItem] = {}
        self._page_bytes: dict[int, bytes] = {}
        self._dragging = None
        self._drag_start_order: list[int] = []
        self._scroll_speed = 0
        self._popups: list[QWidget] = []
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(SCROLL_INTERVAL_MS)
        self._scroll_timer.timeout.connect(self._auto_scroll_tick)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        )
        self.setBackgroundBrush(QColor("#1e1e1e"))
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)

    @property
    def dragging(self):
        return self._dragging

    def set_pages(self, names: list[str], pages: list[bytes] | None = None) -> None:
        """Initialize the grid with empty placeholder items.

        `pages` holds the raw, full-resolution bytes for each page so the
        click-to-view popup can decode them on demand; without it the popup
        falls back to the low-res thumbnail.
        """
        self._scene.clear()
        self._items.clear()
        self._page_index_to_item.clear()
        self._page_bytes = dict(enumerate(pages)) if pages is not None else {}

        for index, name in enumerate(names):
            pm = QPixmap(THUMB_SIZE, THUMB_SIZE)
            pm.fill(QColor(80, 80, 80))
            item = ThumbnailItem(index, pm)
            item._grid = self
            item.setPos(self._slot_pos(index))
            self._scene.addItem(item)
            self._items.append(item)
            self._page_index_to_item[index] = item

        self._update_scene_rect()

    def set_thumbnail(self, page_index: int, pixmap: QPixmap) -> None:
        if page_index in self._page_index_to_item:
            self._page_index_to_item[page_index].update_pixmap(pixmap)

    def full_pixmap(self, page_index: int) -> QPixmap:
        """Full-resolution pixmap for a page, decoded from the raw bytes.

        Falls back to the (low-res) thumbnail if the bytes are unavailable or
        cannot be decoded, so the popup always shows something.
        """
        item = self._page_index_to_item.get(page_index)
        data = self._page_bytes.get(page_index)
        if data is not None:
            try:
                return QPixmap.fromImage(decode_full_image(data))
            except Exception:
                pass  # fall back to the thumbnail below
        return item._original_pixmap if item is not None else QPixmap()

    def count(self) -> int:
        return len(self._items)

    def current_order(self) -> list[int]:
        return [item.page_index() for item in self._items]

    def apply_order(self, order: list[int]) -> None:
        """Rearrange items to the given page-index order."""
        if order == self.current_order():
            return
        new_items = [self._page_index_to_item[idx] for idx in order]
        self._items = new_items
        for index, item in enumerate(self._items):
            item.animate_to_pos(self._slot_pos(index))

    def _slot_pos(self, index: int) -> QPointF:
        row, col = divmod(index, self._columns)
        return QPointF(
            GRID_SPACING + col * self._cell,
            GRID_SPACING + row * self._cell,
        )

    def _target_index(self, item: ThumbnailItem) -> int:
        center = item.pos() + QPointF(THUMB_SIZE / 2, THUMB_SIZE / 2)
        col = round((center.x() - GRID_SPACING - THUMB_SIZE / 2) / self._cell)
        row = round((center.y() - GRID_SPACING - THUMB_SIZE / 2) / self._cell)
        col = max(0, min(self._columns - 1, col))
        rows = (len(self._items) + self._columns - 1) // self._columns
        row = max(0, min(max(rows - 1, 0), row))
        index = row * self._columns + col
        return max(0, min(len(self._items) - 1, index))

    def _update_scene_rect(self):
        rows = (len(self._items) + self._columns - 1) // self._columns
        self._scene.setSceneRect(
            0, 0,
            GRID_SPACING + self._columns * self._cell,
            GRID_SPACING + max(rows, 1) * self._cell,
        )

    def _reflow(self, skip=None):
        for index, item in enumerate(self._items):
            if item is skip:
                continue
            item.animate_to_pos(self._slot_pos(index))

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self._dragging is not None:
            self._update_auto_scroll(event.position().y())

    def _update_auto_scroll(self, y: float):
        height = self.viewport().height()
        if y < EDGE_ZONE:
            frac = min(1.0, (EDGE_ZONE - y) / EDGE_ZONE)
            self._scroll_speed = -max(1, round(MAX_SCROLL_SPEED * frac))
        elif y > height - EDGE_ZONE:
            frac = min(1.0, (y - (height - EDGE_ZONE)) / EDGE_ZONE)
            self._scroll_speed = max(1, round(MAX_SCROLL_SPEED * frac))
        else:
            self._scroll_speed = 0

        if self._scroll_speed != 0 and not self._scroll_timer.isActive():
            self._scroll_timer.start()
        elif self._scroll_speed == 0 and self._scroll_timer.isActive():
            self._scroll_timer.stop()

    def _auto_scroll_tick(self):
        if self._dragging is None:
            self._scroll_timer.stop()
            return
        vbar = self.verticalScrollBar()
        before = vbar.value()
        vbar.setValue(before + self._scroll_speed)
        dy = vbar.value() - before
        if dy == 0:
            return
        self._dragging.moveBy(0, dy)
        self.update_drag(self._dragging)

    def begin_drag(self, item: ThumbnailItem):
        self._dragging = item
        self._drag_start_order = self.current_order()
        item.setZValue(2)

    def update_drag(self, item: ThumbnailItem):
        target = self._target_index(item)
        current = self._items.index(item)
        if target != current:
            self._items.pop(current)
            self._items.insert(target, item)
            self._reflow(skip=item)

    def end_drag(self, item: ThumbnailItem):
        self._scroll_timer.stop()
        self._scroll_speed = 0
        index = self._items.index(item)
        item.animate_to_pos(
            self._slot_pos(index), easing=SETTLE_EASING, duration=DROP_MS
        )
        new_order = self.current_order()
        self._dragging = None
        if new_order != self._drag_start_order:
            self.order_changed.emit(self._drag_start_order, new_order)

    def move_selected_to_front(self) -> None:
        pass

    def move_selected_to_back(self) -> None:
        pass

    def selectAll(self) -> None:
        pass

    def zoom_in(self) -> None:
        pass

    def zoom_out(self) -> None:
        pass


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
