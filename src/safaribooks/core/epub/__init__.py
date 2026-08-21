"""EPUB generation: directory structure, OPF metadata, TOC NCX, chapter HTML, ZIP packaging.

This package re-exports its full public API so callers keep using
`from safaribooks.core.epub import Thing` after the WPS202 split. The ``sys``
and ``zipfile`` modules are re-exported so tests can patch
``epub.sys.platform`` and ``epub.zipfile.ZipFile`` at this import path.
"""

from safaribooks.core.epub.opf import render_content_opf
from safaribooks.core.epub.packaging import build_epub, write_chapter_html, zipfile
from safaribooks.core.epub.paths import BookPaths, ensure_book_dirs, sanitize_dirname, sys
from safaribooks.core.epub.toc import _render_navpoints, normalize_toc, render_toc_ncx

__all__ = [  # noqa: WPS410  -- public re-export surface for the epub package
    "BookPaths",
    "_render_navpoints",
    "build_epub",
    "ensure_book_dirs",
    "normalize_toc",
    "render_content_opf",
    "render_toc_ncx",
    "sanitize_dirname",
    "sys",
    "write_chapter_html",
    "zipfile",
]
