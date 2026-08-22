"""Tests for HTML -> IR extraction, including lxml ``.tail`` handling."""

from lxml import html

from safaribooks.core.markdown import ir
from safaribooks.core.markdown.extract import blocks_from_element


def _blocks(fragment: str) -> tuple[ir.Block, ...]:
    return blocks_from_element(html.fromstring(f"<div>{fragment}</div>"))


def test_paragraph_and_emphasis() -> None:
    blocks = _blocks("<p>hello <em>world</em></p>")
    para = blocks[0]
    assert isinstance(para, ir.Paragraph)
    children = para.children
    assert children[0] == ir.Text("hello ")
    assert isinstance(children[1], ir.Emphasis)


def test_tail_text_across_inline_elements() -> None:
    blocks = _blocks("<p>they <em>did</em><span> warn you</span>.</p>")
    para = blocks[0]
    assert isinstance(para, ir.Paragraph)
    rendered_children = (
        child.value if isinstance(child, ir.Text) else "*X*" for child in para.children
    )
    rendered = "".join(rendered_children)
    # Space before "warn" (from the span text) and trailing "." (em's tail) survive.
    assert rendered == "they *X* warn you."


def test_heading_levels() -> None:
    blocks = _blocks("<h1>A</h1><h3>B</h3>")
    heading = blocks[0]
    assert isinstance(heading, ir.Heading)
    assert heading.level == 1
    assert blocks[1].level == 3


def test_image_becomes_alt_text_only() -> None:
    blocks = _blocks('<p><img src="x.png" alt="A diagram"/></p>')
    para = blocks[0]
    assert isinstance(para, ir.Paragraph)
    assert para.children == (ir.Image(alt="A diagram", src="x.png"),)


def test_code_block_language() -> None:
    blocks = _blocks('<pre><code class="language-python">x = 1</code></pre>')
    block = blocks[0]
    assert isinstance(block, ir.CodeBlock)
    assert block.language == "python"
    assert block.code == "x = 1"


def test_nested_list() -> None:
    blocks = _blocks("<ul><li>a<ul><li>b</li></ul></li></ul>")
    outer = blocks[0]
    assert isinstance(outer, ir.ListBlock)
    assert not outer.ordered
    assert len(outer.items) == 1


def test_footnote_ref_and_def() -> None:
    fragment = (
        '<p>text<sup><a href="#fn1">1</a></sup></p>'
        '<aside id="fn1" epub:type="footnote"><p>note body</p></aside>'
    )
    blocks = blocks_from_element(
        html.fromstring(f'<div xmlns:epub="http://www.idpf.org/2007/ops">{fragment}</div>'),
    )
    para, note = blocks
    assert isinstance(para, ir.Paragraph)
    assert any(isinstance(child, ir.FootnoteRef) for child in para.children)
    assert isinstance(note, ir.FootnoteDef)
    assert note.identifier == "fn1"


def test_styled_div_keeps_provenance() -> None:
    blocks = _blocks('<div class="h1" style="font-size:24px">Title</div>')
    para = blocks[0]
    assert isinstance(para, ir.Paragraph)
    assert "h1" in para.meta.classes
    assert "font-size" in para.meta.style
