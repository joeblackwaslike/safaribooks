"""Convert individual EPUB block-level elements into block IR nodes.

Recursion into nested containers (list items, block quotes, footnote bodies)
goes through :mod:`safaribooks.core.markdown.extract.container`, imported as a
module so the two-way dependency stays acyclic at definition time.
"""

from lxml import html

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.extract import container, epub_types
from safaribooks.core.markdown.extract.code import code_language
from safaribooks.core.markdown.extract.inline import collect_inline
from safaribooks.core.markdown.extract.normalize import trim_inlines
from safaribooks.core.markdown.extract.tables import convert_table
from safaribooks.core.markdown.extract.tags import (
    HEADING_TAGS,
    LIST_TAGS,
    localname,
    meta,
)


def _convert_list(element: html.HtmlElement) -> ir.ListBlock:  # type: ignore[no-any-unimported]
    """Convert ``<ul>``/``<ol>`` into a :class:`ir.ListBlock`."""
    list_items = tuple(
        ir.ListItem(tuple(container.blocks_from_container(child, child)))
        for child in element
        if localname(child) == "li"
    )
    return ir.ListBlock(ordered=localname(element) == "ol", items=list_items)


def _convert_heading(child: html.HtmlElement, tag: str) -> list[ir.Block]:  # type: ignore[no-any-unimported]
    """Convert an ``<h1>``-``<h6>`` element into a heading block."""
    children = trim_inlines(collect_inline(child))
    return [ir.Heading(HEADING_TAGS[tag], children, meta(child))]


def _convert_paragraph(child: html.HtmlElement) -> list[ir.Block]:  # type: ignore[no-any-unimported]
    """Convert a ``<p>`` element, dropping it when it has no content."""
    children = trim_inlines(collect_inline(child))
    return [ir.Paragraph(children, meta(child))] if children else []


def _convert_simple_block(child: html.HtmlElement, tag: str) -> list[ir.Block]:  # type: ignore[no-any-unimported]
    """Convert the remaining single-tag block kinds (``pre``/``blockquote``/...)."""
    if tag == "pre":
        code = "".join(child.itertext()).strip("\n")
        return [ir.CodeBlock(code, code_language(child))]
    if tag == "blockquote":
        return [ir.BlockQuote(tuple(container.blocks_from_container(child, child)))]
    if tag == "hr":
        return [ir.HorizontalRule()]
    if tag == "table":
        return [convert_table(child)]
    return container.blocks_from_container(child, child)


def convert_block(child: html.HtmlElement) -> list[ir.Block]:  # type: ignore[no-any-unimported]
    """Convert a block-level child element into IR block nodes."""
    tag = localname(child)
    if epub_types.is_footnote_def(child):
        body = tuple(container.blocks_from_container(child, child))
        return [ir.FootnoteDef(child.get("id", ""), body)]
    if tag in HEADING_TAGS:
        return _convert_heading(child, tag)
    if tag == "p":
        return _convert_paragraph(child)
    if tag in LIST_TAGS:
        return [_convert_list(child)]
    return _convert_simple_block(child, tag)
