"""Markdown transformation extensions (built-ins + entry-point discovery)."""
# flake8: noqa: WPS412

from safaribooks.core.markdown.extensions.base import ExtCtx, MarkdownExtension
from safaribooks.core.markdown.extensions.discovery import ENTRY_POINT_GROUP, discover
from safaribooks.core.markdown.extensions.fix_broken_links import FixBrokenLinks
from safaribooks.core.markdown.extensions.fix_headings import FixHeadings
from safaribooks.core.markdown.extensions.pipeline import resolve, run
from safaribooks.core.markdown.extensions.reformat_toc import ReformatToc
from safaribooks.core.markdown.extensions.remove_footnotes import RemoveFootnotes

__all__ = [
    "ENTRY_POINT_GROUP",
    "ExtCtx",
    "FixBrokenLinks",
    "FixHeadings",
    "MarkdownExtension",
    "ReformatToc",
    "RemoveFootnotes",
    "discover",
    "resolve",
    "run",
]
