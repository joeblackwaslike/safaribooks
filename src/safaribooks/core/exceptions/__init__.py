"""Custom exception hierarchy for safaribooks.

This package re-exports its full public API so callers keep using
`from safaribooks.core.exceptions import Thing` after the WPS202 split.
"""

from safaribooks.core.exceptions.core import (
    ApiError,
    AuthenticationError,
    CookieError,
    DownloadError,
    ParsingError,
    SafariBooksError,
    SearchError,
)
from safaribooks.core.exceptions.markdown import (
    EpubReadError,
    OffsetOverflowError,
    UnknownExtensionError,
)

__all__ = [  # noqa: WPS410  -- public re-export surface for the exceptions package
    "ApiError",
    "AuthenticationError",
    "CookieError",
    "DownloadError",
    "EpubReadError",
    "OffsetOverflowError",
    "ParsingError",
    "SafariBooksError",
    "SearchError",
    "UnknownExtensionError",
]
