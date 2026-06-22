"""Chapter HTML fetching, parsing, and body serialization."""

import re
from typing import Any

from lxml import etree, html
from lxml.html import html5parser as _html5parser

from safaribooks.core.api import ApiClient
from safaribooks.core.chapters import cover, css, urls
from safaribooks.core.constants import SAFARI_BASE_URL
from safaribooks.core.exceptions import ApiError, ParsingError
from safaribooks.core.models import ParseResult

_SRC_ATTR = "src"
_HTTP_OK = 200


def _register_lowercase_xpath() -> None:
    """Register a ``lower-case`` XPath function in the default namespace."""

    def lower_case(_ctx: Any, nodes: list[Any]) -> str:
        """XPath ``lower-case`` implementation operating on the first node."""
        if nodes:
            return str(nodes[0].lower())
        return ""

    ns = etree.FunctionNamespace(None)
    ns["lower-case"] = lower_case


async def fetch_chapter_html(client: ApiClient, url: str) -> html.HtmlElement:  # type: ignore[no-any-unimported]
    """Fetch raw chapter HTML from the API and parse it into an lxml tree.

    Parameters
    ----------
    client:
        Authenticated API client.
    url:
        The chapter content URL.

    Returns:
    -------
    HtmlElement
        Parsed HTML tree rooted at ``<html>``.

    Raises:
    ------
    ApiError
        When the HTTP request fails.
    ParsingError
        When the response cannot be parsed as HTML.

    """
    response = await client.get(url)
    if response.status_code != _HTTP_OK:
        msg = f"Failed to retrieve chapter HTML from {url} (status {response.status_code})"
        raise ApiError(msg)

    html_text = response.text
    try:
        if not re.search("<html", html_text, re.IGNORECASE):
            html_text = etree.tostring(_html5parser.fromstring(html_text), encoding="unicode")
        return html.fromstring(html_text, base_url=SAFARI_BASE_URL)
    except (etree.ParseError, etree.ParserError) as exc:
        msg = f"Failed to parse chapter HTML from {url}: {exc}"
        raise ParsingError(msg) from exc


def _convert_svg_images(root: html.HtmlElement) -> None:  # type: ignore[no-any-unimported]
    """Replace SVG ``<image>`` wrappers with plain ``<img>`` elements."""
    for img in root.xpath("//image"):
        href_attrs = [attr for attr in img.attrib if "href" in attr]
        if not href_attrs:
            continue
        svg_url = img.attrib.get(href_attrs[0])
        svg_root = img.getparent().getparent()
        new_img = svg_root.makeelement("img")
        new_img.attrib[_SRC_ATTR] = svg_url
        svg_root.remove(img.getparent())
        svg_root.append(new_img)


def _serialize_body(content_el: html.HtmlElement) -> str:  # type: ignore[no-any-unimported]
    """Serialize the chapter content element to an XHTML string."""
    try:
        return str(html.tostring(content_el, method="xml", encoding="unicode"))
    except (etree.ParseError, etree.ParserError) as exc:
        msg = f"Failed to serialize chapter body to XHTML: {exc}"
        raise ParsingError(msg) from exc


def _discover_videos(root: html.HtmlElement) -> list[str]:  # type: ignore[no-any-unimported]
    """Return the ``src`` values of all chapter ``<video>`` sources."""
    sources = root.xpath("//div[@id='sbo-rt-content']//video/source/@src")
    return [src for src in sources if src]


def _extract_content_element(  # type: ignore[no-any-unimported]
    root: html.HtmlElement,
    book_id: str,
) -> tuple[html.HtmlElement, list[str]]:
    """Return the ``#sbo-rt-content`` element and its video sources.

    Video sources are discovered *before* links are rewritten so the
    returned ``src`` values are the original (un-rewritten) URLs.
    """
    book_content = root.xpath("//div[@id='sbo-rt-content']")
    if not book_content:
        msg = "Book content element (#sbo-rt-content) not found in chapter HTML"
        raise ParsingError(msg)
    discovered_videos = _discover_videos(root)
    content_el = book_content[0]
    content_el.rewrite_links(lambda link: urls.rewrite_link(link, book_id))
    return content_el, discovered_videos


def parse_chapter_html(  # type: ignore[no-any-unimported]
    root: html.HtmlElement,
    chapter_stylesheets: list[str],
    known_css: list[str],
    book_id: str,
    base_url: str,
    *,
    first_page: bool = False,
) -> ParseResult:
    """Parse a chapter's HTML tree and extract assets.

    This is the refactored replacement for the legacy ``parse_html()``
    method.  Instead of mutating instance state, it returns a
    :class:`ParseResult` containing all discovered assets and the
    processed XHTML body.

    Parameters
    ----------
    root:
        Parsed HTML tree of the chapter.
    chapter_stylesheets:
        CSS URLs derived from the chapter's metadata (stylesheets +
        site_styles).
    known_css:
        Ordered list of CSS URLs already collected from previous
        chapters, in download order. Used as the stable index base when
        assigning ``Style##`` filenames, so the links emitted here line
        up with the files written by ``download_css``; callers should
        append ``discovered_css`` to this list after the call.
    book_id:
        The O'Reilly book identifier (for link rewriting).
    base_url:
        The book's web URL, used to resolve relative stylesheet ``href``
        values.
    first_page:
        If ``True``, attempt to detect a cover image and produce a
        dedicated cover page layout.

    Returns:
    -------
    ParseResult
        The parsed chapter output and all discovered assets.

    Raises:
    ------
    ParsingError
        When the chapter body cannot be found or serialized.

    """
    discovered_css: list[str] = []
    page_css = css._collect_page_css(
        root, chapter_stylesheets, known_css, base_url, discovered_css
    )

    _convert_svg_images(root)

    content_el, discovered_videos = _extract_content_element(root, book_id)
    page_css, content_el, cover_src = cover._maybe_apply_cover(
        content_el, page_css, first_page=first_page
    )

    return ParseResult(
        page_css=page_css,
        body_xhtml=_serialize_body(content_el),
        discovered_css=discovered_css,
        discovered_images=[],
        discovered_videos=discovered_videos,
        cover_src=cover_src,
    )
