"""Exceptions raised by the EPUB-to-Markdown export pipeline."""

from safaribooks.core.exceptions.core import SafariBooksError


class EpubReadError(SafariBooksError):
    """Raised when an EPUB archive cannot be opened or its OPF parsed."""


class OffsetOverflowError(SafariBooksError):
    """Raised when a chapter offset exceeds the fixed front-matter field width."""

    def __init__(self, chapter: str, offset: int, width: int) -> None:
        """Record the offending chapter, offset, and field width."""
        self.chapter = chapter
        self.offset = offset
        self.width = width
        super().__init__(
            f"Offset {offset} for chapter {chapter!r} exceeds {width}-digit field width",
        )


class UnknownExtensionError(SafariBooksError):
    """Raised when a configured Markdown extension name is not registered."""

    def __init__(self, name: str, available: list[str]) -> None:
        """Record the unknown name and the list of available extensions."""
        self.name = name
        self.available = available
        joined = ", ".join(available) or "(none)"
        super().__init__(f"Unknown markdown extension {name!r}; available: {joined}")
