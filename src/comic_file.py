"""CBR/CBZ reading and writing. Pure file I/O — no Qt imports."""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import rarfile

from src.utils import is_image, natural_sort_key

COMIC_INFO_NAME = "comicinfo.xml"
ZIP_SUFFIXES = {".cbz", ".zip"}
RAR_SUFFIXES = {".cbr", ".rar"}


class ComicFileError(Exception):
    """A comic archive could not be read or written."""


class EmptyArchiveError(ComicFileError):
    """The archive contains no image pages."""


@dataclass
class ComicArchive:
    """An opened comic: page bytes and names in reading order, plus optional metadata."""

    path: str
    pages: list[bytes]
    names: list[str]
    comic_info: bytes | None = None


def cbr_support_available() -> bool:
    """True if a RAR extraction tool (unrar/unar/bsdtar) is installed."""
    try:
        rarfile.tool_setup()
    except rarfile.RarCannotExec:
        return False
    return True


def load_comic(path: str) -> ComicArchive:
    """Load a CBZ or CBR file into memory, pages in natural reading order."""
    file = Path(path)
    if not file.is_file():
        raise ComicFileError(f"File not found: {path}")

    suffix = file.suffix.lower()
    if suffix in ZIP_SUFFIXES:
        pages, names, comic_info = _load_zip(path)
    elif suffix in RAR_SUFFIXES:
        # Some .cbr files in the wild are actually ZIP archives.
        if zipfile.is_zipfile(path):
            pages, names, comic_info = _load_zip(path)
        else:
            pages, names, comic_info = _load_rar(path)
    else:
        raise ComicFileError(f"Unsupported file type: {file.name}")

    if not pages:
        raise EmptyArchiveError(f"No images found in {file.name}")
    return ComicArchive(path=path, pages=pages, names=names, comic_info=comic_info)


def _load_zip(path: str) -> tuple[list[bytes], list[str], bytes | None]:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            return _read_entries(zf)
    except zipfile.BadZipFile as exc:
        raise ComicFileError(f"Corrupt or invalid ZIP archive: {Path(path).name}") from exc


def _load_rar(path: str) -> tuple[list[bytes], list[str], bytes | None]:
    try:
        with rarfile.RarFile(path, "r") as rf:
            return _read_entries(rf)
    except rarfile.RarCannotExec as exc:
        raise ComicFileError(
            "CBR support requires the 'unrar' or 'unar' tool to be installed."
        ) from exc
    except rarfile.Error as exc:
        raise ComicFileError(f"Corrupt or invalid RAR archive: {Path(path).name}") from exc


def _read_entries(
    archive: zipfile.ZipFile | rarfile.RarFile,
) -> tuple[list[bytes], list[str], bytes | None]:
    names = sorted((n for n in archive.namelist() if is_image(n)), key=natural_sort_key)
    pages = [archive.read(name) for name in names]
    comic_info = None
    for name in archive.namelist():
        if Path(name).name.lower() == COMIC_INFO_NAME:
            comic_info = archive.read(name)
            break
    return pages, names, comic_info


def save_cbz(
    path: str,
    pages: list[bytes],
    original_names: list[str],
    comic_info: bytes | None = None,
) -> None:
    """Write pages to a CBZ, renamed sequentially so order holds in any reader."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, (data, orig_name) in enumerate(zip(pages, original_names)):
            ext = Path(orig_name).suffix.lower() or ".jpg"
            zf.writestr(f"{i + 1:04d}{ext}", data)
        if comic_info is not None:
            zf.writestr("ComicInfo.xml", comic_info)


def safe_save(
    target_path: str,
    pages: list[bytes],
    names: list[str],
    comic_info: bytes | None = None,
) -> None:
    """Write to a temp file in the target directory, then rename over the target.

    The original file is never touched unless the full write succeeds.
    """
    dir_ = Path(target_path).parent
    with tempfile.NamedTemporaryFile(dir=dir_, delete=False, suffix=".cbz") as tmp:
        tmp_path = tmp.name
    try:
        save_cbz(tmp_path, pages, names, comic_info)
        shutil.move(tmp_path, target_path)
    except Exception:
        os.unlink(tmp_path)
        raise
