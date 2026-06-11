"""Tests for safaribooks.core.epub — sanitize_dirname, dirs, chapter HTML, ZIP packaging."""


import sys
import zipfile
from pathlib import Path

from safaribooks.core.epub import (
    BookPaths,
    build_epub,
    ensure_book_dirs,
    sanitize_dirname,
    write_chapter_html,
)


class TestSanitizeDirname:
    def test_removes_unsafe_characters(self):
        result = sanitize_dirname("Book<Title>With*Special?Chars")
        assert "<" not in result
        assert ">" not in result
        assert "*" not in result
        assert "?" not in result

    def test_colon_truncation_after_position_15(self):
        name = "A Very Long Title: The Subtitle"
        result = sanitize_dirname(name)
        assert "Subtitle" not in result

    def test_colon_early_in_string_preserved_on_non_windows(self):
        if "win" in sys.platform:
            return
        name = "C: Drive Stuff"
        result = sanitize_dirname(name)
        # Colon at position 1 (<= 15), kept on non-Windows but replaced as unsafe char
        assert ":" not in result  # colon is in _UNSAFE_CHARS

    def test_clean_space_removes_spaces(self):
        result = sanitize_dirname("My Book Title", clean_space=True)
        assert " " not in result
        assert result == "MyBookTitle"

    def test_clean_space_false_preserves_spaces(self):
        result = sanitize_dirname("My Book Title", clean_space=False)
        assert result == "My Book Title"

    def test_tilde_replaced(self):
        result = sanitize_dirname("Book~v2")
        assert "~" not in result

    def test_pipe_replaced(self):
        result = sanitize_dirname("A | B")
        assert "|" not in result

    def test_plain_name_unchanged(self):
        result = sanitize_dirname("Clean Book Name")
        assert result == "Clean Book Name"


class TestEnsureBookDirs:
    def test_creates_expected_structure(self, tmp_path):
        paths = ensure_book_dirs(tmp_path, "TestBook")
        assert paths.book_dir.is_dir()
        assert paths.oebps.is_dir()
        assert paths.text.is_dir()
        assert paths.styles.is_dir()
        assert paths.images.is_dir()
        assert paths.videos.is_dir()
        assert paths.meta_inf.is_dir()

    def test_directory_names_correct(self, tmp_path):
        paths = ensure_book_dirs(tmp_path, "MyBook")
        assert paths.book_dir.name == "MyBook"
        assert paths.oebps.name == "OEBPS"
        assert paths.meta_inf.name == "META-INF"
        assert paths.styles.name == "Styles"
        assert paths.images.name == "Images"
        assert paths.videos.name == "Video"

    def test_idempotent_on_existing_dirs(self, tmp_path):
        paths1 = ensure_book_dirs(tmp_path, "TestBook")
        paths2 = ensure_book_dirs(tmp_path, "TestBook")
        assert paths1.book_dir == paths2.book_dir
        assert paths1.oebps.is_dir()


class TestWriteChapterHtml:
    def test_writes_valid_xhtml(self, tmp_path):
        out = tmp_path / "chapter.xhtml"
        write_chapter_html(out, css_content="", body_content="<p>Hello</p>")
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<p>Hello</p>" in content
        assert "</html>" in content

    def test_includes_css_content(self, tmp_path):
        out = tmp_path / "chapter.xhtml"
        css = '<link href="Styles/Style00.css" rel="stylesheet" type="text/css" />'
        write_chapter_html(out, css_content=css, body_content="<p>Body</p>")
        content = out.read_text(encoding="utf-8")
        assert "Style00.css" in content

    def test_kindle_mode_adds_overrides(self, tmp_path):
        out = tmp_path / "chapter.xhtml"
        write_chapter_html(out, css_content="", body_content="<p>Kindle</p>", kindle=True)
        content = out.read_text(encoding="utf-8")
        assert "word-wrap:break-word" in content

    def test_non_kindle_mode_no_overrides(self, tmp_path):
        out = tmp_path / "chapter.xhtml"
        write_chapter_html(out, css_content="", body_content="<p>Normal</p>", kindle=False)
        content = out.read_text(encoding="utf-8")
        assert "word-wrap:break-word" not in content


class TestBuildEpub:
    @staticmethod
    def _setup_book(tmp_path: Path) -> BookPaths:
        paths = ensure_book_dirs(tmp_path, "TestEpub")
        # Write a chapter file
        chapter_path = paths.oebps / "ch01.xhtml"
        chapter_path.write_text("<html><body>Chapter 1</body></html>", encoding="utf-8")
        return paths

    def test_creates_epub_file(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, "Test Epub")
        assert epub_path.exists()
        assert epub_path.suffix == ".epub"

    def test_mimetype_is_first_entry(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, "Test Epub")
        with zipfile.ZipFile(epub_path) as zf:
            assert zf.namelist()[0] == "mimetype"

    def test_mimetype_is_stored_not_compressed(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, "Test Epub")
        with zipfile.ZipFile(epub_path) as zf:
            info = zf.getinfo("mimetype")
            assert info.compress_type == zipfile.ZIP_STORED

    def test_mimetype_content_correct(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, "Test Epub")
        with zipfile.ZipFile(epub_path) as zf:
            content = zf.read("mimetype").decode("utf-8")
            assert content == "application/epub+zip"

    def test_contains_container_xml(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, "Test Epub")
        with zipfile.ZipFile(epub_path) as zf:
            assert "META-INF/container.xml" in zf.namelist()

    def test_contains_chapter_file(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, "Test Epub")
        with zipfile.ZipFile(epub_path) as zf:
            assert "OEBPS/ch01.xhtml" in zf.namelist()

    def test_does_not_contain_epub_inside_epub(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, "Test Epub")
        with zipfile.ZipFile(epub_path) as zf:
            epub_entries = [n for n in zf.namelist() if n.endswith(".epub")]
            assert epub_entries == []
