"""Footnote definitions, the :data:`Block` union, and the chapter container."""

from dataclasses import dataclass

from safaribooks.core.markdown.ir.block import (
    CodeBlock,
    Heading,
    HorizontalRule,
    Paragraph,
)
from safaribooks.core.markdown.ir.containers import BlockQuote, ListBlock
from safaribooks.core.markdown.ir.table import Table


@dataclass(frozen=True, slots=True)
class FootnoteDef:
    """A footnote definition, rendered ``[^identifier]: ...`` at chapter end."""

    identifier: str
    children: tuple["Block", ...]


_TextBlock = Paragraph | Heading | CodeBlock | HorizontalRule
_ContainerBlock = BlockQuote | ListBlock | Table | FootnoteDef
Block = _TextBlock | _ContainerBlock


@dataclass(frozen=True, slots=True)
class ChapterIR:
    """One assembled chapter: a title, body blocks, and hoisted footnotes."""

    title: str
    blocks: tuple[Block, ...]
    footnotes: tuple[FootnoteDef, ...] = ()
