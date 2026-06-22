"""Pydantic v2 domain models for safaribooks."""
# This package re-exports its full public API so callers keep using
# `from safaribooks.core.models import Thing` after the WPS202 split.

from safaribooks.core.models.book import (
    Author,
    BookInfo,
    Chapter,
    Publisher,
    Stylesheet,
    Subject,
)
from safaribooks.core.models.cookies import CookieSet
from safaribooks.core.models.parse import ParseResult
from safaribooks.core.models.search import SearchResponse, SearchResult
from safaribooks.core.models.toc import TocEntry

__all__ = [  # noqa: WPS410  -- public re-export surface for the models package
    "Author",
    "BookInfo",
    "Chapter",
    "CookieSet",
    "ParseResult",
    "Publisher",
    "SearchResponse",
    "SearchResult",
    "Stylesheet",
    "Subject",
    "TocEntry",
]
