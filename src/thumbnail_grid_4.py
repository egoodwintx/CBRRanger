#!/usr/bin/env python3
"""
Thumbnail grid with Mac OS X Dock-style interactions (PySide6).

* Hover a thumbnail -> it smoothly magnifies (grows from its centre).
* Drag a thumbnail -> it follows the cursor while the others slide aside
  (OutCubic) to open a gap.
* Drag near the top/bottom edge of a scrolled grid -> the view auto-scrolls
  and the dragged item stays pinned under the cursor.
* Drop -> the item settles into the gap with a gentle overshoot (OutBack).

All motion runs through QPropertyAnimation on QGraphicsObject properties
(`scale` for hover, `pos` for the slide/settle), so the effects share one
consistent feel.

Usage:
    python thumbnail_grid.py [path/to/folder/of/jpgs]

With no folder (or an empty one) the grid fills with placeholder tiles so it
runs out of the box.
"""

import sys
from pathlib import Path

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QTimer, QPropertyAnimation, QEasingCurve, QSize,
)
from PySide6.QtGui import (
    QPixmap, QPainter, QPainterPath, QColor, QBrush, QPen, QLinearGradient,
)
from PySide6.QtWidgets import (
    QApplication, QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsView,
    QWidget, QLabel, QVBoxLayout,
)

# ---- Tunable constants -----------------------------------------------------
THUMB_SIZE = 140       # px, width & height of each thumbnail
GRID_SPACING = 24      # px, gap between thumbnails
COLUMNS = 4            # thumbnails per row
HOVER_SCALE = 1.18     # how much a thumbnail grows on hover
HOVER_MS = 160         # hover animation duration, milliseconds
SLIDE_MS = 220         # neighbour slide duration, milliseconds
DROP_MS = 280          # final-drop settle duration, milliseconds
CORNER_RADIUS = 10     # rounded-corner radius for thumbnails

EDGE_ZONE = 60         # px from top/bottom edge that triggers auto-scroll
MAX_SCROLL_SPEED = 18  # px per tick at the very edge
SCROLL_INTERVAL_MS = 16  # auto-scroll tick (~60 fps)

EASING = QEasingCurve.OutCubic              # hover + neighbour slides
SETTLE_EASING = QEasingCurve(QEasingCurve.OutBack)   # final drop only
SETTLE_EASING.setOvershoot(1.2)             # default 1.70158; lower = subtler


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

        # Scale image to fit screen while maintaining aspect ratio
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
        # Center the window on screen
        x = (screen.width() - scaled_pixmap.width()) // 2 + screen.x()
        y = (screen.height() - scaled_pixmap.height()) // 2 + screen.y()
        self.move(x, y)

    def mousePressEvent(self, event):
        self.close()


