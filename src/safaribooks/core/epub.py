"""EPUB generation: directory structure, OPF metadata, TOC NCX, chapter HTML, ZIP packaging."""

import logging
import re
import sys
import zipfile
from dataclasses import astuple, dataclass
from html import escape
from pathlib import Path
from types import MappingProxyType
from typing import Any
from urllib.parse import unquote

from safaribooks.core.api import ApiClient
from safaribooks.core.constants import (
    BASE_01_HTML,
    BASE_02_HTML,
    CONTAINER_XML,
    CONTENT_OPF,
    EREADER_CSS,
    TOC_NCX,
)
from safaribooks.core.exceptions import ApiError, DownloadError
from safaribooks.core.models import BookInfo, Chapter, TocEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

_UNSAFE_CHARS = frozenset((
    "~",
    "#",
    "%",
    "&",
    "*",
    "{",
    "}",
    "\\",
    "<",
    ">",
    "?",
    "/",
    "`",
    "'",
    '"',
    "|",
    "+",
    ":",
))
_COLON = ":"
_REPLACEMENT_CHAR = "_"
_TITLE_TRUNCATE_INDEX = 15


@dataclass
class BookPaths:
    """Resolved directory paths for a single EPUB book."""

    book_dir: Path
    oebps: Path
    text: Path
    styles: Path
    images: Path
    videos: Path
    meta_inf: Path


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def sanitize_dirname(name: str, *, clean_space: bool = False) -> str:
    """Sanitize a book title for use as a filesystem directory name.

    Mirrors the legacy ``escape_dirname`` behaviour: truncates at colons
    that appear late in the string and replaces on Windows, then strips
    a set of characters that are unsafe on most filesystems.

    Parameters
    ----------
    name:
        The raw directory name (typically the book title).
    clean_space:
        If ``True``, also strip spaces.

    Returns:
    -------
    str
        A filesystem-safe directory name.

    """
    if _COLON in name:
        colon_index = name.index(_COLON)
        if colon_index > _TITLE_TRUNCATE_INDEX:
            name = name.split(_COLON)[0]
        elif "win" in sys.platform:
            name = name.replace(_COLON, ",")

    for unsafe in _UNSAFE_CHARS:
        if unsafe in name:
            name = name.replace(unsafe, _REPLACEMENT_CHAR)

    if clean_space:
        name = name.replace(" ", "")

    return name


def ensure_book_dirs(build_dir: Path) -> BookPaths:
    """Create the standard EPUB directory tree under *build_dir*.

    The tree looks like::

        <build_dir>/
            OEBPS/
                Text/
                Styles/
                Images/
                Video/
            META-INF/

    Parameters
    ----------
    build_dir:
        Root staging directory for this book's build artifacts.

    Returns:
    -------
    BookPaths
        Resolved paths to every subdirectory.

    """
    oebps = build_dir / "OEBPS"
    paths = BookPaths(
        book_dir=build_dir,
        oebps=oebps,
        text=oebps / "Text",
        styles=oebps / "Styles",
        images=oebps / "Images",
        videos=oebps / "Video",
        meta_inf=build_dir / "META-INF",
    )

    for created in astuple(paths):
        if created.exists():
            logger.debug("Directory already exists: %s", created)
        else:
            created.mkdir(parents=True, exist_ok=True)

    return paths


# ---------------------------------------------------------------------------
# Chapter HTML
# ---------------------------------------------------------------------------


def write_chapter_html(
    path: Path,
    css_content: str,
    body_content: str,
) -> None:
    """Write a single chapter XHTML file.

    Wraps the CSS and body content in the standard EPUB XHTML template
    (``BASE_01_HTML`` + ``EREADER_CSS`` + ``BASE_02_HTML``).

    Parameters
    ----------
    path:
        Destination file path (should end in ``.xhtml``).
    css_content:
        CSS ``<link>`` tags and/or inline ``<style>`` blocks.
    body_content:
        The XHTML body fragment.

    """
    template = BASE_01_HTML + EREADER_CSS + BASE_02_HTML

    html = template.format(css_content, body_content)
    path.write_bytes(html.encode("utf-8", "xmlcharrefreplace"))
    logger.debug("Created chapter: %s", path.name)


# ---------------------------------------------------------------------------
# content.opf generation
# ---------------------------------------------------------------------------

# Map of font file extensions to their MIME types.
_FONT_MIMETYPES: MappingProxyType[str, str] = MappingProxyType({
    "otf": "font/otf",
    "ttf": "font/ttf",
    "woff": "font/woff",
    "woff2": "font/woff2",
})

