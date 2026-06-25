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


class EpubReadError(SafariBooksError):
    """Raised when an EPUB archive cannot be opened or its OPF parsed."""


class OffsetOverflowError(SafariBooksError):
    """Raised when a chapter offset exceeds the fixed front-matter field width."""

    def __init__(self, chapter: str, value: int, width: int) -> None:
        """Record the offending chapter, value, and field width."""
        self.chapter = chapter
        self.value = value
        self.width = width
        super().__init__(
            f"Offset {value} for chapter {chapter!r} exceeds {width}-digit field width",
        )


class UnknownExtensionError(SafariBooksError):
    """Raised when a configured Markdown extension name is not registered."""

    def __init__(self, name: str, available: list[str]) -> None:
        """Record the unknown name and the list of available extensions."""
        self.name = name
        self.available = available
        joined = ", ".join(available) or "(none)"
        super().__init__(f"Unknown markdown extension {name!r}; available: {joined}")
