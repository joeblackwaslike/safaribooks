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

# HTTP status that indicates a successful asset download.
_HTTP_OK = 200

# Sentinel marking "no value applies" where ``None`` is itself a valid value.
_MISSING = object()

# Repeated field names / fragments, hoisted to avoid string-literal over-use.
_PATH_SEP = "/"
_KEY_RESULTS = "results"
_KEY_WEB_URL = "web_url"
_KEY_COVER = "cover"
_KEY_COVER_URL = "cover_url"
_KEY_PUBLISHERS = "publishers"
_KEY_ISSUED = "issued"
_KEY_RELATED_ASSETS = "related_assets"


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
    api_url = f"{SAFARI_BASE_URL}{_PATH_SEP}api/v2/epubs/urn:orm:book:{book_id}{_PATH_SEP}"
    payload = await client.get_json(api_url)

    if not isinstance(payload, dict) or "title" not in payload:
        msg = f"API returned unexpected data for book {book_id}"
        raise ApiError(msg)

    desc = payload.get("description", "")
    descriptions = payload.get("descriptions")
    if isinstance(descriptions, dict):
        desc = descriptions.get("text/plain", descriptions.get("text/html", desc))

    # Use `or` (not a dict default) so an explicit JSON null from the API
    # coalesces to a valid default instead of failing BookInfo validation.
    return BookInfo(
        title=payload.get("title") or "",
        identifier=payload.get("identifier") or book_id,
        isbn=payload.get("isbn") or "",
        description=desc or "",
        web_url=payload.get(_KEY_WEB_URL) or f"{SAFARI_BASE_URL}/library/view/-/{book_id}/",
        rights=payload.get("rights") or "",
        cover=payload.get(_KEY_COVER_URL, payload.get(_KEY_COVER, None)),
        authors=[],
        publishers=[],
        subjects=[],
        issued=payload.get("publication_date", None),
    )


