"""Resolve the OPF manifest, spine order, and NCX location."""

import posixpath
import zipfile

from lxml import etree

from safaribooks.core.exceptions import EpubReadError
from safaribooks.core.markdown.reader.models import CONTAINER_PATH
from safaribooks.core.markdown.reader.xml import anywhere, local, parse_xml


def resolve(base_dir: str, href: str) -> str:
    """Resolve a manifest/NCX *href* (minus fragment) to a normalized zip path."""
    clean = href.split("#", 1)[0]
    joined = posixpath.join(base_dir, clean) if base_dir else clean
    return posixpath.normpath(joined)


def opf_path(archive: zipfile.ZipFile) -> str:
    """Return the OPF path declared in ``META-INF/container.xml``."""
    try:
        container = archive.read(CONTAINER_PATH)
    except KeyError as exc:
        raise EpubReadError(f"EPUB missing {CONTAINER_PATH}") from exc
    root = parse_xml(container, source=CONTAINER_PATH)
    full_paths = root.xpath(f"{anywhere('rootfile')}/@full-path")
    if not full_paths:
        raise EpubReadError("container.xml declares no rootfile full-path")
    return str(full_paths[0])


def manifest_map(opf_root: etree._Element, opf_dir: str) -> dict[str, str]:  # type: ignore[no-any-unimported]
    """Map manifest item id -> archive path (resolved against the OPF dir)."""
    mapping: dict[str, str] = {}
    for manifest_item in _manifest_items(opf_root):
        item_id = manifest_item.get("id")
        href = manifest_item.get("href")
        if item_id and href:
            mapping[item_id] = resolve(opf_dir, href)
    return mapping


def media_types(opf_root: etree._Element) -> dict[str, str]:  # type: ignore[no-any-unimported]
    """Map manifest item id -> declared media type."""
    types: dict[str, str] = {}
    for entry in _manifest_items(opf_root):
        types[entry.get("id")] = entry.get("media-type", "")
    return types


def spine_idrefs(opf_root: etree._Element) -> list[str]:  # type: ignore[no-any-unimported]
    """Return spine itemref idrefs in document order."""
    query = f"{anywhere('spine')}/{local('itemref')}/@idref"
    return [str(idref) for idref in opf_root.xpath(query)]


def ncx_path(opf_root: etree._Element, manifest: dict[str, str]) -> str:  # type: ignore[no-any-unimported]
    """Return the NCX archive path declared by the spine ``toc`` attribute."""
    toc_ids = opf_root.xpath(f"{anywhere('spine')}/@toc")
    if toc_ids:
        return manifest.get(str(toc_ids[0]), "")
    return ""


def _manifest_items(opf_root: etree._Element) -> list[etree._Element]:  # type: ignore[no-any-unimported]
    """Return every ``<item>`` element under the OPF manifest."""
    return list(opf_root.xpath(f"{anywhere('manifest')}/{local('item')}"))
