#!/usr/bin/env python3
"""
Thumbnail grid with Mac OS X Dock-style hover magnification (PySide6).

A starting skeleton: a QGraphicsScene grid of jpg thumbnails where each
thumbnail smoothly grows when the mouse hovers over it. It is built on
QGraphicsObject so that position and scale can both be animated with
QPropertyAnimation -- the same machinery you'll reuse to add the
"slide-to-make-room" drag reordering later (see notes at the bottom).

Usage:
    python thumbnail_grid.py [path/to/folder/of/jpgs]

If no folder is given -- or the folder contains no images -- the app fills
the grid with generated placeholder tiles so it runs out of the box.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPixmap, QPainter, QPainterPath, QColor, QBrush, QPen, QLinearGradient,
)
from PySide6.QtWidgets import (
    QApplication, QGraphicsObject, QGraphicsScene, QGraphicsView,
)

# ---- Tunable constants -----------------------------------------------------
THUMB_SIZE = 140       # px, width & height of each thumbnail
GRID_SPACING = 24      # px, gap between thumbnails
COLUMNS = 4            # thumbnails per row
HOVER_SCALE = 1.18     # how much a thumbnail grows on hover
ANIM_MS = 160          # hover animation duration, milliseconds
CORNER_RADIUS = 10     # rounded-corner radius for thumbnails


class ThumbnailItem(QGraphicsObject):
    """A single thumbnail that magnifies smoothly on hover.

    Subclasses QGraphicsObject (not QGraphicsPixmapItem) because
    QGraphicsObject is a QObject and therefore exposes `scale`, `pos`,
    `opacity`, etc. as animatable Qt properties -- which is what lets
    QPropertyAnimation drive them.
    """

    def __init__(self, pixmap: QPixmap, size: int = THUMB_SIZE):
        super().__init__()
        self._size = size
        # Scale the source pixmap once, smoothly, to fill the square.
        self._pixmap = pixmap.scaled(
            size, size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )

        self.setAcceptHoverEvents(True)
        # Grow from the centre, like the Dock -- not from the top-left corner.
        self.setTransformOriginPoint(size / 2, size / 2)

        # One reusable animation that drives the `scale` property.
        self._anim = QPropertyAnimation(self, b"scale", self)
        self._anim.setDuration(ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

    # -- required QGraphicsItem interface ------------------------------------
    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._size, self._size)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = self.boundingRect()

        # Clip to rounded corners for soft edges.
        path = QPainterPath()
        path.addRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)
        painter.setClipPath(path)

        # Centre-crop the (expanded) pixmap into the square.
        px = self._pixmap
        x = (rect.width() - px.width()) / 2
        y = (rect.height() - px.height()) / 2
        painter.drawPixmap(int(x), int(y), px)

        # Subtle 1px border on top of the clip.
        painter.setClipping(False)
        painter.setPen(QPen(QColor(0, 0, 0, 50), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(
            rect.adjusted(0.5, 0.5, -0.5, -0.5), CORNER_RADIUS, CORNER_RADIUS
        )

    # -- hover magnification --------------------------------------------------
    def hoverEnterEvent(self, event):
        self.setZValue(1)               # draw above neighbours while enlarged
        self._animate_to(HOVER_SCALE)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._animate_to(1.0)
        super().hoverLeaveEvent(event)

    def _animate_to(self, target_scale: float):
        self._anim.stop()
        self._anim.setStartValue(self.scale())
        self._anim.setEndValue(target_scale)
        self._anim.start()

    def _on_anim_finished(self):
        # Drop back behind neighbours only once fully shrunk.
        if self.scale() <= 1.0001:
            self.setZValue(0)


class ThumbnailGrid(QGraphicsView):
    """A scrollable QGraphicsView laying thumbnails out in a grid."""

    def __init__(self, pixmaps, columns: int = COLUMNS):
        super().__init__()
        self._columns = columns
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        )
        self.setBackgroundBrush(QColor("#1e1e1e"))
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._items = []
        cell = THUMB_SIZE + GRID_SPACING
        for index, pm in enumerate(pixmaps):
            row, col = divmod(index, columns)
            item = ThumbnailItem(pm)
            item.setPos(GRID_SPACING + col * cell, GRID_SPACING + row * cell)
            self._scene.addItem(item)
            self._items.append(item)

        rows = (len(pixmaps) + columns - 1) // columns
        self._scene.setSceneRect(
            0, 0,
            GRID_SPACING + columns * cell,
            GRID_SPACING + max(rows, 1) * cell,
        )


# ---- Image loading / placeholders ------------------------------------------
def load_pixmaps(folder, count_if_empty: int = 12):
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
    view.setWindowTitle("Thumbnail Grid \u2014 hover to magnify")
    view.resize(
        GRID_SPACING + COLUMNS * (THUMB_SIZE + GRID_SPACING) + 24, 700
    )
    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


# ============================================================================
# NEXT STEP: drag-to-reorder with Dock-style sliding
# ----------------------------------------------------------------------------
# The pieces above are deliberately the foundation for the reorder. To extend:
#
#   1. In ThumbnailItem, store its grid index and accept mouse events. On
#      mousePressEvent record the grab; on mouseMoveEvent call setPos() to
#      follow the cursor and raise its Z so it floats above the others.
#
#   2. As the dragged item moves, compute which slot the cursor is over
#      (cursor_x // cell, cursor_y // cell). When that target slot changes,
#      reorder your backing list and re-assign every *other* item's target
#      grid position.
#
#   3. Animate the others into their new slots by giving each its own
#      QPropertyAnimation on b"pos" and starting them together inside a
#      QParallelAnimationGroup -- that synchronised slide is the Dock feel.
#
#   4. On mouseRelease, animate the dragged item's pos into its final slot
#      and reset Z-values.
#
# Keep the easing curve consistent (OutCubic here) so hover and reorder
# motion feel like one system.
# ============================================================================
