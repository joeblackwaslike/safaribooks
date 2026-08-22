"""Convert anchor and ``<sup>``/``<sub>`` elements, detecting footnote refs."""

from lxml import html

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.extract import epub_types, inline
from safaribooks.core.markdown.extract.normalize import normalize_inlines

_HREF = "href"


def convert_anchor(child: html.HtmlElement) -> list[ir.Inline]:  # type: ignore[no-any-unimported]
    """Convert an ``<a>`` into a footnote ref or a link."""
    if epub_types.is_noteref(child):
        return [ir.FootnoteRef(child.get(_HREF, "#")[1:])]
    return [ir.Link(child.get(_HREF, ""), inline.normalized_children(child))]


def _wrapped_noteref(child: html.HtmlElement) -> str | None:  # type: ignore[no-any-unimported]
    """Return the anchor target if *child* wraps exactly one in-document anchor."""
    anchors = child.findall(".//a")
    if len(anchors) != 1:
        return None
    href = anchors[0].get(_HREF, "")
    return href if href.startswith("#") else None


def convert_sup_sub(child: html.HtmlElement) -> list[ir.Inline]:  # type: ignore[no-any-unimported]
    """Convert ``<sup>``/``<sub>``, detecting a wrapped footnote reference."""
    href = _wrapped_noteref(child)
    if href is not None:
        return [ir.FootnoteRef(href[1:])]
    return normalize_inlines(inline.collect_inline(child))
