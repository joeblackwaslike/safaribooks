"""Rendering of the EPUB package document (``content.opf``)."""

import re
from html import escape
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

from safaribooks.core.constants import CONTENT_OPF
from safaribooks.core.epub.paths import BookPaths
from safaribooks.core.models import BookInfo, Chapter


def _to_xhtml(filename: str) -> str:
    """Return *filename* with its ``.html`` suffix swapped for ``.xhtml``."""
    return filename.replace(".html", ".xhtml")


def _basename_id(name: str) -> str:
    """Return *name* without its final dot-extension, HTML-escaped."""
    return escape("".join(name.split(".")[:-1]))


class _ManifestItems:
    """Builds the OPF ``<manifest>`` items and ``<spine>`` references."""

    font_mimetypes: ClassVar[MappingProxyType[str, str]] = MappingProxyType({
        "otf": "font/otf",
        "ttf": "font/ttf",
        "woff": "font/woff",
        "woff2": "font/woff2",
    })
    img_id_prefix: ClassVar[str] = "img_"
    item_open: ClassVar[str] = '<item id="'

    def __init__(self) -> None:
        self.manifest: list[str] = []
        self.spine: list[str] = []

    def add_chapters(self, chapters: list[Chapter]) -> None:
        """Append manifest items and spine refs for every chapter."""
        for chapter in chapters:
            xhtml_name = _to_xhtml(chapter.filename)
            item_id = _basename_id(xhtml_name)
            self.manifest.append(
                f'{self.item_open}{item_id}" href="{xhtml_name}" '
                'media-type="application/xhtml+xml" />'
            )
            self.spine.append(f'<itemref idref="{item_id}"/>')

    def add_images(self, image_files: list[str]) -> None:
        """Append manifest items for every discovered image file."""
        for img_name in set(image_files):
            parts = img_name.split(".")
            head = f"{self.img_id_prefix}{_basename_id(img_name)}"
            extension = parts[-1] if len(parts) > 1 else ""
            media_type = "jpeg" if "jp" in extension else extension
            self.manifest.append(
                f'{self.item_open}{head}" href="Images/{img_name}" '
                f'media-type="image/{media_type}" />'
            )

    def add_styles(self, css_files: list[str]) -> None:
        """Append manifest items for every discovered CSS file."""
        for idx, css_name in enumerate(css_files):
            self.manifest.append(
                f'{self.item_open}style_{idx:0>2}" href="Styles/{css_name}" '
                'media-type="text/css" />'
            )

    def add_fonts(self, fonts: list[str]) -> None:
        """Append manifest items for every recognized font file."""
        for font_file in fonts:
            ext = font_file.split(".")[-1].lower()
            mime = self.font_mimetypes.get(ext)
            if not mime:
                continue
            font_id = f"font_{_basename_id(font_file)}"
            self.manifest.append(
                f'{self.item_open}{font_id}" href="Styles/{font_file}" media-type="{mime}" />'
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
                f'{self.item_open}{video_id}" href="Video/{video_file.name}" '
                f'media-type="video/{ext}" />'
            )


class _AssetScanner:
    """Discovers on-disk asset files and resolves the cover manifest id."""

    def discover_css(self, css_dir: Path) -> list[str]:
        """Return sorted CSS filenames found directly in *css_dir*."""
        if not css_dir.is_dir():
            return []
        return sorted(entry.name for entry in css_dir.iterdir() if entry.suffix == ".css")

    def discover_images(self, images_dir: Path) -> list[str]:
        """Return sorted image filenames found directly in *images_dir*."""
        if not images_dir.is_dir():
            return []
        return sorted(entry.name for entry in images_dir.iterdir() if entry.is_file())

    def resolve_cover_id(self, cover_src: str | None, book_info: BookInfo) -> str:
        """Resolve the manifest cover id from *cover_src* or book metadata."""
        cover_id = cover_src or (book_info.cover or "")
        if not cover_id:
            return ""
        match = re.search(r"/(\w+)\.", cover_id)
        if match is None:
            match = re.search(r"(\w+)\.", cover_id)
        if match is not None:
            return f"{_ManifestItems.img_id_prefix}{match.group(1)}"
        return cover_id


def render_content_opf(
    book_info: BookInfo,
    chapters: list[Chapter],
    book_paths: BookPaths,
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
    book_paths:
        Resolved directory paths for the book (uses ``styles``,
        ``images``, and ``videos``).
    fonts:
        List of font filenames that were downloaded.
    cover_src:
        Optional cover image ``src`` attribute (e.g. ``"Images/cover.png"``).

    Returns:
    -------
    str
        The rendered ``content.opf`` XML string.

    """
    scanner = _AssetScanner()
    builder = _ManifestItems()
    builder.add_chapters(chapters)
    builder.add_images(scanner.discover_images(book_paths.images))
    builder.add_styles(scanner.discover_css(book_paths.styles))
    builder.add_fonts(fonts)
    builder.add_videos(book_paths.videos)

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
        scanner.resolve_cover_id(cover_src, book_info),
        "\n".join(builder.manifest),
        "\n".join(builder.spine),
        first_chapter,
    )
