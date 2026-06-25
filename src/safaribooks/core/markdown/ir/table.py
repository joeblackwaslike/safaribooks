"""Table IR nodes."""

from dataclasses import dataclass

from safaribooks.core.markdown.ir.references import Inline


@dataclass(frozen=True, slots=True)
class TableCell:
    """A single table cell."""

    children: tuple[Inline, ...]


@dataclass(frozen=True, slots=True)
class Table:
    """A table with an optional header row and zero or more body rows."""

    header: tuple[TableCell, ...] | None
    rows: tuple[tuple[TableCell, ...], ...]
