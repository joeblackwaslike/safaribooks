"""Table-of-contents Pydantic models for safaribooks."""

from pydantic import BaseModel


class TocEntry(BaseModel):
    """A table-of-contents entry (self-referential tree)."""

    depth: int
    fragment: str
    id: str
    label: str
    href: str
    children: list["TocEntry"] = []


TocEntry.model_rebuild()
