"""HTML parsing, link processing, and TOC normalization for chapters."""


import logging
import pathlib
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from lxml import etree, html
from lxml.html import HtmlElement

from safaribooks.core.api import ApiClient
from safaribooks.core.constants import SAFARI_BASE_URL
from safaribooks.core.exceptions import ApiError, ParsingError
from safaribooks.core.models import ParseResult, TocEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Image / video / link file extensions
# ---------------------------------------------------------------------------
_IMAGE_EXTENSIONS: frozenset[str] = frozenset({"jpg", "jpeg", "png", "gif"})
_VIDEO_EXTENSIONS: frozenset[str] = frozenset({"mp4"})
_HTML_EXTENSIONS: frozenset[str] = frozenset({"html", "xhtml", "htm"})
_IMAGE_PATH_HINTS: tuple[str, ...] = ("cover", "images", "graphics")


# ---------------------------------------------------------------------------
# URL classification helpers
# ---------------------------------------------------------------------------


def is_absolute_url(url: str) -> bool:
    """Return ``True`` if *url* has a network location (scheme + host)."""
    return bool(urlparse(url).netloc)


def is_image_link(url: str) -> bool:
    """Return ``True`` if *url* points to a known image extension."""
    return pathlib.Path(url).suffix[1:].lower() in _IMAGE_EXTENSIONS


def is_video_link(url: str) -> bool:
    """Return ``True`` if *url* points to a known video extension."""
    clean = url.split("?")[0].split("#")[0]
    return pathlib.Path(clean).suffix[1:].lower() in _VIDEO_EXTENSIONS


def is_html_link(url: str) -> bool:
    """Return ``True`` if *url* points to a known HTML extension."""
    clean = url.split("#")[0].split("?")[0]
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

    if not is_absolute_url(link):
        if is_video_link(link):
            return "Video/" + link.split("/")[-1]

        if is_possible_image(link):
            return "Images/" + link.split("/")[-1]

        return link.replace(".html", ".xhtml")

    # Absolute link that references the same book — strip and recurse.
    if book_id in link:
        return rewrite_link(link.split(book_id)[-1], book_id)

    return link


# ---------------------------------------------------------------------------
# Chapter HTML fetching
# ---------------------------------------------------------------------------


async def fetch_chapter_html(client: ApiClient, url: str) -> HtmlElement:  # type: ignore[no-any-unimported]
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
    if response.status_code != 200:
        msg = f"Failed to retrieve chapter HTML from {url} (status {response.status_code})"
        raise ApiError(msg)

    try:
        html_text = response.text
        if not re.search("<html", html_text, re.IGNORECASE):
            html_text = etree.tostring(html.html5parser.fromstring(html_text), encoding="unicode")
        return html.fromstring(html_text, base_url=SAFARI_BASE_URL)

    except (etree.ParseError, etree.ParserError) as exc:
        msg = f"Failed to parse chapter HTML from {url}: {exc}"
        raise ParsingError(msg) from exc


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


def _register_lowercase_xpath() -> None:
    """Register a ``lower-case`` XPath function in the default namespace."""
    ns = etree.FunctionNamespace(None)
    ns["lower-case"] = lambda _ctx, nodes: nodes[0].lower() if nodes and len(nodes) else ""


def find_cover_image(root: HtmlElement) -> str | None:  # type: ignore[no-any-unimported]
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
        return str(images[0].attrib.get("src")) if images[0].attrib.get("src") else None

    # <img> inside a <div> with cover attributes.
    divs = root.xpath(f"//div[{cover_pred}]//img")
    if divs:
        return str(divs[0].attrib.get("src")) if divs[0].attrib.get("src") else None

    # <img> inside an <a> with cover attributes.
    anchors = root.xpath(f"//a[{cover_pred}]//img")
    if anchors:
        return str(anchors[0].attrib.get("src")) if anchors[0].attrib.get("src") else None

    return None


# ---------------------------------------------------------------------------
# Chapter HTML parsing (the critical refactored method)
# ---------------------------------------------------------------------------


