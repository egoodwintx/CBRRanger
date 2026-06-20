# Drag and Drop Animation in PySide6


## Prompt

How do I make a seamless drag and drop experience with PySide6 similar to what you have on the iPhone screen where when I move an image between two other images the other images smoothly glide out to create room for the dragged image? I would like the image gallery on CBRRanger to snap to a grid when dropped.

## Overview

Creating a smooth drag-and-drop experience with animated visual feedback requires enhancing the default `QListWidget` behavior to smoothly animate items into their final positions when dropped.

## Recommended Approach

Override `dropEvent` in your `ThumbnailGrid` to:

1. **Determine the drop position** — calculate where the item will land in the reordered list
2. **Show a visual drop indicator** — display a gap or highlight during drag showing where the item will land
3. **Animate affected items** — use `QPropertyAnimation` on item geometry to smoothly transition items into their new positions

### Why This Approach

- **Minimal disruption** — Builds on existing `QListWidget` in IconMode, preserving current undo/redo logic
- **Familiar interaction** — Similar to iPhone home screen: items glide out of the way to make room
- **Maintainable** — ~80–100 lines of code, no architectural rewrites

### Alternative: QGraphicsView

Switching to `QGraphicsView` gives more animation control but requires:
- Rewriting the entire grid layout from scratch
- Reimplementing undo/redo integration
- Rebuilding the drag-drop system

**Only consider this if you need very sophisticated animation behaviors beyond item movement.**

## Implementation Strategy

### Phase 1: Enhanced Drop Event
- Override `dropEvent()` in `ThumbnailGrid`
- Calculate new page order from drop position
- Create `ReorderCommand` and push to undo stack
- Trigger animations for all affected items

### Phase 2: Visual Feedback During Drag
- Override `dragMoveEvent()` to show drop indicator
- Display a gap or highlight where the item will land
- Update indicator as cursor moves over items

### Phase 3: Animation on Drop
- Use `QPropertyAnimation` to animate item positions
- Animate one row/column at a time for smoothness
- Use `QSequentialAnimationGroup` if animating multiple items
- Duration: 150–200ms feels natural (not too fast, not sluggish)

## Key Implementation Details

### Detecting Drop Position

```python
def dropEvent(self, event):
    # Find the item at the drop location
    drop_pos = event.pos()
    index_at_drop = self.indexAt(drop_pos).row()
    # Reorder based on this index
```

### Animating Items

```python
from PySide6.QtCore import QPropertyAnimation, QSequentialAnimationGroup

animation_group = QSequentialAnimationGroup()
for item_index in affected_items:
    anim = QPropertyAnimation(item, b"geometry")
    anim.setDuration(150)
    anim.setEndValue(new_geometry)
    animation_group.addAnimation(anim)

animation_group.start()
```

### Visual Drop Indicator

Store a reference to a visual indicator (can be a thin line or highlighted region) and update its position in `dragMoveEvent()`.

## Testing

- Test dragging between different grid positions
- Verify animations complete before subsequent drags
- Ensure undo/redo still work correctly
- Check performance with 50+ page comics (may need to throttle animations)

## References

- PySide6 Drag and Drop: https://doc.qt.io/qt-6/dnd.html
- QPropertyAnimation: https://doc.qt.io/qt-6/qpropertyanimation.html
- QListWidget: https://doc.qt.io/qt-6/qlistwidget.html



## Gemini Output

Yes, absolutely — PySide6 has everything needed to replicate this. Here's how each feature maps:

- **Magnification on hover** — use `QGraphicsScene`/`QGraphicsView` with `QGraphicsItem` subclasses, and handle `hoverMoveEvent` to scale items via `setScale()` or `QTransform`. Neighbor scaling is just a distance calculation on sibling items.
- **Drag to reorder** — handle `mousePressEvent`, `mouseMoveEvent`, `mouseReleaseEvent` on items, or use Qt's built-in drag system. A floating "ghost" pixmap can follow the cursor via a temporary `QLabel` or overlay widget.
- **Gap animation** — animate item positions with `QPropertyAnimation` or `QTimeLine` when the drag target index changes.
- **Fixed grid** — lay items out at fixed intervals (`x = index * CELL_SIZE`) and animate them sliding to new positions on reorder.

