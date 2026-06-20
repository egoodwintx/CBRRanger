"""Tests for ThumbnailGrid drag-and-drop and animation features."""

import pytest
from PySide6.QtCore import Qt, QMimeData, QPoint
from PySide6.QtGui import QDrag, QDropEvent
from PySide6.QtWidgets import QApplication

from src.thumbnail_grid import ThumbnailGrid, ThumbnailItem
from src.thumbnail_item import PAGE_INDEX_ROLE


@pytest.fixture
def grid(qtbot):
    """Create a ThumbnailGrid with test items."""
    grid = ThumbnailGrid()
    grid.set_pages([f"page{i}.jpg" for i in range(1, 6)])
    qtbot.addWidget(grid)
    return grid


def test_grid_initialization(grid):
    """Test that grid initializes with correct page count."""
    assert grid.count() == 5
    assert grid.current_order() == [0, 1, 2, 3, 4]


def test_drop_indicator_row_tracking(grid, qtbot):
    """Test that _drop_indicator_row is tracked during drag."""
    # Initially no drop indicator
    assert grid._drop_indicator_row == -1

    # Simulate drag move to position 2
    from PySide6.QtGui import QDragMoveEvent
    pos = grid.visualItemRect(grid.item(2)).center()
    event = QDragMoveEvent(pos, Qt.DropActions.MoveAction, QMimeData(),
                          Qt.MouseButtons.LeftButton, Qt.KeyboardModifiers())
    grid.dragMoveEvent(event)

    # Drop indicator should be updated
    assert grid._drop_indicator_row == 2

    # Simulate drag leave
    grid.dragLeaveEvent(None)
    assert grid._drop_indicator_row == -1


def test_drop_reorders_items(grid, qtbot):
    """Test that dropping items reorders them correctly."""
    # Use move_selected since we can't easily simulate a drag in a unit test
    # Select item 1 and move it to position after item 3
    grid.item(1).setSelected(True)
    old_order = grid.current_order()

    # Move to back
    grid.move_selected_to_back()

    new_order = grid.current_order()
    # Order should have changed (item 1 moved to end)
    assert new_order != old_order
    # Item 1 should still be in the grid
    assert 1 in new_order
    # Item 1 (page index 1) should now be at the end
    assert grid.item(grid.count() - 1).data(PAGE_INDEX_ROLE) == 1


def test_drop_indicator_row_at_end(grid, qtbot):
    """Test drop indicator at the end of the grid."""
    # Simulate drag move below last item
    from PySide6.QtGui import QDragMoveEvent
    pos = grid.viewport().rect().bottomRight()
    event = QDragMoveEvent(pos, Qt.DropActions.MoveAction, QMimeData(),
                          Qt.MouseButtons.LeftButton, Qt.KeyboardModifiers())
    grid.dragMoveEvent(event)

    # Should be positioned at the end
    assert grid._drop_indicator_row == grid.count()


def test_animation_highlights_items(grid, qtbot):
    """Test that _animate_reordered_items highlights items briefly."""
    item_0 = grid.item(0)

    # Trigger animation
    grid._animate_reordered_items([0])

    # Item should now have a highlight color (non-transparent)
    bg_color = item_0.background().color()
    assert bg_color.alpha() > 0

    # Wait for animation timer
    qtbot.wait(250)

    # Background should be cleared
    bg_color_after = item_0.background().color()
    assert bg_color_after.alpha() == 0


def test_move_to_front_animates(grid, qtbot):
    """Test that move_selected_to_front triggers animation."""
    # Select item 2
    grid.item(2).setSelected(True)

    # Move to front
    grid.move_selected_to_front()

    # Item 2 (page index 2) should now be at index 0
    assert grid.item(0).data(PAGE_INDEX_ROLE) == 2

    # Item should have highlight color from animation
    bg_color = grid.item(0).background().color()
    assert bg_color.alpha() > 0


def test_move_to_back_animates(grid, qtbot):
    """Test that move_selected_to_back triggers animation."""
    # Select item 0
    grid.item(0).setSelected(True)

    # Move to back
    grid.move_selected_to_back()

    # Item 0 (page index 0) should now be at the end
    assert grid.item(grid.count() - 1).data(PAGE_INDEX_ROLE) == 0

    # Item should have highlight color from animation
    bg_color = grid.item(grid.count() - 1).background().color()
    assert bg_color.alpha() > 0


def test_order_changed_signal_emitted(grid, qtbot):
    """Test that order_changed signal is emitted on drop."""
    signal_emitted = []

    def on_order_changed(old, new):
        signal_emitted.append((old, new))

    grid.order_changed.connect(on_order_changed)

    # Select item 3 and move it to front (this will actually move it)
    grid.item(3).setSelected(True)
    grid.move_selected_to_front()

    # Signal should be emitted
    assert len(signal_emitted) > 0
    # Verify the old and new orders
    old, new = signal_emitted[0]
    assert old == [0, 1, 2, 3, 4]
    assert new[0] == 3  # Item 3 (page index 3) is now first


def test_no_reorder_on_drop_self(grid, qtbot):
    """Test that dropping on self doesn't reorder."""
    grid.item(0).setSelected(True)
    old_order = grid.current_order()

    # Drop on the same item
    rect = grid.visualItemRect(grid.item(0))
    drop_pos = QPoint(rect.center().x(), rect.center().y())

    mime_data = QMimeData()
    drop_event = QDropEvent(drop_pos, Qt.DropActions.MoveAction, mime_data,
                           Qt.MouseButtons.LeftButton, Qt.KeyboardModifiers())

    grid.dropEvent(drop_event)

    # Order should not change
    assert grid.current_order() == old_order
