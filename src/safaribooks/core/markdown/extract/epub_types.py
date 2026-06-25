"""Detect EPUB footnote references and definitions via ``epub:type``/classes."""

import re

from lxml import html

from safaribooks.core.markdown.extract.tags import CLASS_ATTR

_HREF = "href"
_FOOTNOTE_HINT = re.compile(r"footnote|endnote|\bfn\b|noteref", re.IGNORECASE)
_DEF_TYPES = ("footnote", "endnote", "rearnote")


def epub_type(element: html.HtmlElement) -> str:  # type: ignore[no-any-unimported]
    """Return the ``epub:type`` value regardless of namespace spelling."""
    for key, attr_value in element.attrib.items():
        if key == "epub:type" or key.endswith("}type"):
            return str(attr_value)
    return ""


def is_noteref(anchor: html.HtmlElement) -> bool:  # type: ignore[no-any-unimported]
    """Return ``True`` when an ``<a>`` is a footnote reference."""
    href = anchor.get(_HREF, "")
    if not href.startswith("#"):
        return False
    if "noteref" in epub_type(anchor).lower():
        return True
    return bool(_FOOTNOTE_HINT.search(anchor.get(CLASS_ATTR, "")))


def is_footnote_def(element: html.HtmlElement) -> bool:  # type: ignore[no-any-unimported]
    """Return ``True`` when a block element is a footnote/endnote definition."""
    if not element.get("id"):
        return False
    type_value = epub_type(element).lower()
    if any(kind in type_value for kind in _DEF_TYPES):
        return True
    return bool(_FOOTNOTE_HINT.search(element.get(CLASS_ATTR, "")))