Two reasonable approaches:

**`QGraphicsView` + `QGraphicsItem`** (recommended) — purpose-built for this kind of scene. Items are individually transformable, hoverable, and draggable with fine-grained control. Scaling and position animation are straightforward.

**`QWidget`-based** — use a `QHBoxLayout` with custom `QLabel` or `QFrame` widgets, override paint and mouse events. Simpler to start but fighting the layout engine for smooth animation gets messy.

The `QGraphicsView` route is the cleaner fit. Want me to generate the full Python/PySide6 code for the dock?


"""
macOS-style Dock in PySide6
----------------------------
Features:
  - Hover magnification with neighbour falloff
  - Drag to reorder with animated gap
  - Smooth QPropertyAnimation for all size/position changes
  - Fixed-size grid baseline

Requirements:
    pip install PySide6
"""

import sys
import math
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView,
    QGraphicsScene, QGraphicsItem, QGraphicsRectItem,
    QGraphicsTextItem, QWidget, QVBoxLayout,
)
from PySide6.QtCore import (
    Qt, QPointF, QRectF, QPropertyAnimation,
    QEasingCurve, QObject, Property, QTimer,
)
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont,
    QLinearGradient, QPixmap, QCursor,
)


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
CELL      = 64          # grid cell width (spacing between icon centres)
BASE_SIZE = 52          # default icon size (px)
MAX_SIZE  = 84          # magnified icon size at cursor
MAG_CELLS = 2.5         # how many cells either side feel magnification
DOCK_PAD  = 24          # horizontal padding inside the dock bar
LABEL_H   = 18          # height reserved below icon for label
ANIM_MS   = 140         # animation duration (ms)

# Palette (works on light and dark window backgrounds)
ICON_COLORS = [
    "#4A90D9", "#E8734A", "#5BBF6B", "#A569BD",
    "#F5A623", "#50C8C6", "#E85D75",
]
DOCK_BG     = QColor(220, 220, 220, 80)
DOCK_BORDER = QColor(180, 180, 180, 140)
ICON_RADIUS = 14        # px, rounded-rect corner radius


# ---------------------------------------------------------------------------
# Animatable size helper (QObject wrapper so QPropertyAnimation works)
# ---------------------------------------------------------------------------
class SizeAnimator(QObject):
    def __init__(self, item: "DockIcon"):
        super().__init__()
        self._item = item
        self._size = float(BASE_SIZE)

    def get_size(self) -> float:
        return self._size

    def set_size(self, value: float):
        self._size = value
        self._item.update_geometry()

    size = Property(float, get_size, set_size)


