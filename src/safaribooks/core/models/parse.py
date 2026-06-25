"""Chapter-parsing Pydantic models for safaribooks."""

from pydantic import BaseModel


class ParseContext(BaseModel):
    """Per-chapter context controlling how a chapter is parsed and rewritten."""

    book_id: str
    base_url: str
    first_page: bool = False


class ParseResult(BaseModel):
    """Result of parsing a chapter's HTML content."""

    page_css: str
    body_xhtml: str
    discovered_css: list[str]
    discovered_images: list[str]
    discovered_videos: list[str]
    cover_src: str | None = None
