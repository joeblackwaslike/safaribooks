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


def _parse_frontmatter(text: str) -> list[_Entry]:
    """Parse chapter entries from the YAML front matter by scanning lines."""
    entries: list[_Entry] = []
    in_chapters = False
    current: dict[str, object] = {}
    for line in text.split("\n"):
        if line == "chapters:":
            in_chapters = True
            continue
        if not in_chapters:
            continue
        if line == "---":
            break
        stripped = line.strip()
        if stripped.startswith("- title:"):
            if current:
                entries.append(_to_entry(current))
            current = {"title": stripped.split("title:", 1)[1].strip().strip('"')}
        elif ":" in stripped:
            key, _, value = stripped.partition(":")
            current[key.strip()] = int(value)
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
    specs = [
        ChapterSpec("First", "<p>aaa</p>"),
        ChapterSpec("Second", "<p>" + "bbb " * 60 + "</p>" + "<p>more</p>" * 5),
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


def test_ranges_tile_the_file(tmp_path: Path) -> None:
    md = _convert(tmp_path)
    text = md.read_text("utf-8")
    entries = _parse_frontmatter(text)
    for earlier, later in pairwise(entries):
        assert earlier.end_line == later.start_line - 1
        assert earlier.end_byte == later.start_byte - 1
    total_lines = text.count("\n")  # body ends with newline
    assert entries[-1].end_line == total_lines


def test_offsets_survive_extensions(tmp_path: Path) -> None:
    md = _convert(tmp_path, extensions=["fix-headings", "remove-footnotes"])
    raw = md.read_bytes()
    for entry in _parse_frontmatter(raw.decode("utf-8")):
        assert raw[entry.start_byte :].decode("utf-8").startswith(f"## {entry.title}")
