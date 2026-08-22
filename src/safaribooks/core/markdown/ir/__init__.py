"""Intermediate representation for Markdown rendering.

The IR is a small recursive AST of immutable nodes produced by ``extract`` from
EPUB XHTML, transformed by the extension pipeline, and serialized by ``render``.
Frozen dataclasses are used (rather than Pydantic) because this is an internal
syntax tree, not validated boundary data: immutability makes extension
transforms functional and deterministic, and ``match`` statements stay clean.
"""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from safaribooks.core.markdown.ir.block import (
    CodeBlock,
    Heading,
    HorizontalRule,
    Paragraph,
)
from safaribooks.core.markdown.ir.book import BookMeta
from safaribooks.core.markdown.ir.containers import BlockQuote, ListBlock, ListItem
from safaribooks.core.markdown.ir.document import Block, ChapterIR, FootnoteDef
from safaribooks.core.markdown.ir.inline import (
    CodeSpan,
    Emphasis,
    LineBreak,
    Strong,
    Text,
)
from safaribooks.core.markdown.ir.meta import Meta
from safaribooks.core.markdown.ir.references import FootnoteRef, Image, Inline, Link
from safaribooks.core.markdown.ir.table import Table, TableCell

__all__ = [
    "Block",
    "BlockQuote",
    "BookMeta",
    "ChapterIR",
    "CodeBlock",
    "CodeSpan",
    "Emphasis",
    "FootnoteDef",
    "FootnoteRef",
    "Heading",
    "HorizontalRule",
    "Image",
    "Inline",
    "LineBreak",
    "Link",
    "ListBlock",
    "ListItem",
    "Meta",
    "Paragraph",
    "Strong",
    "Table",
    "TableCell",
    "Text",
]
