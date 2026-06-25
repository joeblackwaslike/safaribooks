"""Source provenance metadata carried from the original HTML element."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Meta:
    """Source provenance carried from the original HTML element.

    Extensions such as ``fix-headings`` inspect this to decide whether a styled
    paragraph should become a real heading.
    """

    tag: str = ""
    classes: tuple[str, ...] = ()
    style: str = ""