# ---------------------------------------------------------------------------
# Individual dock icon
# ---------------------------------------------------------------------------
class DockIcon(QGraphicsItem):
    def __init__(self, emoji: str, label: str, color: str, index: int, dock: "DockScene"):
        super().__init__()
        self._emoji   = emoji
        self._label   = label
        self._color   = QColor(color)
        self._index   = index          # logical order in the dock
        self._dock    = dock
        self._dragging = False
        self._drag_offset = QPointF()

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setZValue(0)

        self._anim_helper = SizeAnimator(self)
        self._animation   = QPropertyAnimation(self._anim_helper, b"size", self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutBack)
        self._animation.setDuration(ANIM_MS)

        # Target x position (animated separately via QTimer-driven lerp)
        self._target_x = self._logical_x()
        self._current_x = self._target_x
        self.setPos(self._current_x, 0)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    def _logical_x(self) -> float:
        return DOCK_PAD + self._index * CELL

    def current_size(self) -> float:
        return self._anim_helper.get_size()

    def update_geometry(self):
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        s = self.current_size()
        return QRectF(-s / 2, -(s + LABEL_H), s, s + LABEL_H)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paint(self, painter: QPainter, option, widget=None):
        s = self.current_size()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Icon background
        rect = QRectF(-s / 2, -s, s, s)
        painter.setBrush(QBrush(self._color))
        painter.setPen(QPen(self._color.darker(120), 0.5))
        painter.drawRoundedRect(rect, ICON_RADIUS, ICON_RADIUS)

        # Emoji / text
        font = QFont("Segoe UI Emoji", int(s * 0.42))
        painter.setFont(font)
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._emoji)

        # Label (only when not dragging and size >= BASE_SIZE * 0.9)
        if not self._dragging and s >= BASE_SIZE * 0.9:
            lbl_rect = QRectF(-s / 2, -LABEL_H + 2, s, LABEL_H)
            lbl_font = QFont("Arial", 9)
            painter.setFont(lbl_font)
            painter.setPen(QPen(QColor(50, 50, 50)))
            painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, self._label)

        # Dot indicator (always)
        dot_r = 3
        painter.setBrush(QBrush(QColor(80, 80, 80, 180)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 3), dot_r, dot_r)

    # ------------------------------------------------------------------
    # Hover → magnify
    # ------------------------------------------------------------------
    def hoverMoveEvent(self, event):
        self._dock.on_hover(self._index)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._dock.on_hover_leave()
        super().hoverLeaveEvent(event)

    # ------------------------------------------------------------------
    # Drag to reorder
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.pos()
            self.setZValue(100)
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            self._dock.on_drag_start(self._index)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_scene_x = self.pos().x() + event.pos().x() - self._drag_offset.x()
            self.setPos(new_scene_x, 0)
            self._dock.on_drag_move(self._index, new_scene_x)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.setZValue(0)
            self.unsetCursor()
            self._dock.on_drag_end(self._index)
            event.accept()

    # ------------------------------------------------------------------
    # Animate to target size
    # ------------------------------------------------------------------
    def animate_size(self, target: float):
        if abs(self.current_size() - target) < 0.5:
            return
        self._animation.stop()
        self._animation.setStartValue(self.current_size())
        self._animation.setEndValue(target)
        self._animation.start()

    # ------------------------------------------------------------------
    # Animate to target x position (called by dock each tick)
    # ------------------------------------------------------------------
    def set_target_x(self, x: float):
        self._target_x = x

    def lerp_x(self, factor: float = 0.22):
        diff = self._target_x - self._current_x
        if abs(diff) < 0.3:
            self._current_x = self._target_x
        else:
            self._current_x += diff * factor
        self.setPos(self._current_x, 0)


