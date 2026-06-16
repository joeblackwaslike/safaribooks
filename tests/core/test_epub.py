"""Tests for safaribooks.core.epub — sanitize_dirname, dirs, chapter HTML, ZIP packaging."""


import sys
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from safaribooks.core.epub import (
    BookPaths,
    _render_navpoints,
    build_epub,
    ensure_book_dirs,
    normalize_toc,
    render_content_opf,
    render_toc_ncx,
    sanitize_dirname,
    write_chapter_html,
)
from safaribooks.core.exceptions import ApiError, DownloadError
from safaribooks.core.models import (
    Author,
    BookInfo,
    Chapter,
    Publisher,
    Subject,
    TocEntry,
)


def _book_info(**overrides) -> BookInfo:
    """Build a minimal BookInfo for tests, allowing field overrides."""
    defaults = {
        "title": "My <Great> Book",
        "identifier": "urn:orm:book:9999",
        "isbn": "9781234567890",
        "description": "A <fine> description & more.",
        "web_url": "https://learning.oreilly.com/library/view/x/9781234567890/",
        "rights": "Copyright © Acme",
        "cover": "Images/cover.png",
        "authors": [Author(name="Ada Lovelace"), Author(name="Alan Turing")],
        "publishers": [Publisher(name="O'Reilly Media")],
        "subjects": [Subject(name="Programming"), Subject(name="Python")],
        "issued": "2024-01-01",
    }
    defaults.update(overrides)
    return BookInfo(**defaults)


