"""Book metadata retrieval and chapter normalization."""


import logging
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from safaribooks.core.api import ApiClient
from safaribooks.core.constants import (
    CHAPTERS_API_TEMPLATE,
    FILES_API_TEMPLATE,
    SAFARI_BASE_URL,
    SEARCH_API_TEMPLATE,
)
from safaribooks.core.exceptions import ApiError
from safaribooks.core.models import (
    Author,
    BookInfo,
    Chapter,
    Publisher,
    Stylesheet,
    Subject,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_book_info(client: ApiClient, book_id: str) -> BookInfo:
    """Fetch book metadata from the O'Reilly v2 API.

    Parameters
    ----------
    client:
        Authenticated API client.
    book_id:
        The O'Reilly book identifier (ISBN or archive ID).

    Returns:
    -------
    BookInfo
        Validated book metadata.

    Raises:
    ------
    ApiError
        When the API response is missing or malformed.

    """
    api_url = f"{SAFARI_BASE_URL}/api/v2/epubs/urn:orm:book:{book_id}/"
    data = await client.get_json(api_url)

    if not isinstance(data, dict) or "title" not in data:
        msg = f"API returned unexpected data for book {book_id}"
        raise ApiError(msg)

    desc = data.get("description", "")
    if isinstance(data.get("descriptions"), dict):
        desc = data["descriptions"].get("text/plain", data["descriptions"].get("text/html", desc))

    info = BookInfo(
        title=data.get("title", ""),
        identifier=data.get("identifier", book_id),
        isbn=data.get("isbn", ""),
        description=desc or "",
        web_url=data.get("web_url", f"{SAFARI_BASE_URL}/library/view/-/{book_id}/"),
        rights=data.get("rights", ""),
        cover=data.get("cover_url", data.get("cover", None)),
        authors=[],
        publishers=[],
        subjects=[],
        issued=data.get("publication_date", None),
    )

    return _replace_none_fields(info)


async def enrich_book_metadata(
    client: ApiClient,
    book_id: str,
    info: BookInfo,
) -> BookInfo:
    """Enrich *info* with supplementary data from the search API.

    This is a best-effort operation: if the search API is unreachable or
    returns no results, the original *info* is returned unchanged.

    Parameters
    ----------
    client:
        Authenticated API client.
    book_id:
        The O'Reilly book identifier.
    info:
        Base book metadata to enrich.

    Returns:
    -------
    BookInfo
        A (possibly updated) copy of the metadata.

    """
    try:
        search_url = SEARCH_API_TEMPLATE.format(book_id)
        data = await client.get_json(search_url)

        results = data.get("results", [])
        if not results:
            return info

        result = results[0]

        # Verify the search result actually matches our book.
        result_id = str(result.get("isbn", result.get("identifier", "")))
        if book_id not in result_id and result.get("archive_id", "") != book_id:
            return info

        updates: dict[str, object] = {}

        if result.get("authors"):
            updates["authors"] = [Author(name=a) for a in result["authors"]]

        if "publishers" in result:
            pub = result["publishers"]
            if isinstance(pub, str):
                updates["publishers"] = [Publisher(name=pub)]
            elif isinstance(pub, list):
                updates["publishers"] = [
                    Publisher(name=p) if isinstance(p, str) else Publisher(**p) for p in pub
                ]

        if result.get("issued"):
            updates["issued"] = result["issued"]
        elif "date_added" in result:
            updates["issued"] = result["date_added"]

        if result.get("subjects"):
            updates["subjects"] = [Subject(name=s) for s in result["subjects"]]

        if not info.cover and "cover_url" in result:
            updates["cover"] = result["cover_url"]

        if not info.web_url and "web_url" in result:
            updates["web_url"] = result["web_url"]

        if updates:
            info = info.model_copy(update=updates)

    except Exception:
        logger.warning("Could not enrich metadata from search API", exc_info=True)

    return info


async def fetch_chapters(client: ApiClient, book_id: str) -> list[Chapter]:
    """Fetch and normalize all chapters for a book.

    Follows pagination links and reorders chapters so that cover-related
    chapters appear first.

    Parameters
    ----------
    client:
        Authenticated API client.
    book_id:
        The O'Reilly book identifier.

    Returns:
    -------
    list[Chapter]
        Ordered list of normalized chapters.

    Raises:
    ------
    ApiError
        When the chapter list cannot be retrieved.

    """
    chapters_url: str | None = CHAPTERS_API_TEMPLATE.format(book_id)
    all_chapters: list[Chapter] = []

    while chapters_url:
        data = await client.get_json(chapters_url)

        if not isinstance(data, dict):
            msg = f"API returned unexpected data for chapters of book {book_id}"  # type: ignore[unreachable]
            raise ApiError(msg)

        results = data.get("results", [])
        if not results:
            if not all_chapters:
                msg = f"API returned no chapters for book {book_id}"
                raise ApiError(msg)
            break

        all_chapters.extend(normalize_chapter(raw, book_id) for raw in results)

        chapters_url = data.get("next")

    # Reorder: cover chapters first, then the rest.
    cover_chapters = [
        c for c in all_chapters if "cover" in c.filename.lower() or "cover" in c.title.lower()
    ]
    other_chapters = [c for c in all_chapters if c not in cover_chapters]
    return cover_chapters + other_chapters


def normalize_chapter(raw_chapter: dict[str, Any], book_id: str) -> Chapter:
    """Normalize a v2 API chapter response into a :class:`Chapter`.

    Handles the various field-name variants across API versions and
    extracts images, stylesheets, and site styles from both top-level
    fields and the ``related_assets`` sub-object.

    Parameters
    ----------
    raw_chapter:
        Raw chapter dict from the API.
    book_id:
        The O'Reilly book identifier (used for asset URL construction).

    Returns:
    -------
    Chapter
        Normalized chapter model.

    """
    filename = _resolve_filename(raw_chapter)
    content_url = raw_chapter.get("content_url", raw_chapter.get("content", ""))
    asset_base_url = FILES_API_TEMPLATE.format(book_id)

    images = _extract_images(raw_chapter)
    stylesheets = _extract_stylesheets(raw_chapter)
    site_styles = _extract_site_styles(raw_chapter)

    return Chapter(
        filename=filename,
        title=raw_chapter.get("title", ""),
        content_url=content_url,
        asset_base_url=asset_base_url,
        images=images,
        stylesheets=stylesheets,
        site_styles=site_styles,
    )


async def fetch_default_cover(
    client: ApiClient,
    book_info: BookInfo,
    images_path: Path,
) -> str | None:
    """Download the default cover image to *images_path*.

    Tries several URL variants (HD, original, thumbnail) before falling
    back to the raw ``cover`` URL from the book metadata.

    Parameters
    ----------
    client:
        Authenticated API client.
    book_info:
        Book metadata containing the ``cover`` URL.
    images_path:
        Directory where the cover image will be saved.

    Returns:
    -------
    str | None
        The filename of the saved cover (e.g. ``"default_cover.jpeg"``)
        or ``None`` if no cover could be retrieved.

    """
    cover_url = book_info.cover
    if not cover_url:
        logger.info("No cover URL available for this book.")
        return None

    hd_url_attempts = [
        cover_url.replace("/thumb/", "/orig/"),
        cover_url.replace("/thumb/", "/"),
        cover_url.replace("thumbnail", "cover"),
        cover_url,
    ]

    response = None
    for url in hd_url_attempts:
        try:
            response = await client.get(url, stream=True)
            if response.status_code == 200:
                logger.info("Retrieved HD cover from: %s", url)
                break
        except ApiError:
            continue

    if response is None or response.status_code != 200:
        logger.error("Error trying to retrieve the cover: %s", cover_url)
        return None

    content_type = response.headers.get("Content-Type", "image/jpeg")
    file_ext = content_type.split("/")[-1]
    filename = f"default_cover.{file_ext}"

    dest = images_path / filename
    dest.write_bytes(response.content)

    return filename


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _replace_none_fields(info: BookInfo) -> BookInfo:
    """Replace any ``None`` string fields with ``"n/a"``."""
    updates: dict[str, str] = {}
    for field_name in ("title", "identifier", "isbn", "description", "web_url", "rights"):
        if getattr(info, field_name) is None:
            updates[field_name] = "n/a"
    if updates:
        return info.model_copy(update=updates)
    return info


def _resolve_filename(raw_chapter: dict[str, Any]) -> str:
    """Derive a usable filename from a raw v2 API chapter dict."""
    filename = unquote(raw_chapter.get("filename", ""))

    if not filename:
        ourn = raw_chapter.get("ourn", "")
        filename = (
            unquote(ourn.split(":")[-1])
            if ":" in ourn
            else raw_chapter.get("reference_id", "").split("/")[-1]
        )

    if not filename:
        hash_source = raw_chapter.get("content_url", raw_chapter.get("ourn", ""))
        filename = f"chapter_{abs(hash(hash_source))}.html"

    return filename


def _extract_images(raw_chapter: dict[str, Any]) -> list[str]:
    """Extract image URLs from a raw chapter, stripping full URLs to relative paths."""
    images = raw_chapter.get("images", [])
    if not images and "related_assets" in raw_chapter:
        images = raw_chapter["related_assets"].get("images", [])

    return [url.split("/files/")[-1] if "/files/" in url else url for url in images]


def _extract_stylesheets(raw_chapter: dict[str, Any]) -> list[Stylesheet]:
    """Extract stylesheet references, wrapping bare URL strings."""
    stylesheets_raw = raw_chapter.get("stylesheets", [])
    if not stylesheets_raw and "related_assets" in raw_chapter:
        stylesheets_raw = raw_chapter["related_assets"].get("stylesheets", [])

    return [Stylesheet(url=s) if isinstance(s, str) else Stylesheet(**s) for s in stylesheets_raw]


def _extract_site_styles(raw_chapter: dict[str, Any]) -> list[str]:
    """Extract site-level style URLs."""
    site_styles = raw_chapter.get("site_styles", [])
    if not site_styles and "related_assets" in raw_chapter:
        site_styles = raw_chapter["related_assets"].get("site_styles", [])
    return list(site_styles) if site_styles else []
