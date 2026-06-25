"""Heading and inline-text helpers shared by the renderer.

Kept separate from ``render`` so the ``Renderer`` class stays small and within
the wemake-python-styleguide method/complexity budgets.
"""

import re

from safaribooks.core.markdown import ir

_WS_RE = re.compile(r"\s+")
_MAX_HEADING_LEVEL = 6


def normalize_ws(text: str) -> str:
    """Collapse internal whitespace and strip the ends."""
    return _WS_RE.sub(" ", text).strip()


def text_of_inlines(nodes: tuple[ir.Inline, ...]) -> str:
    """Return the concatenated plain text of an inline sequence."""
    return "".join(_inline_text(node) for node in nodes)


def _inline_text(node: ir.Inline) -> str:
    """Return the plain text of a single inline node."""
    if isinstance(node, (ir.Text, ir.CodeSpan)):
        return node.value
    if isinstance(node, ir.Image):
        return node.alt
    if isinstance(node, ir.LineBreak):
        return " "
    if isinstance(node, ir.FootnoteRef):
        return ""
    return text_of_inlines(node.children)


def shift_level(level: int) -> int:
    """Demote a heading by one level, clamped to the max heading depth.

    Chapter titles render as ``##`` (level 2), so an in-chapter ``<h1>`` becomes
    ``###`` and so on, preserving relative structure under the chapter heading.
    """
    return min(level + 1, _MAX_HEADING_LEVEL)


def titles_match(left: str, right: str) -> bool:
    """Return ``True`` when two heading-ish strings match after normalization."""
    return normalize_ws(left).casefold() == normalize_ws(right).casefold()
