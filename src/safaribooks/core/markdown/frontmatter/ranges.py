"""File-absolute chapter ranges within the rendered Markdown document."""

from dataclasses import dataclass

from safaribooks.core.markdown.frontmatter.numbers import line_count
from safaribooks.core.markdown.render import ChapterOffset


@dataclass(frozen=True, slots=True)
class ChapterRange:
    """File-absolute offsets describing where a chapter lives in the ``.md``."""

    title: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int


def preliminary_ranges(
    titles: list[str],
    offsets: list[ChapterOffset],
) -> list[ChapterRange]:
    """Return body-relative ranges (start == end) used to size the front matter."""
    paired = zip(titles, offsets, strict=True)
    return [
        ChapterRange(title, off.line, off.line, off.byte, off.byte)
        for title, off in paired
    ]


def _spans(starts: list[int], total: int) -> list[tuple[int, int]]:
    """Pair each start with its end (one before the next; *total* for the last)."""
    ends = [start - 1 for start in starts[1:]]
    ends.append(total)
    return list(zip(starts, ends, strict=True))


def absolute_ranges(
    titles: list[str],
    offsets: list[ChapterOffset],
    body: str,
    front_matter_lines: int,
    front_matter_bytes: int,
) -> list[ChapterRange]:
    """Compute file-absolute chapter ranges from body-relative start offsets."""
    lines = _spans(
        [offset.line + front_matter_lines for offset in offsets],
        front_matter_lines + line_count(body),
    )
    bytes_ = _spans(
        [offset.byte + front_matter_bytes for offset in offsets],
        front_matter_bytes + len(body.encode("utf-8")) - 1,
    )
    return [
        ChapterRange(
            title=title,
            start_line=line_span[0],
            end_line=line_span[1],
            start_byte=byte_span[0],
            end_byte=byte_span[1],
        )
        for title, line_span, byte_span in zip(titles, lines, bytes_, strict=True)
    ]
