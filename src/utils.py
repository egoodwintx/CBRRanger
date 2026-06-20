"""Shared helpers. No Qt imports here."""

from __future__ import annotations

import re
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}


def natural_sort_key(s: str) -> list[int | str]:
    """Sort key so 'page10' sorts after 'page9', not after 'page1'."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", s)]


def is_image(name: str) -> bool:
    """True for archive entries that are comic pages.

    Excludes metadata entries such as __MACOSX/, Thumbs.db, .DS_Store and
    ComicInfo.xml (none of which carry an image extension, or which live
    under a dunder-prefixed path).
    """
    return Path(name).suffix.lower() in IMAGE_EXTENSIONS and not name.startswith("__")
