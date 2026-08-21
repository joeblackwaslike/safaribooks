"""Table-of-contents normalization for the v2 API."""

from typing import Any
from urllib.parse import unquote

from safaribooks.core.models import TocEntry

_FRAGMENT_SEP = "#"


def _build_toc_entry(entry: dict[str, Any], depth: int, position: int) -> TocEntry:
    """Convert a single raw TOC *entry* dict into a :class:`TocEntry`."""
    href = unquote(entry.get("url", entry.get("href", "")))
    entry_id = entry.get("id", "")

    fragment = ""
    if _FRAGMENT_SEP in href:
        fragment = href.split(_FRAGMENT_SEP)[-1]

    children: list[TocEntry] = []
    if entry.get("children"):
        children = normalize_toc(entry["children"], depth + 1)

    return TocEntry(
        depth=depth,
        fragment=fragment,
        id=entry_id if entry_id else f"toc_{depth}_{position}",
        label=entry.get("label", entry.get("title", "")),
        href=href,
        children=children,
    )


def normalize_toc(raw_toc: list[dict[str, Any]], depth: int = 0) -> list[TocEntry]:
    """Convert a v2 API table-of-contents tree into :class:`TocEntry` models.

    Parameters
    ----------
    raw_toc:
        List of TOC entry dicts from the API.  Each may have ``url``
        or ``href``, ``label`` or ``title``, and ``children``.
    depth:
        Current nesting depth (0 for top-level entries).

    Returns:
    -------
    list[TocEntry]
        Normalized TOC tree.

    """
    entries: list[TocEntry] = []
    for position, entry in enumerate(raw_toc):
        entries.append(_build_toc_entry(entry, depth, position))
    return entries
