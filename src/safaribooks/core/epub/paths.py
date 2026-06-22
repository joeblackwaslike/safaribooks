"""Filesystem paths and directory-name sanitization for EPUB builds."""

import logging
import sys
from dataclasses import astuple, dataclass
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

_UNSAFE_CHARS: Final = frozenset((
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
    colon = ":"
    title_truncate_index = 15
    replacement_char = "_"
    if colon in name:
        colon_index = name.index(colon)
        if colon_index > title_truncate_index:
            name = name.split(colon)[0]
        elif "win" in sys.platform:
            name = name.replace(colon, ",")

    for unsafe in _UNSAFE_CHARS:
        if unsafe in name:
            name = name.replace(unsafe, replacement_char)

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
