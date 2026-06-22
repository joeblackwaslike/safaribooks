"""Table-of-contents normalization and NCX rendering."""

from html import escape
from typing import Any
from urllib.parse import unquote

from safaribooks.core.api import ApiClient
from safaribooks.core.constants import TOC_NCX
from safaribooks.core.epub.opf import _to_xhtml
from safaribooks.core.exceptions import ApiError, DownloadError
from safaribooks.core.models import BookInfo, TocEntry


def normalize_toc(v2_toc: list[dict[str, Any]], depth: int = 1) -> list[TocEntry]:
    """Convert raw API TOC entries into :class:`TocEntry` models.

    Recursively processes the ``children`` field to build the full tree.

    Parameters
    ----------
    v2_toc:
        Raw TOC entries from the API.
    depth:
        Current nesting depth (starts at 1).

    Returns:
    -------
    list[TocEntry]
        Normalized table of contents entries.

    """
    normalized: list[TocEntry] = []
    for index, entry in enumerate(v2_toc):
        normalized.append(_build_toc_entry(entry, depth, index))
    return normalized


def _build_toc_entry(entry: dict[str, Any], depth: int, index: int) -> TocEntry:
    """Build a single :class:`TocEntry` from a raw API *entry* dict."""
    href = unquote(entry.get("url", entry.get("href", "")))
    fragment = href.split("#")[-1] if "#" in href else ""
    children: list[TocEntry] = []
    if entry.get("children"):
        children = normalize_toc(entry["children"], depth + 1)
    entry_id = entry.get("id", "")
    return TocEntry(
        depth=depth,
        fragment=fragment,
        id=entry_id if entry_id else f"toc_{depth}_{index}",
        label=entry.get("label", entry.get("title", "")),
        href=href,
        children=children,
    )


def _render_navpoints(
    entries: list[TocEntry],
    counter: int = 0,
    max_depth: int = 0,
) -> tuple[str, int, int]:
    """Recursively render ``<navPoint>`` elements for the NCX.

    Parameters
    ----------
    entries:
        TOC entries at the current level.
    counter:
        Running play-order counter.
    max_depth:
        Maximum depth seen so far.

    Returns:
    -------
    tuple[str, int, int]
        ``(xml_string, counter, max_depth)``

    """
    chunks: list[str] = []
    for entry in entries:
        counter += 1
        max_depth = max(max_depth, entry.depth)
        chunks.append(_open_navpoint(entry, counter))

        if entry.children:
            child_xml, counter, max_depth = _render_navpoints(entry.children, counter, max_depth)
            chunks.append(child_xml)

        chunks.append("</navPoint>\n")

    return "".join(chunks), counter, max_depth


def _open_navpoint(entry: TocEntry, play_order: int) -> str:
    """Render the opening ``<navPoint>`` markup for a single *entry*."""
    nav_id = entry.fragment if entry.fragment else entry.id
    href_xhtml = _to_xhtml(entry.href).split("/")[-1]
    return (
        f'<navPoint id="{nav_id}" playOrder="{play_order}">'
        f"<navLabel><text>{escape(entry.label)}</text></navLabel>"
        f'<content src="{href_xhtml}"/>'
    )


def _extract_toc_list(payload: Any) -> list[dict[str, Any]]:
    """Coerce the raw TOC API *payload* into a list of entry dicts.

    Raises:
    ------
    DownloadError
        When the payload is not a recognized TOC shape.

    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        msg = "Unexpected TOC response format."
        raise DownloadError(msg)

    toc_list = payload.get("children") or payload.get("results") or []
    if not isinstance(toc_list, list):
        msg = "TOC data is not a list — API may have returned an error."
        raise DownloadError(msg)
    return toc_list


async def render_toc_ncx(
    client: ApiClient,
    toc_url: str,
    book_info: BookInfo,
) -> str:
    """Fetch TOC data from the API and render the NCX XML.

    Parameters
    ----------
    client:
        Authenticated API client.
    toc_url:
        Full URL to the book's table-of-contents API endpoint.
    book_info:
        Book metadata (used for the NCX header).

    Returns:
    -------
    str
        The rendered ``toc.ncx`` XML string.

    Raises:
    ------
    DownloadError
        When the TOC cannot be fetched or parsed.

    """
    try:
        payload = await client.get_json(toc_url)
    except ApiError as exc:
        msg = (
            "Unable to retrieve book TOC. "
            "Don't delete any files, just run again to complete the EPUB creation."
        )
        raise DownloadError(msg) from exc

    normalized = normalize_toc(_extract_toc_list(payload))
    navmap, _, max_depth = _render_navpoints(normalized)

    return TOC_NCX.format(
        book_info.isbn or book_info.identifier,
        max_depth,
        book_info.title,
        ", ".join(aut.name for aut in book_info.authors),
        navmap,
    )
