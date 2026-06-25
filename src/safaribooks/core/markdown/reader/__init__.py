"""Read a built EPUB archive into chapters and metadata for Markdown export."""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from safaribooks.core.markdown.reader.document import read_epub
from safaribooks.core.markdown.reader.models import (
    EpubChapter,
    EpubDocument,
    EpubMetadata,
)

__all__ = [
    "EpubChapter",
    "EpubDocument",
    "EpubMetadata",
    "read_epub",
]