def parse_chapter_html(  # type: ignore[no-any-unimported]
    root: HtmlElement,
    chapter_stylesheets: list[str],
    known_css: set[str],
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
        Set of CSS URLs already collected from previous chapters.
        Used only for deduplication when assigning ``Style##`` indices;
        callers should merge ``discovered_css`` into this set after the
        call.
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
    book_content = root.xpath("//div[@id='sbo-rt-content']")
    if not book_content:
        msg = "Book content element (#sbo-rt-content) not found in chapter HTML"
        raise ParsingError(msg)

    # Build a combined ordered list of all CSS URLs (chapter metadata + in-page).
    # We need stable indices for Style00, Style01, ... filenames.
    all_css: list[str] = list(known_css)
    discovered_css: list[str] = []
    page_css = ""

    # --- chapter-level stylesheets from metadata ---
    for css_url in chapter_stylesheets:
        if css_url not in all_css:
            all_css.append(css_url)
            discovered_css.append(css_url)
            logger.debug("Found new CSS: %s", css_url)

        idx = all_css.index(css_url)
        page_css += f'<link href="Styles/Style{idx:02d}.css" rel="stylesheet" type="text/css" />\n'

    # --- <link rel="stylesheet"> elements in the HTML ---
    stylesheet_links = root.xpath("//link[@rel='stylesheet']")
    for link_el in stylesheet_links:
        href = link_el.attrib.get("href", "")
        if not href:
            continue

        css_url = urljoin("https:", href) if href.startswith("//") else urljoin(base_url, href)

        if css_url not in all_css:
            all_css.append(css_url)
            discovered_css.append(css_url)
            logger.debug("Found new CSS: %s", css_url)

        idx = all_css.index(css_url)
        page_css += f'<link href="Styles/Style{idx:02d}.css" rel="stylesheet" type="text/css" />\n'

    # --- inline <style> elements ---
    for css_el in root.xpath("//style"):
        data_tpl = css_el.attrib.get("data-template", "")
        if data_tpl:
            css_el.text = data_tpl
            del css_el.attrib["data-template"]

        try:
            page_css += html.tostring(css_el, method="xml", encoding="unicode") + "\n"
        except (etree.ParseError, etree.ParserError) as exc:
            msg = f"Failed to serialize inline <style>: {exc}"
            raise ParsingError(msg) from exc

    # --- SVG <image> → <img> conversion ---
    for img in root.xpath("//image"):
        href_attrs = [attr for attr in img.attrib if "href" in attr]
        if href_attrs:
            svg_url = img.attrib.get(href_attrs[0])
            svg_root = img.getparent().getparent()
            new_img = svg_root.makeelement("img")
            new_img.attrib["src"] = svg_url
            svg_root.remove(img.getparent())
            svg_root.append(new_img)

    # --- Discover video sources ---
    discovered_videos: list[str] = [
        src for src in root.xpath("//div[@id='sbo-rt-content']//video/source/@src") if src
    ]

    # --- Rewrite links ---
    content_el = book_content[0]
    content_el.rewrite_links(lambda link: rewrite_link(link, book_id))

    # --- Cover detection on first page ---
    cover_src: str | None = None
    if first_page:
        cover_img_src = find_cover_image(content_el)
        if cover_img_src is not None:
            page_css = (
                "<style>"
                "body{display:table;position:absolute;margin:0!important;"
                "height:100%;width:100%;}"
                "#Cover{display:table-cell;vertical-align:middle;"
                "text-align:center;}"
                "img{height:90vh;margin-left:auto;margin-right:auto;}"
                "</style>"
            )
            cover_html = html.fromstring('<div id="Cover"></div>')
            cover_div = cover_html.xpath("//div")[0]
            cover_img = cover_div.makeelement("img")
            cover_img.attrib["src"] = cover_img_src
            cover_div.append(cover_img)
            content_el = cover_html
            cover_src = cover_img_src

    # --- Serialize to XHTML ---
    try:
        body_xhtml = html.tostring(content_el, method="xml", encoding="unicode")
    except (etree.ParseError, etree.ParserError) as exc:
        msg = f"Failed to serialize chapter body to XHTML: {exc}"
        raise ParsingError(msg) from exc

    return ParseResult(
        page_css=page_css,
        body_xhtml=body_xhtml,
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
    result: list[TocEntry] = []
    for entry in raw_toc:
        href = unquote(entry.get("url", entry.get("href", "")))
        entry_id = entry.get("id", "")
        label = entry.get("label", entry.get("title", ""))

        fragment = ""
        if "#" in href:
            fragment = href.split("#")[-1]

        children: list[TocEntry] = []
        if entry.get("children"):
            children = normalize_toc(entry["children"], depth + 1)

        result.append(
            TocEntry(
                depth=depth,
                fragment=fragment,
                id=entry_id if entry_id else f"toc_{depth}_{len(result)}",
                label=label,
                href=href,
                children=children,
            )
        )

    return result
