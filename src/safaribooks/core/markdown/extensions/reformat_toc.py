"""Extension: rebuild a table-of-contents chapter as a clean nested list."""

import re
from typing import ClassVar

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.extensions.base import ExtCtx, MarkdownExtension
from safaribooks.core.markdown.headings import titles_match

_TOC_RE = re.compile(r"^(?:table of )?contents$", re.IGNORECASE)


def _is_toc(title: str) -> bool:
    """Return ``True`` when a chapter title denotes a table of contents."""
    return bool(_TOC_RE.match(title.strip()))


def _toc_list(titles: list[str]) -> ir.ListBlock:
    """Build an unordered list of chapter titles."""
    list_items = tuple(
        ir.ListItem((ir.Paragraph((ir.Text(title),)),)) for title in titles
    )
    return ir.ListBlock(ordered=False, items=list_items)


def _rebuild_toc(chapter: ir.ChapterIR, listed: list[str]) -> ir.ChapterIR:
    """Rebuild *chapter* if it is the TOC, else return it unchanged."""
    if not _is_toc(chapter.title):
        return chapter
    other_titles = [title for title in listed if not titles_match(title, chapter.title)]
    body = (_toc_list(other_titles),)
    return ir.ChapterIR(title=chapter.title, blocks=body, footnotes=())


class ReformatToc(MarkdownExtension):
    """Replace a TOC chapter's body with a tidy list of the book's chapters."""

    name: ClassVar[str] = "reformat-toc"

    def transform_book(
        self,
        chapters: tuple[ir.ChapterIR, ...],
        ctx: ExtCtx,
    ) -> tuple[ir.ChapterIR, ...]:
        """Return *chapters* with any TOC chapter's body rebuilt."""
        listed = [chapter.title for chapter in chapters if not _is_toc(chapter.title)]
        return tuple(_rebuild_toc(chapter, listed) for chapter in chapters)