_HTML_SUFFIX = ".html"
_XHTML_SUFFIX = ".xhtml"
_IMG_ID_PREFIX = "img_"
_ITEM_OPEN = '<item id="'


def _to_xhtml(filename: str) -> str:
    """Return *filename* with its ``.html`` suffix swapped for ``.xhtml``."""
    return filename.replace(_HTML_SUFFIX, _XHTML_SUFFIX)


def _basename_id(name: str) -> str:
    """Return *name* without its final dot-extension, HTML-escaped."""
    return escape("".join(name.split(".")[:-1]))


def _discover_css(css_dir: Path) -> list[str]:
    """Return sorted CSS filenames found directly in *css_dir*."""
    if not css_dir.is_dir():
        return []
    return sorted(entry.name for entry in css_dir.iterdir() if entry.suffix == ".css")


def _discover_images(images_dir: Path) -> list[str]:
    """Return sorted image filenames found directly in *images_dir*."""
    if not images_dir.is_dir():
        return []
    return sorted(entry.name for entry in images_dir.iterdir() if entry.is_file())


def _resolve_cover_id(cover_src: str | None, book_info: BookInfo) -> str:
    """Resolve the manifest cover id from *cover_src* or book metadata."""
    cover_id = cover_src or (book_info.cover or "")
    if not cover_id:
        return ""
    match = re.search(r"/(\w+)\.", cover_id)
    if match is None:
        match = re.search(r"(\w+)\.", cover_id)
    if match is not None:
        return f"{_IMG_ID_PREFIX}{match.group(1)}"
    return cover_id


class _OpfManifest:
    """Builds the OPF ``<manifest>`` items and ``<spine>`` references."""

    def __init__(self) -> None:
        self.manifest: list[str] = []
        self.spine: list[str] = []

    def add_chapters(self, chapters: list[Chapter]) -> None:
        """Append manifest items and spine refs for every chapter."""
        for chapter in chapters:
            xhtml_name = _to_xhtml(chapter.filename)
            item_id = _basename_id(xhtml_name)
            self.manifest.append(
                f'{_ITEM_OPEN}{item_id}" href="{xhtml_name}" media-type="application/xhtml+xml" />'
            )
            self.spine.append(f'<itemref idref="{item_id}"/>')

    def add_images(self, image_files: list[str]) -> None:
        """Append manifest items for every discovered image file."""
        for img_name in set(image_files):
            parts = img_name.split(".")
            head = f"{_IMG_ID_PREFIX}{_basename_id(img_name)}"
            extension = parts[-1] if len(parts) > 1 else ""
            media_type = "jpeg" if "jp" in extension else extension
            self.manifest.append(
                f'{_ITEM_OPEN}{head}" href="Images/{img_name}" media-type="image/{media_type}" />'
            )

    def add_styles(self, css_files: list[str]) -> None:
        """Append manifest items for every discovered CSS file."""
        for idx, css_name in enumerate(css_files):
            self.manifest.append(
                f'{_ITEM_OPEN}style_{idx:0>2}" href="Styles/{css_name}" media-type="text/css" />'
            )

    def add_fonts(self, fonts: list[str]) -> None:
        """Append manifest items for every recognized font file."""
        for font_file in fonts:
            ext = font_file.split(".")[-1].lower()
            mime = _FONT_MIMETYPES.get(ext)
            if not mime:
                continue
            font_id = f"font_{_basename_id(font_file)}"
            self.manifest.append(
                f'{_ITEM_OPEN}{font_id}" href="Styles/{font_file}" media-type="{mime}" />'
            )

    def add_videos(self, videos_dir: Path) -> None:
        """Append manifest items for every video file on disk."""
        if not videos_dir.is_dir():
            return
        for video_file in sorted(videos_dir.iterdir()):
            if not video_file.is_file():
                continue
            ext = video_file.suffix.lstrip(".").lower()
            video_id = f"video_{escape(video_file.stem)}"
            self.manifest.append(
                f'{_ITEM_OPEN}{video_id}" href="Video/{video_file.name}" '
                f'media-type="video/{ext}" />'
            )


