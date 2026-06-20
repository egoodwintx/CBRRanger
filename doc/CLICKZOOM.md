# Click-to-Zoom and Thumbnail Magnification in PySide6

## Prompt

How would I modify the codebase to have a thumbnail image magnify slightly when the user mouses over it in the grid (similar to the classic OS X Dock behavior) and have the image overlay on the canvas fullsize when a user clicks on a thumbnail and go back to the grid view when they hit the Esc key?

## Overview

Implementing OS X Dock-style magnification and fullsize image viewing requires two distinct interactions:

1. **Hover magnification** — Smoothly enlarge a thumbnail when the mouse hovers nearby
2. **Click-to-view** — Switch to a fullsize image view; press Esc to return to the grid

This combines animation (for the magnification effect) with view switching (grid ↔ fullsize).

## Recommended Approach

### Architecture: Stacked Views

Use `QStackedWidget` in `MainWindow` to hold both views:

```
MainWindow
├── Main content area (QStackedWidget)
│   ├── [0] Grid view (ThumbnailGrid)
│   └── [1] Fullsize view (ImageViewer)
```

This cleanly separates the two modes and avoids overlays that clutter the grid view.

### Hover Magnification Strategy

Instead of magnifying individual items, track the **mouse position globally** in the grid and apply magnification to the item nearest the cursor. Use `QPropertyAnimation` to smoothly scale the icon size as the mouse approaches.

