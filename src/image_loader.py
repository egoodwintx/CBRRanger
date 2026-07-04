"""Threaded thumbnail generation via Pillow and QThreadPool."""

from __future__ import annotations

import io

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

THUMBNAIL_SIZE = (180, 240)  # width, height in pixels


def _to_qimage(img: Image.Image) -> QImage:
    rgba = img.convert("RGBA")
    qimage = QImage(
        rgba.tobytes(),
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return qimage.copy()  # detach from the Pillow buffer before it is freed


def _decode_thumbnail(data: bytes, size: tuple[int, int]) -> QImage:
    with Image.open(io.BytesIO(data)) as img:
        img.thumbnail(size, Image.Resampling.LANCZOS)
        return _to_qimage(img)


def decode_full_image(data: bytes) -> QImage:
    """Decode page bytes at full resolution (for the click-to-view popup)."""
    with Image.open(io.BytesIO(data)) as img:
        return _to_qimage(img)


class _WorkerSignals(QObject):
    image_ready = Signal(int, int, QImage)  # generation, page index, image
    failed = Signal(int, int, str)  # generation, page index, error message


class _ThumbnailWorker(QRunnable):
    def __init__(self, generation: int, index: int, data: bytes, size: tuple[int, int]) -> None:
        super().__init__()
        self._generation = generation
        self._index = index
        self._data = data
        self._size = size
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            image = _decode_thumbnail(self._data, self._size)
        except Exception as exc:  # Pillow raises many types for bad image data
            self.signals.failed.emit(self._generation, self._index, str(exc))
            return
        self.signals.image_ready.emit(self._generation, self._index, image)


class ImageLoader(QObject):
    """Generates thumbnails off the main thread and emits QPixmaps on it.

    Workers emit QImage (safe to create in any thread); the cross-thread signal
    delivers it back here, where it is converted to QPixmap on the GUI thread.
    """

    thumbnail_ready = Signal(int, QPixmap)  # page index, thumbnail
    thumbnail_failed = Signal(int, str)  # page index, error message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._generation = 0

    def load_thumbnails(self, pages: list[bytes], size: tuple[int, int] = THUMBNAIL_SIZE) -> None:
        self._generation += 1
        for index, data in enumerate(pages):
            worker = _ThumbnailWorker(self._generation, index, data, size)
            worker.signals.image_ready.connect(self._on_image_ready)
            worker.signals.failed.connect(self._on_failed)
            self._pool.start(worker)

    def cancel(self) -> None:
        """Drop results from any in-flight workers (e.g. when a new file is opened)."""
        self._generation += 1

    @Slot(int, int, QImage)
    def _on_image_ready(self, generation: int, index: int, image: QImage) -> None:
        if generation != self._generation:
            return
        self.thumbnail_ready.emit(index, QPixmap.fromImage(image))

    @Slot(int, int, str)
    def _on_failed(self, generation: int, index: int, message: str) -> None:
        if generation != self._generation:
            return
        self.thumbnail_failed.emit(index, message)
