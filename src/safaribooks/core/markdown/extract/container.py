"""Walk an EPUB container element, emitting blocks and grouping loose inlines.

Loose inline content (text and inline elements directly under a container) is
grouped into paragraphs whose provenance is taken from a *meta source*, so a
styled ``<div>`` masquerading as a heading keeps its class/style for the
``fix-headings`` extension.
"""

from lxml import html

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.extract import block_nodes, epub_types
from safaribooks.core.markdown.extract.inline import convert_inline_child
from safaribooks.core.markdown.extract.normalize import trim_inlines
from safaribooks.core.markdown.extract.tags import (
    HEADING_TAGS,
    LIST_TAGS,
    SINGLE_BLOCK_TAGS,
    TRANSPARENT_TAGS,
    localname,
    meta,
)


def _is_block_tag(tag: str) -> bool:
    """Return ``True`` for tags handled as block-level."""
    return (
        tag in HEADING_TAGS
        or tag in TRANSPARENT_TAGS
        or tag in LIST_TAGS
        or tag in SINGLE_BLOCK_TAGS
    )


def _starts_block(child: html.HtmlElement, tag: str) -> bool:  # type: ignore[no-any-unimported]
    """Return ``True`` when *child* begins a new block (vs. loose inline content)."""
    return bool(tag and _is_block_tag(tag)) or epub_types.is_footnote_def(child)


def _flush_inline(pending: list[ir.Inline], source_meta: ir.Meta, blocks: list[ir.Block]) -> None:
    """Append a paragraph for accumulated loose inline content, if any."""
    children = trim_inlines(pending)
    pending.clear()
    if children:
        blocks.append(ir.Paragraph(children, source_meta))


def blocks_from_container(  # type: ignore[no-any-unimported]
    element: html.HtmlElement,
    meta_source: html.HtmlElement,
) -> list[ir.Block]:
    """Walk *element*'s children, emitting blocks and grouping loose inline runs."""
    blocks: list[ir.Block] = []
    pending: list[ir.Inline] = []
    source_meta = meta(meta_source)
    if element.text:
        pending.append(ir.Text(element.text))
    for child in element:
        tag = localname(child)
        if _starts_block(child, tag):
            _flush_inline(pending, source_meta, blocks)
            blocks.extend(block_nodes.convert_block(child))
        elif tag:
            pending.extend(convert_inline_child(child))
        if child.tail:
            pending.append(ir.Text(child.tail))
    _flush_inline(pending, source_meta, blocks)
    return blocks


def blocks_from_element(element: html.HtmlElement) -> tuple[ir.Block, ...]:  # type: ignore[no-any-unimported]
    """Extract the Markdown IR block sequence from a chapter content element."""
    return tuple(blocks_from_container(element, element))
