"""Tests for comic_file.py — pure file I/O, no GUI required."""

from __future__ import annotations

import zipfile

import pytest

from src import comic_file
from src.comic_file import ComicFileError, EmptyArchiveError
from src.utils import is_image, natural_sort_key
from tests.conftest import make_page_bytes, make_test_cbz


class TestNaturalSort:
    def test_page10_sorts_after_page9(self):
        names = ["page10.jpg", "page9.jpg", "page1.jpg"]
        assert sorted(names, key=natural_sort_key) == ["page1.jpg", "page9.jpg", "page10.jpg"]

    def test_zero_padded_names(self):
        names = ["page10.jpg", "page09.jpg", "page2.jpg"]
        assert sorted(names, key=natural_sort_key) == ["page2.jpg", "page09.jpg", "page10.jpg"]

    def test_mixed_filenames(self):
        names = ["scan_12b.png", "scan_2.png", "cover.jpg", "scan_12a.png"]
        assert sorted(names, key=natural_sort_key) == [
            "cover.jpg",
            "scan_2.png",
            "scan_12a.png",
            "scan_12b.png",
        ]

    def test_case_insensitive(self):
        names = ["Page2.jpg", "page1.jpg"]
        assert sorted(names, key=natural_sort_key) == ["page1.jpg", "Page2.jpg"]


class TestIsImage:
    @pytest.mark.parametrize(
        "name", ["a.jpg", "b.JPEG", "c.png", "d.gif", "e.webp", "f.bmp", "g.tiff", "dir/h.jpg"]
    )
    def test_accepts_images(self, name):
        assert is_image(name)

    @pytest.mark.parametrize(
        "name",
        ["ComicInfo.xml", "Thumbs.db", ".DS_Store", "__MACOSX/page1.jpg", "notes.txt", "page1"],
    )
    def test_rejects_non_pages(self, name):
        assert not is_image(name)


class TestLoadComic:
    def test_loads_pages_in_natural_order(self, tmp_path):
        path = str(tmp_path / "comic.cbz")
        # Stored deliberately out of natural order.
        make_test_cbz(path, names=["page10.jpg", "page2.jpg", "page1.jpg"])
        comic = comic_file.load_comic(path)
        assert comic.names == ["page1.jpg", "page2.jpg", "page10.jpg"]
        assert len(comic.pages) == 3
        assert all(isinstance(p, bytes) and p for p in comic.pages)

    def test_extracts_comic_info(self, tmp_path):
        path = str(tmp_path / "comic.cbz")
        info = b"<ComicInfo><Title>Test</Title></ComicInfo>"
        make_test_cbz(path, num_pages=2, comic_info=info)
        comic = comic_file.load_comic(path)
        assert comic.comic_info == info
        assert len(comic.pages) == 2  # ComicInfo.xml is not a page

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ComicFileError, match="not found"):
            comic_file.load_comic(str(tmp_path / "missing.cbz"))

    def test_unsupported_extension_raises(self, tmp_path):
        path = tmp_path / "comic.pdf"
        path.write_bytes(b"%PDF-1.4")
        with pytest.raises(ComicFileError, match="Unsupported"):
            comic_file.load_comic(str(path))

    def test_corrupt_zip_raises(self, tmp_path):
        path = tmp_path / "broken.cbz"
        path.write_bytes(b"this is not a zip file")
        with pytest.raises(ComicFileError, match="Corrupt"):
            comic_file.load_comic(str(path))

    def test_empty_archive_raises(self, tmp_path):
        path = str(tmp_path / "empty.cbz")
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("ComicInfo.xml", b"<ComicInfo/>")
        with pytest.raises(EmptyArchiveError):
            comic_file.load_comic(path)

    def test_mislabeled_cbr_that_is_zip_loads(self, tmp_path):
        path = str(tmp_path / "actually_a_zip.cbr")
        make_test_cbz(path, num_pages=3)
        comic = comic_file.load_comic(path)
        assert len(comic.pages) == 3

    def test_skips_macosx_metadata(self, tmp_path):
        path = str(tmp_path / "comic.cbz")
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("page1.jpg", make_page_bytes())
            zf.writestr("__MACOSX/page1.jpg", b"junk resource fork")
        comic = comic_file.load_comic(path)
        assert comic.names == ["page1.jpg"]


class TestSaveCbz:
    def test_pages_renamed_sequentially(self, tmp_path):
        out = str(tmp_path / "out.cbz")
        pages = [make_page_bytes(color=(i * 50, 0, 0)) for i in range(3)]
        names = ["cover.png", "page1.jpg", "page2.jpg"]
        comic_file.save_cbz(out, pages, names)
        with zipfile.ZipFile(out) as zf:
            assert zf.namelist() == ["0001.png", "0002.jpg", "0003.jpg"]

    def test_round_trip_preserves_reorder(self, tmp_path):
        src = str(tmp_path / "in.cbz")
        out = str(tmp_path / "out.cbz")
        make_test_cbz(src, num_pages=4)
        comic = comic_file.load_comic(src)

        new_order = [2, 0, 3, 1]
        pages = [comic.pages[i] for i in new_order]
        names = [comic.names[i] for i in new_order]
        comic_file.save_cbz(out, pages, names)

        reloaded = comic_file.load_comic(out)
        assert reloaded.pages == pages

    def test_comic_info_preserved(self, tmp_path):
        out = str(tmp_path / "out.cbz")
        info = b"<ComicInfo><Series>X</Series></ComicInfo>"
        comic_file.save_cbz(out, [make_page_bytes()], ["page1.jpg"], comic_info=info)
        reloaded = comic_file.load_comic(out)
        assert reloaded.comic_info == info


class TestSafeSave:
    def test_overwrites_target_on_success(self, tmp_path):
        target = str(tmp_path / "comic.cbz")
        make_test_cbz(target, num_pages=1)
        comic_file.safe_save(target, [make_page_bytes()] * 2, ["a.jpg", "b.jpg"])
        assert len(comic_file.load_comic(target).pages) == 2

    def test_failure_leaves_original_intact(self, tmp_path, monkeypatch):
        target = tmp_path / "comic.cbz"
        make_test_cbz(str(target), num_pages=1)
        original_bytes = target.read_bytes()

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(comic_file, "save_cbz", boom)
        with pytest.raises(OSError):
            comic_file.safe_save(str(target), [make_page_bytes()], ["a.jpg"])

        assert target.read_bytes() == original_bytes
        assert sorted(p.name for p in tmp_path.iterdir()) == ["comic.cbz"]  # no temp left


class TestCbrSupport:
    def test_returns_bool(self):
        assert isinstance(comic_file.cbr_support_available(), bool)
