"""Render inline IR nodes to GitHub-Flavored Markdown."""

from collections.abc import Callable
from types import MappingProxyType

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.render import leaves

Inlines = tuple[ir.Inline, ...]

_LEAF_RENDERERS: MappingProxyType[type, Callable[..., str]] = MappingProxyType({
    ir.Text: leaves.render_text,
    ir.CodeSpan: leaves.render_code_span,
    ir.Image: leaves.render_image,
    ir.LineBreak: leaves.render_line_break,
    ir.FootnoteRef: leaves.render_footnote_ref,
})

_WRAPPERS: MappingProxyType[type, tuple[str, str]] = MappingProxyType({
    ir.Emphasis: ("*", "*"),
    ir.Strong: ("**", "**"),
})


def render_inlines(nodes: Inlines) -> str:
    """Render an inline sequence to a Markdown string."""
    return "".join(_render_inline(node) for node in nodes)


def _render_inline(node: ir.Inline) -> str:
    """Render a single inline node to Markdown."""
    leaf = _LEAF_RENDERERS.get(type(node))
    if leaf is not None:
        return leaf(node)
    if isinstance(node, ir.Link):
        return f"[{render_inlines(node.children)}]({node.href})"
    if isinstance(node, (ir.Emphasis, ir.Strong)):
        prefix, suffix = _WRAPPERS[type(node)]
        return f"{prefix}{render_inlines(node.children)}{suffix}"
    return ""
