"""Convert EPUB ``<table>`` elements into the table IR."""

from lxml import html

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.extract.inline import collect_inline
from safaribooks.core.markdown.extract.normalize import trim_inlines
from safaribooks.core.markdown.extract.tags import localname

_CELL_TAGS = frozenset(("td", "th"))


def _cells_in(row: html.HtmlElement) -> list[html.HtmlElement]:  # type: ignore[no-any-unimported]
    """Return the ``<td>``/``<th>`` children of a table row."""
    return [cell for cell in row if localname(cell) in _CELL_TAGS]


def _row_cells(cells: list[html.HtmlElement]) -> tuple[ir.TableCell, ...]:  # type: ignore[no-any-unimported]
    """Convert a row's cell elements into table-cell IR nodes."""
    return tuple(ir.TableCell(trim_inlines(collect_inline(cell))) for cell in cells)


def _is_header_row(cells: list[html.HtmlElement]) -> bool:  # type: ignore[no-any-unimported]
    """Return ``True`` when every cell in *cells* is a ``<th>``."""
    return all(localname(cell) == "th" for cell in cells)


def convert_table(table: html.HtmlElement) -> ir.Table:  # type: ignore[no-any-unimported]
    """Convert a ``<table>`` into the IR, treating the first ``<th>`` row as header."""
    header: tuple[ir.TableCell, ...] | None = None
    body: list[tuple[ir.TableCell, ...]] = []
    for row in table.findall(".//tr"):
        cells = _cells_in(row)
        if not cells:
            continue
        if header is None and _is_header_row(cells):
            header = _row_cells(cells)
        else:
            body.append(_row_cells(cells))
    return ir.Table(header=header, rows=tuple(body))
