"""QListWidgetItem representing a single comic page.

QListWidget's InternalMove drag-and-drop recreates items on drop, so page
identity must live in data roles (which survive the move) — never in Python
attributes on the item.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

PAGE_INDEX_ROLE = Qt.ItemDataRole.UserRole


class ThumbnailItem(QListWidgetItem):
    def __init__(self, page_index: int, original_name: str) -> None:
        super().__init__()
        self.setData(PAGE_INDEX_ROLE, page_index)
        self.setText(str(page_index + 1))
        self.setToolTip(original_name)
        self.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        # No ItemIsDropEnabled: pages may be reordered but never nested/overwritten.
        self.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
        )