**Why this approach:**
- Simple to implement (no custom item painting)
- Smooth and natural (easing curves work well)
- Preserves grid layout (magnified items don't break the flow)
- Works with existing `QListWidget` infrastructure

### Alternative: Per-Item Magnification

Subclass `QListWidgetItem` to track its own scale, then override `sizeHint()`. More complex but allows independent magnification without a global cursor position.

**Only use if you need multiple items magnified at once (unlikely for a thumbnail grid).**

## Implementation Strategy

### Phase 1: Add fullsize image viewer

Create a new widget `ImageViewer` to display a single image at full resolution. Handle:
- Centering the image
- Scrolling for images larger than the window
- Pressing Esc to return to the grid

### Phase 2: Wire stacked view in MainWindow

Replace the grid container with a `QStackedWidget` that can switch between grid and fullsize views.

### Phase 3: Add hover magnification

Track mouse movement in the grid. Calculate distance from each item to the cursor, then apply magnification to the nearest one using `QPropertyAnimation`.

### Phase 4: Add click handler

Detect clicks on grid items and switch to fullsize view for that page.

## Key Implementation Details

### 1. ImageViewer Widget

```python
# src/image_viewer.py
from PySide6.QtWidgets import QWidget, QLabel, QScrollArea, QVBoxLayout
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, Signal

class ImageViewer(QWidget):
    """Full-screen image viewer. Press Esc to close."""
    
    back_requested = Signal()  # Emitted when user presses Esc
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000;")
        
        # Use QScrollArea to handle images larger than viewport
        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("background-color: #000;")
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #000;")
        
        self.scroll_area.setWidget(self.image_label)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll_area)
    
    def set_image(self, pixmap: QPixmap):
        """Display a pixmap at full size."""
        self.image_label.setPixmap(pixmap)
    
    def keyPressEvent(self, event):
        """Return to grid view on Esc."""
        if event.key() == Qt.Key.Key_Escape:
            self.back_requested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)
```

### 2. Modify ThumbnailGrid

Add mouse tracking and magnification. Override `mouseMoveEvent` to update which item is magnified, and add a click handler to emit a signal.

```python
# src/thumbnail_grid.py
from PySide6.QtWidgets import QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QSize, QTimer
from PySide6.QtGui import QCursor

class ThumbnailGrid(QListWidget):
    
    page_clicked = Signal(int)  # Emitted when user clicks a thumbnail
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # ... existing code ...
        
        self.setMouseTracking(True)  # Enable mouseMoveEvent even without click
        
        # Magnification state
        self.magnified_index = -1
        self.base_icon_size = QSize(180, 240)
        self.max_icon_size = QSize(220, 280)  # ~22% larger
        self.magnification_distance = 100  # pixels
        
        # Animation for smooth magnification changes
        self.mag_animation = None
    
    def mouseMoveEvent(self, event):
        """Update magnification based on cursor position."""
        super().mouseMoveEvent(event)
        
        pos = event.pos()
        nearest_index = self.indexAt(pos).row()
        
        # Also check items near the cursor (within magnification_distance)
        nearest_distance = float('inf')
        for i in range(self.count()):
            item_rect = self.visualItemRect(self.item(i))
            center = item_rect.center()
            distance = (pos - center).manhattanLength()
            
            if distance < self.magnification_distance and distance < nearest_distance:
                nearest_distance = distance
                nearest_index = i
        
        # Only magnify if close enough
        if nearest_distance < self.magnification_distance:
            self._set_magnified_item(nearest_index, nearest_distance)
        else:
            self._clear_magnification()
    
    def _set_magnified_item(self, index: int, distance: float):
        """Magnify the item at index based on cursor distance."""
        if self.magnified_index == index:
            return  # Already magnifying this item
        
        # Clear previous magnification
        if self.magnified_index >= 0:
            prev_item = self.item(self.magnified_index)
            self.setIconSize(self.base_icon_size)
        
        self.magnified_index = index
        
        # Scale based on distance (closer = bigger)
        scale = 1.0 - (distance / self.magnification_distance)  # 0 to 1
        new_size = QSize(
            int(self.base_icon_size.width() + (self.max_icon_size.width() - self.base_icon_size.width()) * scale),
            int(self.base_icon_size.height() + (self.max_icon_size.height() - self.base_icon_size.height()) * scale)
        )
        
        self.setIconSize(new_size)
        # Ensure magnified item is visible
        self.scrollTo(self.model().index(index, 0))
    
    def _clear_magnification(self):
        """Reset all items to base size."""
        if self.magnified_index >= 0:
            self.setIconSize(self.base_icon_size)
            self.magnified_index = -1
    
    def leaveEvent(self, event):
        """Clear magnification when mouse leaves the grid."""
        self._clear_magnification()
        super().leaveEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click or single-click to view fullsize."""
        index = self.indexAt(event.pos()).row()
        if index >= 0:
            self.page_clicked.emit(index)
        super().mouseDoubleClickEvent(event)
    
    def mousePressEvent(self, event):
        """Emit page_clicked on single click instead of double-click."""
        if event.button() == Qt.MouseButton.LeftButton:
            index = self.indexAt(event.pos()).row()
            if index >= 0:
                self.page_clicked.emit(index)
        super().mousePressEvent(event)
```

### 3. Modify MainWindow

Integrate the stacked view and wire up signals.

```python
# src/main_window.py (modifications)
from PySide6.QtWidgets import QMainWindow, QStackedWidget
from .image_viewer import ImageViewer

class MainWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        
        # ... existing menu/toolbar setup ...
        
        # Create stacked widget for grid ↔ fullsize views
        self.stacked_widget = QStackedWidget()
        
        self.thumbnail_grid = ThumbnailGrid()
        self.image_viewer = ImageViewer()
        
        self.stacked_widget.addWidget(self.thumbnail_grid)  # Index 0
        self.stacked_widget.addWidget(self.image_viewer)     # Index 1
        
        self.setCentralWidget(self.stacked_widget)
        
        # Wire signals
        self.thumbnail_grid.page_clicked.connect(self._on_page_clicked)
        self.image_viewer.back_requested.connect(self._on_back_to_grid)
        
        # ... rest of initialization ...
    
    def _on_page_clicked(self, page_index: int):
        """Switch to fullsize view for the clicked page."""
        if 0 <= page_index < len(self.pages):
            page_pixmap = QPixmap()
            page_pixmap.loadFromData(self.pages[page_index])
            
            self.image_viewer.set_image(page_pixmap)
            self.stacked_widget.setCurrentIndex(1)  # Show fullsize view
    
    def _on_back_to_grid(self):
        """Return to grid view."""
        self.stacked_widget.setCurrentIndex(0)  # Show grid view
        self.thumbnail_grid.setFocus()
```

## Testing

- **Hover magnification:** Move mouse over grid items at varying distances; should scale smoothly
- **Magnification boundaries:** Move mouse away from grid; magnification should clear
- **Click to view:** Click a thumbnail; fullsize image should appear
- **Esc to return:** Press Esc in fullsize view; should return to grid with focus
- **Edge cases:** Click on image boundaries, very small comics (< 5 pages), very large comics (100+ pages)
- **Performance:** Ensure smooth magnification animation at 60fps; may need to debounce `mouseMoveEvent` on slower hardware

## Customization Points

### Magnification Tuning

```python
self.base_icon_size = QSize(180, 240)      # Start size
self.max_icon_size = QSize(220, 280)       # Max magnified size
self.magnification_distance = 100          # Pixels from center before magnification starts
```

Increase `magnification_distance` for longer-range effects; adjust size ratio for more/less magnification.

### Animation Duration (if using QPropertyAnimation)

To smooth the magnification transition further, replace the direct `setIconSize()` call with:

```python
if self.mag_animation:
    self.mag_animation.stop()

self.mag_animation = QPropertyAnimation(self, b"iconSize")
self.mag_animation.setDuration(100)  # ms
self.mag_animation.setEndValue(new_size)
self.mag_animation.start()
```

### Fullsize Viewer Styling

Customize background color, scrollbar appearance, or add page number display in `ImageViewer`.

## References

- PySide6 Mouse Events: https://doc.qt.io/qt-6/qwidget.html#mouseMoveEvent
- QStackedWidget: https://doc.qt.io/qt-6/qstackedwidget.html
- QPropertyAnimation: https://doc.qt.io/qt-6/qpropertyanimation.html
- QListWidget Mouse Tracking: https://doc.qt.io/qt-6/qwidget.html#mouseTracking-prop
