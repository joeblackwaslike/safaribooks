"""Search-API Pydantic models for safaribooks."""

from pydantic import BaseModel


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

    results: list[SearchResult] = []  # noqa: WPS110  -- bound to O'Reilly API JSON key
    count: int = 0
    total: int = 0
    next: str | None = None
    previous: str | None = None
