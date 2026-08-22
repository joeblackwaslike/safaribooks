"""Tag classification constants and element-name helpers for extraction."""

import re
from types import MappingProxyType

from lxml import html

from safaribooks.core.markdown import ir

HEADING_TAGS: MappingProxyType[str, int] = MappingProxyType(
    {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6},
)
TRANSPARENT_TAGS = frozenset(
    ("div", "section", "article", "main", "header", "footer", "nav", "figure", "figcaption"),
)
EMPHASIS_TAGS = frozenset(("em", "i", "cite", "var"))
STRONG_TAGS = frozenset(("strong", "b"))
INLINE_PASSTHROUGH = frozenset(("span", "abbr", "small", "u", "mark", "time", "q"))
LIST_TAGS = frozenset(("ul", "ol"))
SINGLE_BLOCK_TAGS = frozenset(("p", "pre", "blockquote", "hr", "table", "aside", "dl"))
CLASS_ATTR = "class"

_WS_RE = re.compile(r"\s+")


def localname(element: html.HtmlElement) -> str:  # type: ignore[no-any-unimported]
    """Return the lowercase local tag name, or ``""`` for comments/PIs."""
    tag = element.tag
    return tag.lower() if isinstance(tag, str) else ""


def meta(element: html.HtmlElement) -> ir.Meta:  # type: ignore[no-any-unimported]
    """Capture source provenance (tag, classes, inline style) for extensions."""
    classes = tuple(element.get(CLASS_ATTR, "").split())
    style = element.get("style", "")
    return ir.Meta(tag=localname(element), classes=classes, style=style)


def normalize_text(text: str) -> str:
    """Collapse runs of whitespace to single spaces."""
    return _WS_RE.sub(" ", text)
