"""HTML parsing, link processing, and TOC normalization for chapters."""

import logging
import pathlib
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from lxml import etree, html
from lxml.html import html5parser as _html5parser

from safaribooks.core.api import ApiClient
from safaribooks.core.constants import SAFARI_BASE_URL
from safaribooks.core.exceptions import ApiError, ParsingError
from safaribooks.core.models import ParseResult, TocEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Image / video / link file extensions
# ---------------------------------------------------------------------------
_IMAGE_EXTENSIONS: frozenset[str] = frozenset(("jpg", "jpeg", "png", "gif"))
_VIDEO_EXTENSIONS: frozenset[str] = frozenset(("mp4",))
_HTML_EXTENSIONS: frozenset[str] = frozenset(("html", "xhtml", "htm"))
_IMAGE_PATH_HINTS: tuple[str, ...] = ("cover", "images", "graphics")

# Repeated string literals (extracted to satisfy WPS226).
_FRAGMENT_SEP = "#"
_QUERY_SEP = "?"
_SRC_ATTR = "src"

# HTTP status / serialization constants.
_HTTP_OK = 200
_NEWLINE = "\n"


# ---------------------------------------------------------------------------
# URL classification helpers
# ---------------------------------------------------------------------------


def is_absolute_url(url: str) -> bool:
    """Return ``True`` if *url* has a network location (scheme + host)."""
    return bool(urlparse(url).netloc)


def is_image_link(url: str) -> bool:
    """Return ``True`` if *url* points to a known image extension."""
    return pathlib.Path(url).suffix[1:].lower() in _IMAGE_EXTENSIONS


def _strip_query_and_fragment(url: str) -> str:
    """Return *url* without its query string or fragment identifier."""
    without_query = url.split(_QUERY_SEP)[0]
    return without_query.split(_FRAGMENT_SEP)[0]


def is_video_link(url: str) -> bool:
    """Return ``True`` if *url* points to a known video extension."""
    clean = _strip_query_and_fragment(url)
    return pathlib.Path(clean).suffix[1:].lower() in _VIDEO_EXTENSIONS


def is_html_link(url: str) -> bool:
    """Return ``True`` if *url* points to a known HTML extension."""
    clean = _strip_query_and_fragment(url)
    return pathlib.Path(clean).suffix[1:].lower() in _HTML_EXTENSIONS


def is_image_implied(url: str) -> bool:
    """Return ``True`` if *url* contains path hints suggesting an image."""
    return any(hint in url for hint in _IMAGE_PATH_HINTS)


def is_possible_image(url: str) -> bool:
    """Return ``True`` if *url* is either an image link or an implied image."""
    return is_image_link(url) or (not is_html_link(url) and is_image_implied(url))


# ---------------------------------------------------------------------------
# Link rewriting
# ---------------------------------------------------------------------------


def rewrite_link(link: str, book_id: str) -> str:
    """Rewrite a chapter-internal link for EPUB packaging.

    Relative video links become ``Video/<filename>``, relative image
    links become ``Images/<filename>``, and HTML links get their
    extension changed to ``.xhtml``.  Absolute links that contain the
    *book_id* are recursively rewritten as relative.

    Parameters
    ----------
    link:
        The original ``href`` or ``src`` attribute value.
    book_id:
        The O'Reilly book identifier for detecting self-references.

    Returns:
    -------
    str
        The rewritten link.

    """
    if not link or link.startswith("mailto"):
        return link

    if is_absolute_url(link):
        # Absolute link that references the same book — strip and recurse.
        if book_id in link:
            return rewrite_link(link.split(book_id)[-1], book_id)
        return link

    return _rewrite_relative_link(link)


def _rewrite_relative_link(link: str) -> str:
    """Rewrite a relative chapter link to its EPUB-local equivalent."""
    filename = link.split("/")[-1]
    if is_video_link(link):
        return f"Video/{filename}"
    if is_possible_image(link):
        return f"Images/{filename}"
    return link.replace(".html", ".xhtml")


# ---------------------------------------------------------------------------
# Chapter HTML fetching
# ---------------------------------------------------------------------------


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

    try:
        return _parse_html_text(response.text)
    except (etree.ParseError, etree.ParserError) as exc:
        msg = f"Failed to parse chapter HTML from {url}: {exc}"
        raise ParsingError(msg) from exc


def _parse_html_text(html_text: str) -> html.HtmlElement:  # type: ignore[no-any-unimported]
    """Parse raw chapter text into an lxml tree, wrapping fragments in ``<html>``."""
    if not re.search("<html", html_text, re.IGNORECASE):
        html_text = etree.tostring(_html5parser.fromstring(html_text), encoding="unicode")
    return html.fromstring(html_text, base_url=SAFARI_BASE_URL)


