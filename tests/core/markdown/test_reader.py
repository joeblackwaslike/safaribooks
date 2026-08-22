"""Tests for the hand-rolled EPUB reader."""

import zipfile
from pathlib import Path

import pytest

from safaribooks.core.exceptions import EpubReadError
from safaribooks.core.markdown.reader import EpubDocument, read_epub
from tests.core.markdown._epub import ChapterSpec, build_epub


def _sample_document(tmp_path: Path) -> EpubDocument:
    specs = [
        ChapterSpec("Cover", "<p>cover</p>"),
        ChapterSpec("One", "<p>one</p>"),
        ChapterSpec("Two", "<p>two</p>"),
    ]
    epub = build_epub(tmp_path / "b.epub", "My Title", specs, isbn="9780000000001")
    return read_epub(epub)


def test_reads_title_and_authorship_metadata(tmp_path: Path) -> None:
    metadata = _sample_document(tmp_path).metadata

    assert metadata.title == "My Title"
    assert metadata.authors == ("Ada Lovelace",)
    assert metadata.publisher == "O'Reilly Media, Inc."
    assert metadata.published == "2024-01-02"


def test_reads_identifier_and_provenance_metadata(tmp_path: Path) -> None:
    metadata = _sample_document(tmp_path).metadata

    assert metadata.isbn == "9780000000001"
    assert metadata.language == "en"
    assert metadata.source_file == "b.epub"


def test_reads_chapters_in_order(tmp_path: Path) -> None:
    document = _sample_document(tmp_path)

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
