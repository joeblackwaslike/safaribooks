"""EPUB generation: directory structure, OPF metadata, TOC NCX, chapter HTML, ZIP packaging."""


import logging
import re
import sys
import zipfile
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from safaribooks.core.api import ApiClient
from safaribooks.core.constants import (
    BASE_01_HTML,
    BASE_02_HTML,
    CONTAINER_XML,
    CONTENT_OPF,
    KINDLE_HTML,
    TOC_NCX,
)
from safaribooks.core.exceptions import ApiError, DownloadError
from safaribooks.core.models import BookInfo, Chapter, TocEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

_UNSAFE_CHARS = frozenset("~#%&*{}\\<>?/`'\"|+:")


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
    if ":" in name:
        idx = name.index(":")
        if idx > 15:
            name = name.split(":")[0]
        elif "win" in sys.platform:
            name = name.replace(":", ",")

    for ch in _UNSAFE_CHARS:
        if ch in name:
            name = name.replace(ch, "_")

    if clean_space:
        name = name.replace(" ", "")

    return name


def ensure_book_dirs(output_dir: Path, dirname: str) -> BookPaths:
    """Create the standard EPUB directory tree under *output_dir*.

    The tree looks like::

        <output_dir>/<dirname>/
            OEBPS/
                Text/          (not used by legacy, kept for completeness)
                Styles/
                Images/
                Video/
            META-INF/

    Parameters
    ----------
    output_dir:
        Parent output directory (e.g. ``Books/``).
    dirname:
        Sanitized directory name for this book.

    Returns:
    -------
    BookPaths
        Resolved paths to every subdirectory.

    """
    book_dir = output_dir / dirname
    oebps = book_dir / "OEBPS"
    text = oebps / "Text"
    styles = oebps / "Styles"
    images = oebps / "Images"
    videos = oebps / "Video"
    meta_inf = book_dir / "META-INF"

    for d in (book_dir, oebps, text, styles, images, videos, meta_inf):
        if d.exists():
            logger.debug("Directory already exists: %s", d)
        else:
            d.mkdir(parents=True, exist_ok=True)

    return BookPaths(
        book_dir=book_dir,
        oebps=oebps,
        text=text,
        styles=styles,
        images=images,
        videos=videos,
        meta_inf=meta_inf,
    )


# ---------------------------------------------------------------------------
# Chapter HTML
# ---------------------------------------------------------------------------


def write_chapter_html(
    path: Path,
    css_content: str,
    body_content: str,
    *,
    kindle: bool = False,
) -> None:
    """Write a single chapter XHTML file.

    Wraps the CSS and body content in the standard EPUB XHTML template
    (``BASE_01_HTML`` + optional ``KINDLE_HTML`` + ``BASE_02_HTML``).

    Parameters
    ----------
    path:
        Destination file path (should end in ``.xhtml``).
    css_content:
        CSS ``<link>`` tags and/or inline ``<style>`` blocks.
    body_content:
        The XHTML body fragment.
    kindle:
        If ``True``, include Kindle-specific CSS overrides.

    """
    template = BASE_01_HTML
    if kindle:
        template += KINDLE_HTML
    template += BASE_02_HTML

    html = template.format(css_content, body_content)
    path.write_bytes(html.encode("utf-8", "xmlcharrefreplace"))
    logger.debug("Created chapter: %s", path.name)


# ---------------------------------------------------------------------------
# content.opf generation
# ---------------------------------------------------------------------------