# ---------------------------------------------------------------------------
# The scene that manages all icons
# ---------------------------------------------------------------------------
class DockScene(QGraphicsScene):
    def __init__(self):
        super().__init__()

        self._data = [
            ("🌐", "Browser"),
            ("📁",  "Files"),
            ("🎵",  "Music"),
            ("📸",  "Photos"),
            ("📝",  "Notes"),
            ("⚙️",  "Settings"),
            ("🗑️",  "Trash"),
        ]

        self._icons: list[DockIcon] = []
        self._drag_idx   = -1
        self._drop_idx   = -1
        self._hover_active = False

        # Dock background bar (drawn as a scene rect item)
        n = len(self._data)
        dock_w = DOCK_PAD * 2 + (n - 1) * CELL + BASE_SIZE
        dock_h = BASE_SIZE + LABEL_H + 16
        self._bar = QGraphicsRectItem(0, -(BASE_SIZE + LABEL_H + 8), dock_w, dock_h)
        self._bar.setBrush(QBrush(DOCK_BG))
        self._bar.setPen(QPen(DOCK_BORDER, 1.0))
        radius = 18
        self._bar.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._bar.setZValue(-1)
        # rounded rect via a custom rect — we'll just use the default rect item
        self.addItem(self._bar)

        for i, (emoji, label) in enumerate(self._data):
            color = ICON_COLORS[i % len(ICON_COLORS)]
            icon  = DockIcon(emoji, label, color, i, self)
            self._icons.append(icon)
            self.addItem(icon)
            icon.setPos(DOCK_PAD + i * CELL, 0)
            icon._current_x = DOCK_PAD + i * CELL

        # Tick timer for smooth x-lerp
        self._timer = QTimer(self)
        self._timer.setInterval(16)          # ~60 fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._update_scene_rect()

    def _update_scene_rect(self):
        n = len(self._icons)
        w = DOCK_PAD * 2 + (n - 1) * CELL + MAX_SIZE
        self.setSceneRect(0, -(MAX_SIZE + LABEL_H + 12), w, MAX_SIZE + LABEL_H + 24)

    # ------------------------------------------------------------------
    # Hover magnification
    # ------------------------------------------------------------------
    def on_hover(self, hovered_idx: int):
        self._hover_active = True
        for i, icon in enumerate(self._icons):
            d = abs(i - hovered_idx)
            if d == 0:
                target = MAX_SIZE
            elif d <= MAG_CELLS:
                t = 1.0 - (d / MAG_CELLS)
                target = BASE_SIZE + (MAX_SIZE - BASE_SIZE) * t * t
            else:
                target = float(BASE_SIZE)
            icon.animate_size(target)

    def on_hover_leave(self):
        if self._hover_active and self._drag_idx == -1:
            self._hover_active = False
            for icon in self._icons:
                icon.animate_size(float(BASE_SIZE))

    # ------------------------------------------------------------------
    # Drag reorder
    # ------------------------------------------------------------------
    def on_drag_start(self, idx: int):
        self._drag_idx = idx
        self._drop_idx = idx
        # Reset all sizes
        for icon in self._icons:
            icon.animate_size(float(BASE_SIZE))

    def on_drag_move(self, idx: int, scene_x: float):
        # Determine drop slot from the dragged icon's centre x
        cx = scene_x
        new_drop = 0
        for i, icon in enumerate(self._icons):
            if i == self._drag_idx:
                continue
            if cx > icon._current_x:
                new_drop = self._icons.index(icon) + 1

        # Clamp
        new_drop = max(0, min(new_drop, len(self._icons)))
        if new_drop != self._drop_idx:
            self._drop_idx = new_drop
            self._update_positions()

    def on_drag_end(self, idx: int):
        if self._drop_idx != -1 and self._drop_idx != self._drag_idx:
            # Reorder list
            icon = self._icons.pop(self._drag_idx)
            target = self._drop_idx if self._drop_idx <= self._drag_idx else self._drop_idx - 1
            self._icons.insert(target, icon)
            # Reassign indices
            for i, ic in enumerate(self._icons):
                ic._index = i

        self._drag_idx = -1
        self._drop_idx = -1
        self._update_positions()
        for icon in self._icons:
            icon.animate_size(float(BASE_SIZE))

    def _update_positions(self):
        """Push target x values to all icons, creating a gap at drop_idx."""
        slot = 0
        for i, icon in enumerate(self._icons):
            if i == self._drag_idx:
                continue
            # Insert gap before drop slot
            if self._drop_idx != -1 and slot == self._drop_idx:
                slot += 1
            icon.set_target_x(DOCK_PAD + slot * CELL)
            slot += 1

    def _tick(self):
        """Lerp all icons toward their target x each frame."""
        for icon in self._icons:
            if not icon._dragging:
                icon.lerp_x()


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------
class DockView(QGraphicsView):
    def __init__(self, scene: DockScene):
        super().__init__(scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")
        self.viewport().setStyleSheet("background: transparent;")
        self.setFixedHeight(MAX_SIZE + LABEL_H + 32)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 Dock")
        self.setMinimumSize(600, 180)
        self.setStyleSheet("background-color: #2d2d2d;")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
        layout.setContentsMargins(0, 0, 0, 20)

        self._scene = DockScene()
        self._view  = DockView(self._scene)
        layout.addWidget(self._view)

        # Size view to fit scene
        n = len(self._scene._data)
        dock_w = DOCK_PAD * 2 + (n - 1) * CELL + MAX_SIZE + 20
        self._view.setFixedWidth(dock_w)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()