async def enrich_book_metadata(
    client: ApiClient,
    book_id: str,
    book_info: BookInfo,
) -> BookInfo:
    """Enrich *book_info* with supplementary data from the search API.

    This is a best-effort operation: if the search API is unreachable or
    returns no results, the original *book_info* is returned unchanged.

    Parameters
    ----------
    client:
        Authenticated API client.
    book_id:
        The O'Reilly book identifier.
    book_info:
        Base book metadata to enrich.

    Returns:
    -------
    BookInfo
        A (possibly updated) copy of the metadata.

    """
    try:
        updates = await _Metadata.build_updates(client, book_id, book_info)
    except Exception:
        logger.warning("Could not enrich metadata from search API", exc_info=True)
        return book_info

    if updates:
        return book_info.model_copy(update=updates)
    return book_info


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
    all_chapters = await _Chapters.collect(client, book_id)

    # Reorder: cover chapters first, then the rest.
    cover_chapters = [chapter for chapter in all_chapters if _Metadata.is_cover(chapter)]
    other_chapters = [chapter for chapter in all_chapters if chapter not in cover_chapters]
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
    content_url = raw_chapter.get("content_url", raw_chapter.get("content", ""))
    return Chapter(
        filename=_Chapters.resolve_filename(raw_chapter),
        title=raw_chapter.get("title", ""),
        content_url=content_url,
        asset_base_url=FILES_API_TEMPLATE.format(book_id),
        images=_Chapters.extract_images(raw_chapter),
        stylesheets=_Chapters.extract_stylesheets(raw_chapter),
        site_styles=_Chapters.extract_site_styles(raw_chapter),
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

    response = await _Metadata.download_cover(client, cover_url)
    if response is None or response.status_code != _HTTP_OK:
        logger.error("Error trying to retrieve the cover: %s", cover_url)
        return None

    content_type = response.headers.get("Content-Type", "image/jpeg")
    file_ext = content_type.split(_PATH_SEP)[-1]
    filename = f"default_cover.{file_ext}"
    (images_path / filename).write_bytes(response.content)
    return filename


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


class _Metadata:
    """Helpers for assembling and enriching :class:`BookInfo` payloads."""

    @classmethod
    async def build_updates(
        cls,
        client: ApiClient,
        book_id: str,
        base_info: BookInfo,
    ) -> dict[str, object]:
        """Build the field-update mapping for :func:`enrich_book_metadata`."""
        search_url = SEARCH_API_TEMPLATE.format(book_id)
        payload = await client.get_json(search_url)

        search_results = payload.get(_KEY_RESULTS, [])
        if not search_results:
            return {}

        top_result = search_results[0]
        if not cls.result_matches(top_result, book_id):
            return {}

        updates = cls.collect_updates(top_result)
        if not base_info.cover and _KEY_COVER_URL in top_result:
            updates[_KEY_COVER] = top_result[_KEY_COVER_URL]
        if not base_info.web_url and _KEY_WEB_URL in top_result:
            updates[_KEY_WEB_URL] = top_result[_KEY_WEB_URL]
        return updates

    @classmethod
    def result_matches(cls, entry: dict[str, Any], book_id: str) -> bool:
        """Return whether a search *entry* refers to *book_id*."""
        result_id = str(entry.get("isbn", entry.get("identifier", "")))
        return book_id in result_id or entry.get("archive_id", "") == book_id

    @classmethod
    def collect_updates(cls, entry: dict[str, Any]) -> dict[str, object]:
        """Translate a matched search result into model-ready updates."""
        updates: dict[str, object] = {}

        if entry.get("authors"):
            updates["authors"] = [Author(name=author) for author in entry["authors"]]

        publishers = cls.parse_publishers(entry.get(_KEY_PUBLISHERS))
        if publishers is not None:
            updates[_KEY_PUBLISHERS] = publishers

        issued = entry.get(_KEY_ISSUED) or entry.get("date_added", _MISSING)
        if issued is not _MISSING:
            updates[_KEY_ISSUED] = issued

        if entry.get("subjects"):
            updates["subjects"] = [Subject(name=subject) for subject in entry["subjects"]]

        return updates

    @classmethod
    def parse_publishers(cls, raw_publishers: Any) -> list[Publisher] | None:
        """Normalize the ``publishers`` field into :class:`Publisher` models."""
        if isinstance(raw_publishers, str):
            return [Publisher(name=raw_publishers)]
        if isinstance(raw_publishers, list):
            return [cls.to_publisher(entry) for entry in raw_publishers]
        return None

    @classmethod
    def to_publisher(cls, entry: Any) -> Publisher:
        """Wrap a single publisher entry (string or mapping) into a model."""
        if isinstance(entry, str):
            return Publisher(name=entry)
        return Publisher(**entry)

    @classmethod
    def is_cover(cls, chapter: Chapter) -> bool:
        """Return whether a chapter looks like cover front-matter."""
        return _KEY_COVER in chapter.filename.lower() or _KEY_COVER in chapter.title.lower()

    @classmethod
    async def download_cover(cls, client: ApiClient, cover_url: str) -> Any:
        """Try cover URL variants in order, returning the first 200 response."""
        attempts = [
            cover_url.replace("/thumb/", "/orig/"),
            cover_url.replace("/thumb/", _PATH_SEP),
            cover_url.replace("thumbnail", _KEY_COVER),
            cover_url,
        ]
        # A ``while`` loop (rather than ``for``) keeps the single ``await``
        # out of a ``for`` body while preserving sequential variant order.
        while attempts:
            url = attempts.pop(0)
            try:
                response = await client.get(url)
            except ApiError:
                continue
            if response.status_code == _HTTP_OK:
                logger.info("Retrieved HD cover from: %s", url)
                return response
        return None


class _Chapters:
    """Helpers for fetching, ordering, and normalizing chapters."""

    @classmethod
    async def collect(cls, client: ApiClient, book_id: str) -> list[Chapter]:
        """Page through the chapters API, normalizing every result."""
        chapters_url: str | None = CHAPTERS_API_TEMPLATE.format(book_id)
        all_chapters: list[Chapter] = []

        while chapters_url:
            payload = await client.get_json(chapters_url)
            if not isinstance(payload, dict):
                msg = f"API returned unexpected data for chapters of book {book_id}"  # type: ignore[unreachable]
                raise ApiError(msg)

            page = payload.get(_KEY_RESULTS, [])
            if not page:
                break

            all_chapters.extend(normalize_chapter(raw, book_id) for raw in page)
            chapters_url = payload.get("next")

        if not all_chapters:
            msg = f"API returned no chapters for book {book_id}"
            raise ApiError(msg)

        return all_chapters

    @classmethod
    def resolve_filename(cls, raw_chapter: dict[str, Any]) -> str:
        """Derive a usable filename from a raw v2 API chapter dict."""
        filename = unquote(raw_chapter.get("filename", ""))

        if not filename:
            ourn = raw_chapter.get("ourn", "")
            filename = (
                unquote(ourn.split(":")[-1])
                if ":" in ourn
                else raw_chapter.get("reference_id", "").split(_PATH_SEP)[-1]
            )

        if not filename:
            hash_source = raw_chapter.get("content_url", raw_chapter.get("ourn", ""))
            filename = f"chapter_{abs(hash(hash_source))}.html"

        return filename

    @classmethod
    def extract_images(cls, raw_chapter: dict[str, Any]) -> list[str]:
        """Extract image URLs, stripping full URLs to relative paths."""
        images = raw_chapter.get("images", [])
        if not images and _KEY_RELATED_ASSETS in raw_chapter:
            images = raw_chapter[_KEY_RELATED_ASSETS].get("images", [])

        return [cls.relative_image(url) for url in images]

    @classmethod
    def relative_image(cls, url: str) -> str:
        """Strip a full asset URL down to its path relative to ``/files/``."""
        if "/files/" in url:
            return url.split("/files/")[-1]
        return url

    @classmethod
    def extract_stylesheets(cls, raw_chapter: dict[str, Any]) -> list[Stylesheet]:
        """Extract stylesheet references, wrapping bare URL strings."""
        stylesheets_raw = raw_chapter.get("stylesheets", [])
        if not stylesheets_raw and _KEY_RELATED_ASSETS in raw_chapter:
            stylesheets_raw = raw_chapter[_KEY_RELATED_ASSETS].get("stylesheets", [])

        return [cls.to_stylesheet(entry) for entry in stylesheets_raw]

    @classmethod
    def to_stylesheet(cls, entry: Any) -> Stylesheet:
        """Wrap a single stylesheet entry (string or mapping) into a model."""
        if isinstance(entry, str):
            return Stylesheet(url=entry)
        return Stylesheet(**entry)

    @classmethod
    def extract_site_styles(cls, raw_chapter: dict[str, Any]) -> list[str]:
        """Extract site-level style URLs."""
        site_styles = raw_chapter.get("site_styles", [])
        if not site_styles and _KEY_RELATED_ASSETS in raw_chapter:
            site_styles = raw_chapter[_KEY_RELATED_ASSETS].get("site_styles", [])
        return list(site_styles) if site_styles else []
