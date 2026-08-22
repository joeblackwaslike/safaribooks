"""Fixed-width numeric padding and line counting for front-matter offsets."""

from safaribooks.core.exceptions import OffsetOverflowError

NUMERIC_WIDTH = 10


def line_count(text: str) -> int:
    """Return the number of content lines (a trailing newline adds no line)."""
    if not text:
        return 0
    if text.endswith("\n"):
        return text.count("\n")
    return text.count("\n") + 1


def pad_number(number: int, chapter: str) -> str:
    """Right-align *number* to the fixed numeric width, or raise on overflow."""
    rendered = str(number)
    if len(rendered) > NUMERIC_WIDTH:
        raise OffsetOverflowError(chapter, number, NUMERIC_WIDTH)
    return rendered.rjust(NUMERIC_WIDTH)
