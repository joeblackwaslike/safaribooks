"""Book-domain Pydantic models for safaribooks."""

from pydantic import BaseModel


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
