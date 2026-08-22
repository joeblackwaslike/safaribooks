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
    heading = ir.Heading(1, (ir.Text("Intro"),))
    body = _render(heading, title="Intro")
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
    inlines = (ir.Text("a"), ir.LineBreak(), ir.Text("b"))
    rendered = render_inlines(inlines)
    assert rendered == "a  \nb"


def test_code_fence_widens_for_backticks() -> None:
    body = _render(ir.CodeBlock("```\ninner\n```", "py"))
    assert "````py" in body


def _cell(text: str) -> ir.TableCell:
    return ir.TableCell((ir.Text(text),))


def test_table_with_header() -> None:
    header = (_cell("H1"), _cell("H2"))
    rows = ((_cell("a"), _cell("b|c")),)
    table = ir.Table(header=header, rows=rows)
    body = _render(table)
    assert "| H1 | H2 |" in body
    assert "| --- | --- |" in body
    assert r"b\|c" in body


def test_footnotes_render_after_rule() -> None:
    paragraph = ir.Paragraph((ir.Text("body"), ir.FootnoteRef("c0-fn1")))
    footnote_body = ir.Paragraph((ir.Text("note"),))
    chapter = ir.ChapterIR(
        title="C",
        blocks=(paragraph,),
        footnotes=(ir.FootnoteDef("c0-fn1", (footnote_body,)),),
    )
    body = Renderer().render((chapter,)).body
    assert "[^c0-fn1]" in body
    assert "[^c0-fn1]: note" in body
    assert "\n---\n" in body
