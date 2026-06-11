"""Tests for safaribooks.core.chapters — link helpers, TOC normalization, HTML parsing."""


import pytest
from lxml import html

from safaribooks.core.chapters import (
    is_absolute_url,
    is_html_link,
    is_image_link,
    is_video_link,
    normalize_toc,
    parse_chapter_html,
    rewrite_link,
)
from safaribooks.core.exceptions import ParsingError
from safaribooks.core.models import TocEntry

BOOK_ID = "9781234567890"


class TestIsAbsoluteUrl:
    def test_https_is_absolute(self):
        assert is_absolute_url("https://example.com/page") is True

    def test_http_is_absolute(self):
        assert is_absolute_url("http://example.com/page") is True

    def test_relative_path_is_not_absolute(self):
        assert is_absolute_url("relative/path") is False

    def test_bare_filename_is_not_absolute(self):
        assert is_absolute_url("file.html") is False

    def test_fragment_only_is_not_absolute(self):
        assert is_absolute_url("#section") is False

    def test_empty_string_is_not_absolute(self):
        assert is_absolute_url("") is False


class TestIsImageLink:
    def test_png(self):
        assert is_image_link("img/figure.png") is True

    def test_jpg(self):
        assert is_image_link("cover.jpg") is True

    def test_jpeg(self):
        assert is_image_link("photo.jpeg") is True

    def test_gif(self):
        assert is_image_link("anim.gif") is True

    def test_svg_is_not_image(self):
        assert is_image_link("diagram.svg") is False

    def test_html_is_not_image(self):
        assert is_image_link("chapter.html") is False

    def test_no_extension(self):
        assert is_image_link("noext") is False


class TestIsVideoLink:
    def test_mp4(self):
        assert is_video_link("video/clip.mp4") is True

    def test_mp4_with_query_string(self):
        assert is_video_link("clip.mp4?token=abc") is True

    def test_html_is_not_video(self):
        assert is_video_link("page.html") is False

    def test_png_is_not_video(self):
        assert is_video_link("image.png") is False


class TestIsHtmlLink:
    def test_html(self):
        assert is_html_link("chapter.html") is True

    def test_xhtml(self):
        assert is_html_link("chapter.xhtml") is True

    def test_htm(self):
        assert is_html_link("page.htm") is True

    def test_html_with_fragment(self):
        assert is_html_link("chapter.html#section1") is True

    def test_html_with_query(self):
        assert is_html_link("chapter.html?foo=bar") is True

    def test_png_is_not_html(self):
        assert is_html_link("image.png") is False


class TestRewriteLink:
    def test_empty_link_unchanged(self):
        assert rewrite_link("", BOOK_ID) == ""

    def test_mailto_unchanged(self):
        assert rewrite_link("mailto:test@example.com", BOOK_ID) == "mailto:test@example.com"

    def test_relative_video_link(self):
        result = rewrite_link("media/clip.mp4", BOOK_ID)
        assert result == "Video/clip.mp4"

    def test_relative_image_link(self):
        result = rewrite_link("images/fig1.png", BOOK_ID)
        assert result == "Images/fig1.png"

    def test_relative_html_to_xhtml(self):
        result = rewrite_link("chapter2.html", BOOK_ID)
        assert result == "chapter2.xhtml"

    def test_absolute_same_book_stripped_to_relative(self):
        link = f"https://learning.oreilly.com/api/v2/epubs/urn:orm:book:{BOOK_ID}/files/ch02.html"
        result = rewrite_link(link, BOOK_ID)
        assert "https://" not in result
        assert result == "/files/ch02.xhtml"

    def test_absolute_external_link_unchanged(self):
        link = "https://en.wikipedia.org/wiki/Python"
        result = rewrite_link(link, BOOK_ID)
        assert result == link

    def test_relative_image_in_cover_path(self):
        result = rewrite_link("cover/img.jpg", BOOK_ID)
        assert result == "Images/img.jpg"


