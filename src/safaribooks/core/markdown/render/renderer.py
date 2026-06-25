"""Serialize the Markdown IR to GFM while tracking per-chapter offsets.

Mirrors the books-for-bots renderer: a single buffer accumulates the body, and
``_Buffer.write`` is the *only* place the line and byte counters advance. Each
chapter's ``(byte, line)`` start offset is snapshotted immediately before its
``## {title}`` heading is written. Offsets are body-relative; the front-matter
size is added later (see ``frontmatter``).
"""

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.headings import normalize_ws, text_of_inlines, titles_match
from safaribooks.core.markdown.render.blocks import render_block_string
from safaribooks.core.markdown.render.offsets import ChapterOffset, RenderResult

_BLANK_LINE_NEWLINES = 2


def _is_redundant_heading(block: ir.Block, title: str) -> bool:
    """Return ``True`` for an in-body heading that duplicates the chapter title."""
    if not isinstance(block, ir.Heading):
        return False
    return titles_match(text_of_inlines(block.children), title)


class _Buffer:
    """Append-only Markdown buffer that tracks the current line and byte offset."""

    def __init__(self) -> None:
        """Start an empty buffer at line 1, byte 0, with no trailing newlines."""
        self._parts: list[str] = []
        self.line = 1
        self.byte = 0
        self._trailing_newlines = 0

    def write(self, text: str) -> None:
        """Append *text*, advancing the line and byte counters (the only place)."""
        if not text:
            return
        self._parts.append(text)
        self.line += text.count("\n")
        self.byte += len(text.encode("utf-8"))
        stripped = text.rstrip("\n")
        if stripped:
            self._trailing_newlines = len(text) - len(stripped)
        else:
            self._trailing_newlines += len(text)

    def ensure_blank_line(self) -> None:
        """Ensure the buffer ends with a blank line (two newlines)."""
        if self.byte == 0:
            return
        needed = _BLANK_LINE_NEWLINES - self._trailing_newlines
        if needed > 0:
            self.write("\n" * needed)

    def text(self) -> str:
        """Return the accumulated body."""
        return "".join(self._parts)


class Renderer:
    """Accumulates the Markdown body and records per-chapter start offsets."""

    def __init__(self) -> None:
        """Initialise an empty buffer with no recorded offsets."""
        self._buffer = _Buffer()
        self._offsets: list[ChapterOffset] = []

    def render(self, chapters: tuple[ir.ChapterIR, ...]) -> RenderResult:
        """Render all *chapters* and return the body plus start offsets."""
        for chapter in chapters:
            self._start_chapter(chapter.title)
            self._render_body(chapter)
        return RenderResult(body=self._buffer.text(), offsets=self._offsets)

    def _start_chapter(self, title: str) -> None:
        """Record the start offset, then write the ``## {title}`` heading."""
        self._buffer.ensure_blank_line()
        start = ChapterOffset(byte=self._buffer.byte, line=self._buffer.line)
        self._offsets.append(start)
        self._buffer.write(f"## {normalize_ws(title)}\n")

    def _render_body(self, chapter: ir.ChapterIR) -> None:
        """Render a chapter's blocks (skipping a redundant title heading) + notes."""
        for block in chapter.blocks:
            if not _is_redundant_heading(block, chapter.title):
                self._emit_block(block)
        if chapter.footnotes:
            self._emit_block(ir.HorizontalRule())
            for note in chapter.footnotes:
                self._emit_block(note)

    def _emit_block(self, block: ir.Block) -> None:
        """Write a block with a preceding blank line and a trailing newline."""
        text = render_block_string(block)
        if not text:
            return
        self._buffer.ensure_blank_line()
        self._buffer.write(f"{text}\n")