# ---------------------------------------------------------------------------
# Cover detection
# ---------------------------------------------------------------------------

# XPath predicate for case-insensitive "cover" matching.
_COVER_ATTR_PRED = (
    "contains(lower-case(@id), 'cover') or "
    "contains(lower-case(@class), 'cover') or "
    "contains(lower-case(@name), 'cover') or "
    "contains(lower-case(@src), 'cover')"
)


def _xpath_lower_case(_ctx: Any, nodes: list[Any]) -> str:
    """XPath ``lower-case`` implementation operating on the first node."""
    if nodes:
        return str(nodes[0].lower())
    return ""


def _register_lowercase_xpath() -> None:
    """Register a ``lower-case`` XPath function in the default namespace."""
    ns = etree.FunctionNamespace(None)
    ns["lower-case"] = _xpath_lower_case


def _first_img_src(elements: list[Any]) -> str | None:
    """Return the ``src`` of the first element in *elements*, if present."""
    if not elements:
        return None
    src_value = elements[0].attrib.get(_SRC_ATTR)
    return str(src_value) if src_value else None


def find_cover_image(root: html.HtmlElement) -> str | None:  # type: ignore[no-any-unimported]
    """Find a cover ``<img>`` element in *root* and return its ``src``.

    Searches ``<img>`` tags, ``<div>`` wrappers, and ``<a>`` wrappers
    whose attributes contain the word "cover".

    Parameters
    ----------
    root:
        Parsed HTML element tree to search.

    Returns:
    -------
    str | None
        The ``src`` attribute of the first matching ``<img>``, or
        ``None`` if no cover image is found.

    """
    _register_lowercase_xpath()

    cover_pred = _COVER_ATTR_PRED
    alt_pred = f"{cover_pred} or contains(lower-case(@alt), 'cover')"

    # Direct <img> with cover attributes.
    images = root.xpath(f"//img[{alt_pred}]")
    if images:
        return _first_img_src(images)

    # <img> inside a <div> with cover attributes.
    divs = root.xpath(f"//div[{cover_pred}]//img")
    if divs:
        return _first_img_src(divs)

    # <img> inside an <a> with cover attributes.
    anchors = root.xpath(f"//a[{cover_pred}]//img")
    if anchors:
        return _first_img_src(anchors)

    return None


# ---------------------------------------------------------------------------
# Chapter HTML parsing (the critical refactored method)
# ---------------------------------------------------------------------------

_COVER_PAGE_CSS = (
    "<style>"
    "body{display:table;position:absolute;margin:0!important;"
    "height:100%;width:100%;}"
    "#Cover{display:table-cell;vertical-align:middle;"
    "text-align:center;}"
    "img{height:90vh;margin-left:auto;margin-right:auto;}"
    "</style>"
)


def _style_link_tag(idx: int) -> str:
    """Return the ``<link>`` tag referencing the ``Style##.css`` at *idx*."""
    return f'<link href="Styles/Style{idx:02d}.css" rel="stylesheet" type="text/css" />{_NEWLINE}'


def _register_css(css_url: str, all_css: list[str], discovered_css: list[str]) -> int:
    """Register *css_url*, returning its stable index in *all_css*."""
    if css_url not in all_css:
        all_css.append(css_url)
        discovered_css.append(css_url)
        logger.debug("Found new CSS: %s", css_url)
    return all_css.index(css_url)


def _collect_link_css(
    chapter_stylesheets: list[str],
    all_css: list[str],
    discovered_css: list[str],
) -> str:
    """Build ``<link>`` tags for chapter-metadata stylesheets."""
    tags = [
        _style_link_tag(_register_css(css_url, all_css, discovered_css))
        for css_url in chapter_stylesheets
    ]
    return "".join(tags)


def _resolve_css_href(href: str, base_url: str) -> str:
    """Resolve a stylesheet ``href`` against *base_url* (or the https scheme)."""
    if href.startswith("//"):
        return urljoin("https:", href)
    return urljoin(base_url, href)


def _collect_html_link_css(  # type: ignore[no-any-unimported]
    root: html.HtmlElement,
    base_url: str,
    all_css: list[str],
    discovered_css: list[str],
) -> str:
    """Build ``<link>`` tags for in-page ``<link rel="stylesheet">`` elements."""
    tags: list[str] = []
    for link_el in root.xpath("//link[@rel='stylesheet']"):
        href = link_el.attrib.get("href", "")
        if not href:
            continue
        css_url = _resolve_css_href(href, base_url)
        tags.append(_style_link_tag(_register_css(css_url, all_css, discovered_css)))
    return "".join(tags)


