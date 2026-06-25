"""Convert EPUB inline elements (and their text/tails) into the inline IR.

The most error-prone part is lxml's text model: text between sibling elements
lives on the *previous* element's ``.tail`` (not as a separate node), so every
collector reads ``el.text`` and then, for each child, the child's converted
content *and* its ``.tail``.
"""

from lxml import html

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.extract import anchors
from safaribooks.core.markdown.extract.normalize import normalize_inlines
from safaribooks.core.markdown.extract.tags import EMPHASIS_TAGS, STRONG_TAGS, localname


def collect_inline(element: html.HtmlElement) -> list[ir.Inline]:  # type: ignore[no-any-unimported]
    """Collect the inline content of *element* (its text + children + tails)."""
    nodes: list[ir.Inline] = []
    if element.text:
        nodes.append(ir.Text(element.text))
    for child in element:
        nodes.extend(convert_inline_child(child))
        if child.tail:
            nodes.append(ir.Text(child.tail))
    return nodes


def normalized_children(element: html.HtmlElement) -> tuple[ir.Inline, ...]:  # type: ignore[no-any-unimported]
    """Return *element*'s normalized inline children as a tuple."""
    return tuple(normalize_inlines(collect_inline(element)))


def _convert_image(child: html.HtmlElement) -> ir.Image:  # type: ignore[no-any-unimported]
    """Convert an ``<img>`` element into an image node."""
    alt = child.get("alt", "")
    src = child.get("src", "")
    return ir.Image(alt=alt, src=src)


def _convert_simple(child: html.HtmlElement, tag: str) -> list[ir.Inline]:  # type: ignore[no-any-unimported]
    """Convert code/break/image inline tags, else pass through children."""
    if tag == "code":
        return [ir.CodeSpan("".join(child.itertext()))]
    if tag == "br":
        return [ir.LineBreak()]
    if tag == "img":
        return [_convert_image(child)]
    return normalize_inlines(collect_inline(child))


def convert_inline_child(child: html.HtmlElement) -> list[ir.Inline]:  # type: ignore[no-any-unimported]
    """Convert a single inline child element into IR inline nodes."""
    tag = localname(child)
    if tag in EMPHASIS_TAGS:
        return [ir.Emphasis(normalized_children(child))]
    if tag in STRONG_TAGS:
        return [ir.Strong(normalized_children(child))]
    if tag == "a":
        return anchors.convert_anchor(child)
    if tag in {"sup", "sub"}:
        return anchors.convert_sup_sub(child)
    return _convert_simple(child, tag)