class ThumbnailItem(QGraphicsObject):
    """A thumbnail that magnifies on hover and can be dragged to reorder.

    Subclasses QGraphicsObject (not QGraphicsPixmapItem) so that `scale`
    and `pos` are animatable Qt properties. ItemIsMovable lets Qt handle
    the cursor-follow math during a drag; we react to the movement to drive
    the reorder.
    """

    def __init__(self, pixmap: QPixmap, size: int = THUMB_SIZE):
        super().__init__()
        self._size = size
        self._grid = None              # set by the grid when added
        self._original_pixmap = pixmap  # full-size original for popup
        self._pixmap = pixmap.scaled(
            size, size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        self._was_dragged = False      # track if mouse moved during press

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setCursor(Qt.OpenHandCursor)
        # Grow from the centre, like the Dock -- not the top-left corner.
        self.setTransformOriginPoint(size / 2, size / 2)

        # Hover animation: drives `scale`.
        self._scale_anim = QPropertyAnimation(self, b"scale", self)
        self._scale_anim.setDuration(HOVER_MS)
        self._scale_anim.setEasingCurve(EASING)
        self._scale_anim.finished.connect(self._on_scale_finished)

        # Slide/settle animation: drives `pos`.
        self._pos_anim = QPropertyAnimation(self, b"pos", self)
        self._pos_anim.setEasingCurve(EASING)
        self._pos_target = None        # last commanded position target

    # -- required QGraphicsItem interface ------------------------------------
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

    # -- hover magnification --------------------------------------------------
    def hoverEnterEvent(self, event):
        self.setZValue(1)               # above neighbours while enlarged
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
        # Drop behind neighbours only once fully shrunk and not being dragged.
        if self.scale() <= 1.0001 and not (
            self._grid and self._grid.dragging is self
        ):
            self.setZValue(0)

    # -- slide / settle (used by the grid) ------------------------------------
    def animate_to_pos(self, target: QPointF, easing=EASING, duration=SLIDE_MS):
        if target == self._pos_target:
            return                      # already heading there; don't restart
        self._pos_target = target
        self._pos_anim.stop()
        self._pos_anim.setDuration(duration)
        self._pos_anim.setEasingCurve(easing)
        self._pos_anim.setStartValue(self.pos())
        self._pos_anim.setEndValue(target)
        self._pos_anim.start()

    # -- drag to reorder ------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._grid:
            self.setCursor(Qt.ClosedHandCursor)
            self._pos_anim.stop()       # take manual control of position
            self._pos_target = None
            self._grid.begin_drag(self)
        super().mousePressEvent(event)  # enables Qt's move tracking

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)   # Qt repositions us to follow the cursor
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
        popup = ImagePopup(self._original_pixmap)
        self._grid._popups.append(popup)
        popup.destroyed.connect(lambda: self._grid._popups.remove(popup) if popup in self._grid._popups else None)
        popup.show()


class ThumbnailGrid(QGraphicsView):
    """A scrollable grid of thumbnails that can be reordered by dragging."""

    def __init__(self, pixmaps, columns: int = COLUMNS):
        super().__init__()
        self._columns = columns
        self._cell = THUMB_SIZE + GRID_SPACING
        self._order = []               # items in current logical order
        self._dragging = None          # item being dragged, or None
        self._scroll_speed = 0         # signed px/tick for edge auto-scroll
        self._popups = []              # keep popup windows alive
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

        for index, pm in enumerate(pixmaps):
            item = ThumbnailItem(pm)
            item._grid = self
            item.setPos(self._slot_pos(index))
            self._scene.addItem(item)
            self._order.append(item)

        self._update_scene_rect()

    @property
    def dragging(self):
        return self._dragging

    # -- geometry helpers -----------------------------------------------------
    def _slot_pos(self, index: int) -> QPointF:
        row, col = divmod(index, self._columns)
        return QPointF(
            GRID_SPACING + col * self._cell,
            GRID_SPACING + row * self._cell,
        )

    def _target_index(self, item: ThumbnailItem) -> int:
        """Which slot the dragged item's centre is currently over."""
        center = item.pos() + QPointF(THUMB_SIZE / 2, THUMB_SIZE / 2)
        col = round((center.x() - GRID_SPACING - THUMB_SIZE / 2) / self._cell)
        row = round((center.y() - GRID_SPACING - THUMB_SIZE / 2) / self._cell)
        col = max(0, min(self._columns - 1, col))
        rows = (len(self._order) + self._columns - 1) // self._columns
        row = max(0, min(max(rows - 1, 0), row))
        index = row * self._columns + col
        return max(0, min(len(self._order) - 1, index))

    def _update_scene_rect(self):
        rows = (len(self._order) + self._columns - 1) // self._columns
        self._scene.setSceneRect(
            0, 0,
            GRID_SPACING + self._columns * self._cell,
            GRID_SPACING + max(rows, 1) * self._cell,
        )

    def _reflow(self, skip=None):
        """Animate every item (except `skip`) to its slot for its index."""
        for index, item in enumerate(self._order):
            if item is skip:
                continue
            item.animate_to_pos(self._slot_pos(index))

    # -- edge auto-scroll during drag -----------------------------------------
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)   # forwards to the item -> drag/reflow
        if self._dragging is not None:
            self._update_auto_scroll(event.position().y())

    def _update_auto_scroll(self, y: float):
        """Pick scroll direction/speed from how near the cursor is to an edge."""
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
        """While the cursor sits in an edge zone, scroll and follow along."""
        if self._dragging is None:
            self._scroll_timer.stop()
            return
        vbar = self.verticalScrollBar()
        before = vbar.value()
        vbar.setValue(before + self._scroll_speed)
        dy = vbar.value() - before
        if dy == 0:
            return                      # reached the top/bottom; nothing to do
        # Keep the dragged item pinned under the (stationary) cursor, then let
        # the reorder logic re-evaluate which slot it is now over.
        self._dragging.moveBy(0, dy)
        self.update_drag(self._dragging)

    # -- drag lifecycle (called by ThumbnailItem) -----------------------------
    def begin_drag(self, item: ThumbnailItem):
        self._dragging = item
        item.setZValue(2)              # float above hovered neighbours

    def update_drag(self, item: ThumbnailItem):
        target = self._target_index(item)
        current = self._order.index(item)
        if target != current:
            self._order.pop(current)
            self._order.insert(target, item)
            self._reflow(skip=item)    # slide the others out of the way

    def end_drag(self, item: ThumbnailItem):
        self._scroll_timer.stop()
        self._scroll_speed = 0
        index = self._order.index(item)
        # Settle into the gap with a gentle overshoot (OutBack), distinct from
        # the OutCubic slides of the neighbours.
        item.animate_to_pos(
            self._slot_pos(index), easing=SETTLE_EASING, duration=DROP_MS
        )
        self._dragging = None
        # Z resets to 0 once the item shrinks (see _on_scale_finished).

    def current_order(self):
        """The logical order as a list of items -- map back to your data."""
        return list(self._order)