class TestNormalizeToc:
    def test_single_flat_entry(self):
        raw = [{"url": "ch01.html", "label": "Chapter 1", "id": "ch01"}]
        result = normalize_toc(raw)
        assert len(result) == 1
        assert isinstance(result[0], TocEntry)
        assert result[0].label == "Chapter 1"
        assert result[0].href == "ch01.html"
        assert result[0].depth == 0

    def test_entry_with_fragment(self):
        raw = [{"url": "ch01.html#intro", "label": "Intro", "id": "intro"}]
        result = normalize_toc(raw)
        assert result[0].fragment == "intro"

    def test_entry_uses_title_fallback(self):
        raw = [{"href": "ch01.html", "title": "Chapter 1 Title"}]
        result = normalize_toc(raw)
        assert result[0].label == "Chapter 1 Title"

    def test_recursive_children(self):
        raw = [
            {
                "url": "ch01.html",
                "label": "Chapter 1",
                "id": "ch01",
                "children": [
                    {"url": "ch01.html#s1", "label": "Section 1", "id": "s1"},
                    {"url": "ch01.html#s2", "label": "Section 2", "id": "s2"},
                ],
            }
        ]
        result = normalize_toc(raw)
        assert len(result) == 1
        assert len(result[0].children) == 2
        assert result[0].children[0].depth == 1
        assert result[0].children[1].label == "Section 2"

    def test_auto_generated_id(self):
        raw = [{"url": "ch01.html", "label": "No ID"}]
        result = normalize_toc(raw)
        assert result[0].id == "toc_0_0"

    def test_encoded_url_decoded(self):
        raw = [{"url": "ch%2001.html", "label": "Encoded", "id": "enc"}]
        result = normalize_toc(raw)
        assert result[0].href == "ch 01.html"

    def test_empty_list(self):
        result = normalize_toc([])
        assert result == []


class TestParseChapterHtml:
    @staticmethod
    def _make_html(body_content: str, *, stylesheets: str = "") -> html.HtmlElement:
        raw = (
            f"<html><head>{stylesheets}</head>"
            f'<body><div id="sbo-rt-content">{body_content}</div></body></html>'
        )
        return html.fromstring(raw)

    def test_basic_body_extraction(self):
        root = self._make_html("<p>Hello World</p>")
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=set(),
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        assert "<p>Hello World</p>" in result.body_xhtml
        assert result.discovered_css == []
        assert result.cover_src is None

    def test_discovers_new_css(self):
        root = self._make_html("<p>Content</p>")
        result = parse_chapter_html(
            root,
            chapter_stylesheets=["https://example.com/style.css"],
            known_css=set(),
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        assert "https://example.com/style.css" in result.discovered_css
        assert "Style00.css" in result.page_css

    def test_known_css_not_rediscovered(self):
        root = self._make_html("<p>Content</p>")
        known = {"https://example.com/style.css"}
        result = parse_chapter_html(
            root,
            chapter_stylesheets=["https://example.com/style.css"],
            known_css=known,
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        assert result.discovered_css == []

    def test_discovers_video_sources(self):
        root = self._make_html('<video><source src="clip.mp4" type="video/mp4"/></video>')
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=set(),
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        assert "clip.mp4" in result.discovered_videos

    def test_missing_content_div_raises(self):
        root = html.fromstring("<html><body><p>No sbo div</p></body></html>")
        with pytest.raises(ParsingError, match="sbo-rt-content"):
            parse_chapter_html(
                root,
                chapter_stylesheets=[],
                known_css=set(),
                book_id=BOOK_ID,
                base_url="https://example.com",
            )

    def test_link_elements_discovered(self):
        stylesheet_link = '<link rel="stylesheet" href="https://cdn.example.com/lib.css" />'
        root = self._make_html("<p>Content</p>", stylesheets=stylesheet_link)
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=set(),
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        assert any("cdn.example.com" in url for url in result.discovered_css)
