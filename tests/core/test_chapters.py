"""Tests for safaribooks.core.chapters — link helpers, TOC normalization, HTML parsing."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from lxml import etree, html

from safaribooks.core import chapters
from safaribooks.core.exceptions import ApiError, ParsingError
from safaribooks.core.models import TocEntry

BOOK_ID = "9781234567890"

_BASE_URL = "https://example.com"
_STYLE_URL = "https://example.com/style.css"
_HTTP_OK = 200
_HTTP_NOT_FOUND = 404


def _make_html(body_content: str, *, stylesheets: str = "") -> html.HtmlElement:
    raw = (
        f"<html><head>{stylesheets}</head>"
        f'<body><div id="sbo-rt-content">{body_content}</div></body></html>'
    )
    return html.fromstring(raw)


def _make_raw_html(body_content: str) -> html.HtmlElement:
    raw = f'<html><head></head><body><div id="sbo-rt-content">{body_content}</div></body></html>'
    return html.fromstring(raw)


def _parse(root: html.HtmlElement, **overrides):
    kwargs = {
        "chapter_stylesheets": [],
        "known_css": set(),
        "book_id": BOOK_ID,
        "base_url": _BASE_URL,
    }
    kwargs.update(overrides)
    return chapters.parse_chapter_html(root, **kwargs)


def _cover(markup: str):
    return chapters.find_cover_image(html.fromstring(markup))


def _make_mock_client(status_code: int, text: str):
    client = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    client.get = AsyncMock(return_value=response)
    return client


def _raise_parser_error(*args, **kwargs):
    raise etree.ParserError("forced parser error")


def _raise_parse_error(*args, **kwargs):
    raise etree.ParseError("forced parse error", None, 0, 0)


class TestIsAbsoluteUrl:
    def test_https_is_absolute(self):
        assert chapters.is_absolute_url("https://example.com/page") is True

    def test_http_is_absolute(self):
        assert chapters.is_absolute_url("http://example.com/page") is True

    def test_relative_path_is_not_absolute(self):
        assert chapters.is_absolute_url("relative/path") is False

    def test_bare_filename_is_not_absolute(self):
        assert chapters.is_absolute_url("file.html") is False

    def test_fragment_only_is_not_absolute(self):
        assert chapters.is_absolute_url("#section") is False

    def test_empty_string_is_not_absolute(self):
        assert chapters.is_absolute_url("") is False


class TestIsImageLink:
    def test_png(self):
        assert chapters.is_image_link("img/figure.png") is True

    def test_jpg(self):
        assert chapters.is_image_link("cover.jpg") is True

    def test_jpeg(self):
        assert chapters.is_image_link("photo.jpeg") is True

    def test_gif(self):
        assert chapters.is_image_link("anim.gif") is True

    def test_svg_is_not_image(self):
        assert chapters.is_image_link("diagram.svg") is False

    def test_html_is_not_image(self):
        assert chapters.is_image_link("chapter.html") is False

    def test_no_extension(self):
        assert chapters.is_image_link("noext") is False


class TestIsVideoLink:
    def test_mp4(self):
        assert chapters.is_video_link("video/clip.mp4") is True

    def test_mp4_with_query_string(self):
        assert chapters.is_video_link("clip.mp4?token=abc") is True

    def test_html_is_not_video(self):
        assert chapters.is_video_link("page.html") is False

    def test_png_is_not_video(self):
        assert chapters.is_video_link("image.png") is False


class TestIsHtmlLink:
    def test_html(self):
        assert chapters.is_html_link("chapter.html") is True

    def test_xhtml(self):
        assert chapters.is_html_link("chapter.xhtml") is True

    def test_htm(self):
        assert chapters.is_html_link("page.htm") is True

    def test_html_with_fragment(self):
        assert chapters.is_html_link("chapter.html#section1") is True

    def test_html_with_query(self):
        assert chapters.is_html_link("chapter.html?foo=bar") is True

    def test_png_is_not_html(self):
        assert chapters.is_html_link("image.png") is False


class TestRewriteLinkRelative:
    def test_relative_video_link(self):
        assert chapters.rewrite_link("media/clip.mp4", BOOK_ID) == "Video/clip.mp4"

    def test_relative_image_link(self):
        assert chapters.rewrite_link("images/fig1.png", BOOK_ID) == "Images/fig1.png"

    def test_relative_html_to_xhtml(self):
        assert chapters.rewrite_link("chapter2.html", BOOK_ID) == "chapter2.xhtml"

    def test_relative_image_in_cover_path(self):
        assert chapters.rewrite_link("cover/img.jpg", BOOK_ID) == "Images/img.jpg"


class TestRewriteLinkSpecial:
    def test_empty_link_unchanged(self):
        assert chapters.rewrite_link("", BOOK_ID) == ""

    def test_mailto_unchanged(self):
        assert (
            chapters.rewrite_link("mailto:test@example.com", BOOK_ID) == "mailto:test@example.com"
        )

    def test_absolute_same_book_stripped_to_relative(self):
        link = f"https://learning.oreilly.com/api/v2/epubs/urn:orm:book:{BOOK_ID}/files/ch02.html"
        rewritten = chapters.rewrite_link(link, BOOK_ID)
        assert "https://" not in rewritten
        assert rewritten == "/files/ch02.xhtml"

    def test_absolute_external_link_unchanged(self):
        link = "https://en.wikipedia.org/wiki/Python"
        assert chapters.rewrite_link(link, BOOK_ID) == link


class TestNormalizeToc:
    def test_single_flat_entry(self):
        raw = [{"url": "ch01.html", "label": "Chapter 1", "id": "ch01"}]
        entries = chapters.normalize_toc(raw)
        first = entries[0]
        assert len(entries) == 1
        assert isinstance(first, TocEntry)
        assert first.label == "Chapter 1"
        assert first.href == "ch01.html"
        assert first.depth == 0

    def test_entry_with_fragment(self):
        raw = [{"url": "ch01.html#intro", "label": "Intro", "id": "intro"}]
        entries = chapters.normalize_toc(raw)
        assert entries[0].fragment == "intro"

    def test_entry_uses_title_fallback(self):
        raw = [{"href": "ch01.html", "title": "Chapter 1 Title"}]
        entries = chapters.normalize_toc(raw)
        assert entries[0].label == "Chapter 1 Title"

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
        entries = chapters.normalize_toc(raw)
        first = entries[0]
        assert len(entries) == 1
        assert len(first.children) == 2
        assert first.children[0].depth == 1
        assert first.children[1].label == "Section 2"

    def test_auto_generated_id(self):
        raw = [{"url": "ch01.html", "label": "No ID"}]
        entries = chapters.normalize_toc(raw)
        assert entries[0].id == "toc_0_0"

    def test_encoded_url_decoded(self):
        raw = [{"url": "ch%2001.html", "label": "Encoded", "id": "enc"}]
        entries = chapters.normalize_toc(raw)
        assert entries[0].href == "ch 01.html"

    def test_empty_list(self):
        assert chapters.normalize_toc([]) == []


class TestParseChapterBody:
    def test_basic_body_extraction(self):
        root = _make_html("<p>Hello World</p>")
        parsed = _parse(root)
        assert "<p>Hello World</p>" in parsed.body_xhtml
        assert parsed.discovered_css == []
        assert parsed.cover_src is None

    def test_discovers_video_sources(self):
        root = _make_html('<video><source src="clip.mp4" type="video/mp4"/></video>')
        parsed = _parse(root)
        assert "clip.mp4" in parsed.discovered_videos

    def test_missing_content_div_raises(self):
        root = html.fromstring("<html><body><p>No sbo div</p></body></html>")
        with pytest.raises(ParsingError, match="sbo-rt-content"):
            _parse(root)

    def test_svg_image_converted_to_img(self):
        body = '<p>Content</p><svg><g><image xlink:href="diagram.png" /></g></svg>'
        root = _make_raw_html(body)
        parsed = _parse(root)
        # The SVG <image> should have become an <img> with rewritten src.
        assert "<img" in parsed.body_xhtml
        assert "Images/diagram.png" in parsed.body_xhtml

    def test_svg_image_without_href_left_alone(self):
        # An <image> element with no *href attribute hits the false branch
        # of `if href_attrs` (branch 322->320) and is left untouched.
        body = "<p>Content</p><svg><g><image width='10' /></g></svg>"
        root = _make_raw_html(body)
        parsed = _parse(root)
        # No conversion happened; no <img> tag was produced.
        assert "<img" not in parsed.body_xhtml


class TestParseChapterCss:
    def test_discovers_new_css(self):
        root = _make_html("<p>Content</p>")
        parsed = _parse(root, chapter_stylesheets=[_STYLE_URL])
        assert _STYLE_URL in parsed.discovered_css
        assert "Style00.css" in parsed.page_css

    def test_known_css_not_rediscovered(self):
        root = _make_html("<p>Content</p>")
        parsed = _parse(root, chapter_stylesheets=[_STYLE_URL], known_css={_STYLE_URL})
        assert parsed.discovered_css == []

    def test_link_elements_discovered(self):
        stylesheet_link = '<link rel="stylesheet" href="https://cdn.example.com/lib.css" />'
        root = _make_html("<p>Content</p>", stylesheets=stylesheet_link)
        parsed = _parse(root)
        assert any("cdn.example.com" in url for url in parsed.discovered_css)

    def test_link_empty_href_skipped(self):
        # A <link rel="stylesheet"> with no href should be skipped (line 294).
        root = _make_html("<p>Content</p>", stylesheets='<link rel="stylesheet" />')
        parsed = _parse(root, known_css=[])
        assert parsed.discovered_css == []

    def test_link_protocol_relative_href(self):
        # href starting with // resolves against https: (line 296 true branch).
        link = '<link rel="stylesheet" href="//cdn.example.com/lib.css" />'
        root = _make_html("<p>Content</p>", stylesheets=link)
        parsed = _parse(root, known_css=[])
        assert "https://cdn.example.com/lib.css" in parsed.discovered_css

    def test_link_already_known_not_rediscovered(self):
        # A <link> whose resolved URL is already known: covers 298->303 false branch.
        link = '<link rel="stylesheet" href="https://example.com/lib.css" />'
        root = _make_html("<p>Content</p>", stylesheets=link)
        parsed = _parse(root, known_css=["https://example.com/lib.css"])
        assert parsed.discovered_css == []
        # idx should be 0 since it's the first known entry.
        assert "Style00.css" in parsed.page_css


class TestParseChapterInlineStyle:
    def test_inline_style_preserved(self):
        root = _make_html("<p>Content</p>")
        # Inject an inline <style> with content.
        head = root.xpath("//head")[0]
        head.append(html.fromstring("<style>p { color: red; }</style>"))
        parsed = _parse(root, known_css=[])
        assert "color: red" in parsed.page_css

    def test_inline_style_data_template_promoted(self):
        root = _make_html("<p>Content</p>")
        head = root.xpath("//head")[0]
        head.append(html.fromstring('<style data-template="body { margin: 0; }"></style>'))
        parsed = _parse(root, known_css=[])
        assert "margin: 0" in parsed.page_css
        # data-template attribute should be removed from output.
        assert "data-template" not in parsed.page_css

    def test_inline_style_serialize_error_raises(self, monkeypatch):
        # Force html.tostring to fail while serializing the inline <style>
        # element, covering the except branch (lines 315-317).
        root = _make_html("<p>Content</p>")
        head = root.xpath("//head")[0]
        head.append(html.fromstring("<style>p{}</style>"))
        monkeypatch.setattr(chapters.html, "tostring", _raise_parser_error)
        with pytest.raises(ParsingError, match="Failed to serialize inline"):
            _parse(root, known_css=[])

    def test_body_serialize_error_raises(self, monkeypatch):
        # Force html.tostring to fail when serializing the chapter body,
        # covering the except branch (lines 364-366). No inline <style> here,
        # so the first tostring call is the body serialization.
        root = _make_html("<p>Content</p>")
        monkeypatch.setattr(chapters.html, "tostring", _raise_parse_error)
        with pytest.raises(ParsingError, match="Failed to serialize chapter body"):
            _parse(root, known_css=[])


class TestParseChapterCover:
    def test_first_page_with_cover_image(self):
        body = '<img id="cover-image" src="cover.jpg" alt="cover" />'
        root = _make_html(body)
        parsed = _parse(root, known_css=[], first_page=True)
        # Links are rewritten before cover detection, so src is normalized.
        assert parsed.cover_src == "Images/cover.jpg"
        assert 'id="Cover"' in parsed.body_xhtml
        assert "display:table" in parsed.page_css

    def test_first_page_without_cover_image(self):
        root = _make_html("<p>Just text</p>")
        parsed = _parse(root, known_css=[], first_page=True)
        assert parsed.cover_src is None
        assert "Just text" in parsed.body_xhtml


class TestIsImageImplied:
    def test_cover_hint(self):
        assert chapters.is_image_implied("cover/thing") is True

    def test_images_hint(self):
        assert chapters.is_image_implied("path/images/x") is True

    def test_graphics_hint(self):
        assert chapters.is_image_implied("graphics/x") is True

    def test_no_hint(self):
        assert chapters.is_image_implied("chapter/text") is False


class TestIsPossibleImage:
    def test_real_image_extension(self):
        assert chapters.is_possible_image("fig.png") is True

    def test_implied_image_no_extension(self):
        assert chapters.is_possible_image("images/figure") is True

    def test_html_with_image_hint_is_not_image(self):
        # is_html_link short-circuits the implied path.
        assert chapters.is_possible_image("images/page.html") is False

    def test_plain_non_image(self):
        assert chapters.is_possible_image("data/file.txt") is False


class TestFindCoverImageDirect:
    def test_direct_img_with_cover_id(self):
        assert _cover('<html><body><img id="cover" src="c.jpg" /></body></html>') == "c.jpg"

    def test_direct_img_with_cover_alt(self):
        markup = '<html><body><img alt="The Cover" src="c2.jpg" /></body></html>'
        assert _cover(markup) == "c2.jpg"

    def test_direct_cover_img_without_src_none(self):
        assert _cover('<html><body><img id="cover" /></body></html>') is None

    def test_no_cover_returns_none(self):
        assert _cover("<html><body><img src='x.jpg' /></body></html>") is None


class TestFindCoverImageNested:
    def test_img_inside_cover_div(self):
        markup = '<html><body><div class="cover-wrap"><img src="d.jpg" /></div></body></html>'
        assert _cover(markup) == "d.jpg"

    def test_cover_div_img_without_src_none(self):
        markup = '<html><body><div class="cover"><img /></div></body></html>'
        assert _cover(markup) is None

    def test_img_inside_cover_anchor(self):
        markup = '<html><body><a name="cover"><img src="e.jpg" /></a></body></html>'
        assert _cover(markup) == "e.jpg"

    def test_cover_anchor_img_without_src_none(self):
        markup = '<html><body><a class="cover"><img /></a></body></html>'
        assert _cover(markup) is None


class TestFetchChapterHtml:
    async def test_fetches_and_parses_html(self):
        client = _make_mock_client(_HTTP_OK, "<html><body><p>Hi</p></body></html>")
        root = await chapters.fetch_chapter_html(client, "https://example.com/ch.html")
        assert root.xpath("//p")[0].text == "Hi"

    async def test_non_ok_status_raises_api_error(self):
        client = _make_mock_client(_HTTP_NOT_FOUND, "not found")
        with pytest.raises(ApiError, match="status 404"):
            await chapters.fetch_chapter_html(client, "https://example.com/ch.html")

    async def test_html_present_skips_html5parser_branch(self):
        # When the response already contains an <html> tag, the html5parser
        # fallback (line 146) is skipped — this is the working code path.
        client = _make_mock_client(_HTTP_OK, "<html><body><p>Full document</p></body></html>")
        root = await chapters.fetch_chapter_html(client, "https://example.com/ch.html")
        assert "Full document" in html.tostring(root, encoding="unicode")

    async def test_html_tag_match_is_case_insensitive(self):
        # Uppercase <HTML> should also satisfy the re.search and skip
        # the html5parser fallback.
        client = _make_mock_client(_HTTP_OK, "<HTML><BODY><p>Caps</p></BODY></HTML>")
        root = await chapters.fetch_chapter_html(client, "https://example.com/ch.html")
        assert "Caps" in html.tostring(root, encoding="unicode")

    async def test_fragment_without_html_tag_parses(self):
        # A bare fragment (no <html> tag) must go through the html5parser
        # fallback without crashing. Previously this raised AttributeError
        # because lxml.html exposes html5parser only as a submodule.
        client = _make_mock_client(_HTTP_OK, "<p>Just a fragment</p>")
        root = await chapters.fetch_chapter_html(client, "https://example.com/ch.html")
        assert "Just a fragment" in html.tostring(root, encoding="unicode")

    async def test_parse_error_raises_parsing_error(self, monkeypatch):
        # An empty/whitespace body that lxml cannot parse raises ParsingError.
        # Force the parse failure path (lines 149-151) via a patched parser.
        client = _make_mock_client(_HTTP_OK, "<html></html>")
        monkeypatch.setattr(chapters.html, "fromstring", _raise_parser_error)
        with pytest.raises(ParsingError, match="Failed to parse chapter HTML"):
            await chapters.fetch_chapter_html(client, "https://example.com/ch.html")