def _collect_inline_css(root: html.HtmlElement) -> str:  # type: ignore[no-any-unimported]
    """Serialize inline ``<style>`` elements, applying any data templates."""
    fragments: list[str] = []
    for css_el in root.xpath("//style"):
        data_tpl = css_el.attrib.get("data-template", "")
        if data_tpl:
            css_el.text = data_tpl
            css_el.attrib.pop("data-template")
        try:
            serialized = html.tostring(css_el, method="xml", encoding="unicode")
        except (etree.ParseError, etree.ParserError) as exc:
            msg = f"Failed to serialize inline <style>: {exc}"
            raise ParsingError(msg) from exc
        fragments.append(f"{serialized}{_NEWLINE}")
    return "".join(fragments)


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


def _build_cover_page(cover_img_src: str) -> tuple[str, html.HtmlElement]:  # type: ignore[no-any-unimported]
    """Build the dedicated cover-page CSS and content element."""
    cover_html = html.fromstring('<div id="Cover"></div>')
    cover_div = cover_html.xpath("//div")[0]
    cover_img = cover_div.makeelement("img")
    cover_img.attrib[_SRC_ATTR] = cover_img_src
    cover_div.append(cover_img)
    return _COVER_PAGE_CSS, cover_html


def _serialize_body(content_el: html.HtmlElement) -> str:  # type: ignore[no-any-unimported]
    """Serialize the chapter content element to an XHTML string."""
    try:
        return str(html.tostring(content_el, method="xml", encoding="unicode"))
    except (etree.ParseError, etree.ParserError) as exc:
        msg = f"Failed to serialize chapter body to XHTML: {exc}"
        raise ParsingError(msg) from exc


def _collect_page_css(  # type: ignore[no-any-unimported]
    root: html.HtmlElement,
    chapter_stylesheets: list[str],
    known_css: list[str],
    base_url: str,
    discovered_css: list[str],
) -> str:
    """Build the combined page CSS and record newly discovered stylesheets."""
    all_css: list[str] = list(known_css)
    page_css = _collect_link_css(chapter_stylesheets, all_css, discovered_css)
    page_css += _collect_html_link_css(root, base_url, all_css, discovered_css)
    return page_css + _collect_inline_css(root)


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
    content_el.rewrite_links(lambda link: rewrite_link(link, book_id))
    return content_el, discovered_videos


def _maybe_apply_cover(  # type: ignore[no-any-unimported]
    content_el: html.HtmlElement,
    page_css: str,
    *,
    first_page: bool,
) -> tuple[str, html.HtmlElement, str | None]:
    """Swap in a cover-page layout when a cover image is detected."""
    if not first_page:
        return page_css, content_el, None
    cover_img_src = find_cover_image(content_el)
    if cover_img_src is None:
        return page_css, content_el, None
    cover_css, cover_el = _build_cover_page(cover_img_src)
    return cover_css, cover_el, cover_img_src


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
    page_css = _collect_page_css(root, chapter_stylesheets, known_css, base_url, discovered_css)

    _convert_svg_images(root)

    content_el, discovered_videos = _extract_content_element(root, book_id)
    page_css, content_el, cover_src = _maybe_apply_cover(
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


# ---------------------------------------------------------------------------
# Table of contents normalization
# ---------------------------------------------------------------------------


def normalize_toc(raw_toc: list[dict[str, Any]], depth: int = 0) -> list[TocEntry]:
    """Convert a v2 API table-of-contents tree into :class:`TocEntry` models.

    Parameters
    ----------
    raw_toc:
        List of TOC entry dicts from the API.  Each may have ``url``
        or ``href``, ``label`` or ``title``, and ``children``.
    depth:
        Current nesting depth (0 for top-level entries).

    Returns:
    -------
    list[TocEntry]
        Normalized TOC tree.

    """
    entries: list[TocEntry] = []
    for position, entry in enumerate(raw_toc):
        entries.append(_build_toc_entry(entry, depth, position))
    return entries


def _build_toc_entry(entry: dict[str, Any], depth: int, position: int) -> TocEntry:
    """Convert a single raw TOC *entry* dict into a :class:`TocEntry`."""
    href = unquote(entry.get("url", entry.get("href", "")))
    entry_id = entry.get("id", "")

    fragment = ""
    if _FRAGMENT_SEP in href:
        fragment = href.split(_FRAGMENT_SEP)[-1]

    children: list[TocEntry] = []
    if entry.get("children"):
        children = normalize_toc(entry["children"], depth + 1)

    return TocEntry(
        depth=depth,
        fragment=fragment,
        id=entry_id if entry_id else f"toc_{depth}_{position}",
        label=entry.get("label", entry.get("title", "")),
        href=href,
        children=children,
    )
