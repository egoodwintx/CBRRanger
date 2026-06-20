"""Tests for image_loader.py — uses pytest-qt with an offscreen platform."""

from __future__ import annotations

from src.image_loader import THUMBNAIL_SIZE, ImageLoader
from tests.conftest import make_page_bytes


def test_emits_thumbnail_within_bounds(qtbot):
    loader = ImageLoader()
    with qtbot.waitSignal(loader.thumbnail_ready, timeout=5000) as blocker:
        loader.load_thumbnails([make_page_bytes(size=(400, 600))])
    index, pixmap = blocker.args
    assert index == 0
    assert not pixmap.isNull()
    assert pixmap.width() <= THUMBNAIL_SIZE[0]
    assert pixmap.height() <= THUMBNAIL_SIZE[1]


def test_loads_all_pages(qtbot):
    loader = ImageLoader()
    pages = [make_page_bytes(color=(i * 60, 100, 200)) for i in range(3)]
    received: dict[int, object] = {}
    loader.thumbnail_ready.connect(lambda i, pix: received.__setitem__(i, pix))
    loader.load_thumbnails(pages)
    qtbot.waitUntil(lambda: len(received) == 3, timeout=5000)
    assert set(received) == {0, 1, 2}


def test_invalid_image_emits_failed(qtbot):
    loader = ImageLoader()
    with qtbot.waitSignal(loader.thumbnail_failed, timeout=5000) as blocker:
        loader.load_thumbnails([b"this is not an image"])
    assert blocker.args[0] == 0


def test_cancel_drops_pending_results(qtbot):
    loader = ImageLoader()
    loader.load_thumbnails([make_page_bytes()])
    loader.cancel()
    with qtbot.assertNotEmitted(loader.thumbnail_ready, wait=500):
        pass
