"""LLM-oriented Markdown export: convert a built EPUB into a single ``.md``."""
# flake8: noqa: WPS412

from safaribooks.core.markdown.convert import convert_epub
from safaribooks.core.markdown.extract import blocks_from_element
from safaribooks.core.markdown.frontmatter import ChapterRange
from safaribooks.core.markdown.frontmatter import build as build_frontmatter
from safaribooks.core.markdown.reader import EpubDocument, read_epub
from safaribooks.core.markdown.render import (
    ChapterOffset,
    Renderer,
    RenderResult,
    render_inlines,
)

__all__ = [
    "ChapterOffset",
    "ChapterRange",
    "EpubDocument",
    "RenderResult",
    "Renderer",
    "blocks_from_element",
    "build_frontmatter",
    "convert_epub",
    "read_epub",
    "render_inlines",
]
