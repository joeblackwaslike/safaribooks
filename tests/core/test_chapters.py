"""Tests for safaribooks.core.chapters — link helpers, TOC normalization, HTML parsing."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from lxml import html

from safaribooks.core.chapters import (
    fetch_chapter_html,
    find_cover_image,
    is_absolute_url,
    is_html_link,
    is_image_implied,
    is_image_link,
    is_possible_image,
    is_video_link,
    normalize_toc,
    parse_chapter_html,
    rewrite_link,
)
from safaribooks.core.exceptions import ApiError, ParsingError
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

    def test_link_empty_href_skipped(self):
        # A <link rel="stylesheet"> with no href should be skipped (line 294).
        root = self._make_html("<p>Content</p>", stylesheets='<link rel="stylesheet" />')
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=[],
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        assert result.discovered_css == []

    def test_link_protocol_relative_href(self):
        # href starting with // resolves against https: (line 296 true branch).
        link = '<link rel="stylesheet" href="//cdn.example.com/lib.css" />'
        root = self._make_html("<p>Content</p>", stylesheets=link)
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=[],
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        assert "https://cdn.example.com/lib.css" in result.discovered_css

    def test_link_already_known_not_rediscovered(self):
        # A <link> whose resolved URL is already known: covers 298->303 false branch.
        known = ["https://example.com/lib.css"]
        link = '<link rel="stylesheet" href="https://example.com/lib.css" />'
        root = self._make_html("<p>Content</p>", stylesheets=link)
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=known,
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        assert result.discovered_css == []
        # idx should be 0 since it's the first known entry.
        assert "Style00.css" in result.page_css

    def test_inline_style_preserved(self):
        root = self._make_html("<p>Content</p>")
        # Inject an inline <style> with content.
        head = root.xpath("//head")[0]
        style = html.fromstring("<style>p { color: red; }</style>")
        head.append(style)
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=[],
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        assert "color: red" in result.page_css

    def test_inline_style_data_template_promoted(self):
        root = self._make_html("<p>Content</p>")
        head = root.xpath("//head")[0]
        style = html.fromstring('<style data-template="body { margin: 0; }"></style>')
        head.append(style)
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=[],
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        assert "margin: 0" in result.page_css
        # data-template attribute should be removed from output.
        assert "data-template" not in result.page_css

    def test_svg_image_converted_to_img(self):
        body = (
            "<p>Content</p>"
            '<svg><g><image xlink:href="diagram.png" /></g></svg>'
        )
        raw = (
            "<html><head></head>"
            f'<body><div id="sbo-rt-content">{body}</div></body></html>'
        )
        root = html.fromstring(raw)
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=[],
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        # The SVG <image> should have become an <img> with rewritten src.
        assert "<img" in result.body_xhtml
        assert "Images/diagram.png" in result.body_xhtml

    def test_svg_image_without_href_left_alone(self):
        # An <image> element with no *href attribute hits the false branch
        # of `if href_attrs` (branch 322->320) and is left untouched.
        body = "<p>Content</p><svg><g><image width='10' /></g></svg>"
        raw = (
            "<html><head></head>"
            f'<body><div id="sbo-rt-content">{body}</div></body></html>'
        )
        root = html.fromstring(raw)
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=[],
            book_id=BOOK_ID,
            base_url="https://example.com",
        )
        # No conversion happened; no <img> tag was produced.
        assert "<img" not in result.body_xhtml

    def test_first_page_with_cover_image(self):
        body = '<img id="cover-image" src="cover.jpg" alt="cover" />'
        root = self._make_html(body)
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=[],
            book_id=BOOK_ID,
            base_url="https://example.com",
            first_page=True,
        )
        # Links are rewritten before cover detection, so src is normalized.
        assert result.cover_src == "Images/cover.jpg"
        assert 'id="Cover"' in result.body_xhtml
        assert "display:table" in result.page_css

    def test_first_page_without_cover_image(self):
        root = self._make_html("<p>Just text</p>")
        result = parse_chapter_html(
            root,
            chapter_stylesheets=[],
            known_css=[],
            book_id=BOOK_ID,
            base_url="https://example.com",
            first_page=True,
        )
        assert result.cover_src is None
        assert "Just text" in result.body_xhtml

    def test_inline_style_serialize_error_raises(self, monkeypatch):
        # Force html.tostring to fail while serializing the inline <style>
        # element, covering the except branch (lines 315-317).
        import safaribooks.core.chapters as chapters_mod
        from lxml import etree as _etree

        root = self._make_html("<p>Content</p>")
        head = root.xpath("//head")[0]
        head.append(html.fromstring("<style>p{}</style>"))

        def boom(*args, **kwargs):
            raise _etree.ParserError("style boom")

        monkeypatch.setattr(chapters_mod.html, "tostring", boom)
        with pytest.raises(ParsingError, match="Failed to serialize inline"):
            parse_chapter_html(
                root,
                chapter_stylesheets=[],
                known_css=[],
                book_id=BOOK_ID,
                base_url="https://example.com",
            )

    def test_body_serialize_error_raises(self, monkeypatch):
        # Force html.tostring to fail when serializing the chapter body,
        # covering the except branch (lines 364-366). No inline <style> here,
        # so the first tostring call is the body serialization.
        import safaribooks.core.chapters as chapters_mod
        from lxml import etree as _etree

        root = self._make_html("<p>Content</p>")

        def boom(*args, **kwargs):
            raise _etree.ParseError("body boom", None, 0, 0)

        monkeypatch.setattr(chapters_mod.html, "tostring", boom)
        with pytest.raises(ParsingError, match="Failed to serialize chapter body"):
            parse_chapter_html(
                root,
                chapter_stylesheets=[],
                known_css=[],
                book_id=BOOK_ID,
                base_url="https://example.com",
            )


class TestIsImageImplied:
    def test_cover_hint(self):
        assert is_image_implied("cover/thing") is True

    def test_images_hint(self):
        assert is_image_implied("path/images/x") is True

    def test_graphics_hint(self):
        assert is_image_implied("graphics/x") is True

    def test_no_hint(self):
        assert is_image_implied("chapter/text") is False


class TestIsPossibleImage:
    def test_real_image_extension(self):
        assert is_possible_image("fig.png") is True

    def test_implied_image_no_extension(self):
        assert is_possible_image("images/figure") is True

    def test_html_with_image_hint_is_not_image(self):
        # is_html_link short-circuits the implied path.
        assert is_possible_image("images/page.html") is False

    def test_plain_non_image(self):
        assert is_possible_image("data/file.txt") is False


class TestFindCoverImage:
    def test_direct_img_with_cover_id(self):
        root = html.fromstring('<html><body><img id="cover" src="c.jpg" /></body></html>')
        assert find_cover_image(root) == "c.jpg"

    def test_direct_img_with_cover_alt(self):
        root = html.fromstring(
            '<html><body><img alt="The Cover" src="c2.jpg" /></body></html>'
        )
        assert find_cover_image(root) == "c2.jpg"

    def test_direct_cover_img_without_src_returns_none(self):
        root = html.fromstring('<html><body><img id="cover" /></body></html>')
        assert find_cover_image(root) is None

    def test_img_inside_cover_div(self):
        root = html.fromstring(
            '<html><body><div class="cover-wrap"><img src="d.jpg" /></div></body></html>'
        )
        assert find_cover_image(root) == "d.jpg"

    def test_cover_div_img_without_src_returns_none(self):
        root = html.fromstring(
            '<html><body><div class="cover"><img /></div></body></html>'
        )
        assert find_cover_image(root) is None

    def test_img_inside_cover_anchor(self):
        root = html.fromstring(
            '<html><body><a name="cover"><img src="e.jpg" /></a></body></html>'
        )
        assert find_cover_image(root) == "e.jpg"

    def test_cover_anchor_img_without_src_returns_none(self):
        root = html.fromstring(
            '<html><body><a class="cover"><img /></a></body></html>'
        )
        assert find_cover_image(root) is None

    def test_no_cover_returns_none(self):
        root = html.fromstring("<html><body><img src='x.jpg' /></body></html>")
        assert find_cover_image(root) is None


class TestFetchChapterHtml:
    @staticmethod
    def _client(status_code: int, text: str):
        client = MagicMock()
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        client.get = AsyncMock(return_value=response)
        return client

    async def test_fetches_and_parses_html(self):
        client = self._client(200, "<html><body><p>Hi</p></body></html>")
        root = await fetch_chapter_html(client, "https://example.com/ch.html")
        assert root.xpath("//p")[0].text == "Hi"

    async def test_non_200_raises_api_error(self):
        client = self._client(404, "not found")
        with pytest.raises(ApiError, match="status 404"):
            await fetch_chapter_html(client, "https://example.com/ch.html")

    async def test_html_present_skips_html5parser_branch(self):
        # When the response already contains an <html> tag, the html5parser
        # fallback (line 146) is skipped — this is the working code path.
        client = self._client(
            200, "<html><body><p>Full document</p></body></html>"
        )
        root = await fetch_chapter_html(client, "https://example.com/ch.html")
        assert "Full document" in html.tostring(root, encoding="unicode")

    async def test_html_tag_match_is_case_insensitive(self):
        # Uppercase <HTML> should also satisfy the re.search and skip
        # the html5parser fallback.
        client = self._client(200, "<HTML><BODY><p>Caps</p></BODY></HTML>")
        root = await fetch_chapter_html(client, "https://example.com/ch.html")
        assert "Caps" in html.tostring(root, encoding="unicode")

    async def test_parse_error_raises_parsing_error(self):
        # An empty/whitespace body that lxml cannot parse raises ParsingError.
        # Force the parse failure path (lines 149-151) via an empty document.
        client = self._client(200, "<html></html>")
        # Patch html.fromstring to raise a parser error for this call.
        import safaribooks.core.chapters as chapters_mod
        from lxml import etree as _etree

        orig = chapters_mod.html.fromstring

        def boom(*args, **kwargs):
            raise _etree.ParserError("forced")

        chapters_mod.html.fromstring = boom
        try:
            with pytest.raises(ParsingError, match="Failed to parse chapter HTML"):
                await fetch_chapter_html(client, "https://example.com/ch.html")
        finally:
            chapters_mod.html.fromstring = orig
