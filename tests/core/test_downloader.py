"""Tests for safaribooks.core.downloader — EPUB library copy behavior."""

import shutil
from pathlib import Path

from safaribooks.core.config import AppConfig
from safaribooks.core.epub import build_epub, ensure_book_dirs


class TestEpubLibraryCopy:
    @staticmethod
    def _build_test_epub(tmp_path: Path) -> Path:
        paths = ensure_book_dirs(tmp_path / "output", "TestBook")
        (paths.oebps / "ch01.xhtml").write_text(
            "<html><body>Chapter 1</body></html>", encoding="utf-8"
        )
        return build_epub(paths, "Test Book")

    def test_epub_copied_to_library_epubs_dir(self, tmp_path):
        epub_path = self._build_test_epub(tmp_path)
        library_dir = tmp_path / "library"

        epubs_dir = library_dir / "epubs"
        epubs_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(epub_path, epubs_dir / epub_path.name)

        copied = epubs_dir / epub_path.name
        assert copied.exists()
        assert copied.read_bytes() == epub_path.read_bytes()

    def test_epubs_dir_created_if_missing(self, tmp_path):
        epub_path = self._build_test_epub(tmp_path)
        library_dir = tmp_path / "library"

        epubs_dir = library_dir / "epubs"
        assert not epubs_dir.exists()

        epubs_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(epub_path, epubs_dir / epub_path.name)

        assert epubs_dir.is_dir()
        assert (epubs_dir / epub_path.name).exists()

    def test_library_dir_config_default(self):
        config = AppConfig()
        assert config.library_dir == Path.home() / ".safaribooks"
        assert (config.library_dir / "epubs") == Path.home() / ".safaribooks" / "epubs"
