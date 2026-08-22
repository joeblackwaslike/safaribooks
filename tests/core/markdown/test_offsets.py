"""Offset-correctness tests: front-matter line/byte ranges must seek correctly.

Ported from the books-for-bots ``tests/offsets.rs``: parse the front matter by
line-scanning (no YAML lib), then verify that each recorded byte and line offset
lands on the chapter's ``## {title}`` heading, and that ranges tile the file.
"""

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from safaribooks.core.markdown import convert_epub
from tests.core.markdown._epub import ChapterSpec, build_epub


@dataclass(frozen=True)
class _Entry:
    title: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int


def _chapter_lines(text: str) -> list[str]:
    """Return the lines inside the front matter's ``chapters:`` block."""
    lines = text.split("\n")
    start = lines.index("chapters:") + 1
    end = lines.index("---", start)
    return lines[start:end]


def _extract_title(stripped: str) -> str:
    """Pull the quoted chapter title out of a ``- title: "..."`` line."""
    return stripped.split("title:", 1)[1].strip().strip('"')


def _apply_field(current: dict[str, object], stripped: str) -> None:
    """Parse a ``key: value`` line into one of *current*'s integer fields."""
    key, _, field_value = stripped.partition(":")
    current[key.strip()] = int(field_value)


def _parse_frontmatter(text: str) -> list[_Entry]:
    """Parse chapter entries from the YAML front matter by scanning lines."""
    entries: list[_Entry] = []
    current: dict[str, object] = {}
    for line in _chapter_lines(text):
        stripped = line.strip()
        if stripped.startswith("- title:"):
            if current:
                entries.append(_to_entry(current))
            current = {"title": _extract_title(stripped)}
        elif ":" in stripped:
            _apply_field(current, stripped)
    if current:
        entries.append(_to_entry(current))
    return entries


def _to_entry(raw: dict[str, object]) -> _Entry:
    return _Entry(
        title=str(raw["title"]),
        start_line=int(raw["start_line"]),  # type: ignore[arg-type]
        end_line=int(raw["end_line"]),  # type: ignore[arg-type]
        start_byte=int(raw["start_byte"]),  # type: ignore[arg-type]
        end_byte=int(raw["end_byte"]),  # type: ignore[arg-type]
    )


def _convert(tmp_path: Path, *, extensions: list[str] | None = None) -> Path:
    filler = "bbb " * 60
    more_paragraphs = "<p>more</p>" * 5
    specs = [
        ChapterSpec("First", "<p>aaa</p>"),
        ChapterSpec("Second", f"<p>{filler}</p>{more_paragraphs}"),
        ChapterSpec("Third", "<p>ccc</p>"),
    ]
    epub = build_epub(tmp_path / "off.epub", "Off", specs)
    return convert_epub(epub, tmp_path / "off.md", extensions=extensions)


def test_byte_offsets_seek_to_heading(tmp_path: Path) -> None:
    md = _convert(tmp_path)
    raw = md.read_bytes()
    entries = _parse_frontmatter(raw.decode("utf-8"))
    assert len(entries) == 3
    for entry in entries:
        seeked = raw[entry.start_byte :].decode("utf-8")
        assert seeked.startswith(f"## {entry.title}")


def test_line_offsets_seek_to_heading(tmp_path: Path) -> None:
    md = _convert(tmp_path)
    lines = md.read_text("utf-8").split("\n")
    for entry in _parse_frontmatter(md.read_text("utf-8")):
        assert lines[entry.start_line - 1].startswith(f"## {entry.title}")


def _assert_ranges_tile(entries: list[_Entry], total_lines: int) -> None:
    """Assert consecutive entries abut with no gaps, and the last reaches EOF."""
    for earlier, later in pairwise(entries):
        assert earlier.end_line == later.start_line - 1
        assert earlier.end_byte == later.start_byte - 1
    assert entries[-1].end_line == total_lines


def test_ranges_tile_the_file(tmp_path: Path) -> None:
    md = _convert(tmp_path)
    text = md.read_text("utf-8")
    entries = _parse_frontmatter(text)
    total_lines = text.count("\n")  # body ends with newline
    _assert_ranges_tile(entries, total_lines)


def test_offsets_survive_extensions(tmp_path: Path) -> None:
    md = _convert(tmp_path, extensions=["fix-headings", "remove-footnotes"])
    raw = md.read_bytes()
    for entry in _parse_frontmatter(raw.decode("utf-8")):
        assert raw[entry.start_byte :].decode("utf-8").startswith(f"## {entry.title}")
