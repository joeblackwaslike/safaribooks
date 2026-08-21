"""Chapter HTML writing and EPUB (ZIP) packaging."""

import logging
import zipfile
from pathlib import Path
from typing import ClassVar

from safaribooks.core.constants import (
    BASE_HTML_HEAD,
    BASE_HTML_TAIL,
    CONTAINER_XML,
    EREADER_CSS,
)
from safaribooks.core.epub.paths import BookPaths
from safaribooks.core.exceptions import DownloadError

logger = logging.getLogger(__name__)


def write_chapter_html(
    path: Path,
    css_content: str,
    body_content: str,
) -> None:
    """Write a single chapter XHTML file.

    Wraps the CSS and body content in the standard EPUB XHTML template
    (``BASE_HTML_HEAD`` + ``EREADER_CSS`` + ``BASE_HTML_TAIL``).

    Parameters
    ----------
    path:
        Destination file path (should end in ``.xhtml``).
    css_content:
        CSS ``<link>`` tags and/or inline ``<style>`` blocks.
    body_content:
        The XHTML body fragment.

    """
    template = BASE_HTML_HEAD + EREADER_CSS + BASE_HTML_TAIL

    html = template.format(css_content, body_content)
    path.write_bytes(html.encode("utf-8", "xmlcharrefreplace"))
    logger.debug("Created chapter: %s", path.name)


class _EpubArchiver:
    """Stages EPUB source files and writes them into a ZIP archive."""

    mimetype: ClassVar[str] = "mimetype"
    epub_suffix: ClassVar[str] = ".epub"

    def __init__(self, book_paths: BookPaths) -> None:
        self._book_paths = book_paths

    def stage_sources(self) -> Path:
        """Write the ``mimetype`` and ``container.xml`` files, returning the former."""
        mimetype_path = self._book_paths.book_dir / self.mimetype
        mimetype_path.write_text("application/epub+zip", encoding="utf-8")

        container_path = self._book_paths.meta_inf / "container.xml"
        container_path.write_bytes(CONTAINER_XML.encode("utf-8", "xmlcharrefreplace"))
        return mimetype_path

    def add_book_files(self, archive: zipfile.ZipFile, book_dir: Path) -> None:
        """Add every book file except ``mimetype`` and stale EPUBs to *archive*."""
        for file_path in sorted(book_dir.rglob("*")):
            arcname = str(file_path.relative_to(book_dir))
            if self._should_archive(file_path, arcname):
                archive.write(file_path, arcname, compress_type=zipfile.ZIP_DEFLATED)

    def _should_archive(self, file_path: Path, arcname: str) -> bool:
        """Return ``True`` when *file_path* belongs in the EPUB archive.

        Excludes non-files, the already-added ``mimetype`` entry, and stale
        ``.epub`` artifacts.
        """
        if not file_path.is_file():
            return False
        if arcname == self.mimetype:
            return False
        return file_path.suffix != self.epub_suffix


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
    archiver = _EpubArchiver(book_paths)
    book_dir = book_paths.book_dir
    mimetype_path = archiver.stage_sources()

    if epub_output_path.exists():
        epub_output_path.unlink()

    try:
        with zipfile.ZipFile(epub_output_path, "w") as archive:
            archive.write(mimetype_path, archiver.mimetype, compress_type=zipfile.ZIP_STORED)
            archiver.add_book_files(archive, book_dir)
    except OSError as exc:
        msg = f"Failed to create EPUB archive: {exc}"
        raise DownloadError(msg) from exc

    logger.info("EPUB created: %s", epub_output_path)
    return epub_output_path
