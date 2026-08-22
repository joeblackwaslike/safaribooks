"""Render ordered/unordered lists, recursing back into block rendering."""

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.render import blocks
from safaribooks.core.markdown.render.inlines import render_inlines


def render_list(block: ir.ListBlock, indent: int = 0) -> str:
    """Render an ordered/unordered list, recursing into nested lists."""
    lines: list[str] = []
    for number, list_item in enumerate(block.items, start=1):
        marker = f"{number}." if block.ordered else "-"
        lines.append(_render_list_item(list_item, marker, indent))
    return "\n".join(line for line in lines if line)


def _inline_block_text(block: ir.Block) -> str:
    """Render a block that appears inside a list item to a compact string."""
    if isinstance(block, ir.Paragraph):
        return render_inlines(block.children)
    if isinstance(block, ir.ListBlock):
        return render_list(block)
    return blocks.render_block_string(block)


def _render_list_item(list_item: ir.ListItem, marker: str, indent: int) -> str:
    """Render a single list item and its nested blocks."""
    nested_indent = indent + len(marker) + 1
    first, *rest = list_item.children or (ir.Paragraph(()),)
    head = _format_head(" " * indent, marker, _inline_block_text(first))
    lines = [head]
    lines.extend(_render_nested_item(nested, nested_indent) for nested in rest)
    return "\n".join(line for line in lines if line)


def _format_head(pad: str, marker: str, body: str) -> str:
    """Format a list item's first line ``{pad}{marker} {body}`` (right-stripped)."""
    return f"{pad}{marker} {body}".rstrip()


def _render_nested_item(block: ir.Block, nested_indent: int) -> str:
    """Render a list item's trailing block, nested under the item's marker."""
    if isinstance(block, ir.ListBlock):
        return render_list(block, nested_indent)
    return blocks.indent_lines(_inline_block_text(block), " " * nested_indent)
