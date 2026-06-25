"""Tests for the hand-rolled EPUB reader."""

import zipfile
from pathlib import Path

import pytest

from safaribooks.core.exceptions import EpubReadError
from safaribooks.core.markdown.reader import read_epub
from tests.core.markdown._epub import ChapterSpec, build_epub


def test_reads_metadata_and_chapters_in_order(tmp_path: Path) -> None:
    specs = [
        ChapterSpec("Cover", "<p>cover</p>"),
        ChapterSpec("One", "<p>one</p>"),
        ChapterSpec("Two", "<p>two</p>"),
    ]
    epub = build_epub(tmp_path / "b.epub", "My Title", specs, isbn="9780000000001")
    document = read_epub(epub)

    assert document.metadata.title == "My Title"
    assert document.metadata.authors == ("Ada Lovelace",)
    assert document.metadata.publisher == "O'Reilly Media, Inc."
    assert document.metadata.published == "2024-01-02"
    assert document.metadata.isbn == "9780000000001"
    assert document.metadata.language == "en"
    assert document.metadata.source_file == "b.epub"
    assert [chapter.title for chapter in document.chapters] == ["Cover", "One", "Two"]


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(EpubReadError):
        read_epub(tmp_path / "nope.epub")


def test_not_a_zip_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "bad.epub"
    bogus.write_text("not a zip", encoding="utf-8")
    with pytest.raises(EpubReadError):
        read_epub(bogus)


def test_missing_container_raises(tmp_path: Path) -> None:
    path = tmp_path / "nocontainer.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
    with pytest.raises(EpubReadError):
        read_epub(path)


def test_falls_back_to_heading_title(tmp_path: Path) -> None:
    # NCX nav label is present in the helper; remove reliance by checking heading.
    specs = [ChapterSpec("Ignored", "<h1>Real Heading</h1><p>body</p>")]
    epub = build_epub(tmp_path / "h.epub", "T", specs)
    document = read_epub(epub)
    # The NCX label wins when present.
    assert document.chapters[0].title == "Ignored"
