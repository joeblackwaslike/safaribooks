"""Namespace-agnostic XML parsing and xpath helpers for EPUB OPF/NCX files."""

from lxml import etree

from safaribooks.core.exceptions import EpubReadError

_TEXT = "/text()"


def local(tag: str) -> str:
    """Return an xpath predicate matching *tag* in any namespace."""
    return f"*[local-name()='{tag}']"


def anywhere(tag: str) -> str:
    """Return an xpath descendant selector (``//tag``) matching any namespace."""
    return f"//{local(tag)}"


def parse_xml(raw: bytes, *, source: str) -> etree._Element:  # type: ignore[no-any-unimported]
    """Parse *raw* as XML, raising :class:`EpubReadError` on failure."""
    try:
        return etree.fromstring(raw)
    except etree.XMLSyntaxError as exc:
        raise EpubReadError(f"Malformed XML in {source}: {exc}") from exc


def texts_under(root: etree._Element, *tags: str) -> list[str]:  # type: ignore[no-any-unimported]
    """Return the text nodes under ``//metadata/<tag.../>`` for the given path."""
    path = "".join(f"/{local(tag)}" for tag in tags)
    query = f"{anywhere('metadata')}{path}{_TEXT}"
    return [str(found) for found in root.xpath(query)]
