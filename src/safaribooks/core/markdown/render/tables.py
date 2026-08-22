"""Render pipe tables from the table IR."""

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.render.inlines import render_inlines

_ROW_PREFIX = "| "
_ROW_SUFFIX = " |"
_COLUMN_SEP = " | "


def _render_cell(cell: ir.TableCell) -> str:
    """Render a table cell, escaping pipes and flattening line breaks."""
    flattened = render_inlines(cell.children).replace("\n", " ")
    return flattened.replace("|", r"\|").strip()


def _render_row(cells: tuple[ir.TableCell, ...], width: int) -> str:
    """Render one table row padded/truncated to *width* columns."""
    rendered = [_render_cell(cell) for cell in cells][:width]
    rendered.extend("" for _ in range(width - len(rendered)))
    return f"{_ROW_PREFIX}{_COLUMN_SEP.join(rendered)}{_ROW_SUFFIX}"


def _divider(width: int) -> str:
    """Render the header/body divider row for a *width*-column table."""
    dashes = _COLUMN_SEP.join("---" for _ in range(width))
    return f"{_ROW_PREFIX}{dashes}{_ROW_SUFFIX}"


def render_table(block: ir.Table) -> str:
    """Render a pipe table; the first row is the header (synthesized if absent)."""
    header = block.header
    rows = block.rows
    if header is None and rows:
        header, rows = rows[0], rows[1:]
    if header is None:
        return ""
    width = len(header)
    lines = [_render_row(header, width), _divider(width)]
    lines.extend(_render_row(row, width) for row in rows)
    return "\n".join(lines)
