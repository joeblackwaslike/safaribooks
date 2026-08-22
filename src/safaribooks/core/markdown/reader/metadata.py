"""Read Dublin-Core metadata from a parsed OPF root."""

import re

from lxml import etree

from safaribooks.core.markdown.reader.models import EpubMetadata
from safaribooks.core.markdown.reader.xml import texts_under

_ISBN_RE = re.compile(r"\b(\d{13}|\d{10})\b")


def _first_text(root: etree._Element, tag: str) -> str:  # type: ignore[no-any-unimported]
    """Return the stripped text of the first ``metadata`` *tag*, or ``""``."""
    found = texts_under(root, tag)
    return found[0].strip() if found else ""


def _all_text(root: etree._Element, tag: str) -> tuple[str, ...]:  # type: ignore[no-any-unimported]
    """Return the stripped text of every ``metadata`` *tag*."""
    stripped = (text.strip() for text in texts_under(root, tag))
    return tuple(text for text in stripped if text)


def _find_isbn(root: etree._Element) -> str:  # type: ignore[no-any-unimported]
    """Return the first identifier that looks like an ISBN-10/13."""
    for identifier in texts_under(root, "identifier"):
        match = _ISBN_RE.search(identifier)
        if match:
            return match.group(1)
    return ""


def read_metadata(opf_root: etree._Element, source_file: str) -> EpubMetadata:  # type: ignore[no-any-unimported]
    """Build :class:`EpubMetadata` from a parsed OPF root."""
    return EpubMetadata(
        title=_first_text(opf_root, "title"),
        authors=_all_text(opf_root, "creator"),
        publisher=_first_text(opf_root, "publisher"),
        published=_first_text(opf_root, "date"),
        isbn=_find_isbn(opf_root),
        language=_first_text(opf_root, "language"),
        source_file=source_file,
    )
