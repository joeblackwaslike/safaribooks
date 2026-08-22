"""Tests for the extension pipeline, built-ins, and discovery."""

import pytest

from safaribooks.core.exceptions import UnknownExtensionError
from safaribooks.core.markdown import ir
from safaribooks.core.markdown.extensions import discover, resolve
from safaribooks.core.markdown.extensions import discovery as discovery_mod
from safaribooks.core.markdown.extensions.base import ExtCtx, MarkdownExtension
from safaribooks.core.markdown.extensions.fix_broken_links import FixBrokenLinks
from safaribooks.core.markdown.extensions.fix_headings import FixHeadings
from safaribooks.core.markdown.extensions.reformat_toc import ReformatToc
from safaribooks.core.markdown.extensions.remove_footnotes import RemoveFootnotes


def _ctx(**kwargs: object) -> ExtCtx:
    return ExtCtx(book=ir.BookMeta(title="B"), **kwargs)  # type: ignore[arg-type]


def test_discover_includes_builtins() -> None:
    names = set(discover())
    assert {"fix-headings", "remove-footnotes", "fix-broken-links", "reformat-toc"} <= names


def test_resolve_preserves_order() -> None:
    resolved = resolve(["remove-footnotes", "fix-headings"])
    assert [type(ext) for ext in resolved] == [RemoveFootnotes, FixHeadings]


def test_resolve_unknown_raises() -> None:
    with pytest.raises(UnknownExtensionError):
        resolve(["does-not-exist"])


def test_identity_defaults_are_noops() -> None:
    paragraph = ir.Paragraph((ir.Text("x"),))
    chapter = ir.ChapterIR(title="C", blocks=(paragraph,))
    ext = MarkdownExtension()
    assert ext.transform_chapter(chapter, _ctx()) is chapter
    assert ext.transform_book((chapter,), _ctx()) == (chapter,)


def test_remove_footnotes_strips_refs_and_defs() -> None:
    paragraph = ir.Paragraph((ir.Text("a"), ir.FootnoteRef("fn1")))
    footnote_body = ir.Paragraph((ir.Text("note"),))
    chapter = ir.ChapterIR(
        title="C",
        blocks=(paragraph,),
        footnotes=(ir.FootnoteDef("fn1", (footnote_body,)),),
    )
    transformed = RemoveFootnotes().transform_chapter(chapter, _ctx())
    assert transformed.footnotes == ()
    para = transformed.blocks[0]
    assert isinstance(para, ir.Paragraph)
    assert all(not isinstance(child, ir.FootnoteRef) for child in para.children)


def test_fix_headings_promotes_styled_paragraph() -> None:
    meta = ir.Meta(tag="div", style="font-size:26px")
    para = ir.Paragraph((ir.Text("A Big Title"),), meta)
    chapter = ir.ChapterIR(title="C", blocks=(para,))
    transformed = FixHeadings().transform_chapter(chapter, _ctx())
    assert isinstance(transformed.blocks[0], ir.Heading)


def test_fix_broken_links_unwraps_unresolved() -> None:
    chapter = ir.ChapterIR(
        title="C",
        blocks=(
            ir.Paragraph((ir.Link("ch2.xhtml#s", (ir.Text("dead"),)),)),
            ir.Paragraph((ir.Link("https://x", (ir.Text("ok"),)),)),
            ir.Paragraph((ir.Link("#fn1", (ir.Text("note"),)),)),
        ),
    )
    ctx = _ctx(anchors=frozenset(("fn1",)))
    transformed = FixBrokenLinks().transform_book((chapter,), ctx)
    blocks = transformed[0].blocks
    assert blocks[0].children == (ir.Text("dead"),)  # unwrapped
    assert isinstance(blocks[1].children[0], ir.Link)  # external kept
    assert isinstance(blocks[2].children[0], ir.Link)  # valid anchor kept


def test_reformat_toc_rebuilds_contents_chapter() -> None:
    garbage = ir.Paragraph((ir.Text("garbage"),))
    chapters = (
        ir.ChapterIR(title="Contents", blocks=(garbage,)),
        ir.ChapterIR(title="Chapter 1", blocks=()),
        ir.ChapterIR(title="Chapter 2", blocks=()),
    )
    transformed = ReformatToc().transform_book(chapters, _ctx())
    toc_blocks = transformed[0].blocks
    assert isinstance(toc_blocks[0], ir.ListBlock)
    assert len(toc_blocks[0].items) == 2


class _FakeEntryPoint:
    def __init__(self, name: str, type_: type) -> None:
        self.name = name
        self._type = type_

    def load(self) -> type:
        return self._type


class _ShadowFixHeadings(MarkdownExtension):
    """Third-party extension that tries to shadow the built-in ``fix-headings``."""

    name = "fix-headings"


class _FreshThirdPartyExtension(MarkdownExtension):
    """Genuinely new third-party extension name."""

    name = "third-party"


def test_discovery_reserves_builtin_names(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_entry_points = [
        _FakeEntryPoint("fix-headings", _ShadowFixHeadings),
        _FakeEntryPoint("third-party", _FreshThirdPartyExtension),
    ]
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: fake_entry_points)
    registry = discover()
    assert registry["fix-headings"] is FixHeadings  # built-in wins
    assert registry["third-party"] is _FreshThirdPartyExtension
