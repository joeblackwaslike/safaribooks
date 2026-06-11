"""Core download orchestrator — replaces the legacy SafariBooks.__init__() pipeline."""


import logging
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from safaribooks.core.api import ApiClient
from safaribooks.core.assets import download_css, download_fonts, download_images, download_videos
from safaribooks.core.book import (
    enrich_book_metadata,
    fetch_book_info,
    fetch_chapters,
    fetch_default_cover,
)
from safaribooks.core.chapters import fetch_chapter_html, is_absolute_url, parse_chapter_html
from safaribooks.core.config import AppConfig
from safaribooks.core.constants import SAFARI_BASE_URL
from safaribooks.core.epub import (
    BookPaths,
    build_epub,
    ensure_book_dirs,
    render_content_opf,
    render_toc_ncx,
    sanitize_dirname,
    write_chapter_html,
)
from safaribooks.core.exceptions import ApiError
from safaribooks.core.models import Chapter

logger = logging.getLogger(__name__)


class BookDownloader:
    """Orchestrates the full book download pipeline.

    Replaces the legacy ``SafariBooks.__init__()`` method which ran the
    entire download-to-EPUB pipeline as a constructor side effect.

    Usage::

        downloader = BookDownloader(config, book_id)
        epub_path = await downloader.run()
    """

    def __init__(
        self,
        config: AppConfig,
        book_id: str,
        *,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> None:
        """Initialise the downloader with configuration and book identifier.

        Parameters
        ----------
        config:
            Application configuration.
        book_id:
            O'Reilly book identifier (ISBN or archive ID).
        progress_callback:
            Optional callback invoked as ``(stage, current, total)``
            where *stage* is one of ``"chapters"``, ``"css"``,
            ``"images"``, ``"fonts"``, ``"videos"``, ``"epub"``.

        """
        self.config = config
        self.book_id = book_id
        self.progress_callback = progress_callback

    async def run(self) -> Path:
        """Download a book and return the path to the EPUB file.

        Pipeline steps:

        1. Authenticate (check_login)
        2. Fetch book info
        3. Enrich metadata
        4. Create output directories
        5. Fetch chapters
        6. Download chapter HTML and parse
        7. Download CSS, images, fonts, videos
        8. Generate content.opf and toc.ncx
        9. Build EPUB

        Returns:
        -------
        Path
            Path to the generated ``.epub`` file.

        """
        async with ApiClient(self.config) as client:
            # 1. Authenticate
            logger.info("Checking authentication...")
            await client.check_login()

            # 2. Fetch book info
            logger.info("Retrieving book info for %s...", self.book_id)
            book_info = await fetch_book_info(client, self.book_id)
            logger.info("Book: %s", book_info.title)

            # 3. Enrich metadata from search API
            logger.info("Enriching book metadata...")
            book_info = await enrich_book_metadata(client, self.book_id, book_info)

            # 4. Create output directories
            dirname = sanitize_dirname(f"{book_info.title} ({self.book_id})")
            book_paths = ensure_book_dirs(self.config.output_dir, dirname)
            logger.info("Output directory: %s", book_paths.book_dir)

            # 5. Fetch chapter list
            logger.info("Retrieving book chapters...")
            chapters = await fetch_chapters(client, self.book_id)
            logger.info("Found %d chapters.", len(chapters))

            # 6. Process each chapter: fetch HTML, parse, collect assets, write XHTML
            all_css, all_images, all_videos, cover_src = await self._process_chapters(
                client, chapters, book_paths
            )

            # 7a. Default cover if none was found during chapter parsing
            if not cover_src:
                has_cover_chapter = any(
                    "cover" in ch.filename.lower() or "cover" in ch.title.lower() for ch in chapters
                )
                if not has_cover_chapter and book_info.cover:
                    cover_filename = await fetch_default_cover(client, book_info, book_paths.images)
                    if cover_filename:
                        cover_src = f"Images/{cover_filename}"
                        logger.info("Downloaded default cover: %s", cover_filename)

            # 7b. Download CSS
            logger.info("Downloading CSS... (%d files)", len(all_css))
            await download_css(
                client,
                all_css,
                book_paths.styles,
                self.book_id,
                progress_callback=self._make_asset_callback("css"),
            )

            # 7c. Download fonts (scans downloaded CSS for @font-face references)
            logger.info("Downloading fonts...")
            font_files = await download_fonts(
                client,
                book_paths.styles,
                self.book_id,
                progress_callback=self._make_asset_callback("fonts"),
            )

            # 7d. Download images
            logger.info("Downloading images... (%d files)", len(all_images))
            await download_images(
                client,
                all_images,
                book_paths.images,
                self.book_id,
                max_size=self.config.image_max_size,
                quality=self.config.image_quality,
                progress_callback=self._make_asset_callback("images"),
            )

            # 7e. Download videos
            if all_videos:
                logger.info("Downloading videos... (%d files)", len(all_videos))
                await download_videos(
                    client,
                    all_videos,
                    book_paths.videos,
                    progress_callback=self._make_asset_callback("videos"),
                )

            # 8. Generate content.opf and toc.ncx
            logger.info("Generating EPUB metadata...")
            content_opf = render_content_opf(
                book_info,
                chapters,
                book_paths.styles,
                book_paths.images,
                book_paths.videos,
                font_files,
                cover_src=cover_src,
            )
            (book_paths.oebps / "content.opf").write_bytes(
                content_opf.encode("utf-8", "xmlcharrefreplace")
            )

            toc_url = (
                f"{SAFARI_BASE_URL}/api/v2/epubs/urn:orm:book:{self.book_id}/table-of-contents/"
            )
            toc_ncx = await render_toc_ncx(client, toc_url, book_info)
            (book_paths.oebps / "toc.ncx").write_bytes(toc_ncx.encode("utf-8", "xmlcharrefreplace"))

            # 9. Build EPUB
            logger.info("Creating EPUB file...")
            self._notify_progress("epub", 0, 1)
            epub_path = build_epub(book_paths, book_info.title)
            self._notify_progress("epub", 1, 1)

            # 10. Copy EPUB to central library
            epubs_dir = self.config.library_dir / "epubs"
            epubs_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(epub_path, epubs_dir / epub_path.name)
            logger.info("Copied EPUB to library: %s", epubs_dir / epub_path.name)

            # Save cookies to persist any refreshed tokens
            client.save_cookies()

            logger.info("Done! EPUB saved to: %s", epub_path)
            return epub_path

    # ------------------------------------------------------------------
    # Chapter processing loop
    # ------------------------------------------------------------------

    async def _process_chapters(
        self,
        client: ApiClient,
        chapters: list[Chapter],
        book_paths: BookPaths,
    ) -> tuple[list[str], list[str], list[str], str | None]:
        """Process all chapters: fetch, parse, write XHTML, and collect assets.

        Returns:
        -------
        tuple[list[str], list[str], list[str], str | None]
            ``(all_css, all_images, all_videos, cover_src)``

        """
        all_css: list[str] = []
        known_css: set[str] = set()
        all_images: list[str] = []
        all_videos: list[str] = []
        cover_src: str | None = None

        total = len(chapters)

        for idx, chapter in enumerate(chapters):
            first_page = idx == 0

            # Collect image URLs from chapter metadata
            for img_url in chapter.images:
                if is_absolute_url(img_url):
                    all_images.append(img_url)
                else:
                    all_images.append(f"{chapter.asset_base_url}/{img_url}")

            # Build the list of stylesheet URLs for this chapter
            chapter_stylesheet_urls: list[str] = [s.url for s in chapter.stylesheets]
            chapter_stylesheet_urls.extend(chapter.site_styles)

            # Check if chapter XHTML already exists (resume support)
            xhtml_filename = chapter.filename.replace(".html", ".xhtml")
            dest_path = book_paths.oebps / xhtml_filename
            if dest_path.is_file():
                logger.debug("Chapter already exists, skipping: %s", xhtml_filename)
                self._notify_progress("chapters", idx + 1, total)
                continue

            # Fetch and parse chapter HTML
            root = await fetch_chapter_html(client, chapter.content_url)
            result = parse_chapter_html(
                root,
                chapter_stylesheet_urls,
                known_css,
                self.book_id,
                chapter.asset_base_url,
                first_page=first_page,
            )

            # Accumulate discovered assets
            for css_url in result.discovered_css:
                if css_url not in known_css:
                    all_css.append(css_url)
                    known_css.add(css_url)

            all_videos.extend(v for v in result.discovered_videos if v not in all_videos)

            if result.cover_src and cover_src is None:
                cover_src = result.cover_src

            # Write chapter XHTML
            write_chapter_html(
                dest_path,
                result.page_css,
                result.body_xhtml,
                kindle=self.config.kindle,
            )

            self._notify_progress("chapters", idx + 1, total)

        return all_css, all_images, all_videos, cover_src

    # ------------------------------------------------------------------
    # Progress helpers
    # ------------------------------------------------------------------

    def _notify_progress(self, stage: str, current: int, total: int) -> None:
        """Invoke the progress callback if one is registered."""
        if self.progress_callback is not None:
            self.progress_callback(stage, current, total)

    def _make_asset_callback(self, stage: str) -> Callable[[int, int], None] | None:
        """Create a ``(total, completed)`` callback that adapts to our 3-arg progress API.

        The asset download functions use ``(total, completed)`` callbacks,
        while our public progress API uses ``(stage, current, total)``.
        This bridges the two.

        Returns ``None`` if no progress callback is registered.
        """
        if self.progress_callback is None:
            return None

        def _cb(total: int, completed: int) -> None:
            self._notify_progress(stage, completed, total)

        return _cb


# ---------------------------------------------------------------------------
# Standalone helper functions
# ---------------------------------------------------------------------------

# Regex patterns for extract_book_id
_URL_BOOK_ID_RE = re.compile(r"https?://.*?/(\d{10,15})/?")
_BARE_BOOK_ID_RE = re.compile(r"(\d{10,15})$")
_URN_BOOK_ID_RE = re.compile(r"^urn:orm:book:(\d+)")


def extract_book_id(input_str: str) -> str | None:
    """Extract a book ID from a URL, URN, or bare identifier.

    Handles the following input formats:

    - Full O'Reilly URL: ``https://learning.oreilly.com/.../9781234567890/``
    - URN: ``urn:orm:book:9781234567890``
    - Bare decimal ID: ``9781234567890``

    Parameters
    ----------
    input_str:
        The raw input string to extract a book ID from.

    Returns:
    -------
    str | None
        The extracted book ID, or ``None`` if the input cannot be parsed.

    """
    # Full URL
    url_match = _URL_BOOK_ID_RE.match(input_str)
    if url_match:
        return url_match.group(1)

    # URN prefix
    urn_match = _URN_BOOK_ID_RE.match(input_str)
    if urn_match:
        return urn_match.group(1)

    # Bare decimal ID
    if input_str.isdecimal():
        return input_str

    # Decimal ID at end of string
    id_match = _BARE_BOOK_ID_RE.match(input_str)
    if id_match:
        return id_match.group(1)

    return None


async def fetch_playlist_book_ids(client: ApiClient, playlist_id: str) -> list[str]:
    """Fetch book IDs from an O'Reilly playlist/collection.

    Queries the collections API, finds the playlist matching
    *playlist_id* (by UUID or slug), and extracts book IDs from the
    ``content`` entries.

    Parameters
    ----------
    client:
        Authenticated API client.
    playlist_id:
        The playlist UUID or slug.

    Returns:
    -------
    list[str]
        List of book IDs found in the playlist.

    Raises:
    ------
    ApiError
        When the playlist cannot be found or the API is unreachable.

    """
    collections_url = f"{SAFARI_BASE_URL}/api/v2/collections/"

    try:
        data = await client.get_json(collections_url)
    except ApiError:
        logger.exception("Unable to retrieve playlists from the API")
        raise

    playlists = data if isinstance(data, list) else data.get("results", [])  # type: ignore[unreachable]

    target = None
    for pl in playlists:
        if pl.get("uuid") == playlist_id or pl.get("slug") == playlist_id:
            target = pl
            break

    if target is None:
        msg = f"Playlist '{playlist_id}' not found."
        raise ApiError(msg)

    book_ids: list[str] = []
    for item in target.get("content", []):
        ourn = item.get("ourn", item.get("identifier", ""))
        match = _URN_BOOK_ID_RE.match(ourn)
        if match:
            book_ids.append(match.group(1))

    logger.info("Found %d books in playlist '%s'.", len(book_ids), playlist_id)
    return book_ids
