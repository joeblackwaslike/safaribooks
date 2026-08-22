"""Read spine XHTML documents into chapters with resolved titles."""

import posixpath
import zipfile
from pathlib import Path

from lxml import etree, html

from safaribooks.core.exceptions import EpubReadError
from safaribooks.core.markdown.reader import manifest
from safaribooks.core.markdown.reader.models import (
    CONTENT_ID,
    XHTML_MEDIA_TYPES,
    EpubChapter,
)
from safaribooks.core.markdown.reader.xml import local, parse_xml


def _title_map(archive: zipfile.ZipFile, ncx_path: str) -> dict[str, str]:
    """Map content archive path -> nav label text, parsed from the NCX."""
    if not ncx_path:
        return {}
    try:
        ncx_bytes = archive.read(ncx_path)
    except KeyError:
        return {}
    root = parse_xml(ncx_bytes, source=ncx_path)
    ncx_dir = posixpath.dirname(ncx_path)
    return _nav_titles(root, ncx_dir)


def _nav_titles(root: etree._Element, ncx_dir: str) -> dict[str, str]:  # type: ignore[no-any-unimported]
    """Collect ``content src -> navLabel`` pairs from the NCX nav points."""
    titles: dict[str, str] = {}
    for nav_point in root.xpath(f"//{local('navPoint')}"):
        labels = nav_point.xpath(f".//{local('navLabel')}/{local('text')}/text()")
        srcs = nav_point.xpath(f"./{local('content')}/@src")
        if labels and srcs:
            target = manifest.resolve(ncx_dir, str(srcs[0]))
            titles.setdefault(target, str(labels[0]).strip())
    return titles


def _content_element(doc: html.HtmlElement) -> html.HtmlElement:  # type: ignore[no-any-unimported]
    """Return the chapter's content element (``#sbo-rt-content`` or ``<body>``)."""
    content_nodes = doc.xpath(f"//*[@id='{CONTENT_ID}']")
    if content_nodes:
        return content_nodes[0]
    body = doc.xpath("//body")
    return body[0] if body else doc


def _fallback_title(element: html.HtmlElement, href: str) -> str:  # type: ignore[no-any-unimported]
    """Derive a title from the first heading, else the file stem."""
    headings = element.xpath(".//h1 | .//h2 | .//h3")
    if headings:
        text = " ".join(headings[0].itertext()).strip()
        if text:
            return text
    return Path(href).stem


def _read_chapter(archive: zipfile.ZipFile, href: str, titles: dict[str, str]) -> EpubChapter:
    """Read and parse a single spine document into an :class:`EpubChapter`."""
    try:
        chapter_bytes = archive.read(href)
    except KeyError as exc:
        raise EpubReadError(f"Spine references missing file: {href}") from exc
    try:
        doc = html.fromstring(chapter_bytes)
    except (etree.ParserError, etree.XMLSyntaxError) as exc:
        raise EpubReadError(f"Cannot parse chapter HTML in {href}: {exc}") from exc
    element = _content_element(doc)
    title = titles.get(href) or _fallback_title(element, href)
    return EpubChapter(title=title, element=element)


def spine_chapters(  # type: ignore[no-any-unimported]
    archive: zipfile.ZipFile,
    opf_root: etree._Element,
    opf_dir: str,
) -> tuple[EpubChapter, ...]:
    """Read every XHTML spine document in order into chapters."""
    item_map = manifest.manifest_map(opf_root, opf_dir)
    titles = _title_map(archive, manifest.ncx_path(opf_root, item_map))
    types = manifest.media_types(opf_root)
    chapters = [
        _read_chapter(archive, item_map[idref], titles)
        for idref in manifest.spine_idrefs(opf_root)
        if idref in item_map and types.get(idref, "") in XHTML_MEDIA_TYPES
    ]
    return tuple(chapters)
