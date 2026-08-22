"""Tests for chapter assembly: footnote hoisting and identifier namespacing."""

from pathlib import Path

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.assemble import assemble
from safaribooks.core.markdown.reader import read_epub
from tests.core.markdown._epub import ChapterSpec, build_epub


def _assemble(tmp_path: Path, specs: list[ChapterSpec]) -> tuple[ir.ChapterIR, ...]:
    epub = build_epub(tmp_path / "a.epub", "Book", specs)
    _meta, chapters = assemble(read_epub(epub))
    return chapters


def test_titles_from_ncx(tmp_path: Path) -> None:
    chapters = _assemble(tmp_path, [ChapterSpec("Intro", "<p>x</p>")])
    assert chapters[0].title == "Intro"


def test_footnotes_hoisted_and_namespaced(tmp_path: Path) -> None:
    body = (
        '<p>text<sup><a href="#fn1">1</a></sup></p>'
        '<aside id="fn1" epub:type="footnote"><p>note</p></aside>'
    )
    # epub:type namespace must be declared for lxml to keep the attribute.
    spec = ChapterSpec("C1", f'<div xmlns:epub="http://www.idpf.org/2007/ops">{body}</div>')
    chapters = _assemble(tmp_path, [ChapterSpec("Pre", "<p>x</p>"), spec])
    target = chapters[1]
    assert len(target.footnotes) == 1
    assert target.footnotes[0].identifier == "c1-fn1"
    refs = [
        child
        for block in target.blocks
        if isinstance(block, ir.Paragraph)
        for child in block.children
        if isinstance(child, ir.FootnoteRef)
    ]
    assert refs == [ir.FootnoteRef("c1-fn1")]
