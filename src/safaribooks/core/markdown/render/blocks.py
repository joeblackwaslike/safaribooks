"""Render block IR nodes to their Markdown string form (no surrounding blanks).

Block rendering is mutually recursive with list rendering (lists contain
blocks), so :mod:`safaribooks.core.markdown.render.lists` is imported as a module
and dispatched at call time to keep the import graph acyclic at definition time.
"""

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.headings import shift_level
from safaribooks.core.markdown.render import lists
from safaribooks.core.markdown.render.escaping import fence_for
from safaribooks.core.markdown.render.inlines import render_inlines
from safaribooks.core.markdown.render.tables import render_table

_QUOTE_PREFIX = "> "
_NOTE_INDENT = "    "
_BLOCK_GAP = "\n\n"


def indent_lines(text: str, pad: str) -> str:
    """Prefix every line of *text* with *pad*."""
    return "\n".join(pad + line for line in text.split("\n"))


def _render_heading(block: ir.Heading) -> str:
    hashes = "#" * shift_level(block.level)
    return f"{hashes} {render_inlines(block.children)}"


def _render_code_block(block: ir.CodeBlock) -> str:
    fence = fence_for(block.code)
    return f"{fence}{block.language}\n{block.code}\n{fence}"


def render_block_string(block: ir.Block) -> str:
    """Render a block to its string form (no surrounding blank lines)."""
    if isinstance(block, ir.Heading):
        return _render_heading(block)
    if isinstance(block, ir.Paragraph):
        return render_inlines(block.children)
    if isinstance(block, ir.CodeBlock):
        return _render_code_block(block)
    if isinstance(block, ir.Table):
        return render_table(block)
    return _render_nested(block)


def _render_nested(block: ir.Block) -> str:
    """Render the block kinds that nest other blocks (or are constant)."""
    if isinstance(block, ir.HorizontalRule):
        return "---"
    if isinstance(block, ir.BlockQuote):
        inner = _BLOCK_GAP.join(render_block_string(child) for child in block.children)
        return indent_lines(inner, _QUOTE_PREFIX)
    if isinstance(block, ir.ListBlock):
        return lists.render_list(block)
    if isinstance(block, ir.FootnoteDef):
        return _render_footnote_def(block)
    return ""


def _render_footnote_def(block: ir.FootnoteDef) -> str:
    """Render a footnote definition as ``[^id]: ...``."""
    inner = _BLOCK_GAP.join(render_block_string(child) for child in block.children)
    first, _, rest = inner.partition("\n")
    body = f"[^{block.identifier}]: {first}"
    return f"{body}\n{indent_lines(rest, _NOTE_INDENT)}" if rest else body
