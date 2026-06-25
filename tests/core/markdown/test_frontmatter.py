"""Tests for the two-pass padded YAML front matter."""

import pytest

from safaribooks.core.exceptions import OffsetOverflowError
from safaribooks.core.markdown import ir
from safaribooks.core.markdown.frontmatter import (
    NUMERIC_WIDTH,
    ChapterRange,
    build,
    pad_number,
    render,
    yaml_inline_string,
)
from safaribooks.core.markdown.render import ChapterOffset


def _meta() -> ir.BookMeta:
    return ir.BookMeta(title="Book", authors=("A",), isbn="9781234567890", source_file="b.epub")


def test_pad_number_constant_width() -> None:
    assert len(pad_number(5, "c")) == NUMERIC_WIDTH
    assert len(pad_number(123456, "c")) == NUMERIC_WIDTH
    assert pad_number(7, "c").strip() == "7"


def test_pad_number_overflow_raises() -> None:
    with pytest.raises(OffsetOverflowError):
        pad_number(10**NUMERIC_WIDTH, "Chapter X")


def test_yaml_inline_quoting() -> None:
    assert yaml_inline_string("plain") == "plain"
    assert yaml_inline_string("has: colon").startswith('"')
    assert yaml_inline_string("# hash").startswith('"')
    assert yaml_inline_string(" pad ").startswith('"')


def test_build_size_invariant_between_passes() -> None:
    meta = _meta()
    titles = ["One", "Two"]
    offsets = [ChapterOffset(byte=0, line=1), ChapterOffset(byte=40, line=5)]
    body = "## One\n\naaa\n\n## Two\n\nbbb\n"
    # build() returns the front matter only (not concatenated with the body).
    front_matter, ranges = build(meta, titles, offsets, body)
    fm_lines = front_matter.count("\n")
    assert ranges[0].start_line == offsets[0].line + fm_lines
    assert front_matter.startswith("---\n")
    assert ranges[0].end_line == ranges[1].start_line - 1


def test_render_includes_isbn_quoted() -> None:
    text = render(
        _meta(),
        [ChapterRange("C", start_line=1, end_line=2, start_byte=0, end_byte=5)],
    )
    assert 'isbn: "9781234567890"' in text
    assert text.endswith("---\n")
