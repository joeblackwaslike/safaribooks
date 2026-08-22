"""Base class and context for Markdown transformation extensions.

Extensions run on the IR between assembly and rendering, so they never affect
the line/byte offsets recorded by the renderer. Subclass
:class:`MarkdownExtension` and override only the hooks you need; both default to
identity.
"""

from dataclasses import dataclass, field
from typing import ClassVar

from safaribooks.core.markdown import ir


@dataclass(frozen=True, slots=True)
class ExtCtx:
    """Read-only context passed to every extension hook."""

    book: ir.BookMeta
    anchors: frozenset[str] = field(default_factory=frozenset)
    stylesheet: str = ""


class MarkdownExtension:
    """Base class for IR-stage Markdown extensions."""

    name: ClassVar[str] = ""

    def transform_chapter(self, chapter: ir.ChapterIR, ctx: ExtCtx) -> ir.ChapterIR:
        """Transform a single chapter. Defaults to identity."""
        return chapter

    def transform_book(
        self,
        chapters: tuple[ir.ChapterIR, ...],
        ctx: ExtCtx,
    ) -> tuple[ir.ChapterIR, ...]:
        """Transform the whole book after per-chapter passes. Defaults to identity."""
        return chapters