def render_content_opf(
    book_info: BookInfo,
    chapters: list[Chapter],
    css_dir: Path,
    images_dir: Path,
    videos_dir: Path,
    fonts: list[str],
    *,
    cover_src: str | None = None,
) -> str:
    """Generate the EPUB package file (``content.opf``).

    Scans the given asset directories for actual files on disk, then
    builds the OPF manifest and spine from the chapter list.

    Parameters
    ----------
    book_info:
        Validated book metadata.
    chapters:
        Ordered list of chapters (used for manifest and spine).
    css_dir:
        Path to the ``Styles/`` directory.
    images_dir:
        Path to the ``Images/`` directory.
    videos_dir:
        Path to the ``Video/`` directory.
    fonts:
        List of font filenames that were downloaded.
    cover_src:
        Optional cover image ``src`` attribute (e.g. ``"Images/cover.png"``).

    Returns:
    -------
    str
        The rendered ``content.opf`` XML string.

    """
    builder = _OpfManifest()
    builder.add_chapters(chapters)
    builder.add_images(_discover_images(images_dir))
    builder.add_styles(_discover_css(css_dir))
    builder.add_fonts(fonts)
    builder.add_videos(videos_dir)

    first_chapter = _to_xhtml(chapters[0].filename) if chapters else ""

    creators = "\n".join(
        f'<dc:creator opf:file-as="{escape(aut.name)}" '
        f'opf:role="aut">{escape(aut.name)}</dc:creator>'
        for aut in book_info.authors
    )
    subjects = "\n".join(
        f"<dc:subject>{escape(sub.name)}</dc:subject>" for sub in book_info.subjects
    )

    return CONTENT_OPF.format(
        book_info.isbn or book_info.identifier,
        escape(book_info.title),
        creators,
        escape(book_info.description),
        subjects,
        ", ".join(escape(pub.name) for pub in book_info.publishers),
        escape(book_info.rights),
        book_info.issued or "",
        _resolve_cover_id(cover_src, book_info),
        "\n".join(builder.manifest),
        "\n".join(builder.spine),
        first_chapter,
    )


# ---------------------------------------------------------------------------
# TOC NCX generation
# ---------------------------------------------------------------------------


def normalize_toc(v2_toc: list[dict[str, Any]], depth: int = 1) -> list[TocEntry]:
    """Convert raw API TOC entries into :class:`TocEntry` models.

    Recursively processes the ``children`` field to build the full tree.

    Parameters
    ----------
    v2_toc:
        Raw TOC entries from the API.
    depth:
        Current nesting depth (starts at 1).

    Returns:
    -------
    list[TocEntry]
        Normalized table of contents entries.

    """
    normalized: list[TocEntry] = []
    for index, entry in enumerate(v2_toc):
        normalized.append(_build_toc_entry(entry, depth, index))
    return normalized


def _build_toc_entry(entry: dict[str, Any], depth: int, index: int) -> TocEntry:
    """Build a single :class:`TocEntry` from a raw API *entry* dict."""
    href = unquote(entry.get("url", entry.get("href", "")))
    fragment = href.split("#")[-1] if "#" in href else ""
    children: list[TocEntry] = []
    if entry.get("children"):
        children = normalize_toc(entry["children"], depth + 1)
    entry_id = entry.get("id", "")
    return TocEntry(
        depth=depth,
        fragment=fragment,
        id=entry_id if entry_id else f"toc_{depth}_{index}",
        label=entry.get("label", entry.get("title", "")),
        href=href,
        children=children,
    )


def _render_navpoints(
    entries: list[TocEntry],
    counter: int = 0,
    max_depth: int = 0,
) -> tuple[str, int, int]:
    """Recursively render ``<navPoint>`` elements for the NCX.

    Parameters
    ----------
    entries:
        TOC entries at the current level.
    counter:
        Running play-order counter.
    max_depth:
        Maximum depth seen so far.

    Returns:
    -------
    tuple[str, int, int]
        ``(xml_string, counter, max_depth)``

    """
    chunks: list[str] = []
    for entry in entries:
        counter += 1
        max_depth = max(max_depth, entry.depth)
        chunks.append(_open_navpoint(entry, counter))

        if entry.children:
            child_xml, counter, max_depth = _render_navpoints(entry.children, counter, max_depth)
            chunks.append(child_xml)

        chunks.append("</navPoint>\n")

    return "".join(chunks), counter, max_depth


def _open_navpoint(entry: TocEntry, play_order: int) -> str:
    """Render the opening ``<navPoint>`` markup for a single *entry*."""
    nav_id = entry.fragment if entry.fragment else entry.id
    href_xhtml = _to_xhtml(entry.href).split("/")[-1]
    return (
        f'<navPoint id="{nav_id}" playOrder="{play_order}">'
        f"<navLabel><text>{escape(entry.label)}</text></navLabel>"
        f'<content src="{href_xhtml}"/>'
    )


