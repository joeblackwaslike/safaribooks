"""Container block IR nodes (block quote, list item, list)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from safaribooks.core.markdown.ir.document import Block


@dataclass(frozen=True, slots=True)
class BlockQuote:
    """A block quote containing nested blocks."""

    children: tuple["Block", ...]


@dataclass(frozen=True, slots=True)
class ListItem:
    """A single list item containing nested blocks."""

    children: tuple["Block", ...]


@dataclass(frozen=True, slots=True)
class ListBlock:
    """An ordered or unordered list."""

    ordered: bool
    items: tuple[ListItem, ...]  # noqa: WPS110 -- public field read as ``.items`` by tests
