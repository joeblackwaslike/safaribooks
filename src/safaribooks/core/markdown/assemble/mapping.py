"""Assemble parsed EPUB chapters into the render-ready IR.

Responsibilities:
- map EPUB metadata to :class:`ir.BookMeta`;
- extract each chapter's blocks from its content element;
- hoist top-level footnote definitions to the chapter and namespace footnote
  identifiers per chapter so references stay unique across the merged document.
"""

from dataclasses import replace

from safaribooks.core.markdown import extract, ir
from safaribooks.core.markdown.assemble.rewrite import Mapping, rewrite_block
from safaribooks.core.markdown.reader import EpubChapter, EpubDocument, EpubMetadata


def assemble(document: EpubDocument) -> tuple[ir.BookMeta, tuple[ir.ChapterIR, ...]]:
    """Return book metadata and assembled chapters from a parsed EPUB."""
    meta = _book_meta(document.metadata)
    chapters = tuple(
        _assemble_chapter(index, chapter)
        for index, chapter in enumerate(document.chapters)
    )
    return meta, chapters


def _book_meta(metadata: EpubMetadata) -> ir.BookMeta:
    """Map :class:`EpubMetadata` to the front-matter :class:`ir.BookMeta`."""
    return ir.BookMeta(
        title=metadata.title,
        authors=metadata.authors,
        publisher=metadata.publisher,
        published=metadata.published,
        isbn=metadata.isbn,
        language=metadata.language,
        source_file=metadata.source_file,
    )


def _split_footnotes(
    blocks: tuple[ir.Block, ...],
) -> tuple[list[ir.FootnoteDef], list[ir.Block]]:
    """Separate top-level footnote definitions from the chapter body."""
    notes: list[ir.FootnoteDef] = []
    body: list[ir.Block] = []
    for block in blocks:
        if isinstance(block, ir.FootnoteDef):
            notes.append(block)
        else:
            body.append(block)
    return notes, body


def _namespace(notes: list[ir.FootnoteDef], mapping: Mapping) -> tuple[ir.FootnoteDef, ...]:
    """Apply the per-chapter id *mapping* to each footnote definition."""
    return tuple(
        replace(
            note,
            identifier=mapping.get(note.identifier, note.identifier),
            children=tuple(rewrite_block(child, mapping) for child in note.children),
        )
        for note in notes
    )


def _chapter_title(index: int, raw_title: str) -> str:
    """Return the chapter title, falling back to ``Chapter N``."""
    number = index + 1
    return raw_title or f"Chapter {number}"


def _assemble_chapter(index: int, chapter: EpubChapter) -> ir.ChapterIR:
    """Extract, split footnotes, and namespace identifiers for one chapter."""
    notes, body = _split_footnotes(extract.blocks_from_element(chapter.element))
    mapping = {note.identifier: f"c{index}-{note.identifier}" for note in notes if note.identifier}
    body_blocks = tuple(rewrite_block(block, mapping) for block in body)
    title = _chapter_title(index, chapter.title)
    return ir.ChapterIR(title=title, blocks=body_blocks, footnotes=_namespace(notes, mapping))