async def render_toc_ncx(
    client: ApiClient,
    toc_url: str,
    book_info: BookInfo,
) -> str:
    """Fetch TOC data from the API and render the NCX XML.

    Parameters
    ----------
    client:
        Authenticated API client.
    toc_url:
        Full URL to the book's table-of-contents API endpoint.
    book_info:
        Book metadata (used for the NCX header).

    Returns:
    -------
    str
        The rendered ``toc.ncx`` XML string.

    Raises:
    ------
    DownloadError
        When the TOC cannot be fetched or parsed.

    """
    try:
        payload = await client.get_json(toc_url)
    except ApiError as exc:
        msg = (
            "Unable to retrieve book TOC. "
            "Don't delete any files, just run again to complete the EPUB creation."
        )
        raise DownloadError(msg) from exc

    normalized = normalize_toc(_extract_toc_list(payload))
    navmap, _, max_depth = _render_navpoints(normalized)

    return TOC_NCX.format(
        book_info.isbn or book_info.identifier,
        max_depth,
        book_info.title,
        ", ".join(aut.name for aut in book_info.authors),
        navmap,
    )


def _extract_toc_list(payload: Any) -> list[dict[str, Any]]:
    """Coerce the raw TOC API *payload* into a list of entry dicts.

    Raises:
    ------
    DownloadError
        When the payload is not a recognized TOC shape.

    """
    # mypy knows get_json returns dict, but the runtime API can vary.
    if isinstance(payload, list):
        toc_list = payload
    elif isinstance(payload, dict):
        toc_list = payload.get("children") or payload.get("results") or []
    else:
        msg = "Unexpected TOC response format."
        raise DownloadError(msg)

    if not isinstance(toc_list, list):
        msg = "TOC data is not a list — API may have returned an error."
        raise DownloadError(msg)
    return toc_list


# ---------------------------------------------------------------------------
# EPUB packaging
# ---------------------------------------------------------------------------

_MIMETYPE = "mimetype"
_EPUB_SUFFIX = ".epub"


def build_epub(book_paths: BookPaths, epub_output_path: Path) -> Path:
    """Package the book directory into a valid EPUB (ZIP) file.

    Per the EPUB specification, the ``mimetype`` file must be the first
    entry in the ZIP archive and must be stored (not compressed).

    Parameters
    ----------
    book_paths:
        Resolved paths to the book directory tree.
    epub_output_path:
        Full path where the EPUB file will be written.

    Returns:
    -------
    Path
        Path to the generated ``.epub`` file.

    Raises:
    ------
    DownloadError
        If the EPUB cannot be assembled.

    """
    book_dir = book_paths.book_dir
    mimetype_path = _stage_epub_sources(book_paths)

    # Remove old epub if it exists.
    if epub_output_path.exists():
        epub_output_path.unlink()

    try:
        with zipfile.ZipFile(epub_output_path, "w") as archive:
            # Mimetype MUST be first and stored (uncompressed).
            archive.write(mimetype_path, _MIMETYPE, compress_type=zipfile.ZIP_STORED)
            _add_book_files(archive, book_dir)
    except OSError as exc:
        msg = f"Failed to create EPUB archive: {exc}"
        raise DownloadError(msg) from exc

    logger.info("EPUB created: %s", epub_output_path)
    return epub_output_path


def _stage_epub_sources(book_paths: BookPaths) -> Path:
    """Write the ``mimetype`` and ``container.xml`` files, returning the former."""
    mimetype_path = book_paths.book_dir / _MIMETYPE
    mimetype_path.write_text("application/epub+zip", encoding="utf-8")

    container_path = book_paths.meta_inf / "container.xml"
    container_path.write_bytes(CONTAINER_XML.encode("utf-8", "xmlcharrefreplace"))
    return mimetype_path


def _add_book_files(archive: zipfile.ZipFile, book_dir: Path) -> None:
    """Add every book file except ``mimetype`` and stale EPUBs to *archive*."""
    for file_path in sorted(book_dir.rglob("*")):
        arcname = str(file_path.relative_to(book_dir))
        if _should_archive(file_path, arcname):
            archive.write(file_path, arcname, compress_type=zipfile.ZIP_DEFLATED)


def _should_archive(file_path: Path, arcname: str) -> bool:
    """Return ``True`` when *file_path* belongs in the EPUB archive.

    Excludes non-files, the already-added ``mimetype`` entry, and stale
    ``.epub`` artifacts.
    """
    if not file_path.is_file():
        return False
    if arcname == _MIMETYPE:
        return False  # Already added.
    return file_path.suffix != _EPUB_SUFFIX