# Map of font file extensions to their MIME types.
_FONT_MIMETYPES: dict[str, str] = {
    "otf": "font/otf",
    "ttf": "font/ttf",
    "woff": "font/woff",
    "woff2": "font/woff2",
}


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
    # Discover CSS files on disk.
    css_files = (
        sorted(f.name for f in css_dir.iterdir() if f.suffix == ".css") if css_dir.is_dir() else []
    )

    # Discover image files on disk.
    image_files = (
        sorted(f.name for f in images_dir.iterdir() if f.is_file()) if images_dir.is_dir() else []
    )

    manifest: list[str] = []
    spine: list[str] = []

    # Chapters
    for chapter in chapters:
        xhtml_name = chapter.filename.replace(".html", ".xhtml")
        item_id = escape("".join(xhtml_name.split(".")[:-1]))
        manifest.append(
            f'<item id="{item_id}" href="{xhtml_name}" media-type="application/xhtml+xml" />'
        )
        spine.append(f'<itemref idref="{item_id}"/>')

    # Images
    for img_name in set(image_files):
        parts = img_name.split(".")
        head = "img_" + escape("".join(parts[:-1]))
        extension = parts[-1] if len(parts) > 1 else ""
        media_type = "jpeg" if "jp" in extension else extension
        manifest.append(
            f'<item id="{head}" href="Images/{img_name}" media-type="image/{media_type}" />'
        )

    # CSS
    for idx, css_name in enumerate(css_files):
        manifest.append(
            f'<item id="style_{idx:0>2}" href="Styles/{css_name}" media-type="text/css" />'
        )

    # Fonts
    for font_file in fonts:
        ext = font_file.split(".")[-1].lower()
        mime = _FONT_MIMETYPES.get(ext)
        if not mime:
            continue
        font_id = "font_" + escape("".join(font_file.split(".")[:-1]))
        manifest.append(f'<item id="{font_id}" href="Styles/{font_file}" media-type="{mime}" />')

    # Videos
    if videos_dir.is_dir():
        for video_file in sorted(videos_dir.iterdir()):
            if not video_file.is_file():
                continue
            ext = video_file.suffix.lstrip(".").lower()
            video_id = "video_" + escape(video_file.stem)
            manifest.append(
                f'<item id="{video_id}" href="Video/{video_file.name}" media-type="video/{ext}" />'
            )

    # Authors and subjects
    authors = "\n".join(
        f'<dc:creator opf:file-as="{escape(aut.name)}" '
        f'opf:role="aut">{escape(aut.name)}</dc:creator>'
        for aut in book_info.authors
    )

    subjects = "\n".join(
        f"<dc:subject>{escape(sub.name)}</dc:subject>" for sub in book_info.subjects
    )

    # Cover ID resolution
    cover_id = cover_src or (book_info.cover or "")
    if cover_id:
        match = re.search(r"/(\w+)\.", cover_id)
        if match is None:
            match = re.search(r"(\w+)\.", cover_id)
        if match is not None:
            cover_id = "img_" + match.group(1)

    # Publisher string
    publisher_str = ", ".join(escape(pub.name) for pub in book_info.publishers)

    # First chapter filename for guide cover reference
    first_chapter = chapters[0].filename.replace(".html", ".xhtml") if chapters else ""

    return CONTENT_OPF.format(
        book_info.isbn or book_info.identifier,
        escape(book_info.title),
        authors,
        escape(book_info.description),
        subjects,
        publisher_str,
        escape(book_info.rights),
        book_info.issued or "",
        cover_id or "",
        "\n".join(manifest),
        "\n".join(spine),
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
    result: list[TocEntry] = []
    for entry in v2_toc:
        href = unquote(entry.get("url", entry.get("href", "")))
        entry_id = entry.get("id", "")
        label = entry.get("label", entry.get("title", ""))
        fragment = ""
        if "#" in href:
            fragment = href.split("#")[-1]
        children: list[TocEntry] = []
        if entry.get("children"):
            children = normalize_toc(entry["children"], depth + 1)
        result.append(
            TocEntry(
                depth=depth,
                fragment=fragment,
                id=entry_id if entry_id else f"toc_{depth}_{len(result)}",
                label=label,
                href=href,
                children=children,
            )
        )
    return result


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
    result = ""
    for entry in entries:
        counter += 1
        max_depth = max(max_depth, entry.depth)

        nav_id = entry.fragment if entry.fragment else entry.id
        href_xhtml = entry.href.replace(".html", ".xhtml").split("/")[-1]

        result += (
            f'<navPoint id="{nav_id}" playOrder="{counter}">'
            f"<navLabel><text>{escape(entry.label)}</text></navLabel>"
            f'<content src="{href_xhtml}"/>'
        )

        if entry.children:
            child_xml, counter, max_depth = _render_navpoints(entry.children, counter, max_depth)
            result += child_xml

        result += "</navPoint>\n"

    return result, counter, max_depth


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
        data = await client.get_json(toc_url)
    except ApiError as exc:
        msg = (
            "Unable to retrieve book TOC. "
            "Don't delete any files, just run again to complete the EPUB creation."
        )
        raise DownloadError(msg) from exc

    # mypy knows get_json returns dict, but the runtime API can vary.
    raw_data: Any = data
    toc_list: list[dict[str, Any]]
    if isinstance(raw_data, list):
        toc_list = raw_data
    elif isinstance(raw_data, dict):
        toc_list = raw_data.get("children") or raw_data.get("results") or []
    else:
        msg = "Unexpected TOC response format."
        raise DownloadError(msg)

    if not isinstance(toc_list, list):
        msg = "TOC data is not a list — API may have returned an error."
        raise DownloadError(msg)

    normalized = normalize_toc(toc_list)
    navmap, _, max_depth = _render_navpoints(normalized)

    author_str = ", ".join(aut.name for aut in book_info.authors)

    return TOC_NCX.format(
        book_info.isbn or book_info.identifier,
        max_depth,
        book_info.title,
        author_str,
        navmap,
    )


# ---------------------------------------------------------------------------
# EPUB packaging
# ---------------------------------------------------------------------------


def build_epub(book_paths: BookPaths, book_title: str) -> Path:
    """Package the book directory into a valid EPUB (ZIP) file.

    Per the EPUB specification, the ``mimetype`` file must be the first
    entry in the ZIP archive and must be stored (not compressed).

    Parameters
    ----------
    book_paths:
        Resolved paths to the book directory tree.
    book_title:
        Book title used to derive the output filename.

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

    # Write the mimetype file.
    mimetype_path = book_dir / "mimetype"
    mimetype_path.write_text("application/epub+zip", encoding="utf-8")

    # Write container.xml.
    container_path = book_paths.meta_inf / "container.xml"
    container_path.write_bytes(CONTAINER_XML.encode("utf-8", "xmlcharrefreplace"))

    # Determine output path.
    epub_name = sanitize_dirname(book_title, clean_space=True) + ".epub"
    epub_path = book_dir / epub_name

    # Remove old epub if it exists.
    if epub_path.exists():
        epub_path.unlink()

    try:
        with zipfile.ZipFile(epub_path, "w") as zf:
            # Mimetype MUST be first and stored (uncompressed).
            zf.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)

            # Walk the book directory and add everything else.
            for file_path in sorted(book_dir.rglob("*")):
                if not file_path.is_file():
                    continue
                arcname = str(file_path.relative_to(book_dir))
                if arcname == "mimetype":
                    continue  # Already added.
                if file_path.suffix == ".epub":
                    continue  # Don't include old epub files.
                zf.write(file_path, arcname, compress_type=zipfile.ZIP_DEFLATED)

    except OSError as exc:
        msg = f"Failed to create EPUB archive: {exc}"
        raise DownloadError(msg) from exc

    logger.info("EPUB created: %s", epub_path)
    return epub_path
