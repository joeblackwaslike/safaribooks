"""Leaf and formatting inline IR nodes (text, breaks, code, emphasis)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from safaribooks.core.markdown.ir.references import Inline


@dataclass(frozen=True, slots=True)
class Text:
    """A run of literal text."""

    value: str  # noqa: WPS110 -- public field read as ``.value`` by tests/extensions


@dataclass(frozen=True, slots=True)
class LineBreak:
    """A hard line break (``<br/>``)."""


@dataclass(frozen=True, slots=True)
class CodeSpan:
    """Inline code (``<code>`` outside a ``<pre>``)."""

    value: str  # noqa: WPS110 -- public field read as ``.value`` by tests/renderer


@dataclass(frozen=True, slots=True)
class Emphasis:
    """Emphasised inline content (``<em>``/``<i>``)."""

    children: tuple["Inline", ...]


@dataclass(frozen=True, slots=True)
class Strong:
    """Strong inline content (``<strong>``/``<b>``)."""

    children: tuple["Inline", ...]
