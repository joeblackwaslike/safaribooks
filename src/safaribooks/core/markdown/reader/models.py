"""Dataclasses describing a parsed EPUB and shared reader constants."""

from dataclasses import dataclass, field

CONTAINER_PATH = "META-INF/container.xml"
XHTML_MEDIA_TYPES = frozenset(("application/xhtml+xml", "text/html"))
CONTENT_ID = "sbo-rt-content"


@dataclass(frozen=True, slots=True)
class EpubMetadata:
    """Raw Dublin-Core metadata pulled from the OPF."""

    title: str = ""
    authors: tuple[str, ...] = ()
    publisher: str = ""
    published: str = ""
    isbn: str = ""
    language: str = ""
    source_file: str = ""


@dataclass(frozen=True, slots=True)
class EpubChapter:
    """One spine document: a resolved title and its content element."""

    title: str
    element: object  # lxml HtmlElement; typed loosely to avoid no-any-unimported leaks


@dataclass(frozen=True, slots=True)
class EpubDocument:
    """A parsed EPUB: metadata plus chapters in spine order."""

    metadata: EpubMetadata
    chapters: tuple[EpubChapter, ...] = field(default_factory=tuple)