# ---- Image loading / placeholders ------------------------------------------
def load_pixmaps(folder, count_if_empty: int = 24):
    pixmaps = []
    if folder:
        base = Path(folder)
        seen = set()
        for ext in ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG"):
            for f in sorted(base.glob(ext)):
                if f in seen:
                    continue
                seen.add(f)
                pm = QPixmap(str(f))
                if not pm.isNull():
                    pixmaps.append(pm)
    if not pixmaps:
        pixmaps = [make_placeholder(i) for i in range(count_if_empty)]
    return pixmaps


def make_placeholder(i: int) -> QPixmap:
    """Generate a colourful numbered tile so the app runs without images."""
    pm = QPixmap(THUMB_SIZE, THUMB_SIZE)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    hue = (i * 47) % 360
    grad = QLinearGradient(0, 0, THUMB_SIZE, THUMB_SIZE)
    grad.setColorAt(0, QColor.fromHsv(hue, 160, 230))
    grad.setColorAt(1, QColor.fromHsv((hue + 40) % 360, 180, 150))
    painter.fillRect(0, 0, THUMB_SIZE, THUMB_SIZE, QBrush(grad))
    painter.setPen(QPen(QColor(255, 255, 255, 230)))
    font = painter.font()
    font.setPointSize(28)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pm.rect(), Qt.AlignCenter, str(i + 1))
    painter.end()
    return pm


def main():
    app = QApplication(sys.argv)
    folder = sys.argv[1] if len(sys.argv) > 1 else None
    pixmaps = load_pixmaps(folder)

    view = ThumbnailGrid(pixmaps)
    view.setWindowTitle(
        "Thumbnail Grid \u2014 hover to magnify, drag to reorder"
    )
    view.resize(
        GRID_SPACING + COLUMNS * (THUMB_SIZE + GRID_SPACING) + 24, 640
    )
    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
