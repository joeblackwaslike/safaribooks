"""Extension: drop links whose targets cannot resolve within the document.

External links (with a URL scheme or protocol-relative) and in-document anchors
that match a known target are kept; everything else (typically leftover
``chapterNN.xhtml#frag`` cross-references) is unwrapped to plain inline text.
"""

import re
from functools import partial
from typing import ClassVar

from safaribooks.core.markdown import ir, transform
from safaribooks.core.markdown.extensions.base import ExtCtx, MarkdownExtension

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _is_external(href: str) -> bool:
    """Return ``True`` for absolute/protocol-relative/mailto-style links."""
    return href.startswith("//") or bool(_SCHEME_RE.match(href))


def _keep(href: str, anchors: frozenset[str]) -> bool:
    """Return ``True`` when a link target is resolvable and should be kept."""
    if _is_external(href):
        return True
    return href.startswith("#") and href[1:] in anchors


def _unwrap_broken(node: ir.Inline, anchors: frozenset[str]) -> list[ir.Inline]:
    """Unwrap a link to its children when its target does not resolve."""
    if isinstance(node, ir.Link) and not _keep(node.href, anchors):
        return list(node.children)
    return [node]


class FixBrokenLinks(MarkdownExtension):
    """Unwrap links whose targets do not resolve within the merged document."""

    name: ClassVar[str] = "fix-broken-links"

    def transform_book(
        self,
        chapters: tuple[ir.ChapterIR, ...],
        ctx: ExtCtx,
    ) -> tuple[ir.ChapterIR, ...]:
        """Return *chapters* with unresolvable links unwrapped to their text."""
        unwrap = partial(_unwrap_broken, anchors=ctx.anchors)
        return tuple(
            ir.ChapterIR(
                title=chapter.title,
                blocks=transform.map_inlines(chapter.blocks, unwrap),
                footnotes=chapter.footnotes,
            )
            for chapter in chapters
        )
