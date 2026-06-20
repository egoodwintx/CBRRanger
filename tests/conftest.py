"""Shared test helpers: generate minimal comic fixtures programmatically.

No real comic files are committed; everything is built from tiny Pillow images.
"""

from __future__ import annotations

import io
import os
import zipfile

# Allow Qt-based tests to run headless (must be set before Qt is imported).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image


def make_page_bytes(
    color: tuple[int, int, int] = (120, 80, 200),
    size: tuple[int, int] = (100, 150),
    fmt: str = "JPEG",
) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def make_test_cbz(
    path: str,
    num_pages: int = 5,
    names: list[str] | None = None,
    comic_info: bytes | None = None,
) -> list[str]:
    """Write a small CBZ fixture; returns the page names as stored."""
    if names is None:
        names = [f"page{i + 1:02d}.jpg" for i in range(num_pages)]
    with zipfile.ZipFile(path, "w") as zf:
        for i, name in enumerate(names):
            zf.writestr(name, make_page_bytes(color=(i * 40 % 256, 100, 200)))
        if comic_info is not None:
            zf.writestr("ComicInfo.xml", comic_info)
    return names
