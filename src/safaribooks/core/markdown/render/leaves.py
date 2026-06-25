"""Renderers for leaf inline nodes (no inline children to recurse into)."""

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.render.escaping import code_span, escape_text


def render_text(node: ir.Text) -> str:
    """Render literal text, escaped."""
    return escape_text(node.value)


def render_code_span(node: ir.CodeSpan) -> str:
    """Render an inline code span."""
    return code_span(node.value)


def render_image(node: ir.Image) -> str:
    """Render an image as its escaped alt text."""
    return escape_text(node.alt)


def render_line_break(node: ir.LineBreak) -> str:
    """Render a hard line break."""
    return "  \n"


def render_footnote_ref(node: ir.FootnoteRef) -> str:
    """Render a footnote reference."""
    return f"[^{node.identifier}]"