def _chapter(filename: str, title: str = "Chapter") -> Chapter:
    return Chapter(
        filename=filename,
        title=title,
        content_url="https://example.com/" + filename,
        asset_base_url="https://example.com/",
        images=[],
        stylesheets=[],
        site_styles=[],
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
        paths = ensure_book_dirs(tmp_path / "TestBook")
        assert paths.book_dir.is_dir()
        assert paths.oebps.is_dir()
        assert paths.text.is_dir()
        assert paths.styles.is_dir()
        assert paths.images.is_dir()
        assert paths.videos.is_dir()
        assert paths.meta_inf.is_dir()

    def test_directory_names_correct(self, tmp_path):
        paths = ensure_book_dirs(tmp_path / "MyBook")
        assert paths.book_dir.name == "MyBook"
        assert paths.oebps.name == "OEBPS"
        assert paths.meta_inf.name == "META-INF"
        assert paths.styles.name == "Styles"
        assert paths.images.name == "Images"
        assert paths.videos.name == "Video"

    def test_idempotent_on_existing_dirs(self, tmp_path):
        paths1 = ensure_book_dirs(tmp_path / "TestBook")
        paths2 = ensure_book_dirs(tmp_path / "TestBook")
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

    def test_ereader_css_always_included(self, tmp_path):
        out = tmp_path / "chapter.xhtml"
        write_chapter_html(out, css_content="", body_content="<p>Body</p>")
        content = out.read_text(encoding="utf-8")
        assert "word-wrap:break-word" in content


class TestBuildEpub:
    @staticmethod
    def _setup_book(tmp_path: Path) -> BookPaths:
        paths = ensure_book_dirs(tmp_path / "TestEpub")
        # Write a chapter file
        chapter_path = paths.oebps / "ch01.xhtml"
        chapter_path.write_text("<html><body>Chapter 1</body></html>", encoding="utf-8")
        return paths

    def test_creates_epub_file(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, tmp_path / "Test Epub.epub")
        assert epub_path.exists()
        assert epub_path.suffix == ".epub"

    def test_mimetype_is_first_entry(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, tmp_path / "Test Epub.epub")
        with zipfile.ZipFile(epub_path) as zf:
            assert zf.namelist()[0] == "mimetype"

    def test_mimetype_is_stored_not_compressed(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, tmp_path / "Test Epub.epub")
        with zipfile.ZipFile(epub_path) as zf:
            info = zf.getinfo("mimetype")
            assert info.compress_type == zipfile.ZIP_STORED

    def test_mimetype_content_correct(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, tmp_path / "Test Epub.epub")
        with zipfile.ZipFile(epub_path) as zf:
            content = zf.read("mimetype").decode("utf-8")
            assert content == "application/epub+zip"

    def test_contains_container_xml(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, tmp_path / "Test Epub.epub")
        with zipfile.ZipFile(epub_path) as zf:
            assert "META-INF/container.xml" in zf.namelist()

    def test_contains_chapter_file(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, tmp_path / "Test Epub.epub")
        with zipfile.ZipFile(epub_path) as zf:
            assert "OEBPS/ch01.xhtml" in zf.namelist()

    def test_does_not_contain_epub_inside_epub(self, tmp_path):
        paths = self._setup_book(tmp_path)
        epub_path = build_epub(paths, tmp_path / "Test Epub.epub")
        with zipfile.ZipFile(epub_path) as zf:
            epub_entries = [n for n in zf.namelist() if n.endswith(".epub")]
            assert epub_entries == []


class TestSanitizeDirnameWindows:
    def test_early_colon_replaced_with_comma_on_windows(self, monkeypatch):
        # idx <= 15 and platform contains "win" => colon replaced with comma
        # (lines 77-78). Comma is not unsafe, so it survives.
        monkeypatch.setattr("safaribooks.core.epub.sys.platform", "win32")
        result = sanitize_dirname("C: Drive")
        assert result == "C, Drive"

    def test_early_colon_kept_replaced_unsafe_on_non_windows(self, monkeypatch):
        # idx <= 15 and non-windows => no comma substitution; colon then stripped
        # by the unsafe-char pass since ":" is in _UNSAFE_CHARS.
        monkeypatch.setattr("safaribooks.core.epub.sys.platform", "linux")
        result = sanitize_dirname("C: Drive")
        assert result == "C_ Drive"


class TestNormalizeToc:
    def test_root_depth_starts_at_one(self):
        result = normalize_toc([{"url": "ch01.html", "label": "C1", "id": "ch01"}])
        assert result[0].depth == 1

    def test_recursive_children_increment_depth(self):
        raw = [
            {
                "url": "ch01.html",
                "label": "C1",
                "id": "ch01",
                "children": [{"url": "ch01.html#s1", "label": "S1", "id": "s1"}],
            }
        ]
        result = normalize_toc(raw)
        assert result[0].children[0].depth == 2

    def test_fragment_extracted_from_href(self):
        result = normalize_toc([{"url": "ch01.html#intro", "label": "I", "id": "i"}])
        assert result[0].fragment == "intro"

    def test_no_fragment_when_no_hash(self):
        result = normalize_toc([{"url": "ch01.html", "label": "C", "id": "c"}])
        assert result[0].fragment == ""

    def test_href_url_decoded(self):
        result = normalize_toc([{"url": "ch%2001.html", "label": "E", "id": "e"}])
        assert result[0].href == "ch 01.html"

    def test_title_fallback_when_no_label(self):
        result = normalize_toc([{"href": "ch01.html", "title": "Title Fallback"}])
        assert result[0].label == "Title Fallback"

    def test_auto_generated_id_uses_depth_and_index(self):
        result = normalize_toc([{"url": "x.html", "label": "n"}])
        assert result[0].id == "toc_1_0"

    def test_empty_list(self):
        assert normalize_toc([]) == []


class TestRenderNavpoints:
    def test_flat_entries_play_order(self):
        entries = [
            TocEntry(depth=1, fragment="", id="a", label="A", href="a.html"),
            TocEntry(depth=1, fragment="", id="b", label="B", href="b.html"),
        ]
        xml, counter, max_depth = _render_navpoints(entries)
        assert counter == 2
        assert max_depth == 1
        assert 'playOrder="1"' in xml
        assert 'playOrder="2"' in xml

    def test_fragment_used_as_nav_id_when_present(self):
        entries = [TocEntry(depth=1, fragment="frag1", id="entry_id", label="L", href="x.html#frag1")]
        xml, _, _ = _render_navpoints(entries)
        assert 'id="frag1"' in xml

    def test_id_used_as_nav_id_when_no_fragment(self):
        entries = [TocEntry(depth=1, fragment="", id="entry_id", label="L", href="x.html")]
        xml, _, _ = _render_navpoints(entries)
        assert 'id="entry_id"' in xml

    def test_href_converted_to_xhtml_basename(self):
        entries = [
            TocEntry(depth=1, fragment="", id="a", label="A", href="files/sub/ch01.html")
        ]
        xml, _, _ = _render_navpoints(entries)
        assert '<content src="ch01.xhtml"/>' in xml

    def test_label_escaped(self):
        entries = [TocEntry(depth=1, fragment="", id="a", label="A & <B>", href="a.html")]
        xml, _, _ = _render_navpoints(entries)
        assert "A &amp; &lt;B&gt;" in xml

    def test_nested_children_increment_counter_and_depth(self):
        child = TocEntry(depth=2, fragment="s1", id="s1", label="S1", href="a.html#s1")
        parent = TocEntry(
            depth=1, fragment="", id="a", label="A", href="a.html", children=[child]
        )
        xml, counter, max_depth = _render_navpoints([parent])
        assert counter == 2
        assert max_depth == 2
        # child navPoint nested inside parent before parent's closing tag.
        assert xml.index('id="s1"') < xml.index("</navPoint>")


class TestRenderContentOpf:
    def _dirs(self, tmp_path: Path) -> BookPaths:
        return ensure_book_dirs(tmp_path / "Book")

    def test_basic_render_includes_metadata(self, tmp_path):
        paths = self._dirs(tmp_path)
        chapters = [_chapter("ch01.html"), _chapter("ch02.html")]
        opf = render_content_opf(
            _book_info(),
            chapters,
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
        )
        # Title is escaped.
        assert "My &lt;Great&gt; Book" in opf
        # Authors rendered with file-as and role.
        assert "Ada Lovelace" in opf
        assert "Alan Turing" in opf
        # Subjects.
        assert "<dc:subject>Programming</dc:subject>" in opf
        # ISBN used as identifier.
        assert "9781234567890" in opf

    def test_chapters_in_manifest_and_spine(self, tmp_path):
        paths = self._dirs(tmp_path)
        opf = render_content_opf(
            _book_info(),
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
        )
        assert 'href="ch01.xhtml"' in opf
        assert "<itemref idref=" in opf

    def test_identifier_used_when_no_isbn(self, tmp_path):
        paths = self._dirs(tmp_path)
        info = _book_info(isbn="")
        opf = render_content_opf(
            info,
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
        )
        assert "urn:orm:book:9999" in opf

    def test_discovers_css_and_images_on_disk(self, tmp_path):
        paths = self._dirs(tmp_path)
        (paths.styles / "Style00.css").write_text("body{}", encoding="utf-8")
        (paths.styles / "ignore.txt").write_text("x", encoding="utf-8")
        (paths.images / "fig1.png").write_bytes(b"x")
        (paths.images / "photo.jpg").write_bytes(b"x")
        opf = render_content_opf(
            _book_info(),
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
        )
        assert 'href="Styles/Style00.css"' in opf
        assert "ignore.txt" not in opf
        assert 'href="Images/fig1.png"' in opf
        assert 'media-type="image/png"' in opf
        # jpg => jpeg media type.
        assert 'media-type="image/jpeg"' in opf

    def test_fonts_with_known_extensions_included(self, tmp_path):
        paths = self._dirs(tmp_path)
        opf = render_content_opf(
            _book_info(),
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=["MyFont.ttf", "Other.woff2"],
        )
        assert 'href="Styles/MyFont.ttf"' in opf
        assert 'media-type="font/ttf"' in opf
        assert 'media-type="font/woff2"' in opf

    def test_font_with_unknown_extension_skipped(self, tmp_path):
        paths = self._dirs(tmp_path)
        opf = render_content_opf(
            _book_info(),
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=["weird.xyz"],
        )
        assert "weird.xyz" not in opf

    def test_videos_included(self, tmp_path):
        paths = self._dirs(tmp_path)
        (paths.videos / "clip.mp4").write_bytes(b"x")
        (paths.videos / "subdir").mkdir()  # non-file entry skipped
        opf = render_content_opf(
            _book_info(),
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
        )
        assert 'href="Video/clip.mp4"' in opf
        assert 'media-type="video/mp4"' in opf

    def test_cover_src_resolves_cover_id(self, tmp_path):
        paths = self._dirs(tmp_path)
        opf = render_content_opf(
            _book_info(),
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
            cover_src="Images/cover.png",
        )
        assert 'content="img_cover"' in opf

    def test_cover_id_from_book_info_when_no_cover_src(self, tmp_path):
        paths = self._dirs(tmp_path)
        info = _book_info(cover="Images/frontcover.jpg")
        opf = render_content_opf(
            info,
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
        )
        assert 'content="img_frontcover"' in opf

    def test_cover_id_fallback_regex_without_leading_slash(self, tmp_path):
        paths = self._dirs(tmp_path)
        # No slash before the name => second regex branch matches "cover.png".
        info = _book_info(cover="cover.png")
        opf = render_content_opf(
            info,
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
        )
        assert 'content="img_cover"' in opf

    def test_cover_id_unmatched_pattern_kept_verbatim(self, tmp_path):
        paths = self._dirs(tmp_path)
        # cover with no "." anywhere => neither regex matches; cover_id kept as-is
        # (covers 297->301 false branch).
        info = _book_info(cover="coverwithoutdot")
        opf = render_content_opf(
            info,
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
        )
        assert 'content="coverwithoutdot"' in opf

    def test_no_cover_yields_empty_cover_meta(self, tmp_path):
        paths = self._dirs(tmp_path)
        info = _book_info(cover=None)
        opf = render_content_opf(
            info,
            [_chapter("ch01.html")],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
        )
        assert '<meta name="cover" content=""/>' in opf

    def test_no_chapters_yields_empty_guide_reference(self, tmp_path):
        paths = self._dirs(tmp_path)
        opf = render_content_opf(
            _book_info(),
            [],
            paths.styles,
            paths.images,
            paths.videos,
            fonts=[],
        )
        # first_chapter empty when no chapters; still renders.
        assert "<spine" in opf

    def test_missing_asset_dirs_handled(self, tmp_path):
        # css_dir / images_dir do not exist => is_dir() false branches.
        missing = tmp_path / "nope"
        opf = render_content_opf(
            _book_info(),
            [_chapter("ch01.html")],
            missing / "Styles",
            missing / "Images",
            missing / "Video",
            fonts=[],
        )
        assert "ch01.xhtml" in opf


class TestRenderTocNcx:
    @staticmethod
    def _client(json_return) -> MagicMock:
        client = MagicMock()
        client.get_json = AsyncMock(return_value=json_return)
        return client

    async def test_dict_with_children(self):
        data = {
            "children": [
                {"url": "ch01.html", "label": "Chapter 1", "id": "ch01"},
            ]
        }
        client = self._client(data)
        ncx = await render_toc_ncx(client, "https://api/toc", _book_info())
        assert "Chapter 1" in ncx
        assert "ch01.xhtml" in ncx
        # depth 1 => max-depth meta reflects it.
        assert 'content="1"' in ncx

    async def test_dict_with_results_key(self):
        data = {"results": [{"url": "ch01.html", "label": "C1", "id": "c1"}]}
        client = self._client(data)
        ncx = await render_toc_ncx(client, "https://api/toc", _book_info())
        assert "C1" in ncx

    async def test_top_level_list(self):
        data = [{"url": "ch01.html", "label": "Listed", "id": "l1"}]
        client = self._client(data)
        ncx = await render_toc_ncx(client, "https://api/toc", _book_info())
        assert "Listed" in ncx

    async def test_authors_joined_in_header(self):
        data = [{"url": "ch01.html", "label": "C", "id": "c"}]
        client = self._client(data)
        ncx = await render_toc_ncx(client, "https://api/toc", _book_info())
        assert "Ada Lovelace, Alan Turing" in ncx

    async def test_isbn_used_when_present(self):
        data = [{"url": "ch01.html", "label": "C", "id": "c"}]
        client = self._client(data)
        ncx = await render_toc_ncx(client, "https://api/toc", _book_info())
        assert "9781234567890" in ncx

    async def test_identifier_used_when_no_isbn(self):
        data = [{"url": "ch01.html", "label": "C", "id": "c"}]
        client = self._client(data)
        ncx = await render_toc_ncx(client, "https://api/toc", _book_info(isbn=""))
        assert "urn:orm:book:9999" in ncx

    async def test_api_error_wrapped_as_download_error(self):
        client = MagicMock()
        client.get_json = AsyncMock(side_effect=ApiError("boom"))
        with pytest.raises(DownloadError, match="Unable to retrieve book TOC"):
            await render_toc_ncx(client, "https://api/toc", _book_info())

    async def test_unexpected_format_raises_download_error(self):
        # A string is neither list nor dict => DownloadError.
        client = self._client("not a structure")
        with pytest.raises(DownloadError, match="Unexpected TOC response format"):
            await render_toc_ncx(client, "https://api/toc", _book_info())

    async def test_non_list_toc_data_raises_download_error(self):
        # dict whose "children" is a non-list (e.g. an error dict) hits the
        # `not isinstance(toc_list, list)` guard (lines 462-463).
        client = self._client({"children": {"error": "nope"}})
        with pytest.raises(DownloadError, match="TOC data is not a list"):
            await render_toc_ncx(client, "https://api/toc", _book_info())

    async def test_dict_without_known_keys_yields_empty_toc(self):
        # dict with no children/results => empty list, valid empty navmap.
        client = self._client({"unrelated": 1})
        ncx = await render_toc_ncx(client, "https://api/toc", _book_info())
        # max_depth defaults to 0 when no entries.
        assert 'content="0"' in ncx


class TestBuildEpubErrors:
    def test_oserror_wrapped_as_download_error(self, tmp_path, monkeypatch):
        paths = ensure_book_dirs(tmp_path / "ErrBook")
        (paths.oebps / "ch01.xhtml").write_text("<p/>", encoding="utf-8")

        def _boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("safaribooks.core.epub.zipfile.ZipFile", _boom)
        with pytest.raises(DownloadError, match="Failed to create EPUB archive"):
            build_epub(paths, tmp_path / "out.epub")

    def test_existing_epub_removed_before_rebuild(self, tmp_path):
        paths = ensure_book_dirs(tmp_path / "ReBook")
        (paths.oebps / "ch01.xhtml").write_text("<p/>", encoding="utf-8")
        out = tmp_path / "out.epub"
        out.write_text("stale", encoding="utf-8")  # pre-existing => unlink branch
        result = build_epub(paths, out)
        with zipfile.ZipFile(result) as zf:
            assert zf.namelist()[0] == "mimetype"

    def test_non_file_entries_and_old_epub_skipped(self, tmp_path):
        paths = ensure_book_dirs(tmp_path / "SkipBook")
        (paths.oebps / "ch01.xhtml").write_text("<p/>", encoding="utf-8")
        # An .epub file inside the tree must be excluded.
        (paths.oebps / "old.epub").write_bytes(b"old")
        result = build_epub(paths, tmp_path / "out.epub")
        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
        assert not any(n.endswith("old.epub") for n in names)
        # Directories (non-files) are not added as entries.
        assert "OEBPS" not in names
