"""Serialize the Markdown IR to GFM while tracking per-chapter offsets."""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from safaribooks.core.markdown.render.inlines import render_inlines
from safaribooks.core.markdown.render.offsets import ChapterOffset, RenderResult
from safaribooks.core.markdown.render.renderer import Renderer

__all__ = [
    "ChapterOffset",
    "RenderResult",
    "Renderer",
    "render_inlines",
]
