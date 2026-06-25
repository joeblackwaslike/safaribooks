"""Reference inline IR nodes (links, images, footnote refs) and the union."""

from dataclasses import dataclass

from safaribooks.core.markdown.ir.inline import (
    CodeSpan,
    Emphasis,
    LineBreak,
    Strong,
    Text,
)


@dataclass(frozen=True, slots=True)
class Link:
    """A hyperlink with inline children."""

    href: str
    children: tuple["Inline", ...]


@dataclass(frozen=True, slots=True)
class Image:
    """An image, rendered as its alt text only."""

    alt: str
    src: str = ""


@dataclass(frozen=True, slots=True)
class FootnoteRef:
    """A reference to a footnote, rendered ``[^identifier]``."""

    identifier: str


_LeafInline = Text | LineBreak | CodeSpan
_FormattedInline = Emphasis | Strong
_ReferenceInline = Link | Image | FootnoteRef
Inline = _LeafInline | _FormattedInline | _ReferenceInline
