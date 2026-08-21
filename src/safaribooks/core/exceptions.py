"""Custom exception hierarchy for safaribooks."""


class SafariBooksError(Exception):
    """Base exception for all safaribooks errors."""


class AuthenticationError(SafariBooksError):
    """Raised when authentication with O'Reilly fails."""


class CookieError(AuthenticationError):
    """Raised when cookies are missing, invalid, or expired."""


class ApiError(SafariBooksError):
    """Raised when an O'Reilly API request fails."""


class ParsingError(SafariBooksError):
    """Raised when HTML/EPUB content cannot be parsed."""


class DownloadError(SafariBooksError):
    """Raised when a chapter, image, or stylesheet download fails."""


class SearchError(SafariBooksError):
    """Raised when a book search fails or returns no results."""
