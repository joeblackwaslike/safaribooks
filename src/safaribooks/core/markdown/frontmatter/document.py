"""Render the YAML front-matter block and assemble it via the two-pass build.

The front matter sits above the body, so a chapter's file-absolute offset is its
body-relative offset plus the front-matter size. Because every numeric field is
right-aligned to a fixed width, the front matter's own size does not depend on
the offset values -- so a render with body-relative numbers measures the same
length as the final render with file-absolute numbers (asserted below).
"""

from safaribooks.core.exceptions import OffsetOverflowError
from safaribooks.core.markdown import ir
from safaribooks.core.markdown.frontmatter.numbers import pad_number
from safaribooks.core.markdown.frontmatter.ranges import (
    ChapterRange,
    absolute_ranges,
    preliminary_ranges,
)
from safaribooks.core.markdown.frontmatter.yaml import yaml_inline_string
from safaribooks.core.markdown.render import ChapterOffset


def _header(meta: ir.BookMeta) -> list[str]:
    """Render the book-level metadata lines."""
    lines = ["---", f"title: {yaml_inline_string(meta.title)}"]
    if meta.authors:
        joined = ", ".join(yaml_inline_string(author) for author in meta.authors)
        lines.append(f"authors: [{joined}]")
    if meta.publisher:
        lines.append(f"publisher: {yaml_inline_string(meta.publisher)}")
    if meta.published:
        lines.append(f"published: {yaml_inline_string(meta.published)}")
    if meta.isbn:
        lines.append(f'isbn: "{meta.isbn}"')
    if meta.language:
        lines.append(f"language: {yaml_inline_string(meta.language)}")
    if meta.source_file:
        lines.append(f"source_file: {yaml_inline_string(meta.source_file)}")
    return lines


def _chapter_lines(chapter: ChapterRange) -> list[str]:
    """Render one chapter entry's YAML lines."""
    return [
        f"  - title: {yaml_inline_string(chapter.title)}",
        f"    start_line: {pad_number(chapter.start_line, chapter.title)}",
        f"    end_line: {pad_number(chapter.end_line, chapter.title)}",
        f"    start_byte: {pad_number(chapter.start_byte, chapter.title)}",
        f"    end_byte: {pad_number(chapter.end_byte, chapter.title)}",
    ]


def render(meta: ir.BookMeta, chapters: list[ChapterRange]) -> str:
    """Render the complete front-matter block (including trailing ``---``)."""
    lines = _header(meta)
    lines.append("chapters:")
    for chapter in chapters:
        lines.extend(_chapter_lines(chapter))
    lines.append("---")
    return "{joined}\n".format(joined="\n".join(lines))


def build(
    meta: ir.BookMeta,
    titles: list[str],
    offsets: list[ChapterOffset],
    body: str,
) -> tuple[str, list[ChapterRange]]:
    """Return the final front matter and file-absolute ranges (two-pass).

    Pass 1 renders with body-relative numbers to measure the front-matter size;
    pass 2 renders with file-absolute numbers. Fixed-width padding guarantees the
    two renders are byte-identical in length.
    """
    preliminary = render(meta, preliminary_ranges(titles, offsets))
    ranges = absolute_ranges(
        titles,
        offsets,
        body,
        preliminary.count("\n"),
        len(preliminary.encode("utf-8")),
    )
    final = render(meta, ranges)
    if len(final) != len(preliminary):  # pragma: no cover - invariant guard
        msg = "front matter size changed between passes; padding width too small"
        raise OffsetOverflowError(msg, len(final), len(preliminary))
    return final, ranges
