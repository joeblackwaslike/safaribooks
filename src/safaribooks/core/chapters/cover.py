"""Cover-image detection and dedicated cover-page construction."""

from typing import Any

from lxml import html

_SRC_ATTR = "src"

_COVER_ATTR_PRED = (
    "contains(lower-case(@id), 'cover') or "
    "contains(lower-case(@class), 'cover') or "
    "contains(lower-case(@name), 'cover') or "
    "contains(lower-case(@src), 'cover')"
)

_COVER_PAGE_CSS = (
    "<style>"
    "body{display:table;position:absolute;margin:0!important;"
    "height:100%;width:100%;}"
    "#Cover{display:table-cell;vertical-align:middle;"
    "text-align:center;}"
    "img{height:90vh;margin-left:auto;margin-right:auto;}"
    "</style>"
)


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
    from safaribooks.core.chapters import parsing

    parsing._register_lowercase_xpath()

    cover_pred = _COVER_ATTR_PRED
    alt_pred = f"{cover_pred} or contains(lower-case(@alt), 'cover')"

    images = root.xpath(f"//img[{alt_pred}]")
    if images:
        return _first_img_src(images)

    divs = root.xpath(f"//div[{cover_pred}]//img")
    if divs:
        return _first_img_src(divs)

    anchors = root.xpath(f"//a[{cover_pred}]//img")
    if anchors:
        return _first_img_src(anchors)

    return None


def _build_cover_page(cover_img_src: str) -> tuple[str, html.HtmlElement]:  # type: ignore[no-any-unimported]
    """Build the dedicated cover-page CSS and content element."""
    cover_html = html.fromstring('<div id="Cover"></div>')
    cover_div = cover_html.xpath("//div")[0]
    cover_img = cover_div.makeelement("img")
    cover_img.attrib[_SRC_ATTR] = cover_img_src
    cover_div.append(cover_img)
    return _COVER_PAGE_CSS, cover_html


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
