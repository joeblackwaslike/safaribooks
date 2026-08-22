"""Whitespace normalization and edge-trimming for inline node sequences."""

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.extract.tags import normalize_text


def normalize_inlines(nodes: list[ir.Inline]) -> list[ir.Inline]:
    """Normalize whitespace in text nodes and drop empties."""
    normalized: list[ir.Inline] = []
    for node in nodes:
        if not isinstance(node, ir.Text):
            normalized.append(node)
            continue
        collapsed = normalize_text(node.value)
        if collapsed:
            normalized.append(ir.Text(collapsed))
    return normalized


def trim_inlines(nodes: list[ir.Inline]) -> tuple[ir.Inline, ...]:
    """Strip leading/trailing space from the first/last text nodes."""
    trimmed = list(normalize_inlines(nodes))
    if trimmed and isinstance(trimmed[0], ir.Text):
        head = ir.Text(trimmed[0].value.lstrip())
        trimmed[0] = head
        if not head.value:
            trimmed.pop(0)
    if trimmed and isinstance(trimmed[-1], ir.Text):
        tail = ir.Text(trimmed[-1].value.rstrip())
        trimmed[-1] = tail
        if not tail.value:
            trimmed.pop()
    return tuple(trimmed)
