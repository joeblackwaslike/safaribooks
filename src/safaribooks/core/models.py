"""Pydantic v2 domain models for safaribooks."""

from pydantic import BaseModel, model_validator

from safaribooks.core.constants import REQUIRED_COOKIES


class Author(BaseModel):
    """Book author."""

    name: str


class Publisher(BaseModel):
    """Book publisher."""

    name: str


class Subject(BaseModel):
    """Book subject / category tag."""

    name: str


class BookInfo(BaseModel):
    """Metadata for a single O'Reilly book."""

    title: str
    identifier: str
    isbn: str
    description: str
    web_url: str
    rights: str
    cover: str | None = None
    authors: list[Author]
    publishers: list[Publisher]
    subjects: list[Subject]
    issued: str | None = None


class Stylesheet(BaseModel):
    """Reference to a CSS stylesheet used by a chapter."""

    url: str


class Chapter(BaseModel):
    """A single EPUB chapter with its assets."""

    filename: str
    title: str
    content_url: str
    asset_base_url: str
    images: list[str]
    stylesheets: list[Stylesheet]
    site_styles: list[str]


class TocEntry(BaseModel):
    """A table-of-contents entry (self-referential tree)."""

    depth: int
    fragment: str
    id: str
    label: str
    href: str
    children: list["TocEntry"] = []


# Rebuild to resolve the forward reference in `children`.
TocEntry.model_rebuild()


class CookieSet(BaseModel):
    """Validated set of O'Reilly authentication cookies."""

    cookies: dict[str, str]

    @model_validator(mode="after")
    def _check_required_cookies(self) -> "CookieSet":
        missing = REQUIRED_COOKIES - self.cookies.keys()
        if missing:
            msg = f"Missing required cookies: {', '.join(sorted(missing))}"
            raise ValueError(msg)
        return self


class SearchResult(BaseModel):
    """A single book result from the O'Reilly search API."""

    isbn: str = ""
    identifier: str = ""
    archive_id: str = ""
    title: str
    authors: list[str] = []
    publishers: str = ""
    cover_url: str = ""
    web_url: str = ""
    issued: str = ""
    description: str = ""

    @property
    def book_id(self) -> str:
        """Return the best available book identifier."""
        return self.archive_id or self.isbn or self.identifier


class SearchResponse(BaseModel):
    """Paginated response from the O'Reilly search API."""

    results: list[SearchResult] = []
    count: int = 0
    total: int = 0
    next: str | None = None
    previous: str | None = None


class ParseResult(BaseModel):
    """Result of parsing a chapter's HTML content."""

    page_css: str
    body_xhtml: str
    discovered_css: list[str]
    discovered_images: list[str]
    discovered_videos: list[str]
    cover_src: str | None = None
