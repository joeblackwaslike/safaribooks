"""Tests for IR -> Markdown rendering."""

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.render import Renderer, render_inlines


def _render(*blocks: ir.Block, title: str = "Chapter") -> str:
    chapter = ir.ChapterIR(title=title, blocks=tuple(blocks))
    return Renderer().render((chapter,)).body


def test_chapter_heading_and_paragraph() -> None:
    body = _render(ir.Paragraph((ir.Text("hello"),)), title="Intro")
    assert body.startswith("## Intro\n\n")
    assert "hello\n" in body


def test_heading_is_demoted_one_level() -> None:
    # Chapter titles render as ##; an in-body <h1> demotes to ## and <h2> to ###.
    assert "## Sub" in _render(ir.Heading(1, (ir.Text("Sub"),)))
    assert "### Sub" in _render(ir.Heading(2, (ir.Text("Sub"),)))


def test_redundant_heading_skipped() -> None:
    body = _render(ir.Heading(1, (ir.Text("Intro"),)), title="Intro")
    # Only the chapter heading remains; the duplicate in-body heading is dropped.
    assert body.count("Intro") == 1


def test_emphasis_strong_and_link() -> None:
    rendered = render_inlines(
        (
            ir.Emphasis((ir.Text("a"),)),
            ir.Strong((ir.Text("b"),)),
            ir.Link("http://x", (ir.Text("c"),)),
        ),
    )
    assert rendered == "*a***b**[c](http://x)"


def test_code_span_backtick_escalation() -> None:
    rendered = render_inlines((ir.CodeSpan("a`b"),))
    assert rendered == "`` a`b ``"


def test_hard_line_break() -> None:
    rendered = render_inlines((ir.Text("a"), ir.LineBreak(), ir.Text("b")))
    assert rendered == "a  \nb"


def test_code_block_fence_widens_for_internal_backticks() -> None:
    body = _render(ir.CodeBlock("```\ninner\n```", "py"))
    assert "````py" in body


def test_table_with_header() -> None:
    table = ir.Table(
        header=(ir.TableCell((ir.Text("H1"),)), ir.TableCell((ir.Text("H2"),))),
        rows=((ir.TableCell((ir.Text("a"),)), ir.TableCell((ir.Text("b|c"),))),),
    )
    body = _render(table)
    assert "| H1 | H2 |" in body
    assert "| --- | --- |" in body
    assert "b\\|c" in body


def test_footnotes_render_after_rule() -> None:
    chapter = ir.ChapterIR(
        title="C",
        blocks=(ir.Paragraph((ir.Text("body"), ir.FootnoteRef("c0-fn1"))),),
        footnotes=(ir.FootnoteDef("c0-fn1", (ir.Paragraph((ir.Text("note"),)),)),),
    )
    body = Renderer().render((chapter,)).body
    assert "[^c0-fn1]" in body
    assert "[^c0-fn1]: note" in body
    assert "\n---\n" in body
