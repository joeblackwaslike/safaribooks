"""End-to-end tests for ``convert_epub``: determinism, images, overwrite."""

from pathlib import Path

import pytest

from safaribooks.core.markdown import convert_epub
from tests.core.markdown._epub import ChapterSpec, build_epub


def _epub(tmp_path: Path) -> Path:
    specs = [
        ChapterSpec("One", "<p>Alice <em>fell</em>.</p>"),
        ChapterSpec("Two", '<p>See <img src="f.png" alt="the figure"/> here.</p>'),
    ]
    return build_epub(tmp_path / "src.epub", "Story", specs)


def test_deterministic_output(tmp_path: Path) -> None:
    epub = _epub(tmp_path)
    first = convert_epub(epub, tmp_path / "a.md").read_bytes()
    second = convert_epub(epub, tmp_path / "b.md").read_bytes()
    assert first == second


def test_images_render_as_alt_text_only(tmp_path: Path) -> None:
    epub = _epub(tmp_path)
    text = convert_epub(epub, tmp_path / "o.md").read_text("utf-8")
    assert "the figure" in text
    assert "![" not in text
    assert "f.png" not in text


def test_refuses_overwrite_without_force(tmp_path: Path) -> None:
    epub = _epub(tmp_path)
    dest = tmp_path / "o.md"
    convert_epub(epub, dest)
    with pytest.raises(FileExistsError):
        convert_epub(epub, dest)
    # force overwrites cleanly
    assert convert_epub(epub, dest, force=True) == dest
