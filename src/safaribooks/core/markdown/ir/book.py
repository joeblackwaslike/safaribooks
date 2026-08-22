"""Book-level metadata IR node for the YAML front matter."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BookMeta:
    """Book-level metadata read from the EPUB OPF, for the YAML front matter."""

    title: str
    authors: tuple[str, ...] = ()
    publisher: str = ""
    published: str = ""
    isbn: str = ""
    language: str = ""
    source_file: str = ""
