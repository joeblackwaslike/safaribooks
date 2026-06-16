"""Core download orchestrator — replaces the legacy SafariBooks.__init__() pipeline."""

import logging
import re
import shutil
import tempfile
from collections.abc import Awaitable, Callable
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
from safaribooks.core.models import BookInfo, Chapter, ParseResult

logger = logging.getLogger(__name__)

_EPUB_SUFFIX = ".epub"
_IMAGES_PREFIX = "Images"
_TOC_URL_TEMPLATE = f"{SAFARI_BASE_URL}/api/v2/epubs/urn:orm:book:{{0}}/table-of-contents/"
_XML_ENCODING = "utf-8"
_XML_ERRORS = "xmlcharrefreplace"
_COVER_KEYWORD = "cover"

_UrlList = list[str]
_ChapterAssetsTuple = tuple[_UrlList, _UrlList, _UrlList, str | None]
_NotifyCallback = Callable[[str, int, int], None]
_AssetCallback = Callable[[int, int], None]
_MakeAssetCallback = Callable[[str], _AssetCallback | None]
_ProcessChapters = Callable[
    [ApiClient, list[Chapter], BookPaths],
    Awaitable[_ChapterAssetsTuple],
]


class _ChapterAssets:
    """Mutable accumulator for assets discovered while processing chapters."""

    def __init__(self) -> None:
        self.all_css: list[str] = []
        self.all_images: list[str] = []
        self.all_videos: list[str] = []
        self.cover_src: str | None = None
        self._known_css: set[str] = set()

    @classmethod
    def has_cover_chapter(cls, chapters: list[Chapter]) -> bool:
        """Return ``True`` when any chapter looks like a cover page."""
        return any(
            _COVER_KEYWORD in chapter.filename.lower() or _COVER_KEYWORD in chapter.title.lower()
            for chapter in chapters
        )

    @classmethod
    def stylesheet_urls(cls, chapter: Chapter) -> list[str]:
        """Build the ordered list of stylesheet URLs for a chapter."""
        urls: list[str] = [sheet.url for sheet in chapter.stylesheets]
        urls.extend(chapter.site_styles)
        return urls

    def add_images(self, chapter: Chapter) -> None:
        """Collect (and absolutise) image URLs from chapter metadata."""
        for img_url in chapter.images:
            if is_absolute_url(img_url):
                self.all_images.append(img_url)
            else:
                self.all_images.append(f"{chapter.asset_base_url}/{img_url}")

    def add_parsed(self, parsed: ParseResult) -> None:
        """Accumulate CSS, videos, and cover discovered in a parsed chapter."""
        for css_url in parsed.discovered_css:
            if css_url not in self._known_css:
                self.all_css.append(css_url)
                self._known_css.add(css_url)

        self.all_videos.extend(
            video for video in parsed.discovered_videos if video not in self.all_videos
        )

        if parsed.cover_src and self.cover_src is None:
            self.cover_src = parsed.cover_src

    def as_tuple(self) -> _ChapterAssetsTuple:
        """Return the accumulated assets as a 4-tuple."""
        return self.all_css, self.all_images, self.all_videos, self.cover_src


class _AssetProgressBridge:
    """Adapt a ``(total, completed)`` asset callback to the 3-arg progress API."""

    def __init__(self, notify: Callable[[str, int, int], None], stage: str) -> None:
        self._notify = notify
        self._stage = stage

    def __call__(self, total: int, completed: int) -> None:
        self._notify(self._stage, completed, total)


class _BookBuilder:
    """Runs the authenticated download-to-EPUB pipeline for one book."""

    def __init__(
        self,
        config: AppConfig,
        book_id: str,
        *,
        notify: _NotifyCallback,
        make_callback: _MakeAssetCallback,
        process_chapters: _ProcessChapters,
    ) -> None:
        self.config = config
        self.book_id = book_id
        self._notify = notify
        self._make_callback = make_callback
        self._process_chapters = process_chapters
        self.client: ApiClient
        self.book_info: BookInfo
        self.book_paths: BookPaths
        self._epub_output_path: Path

    async def run(self, client: ApiClient) -> Path:
        """Execute the full pipeline against *client* and return the EPUB path."""
        self.client = client
        await self._prepare()
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        epub_filename = sanitize_dirname(self.book_info.title) + _EPUB_SUFFIX
        self._epub_output_path = self.config.output_dir / epub_filename

        with tempfile.TemporaryDirectory(prefix="safaribooks_") as tmp_dir:
            self.book_paths = ensure_book_dirs(Path(tmp_dir))
            logger.info("Build directory: %s", self.book_paths.book_dir)
            epub_path = await self._build()

        _copy_to_library(self.config.library_dir, epub_path)
        await client.stop_keepalive()
        client.save_cookies()
        return epub_path

    async def _prepare(self) -> None:
        """Authenticate, start keepalive, and fetch enriched book metadata."""
        client = self.client
        logger.info("Checking authentication...")
        await client.check_login()
        await client.start_keepalive()

        logger.info("Retrieving book info for %s...", self.book_id)
        book_info = await fetch_book_info(client, self.book_id)
        logger.info("Book: %s", book_info.title)

        logger.info("Enriching book metadata...")
        self.book_info = await enrich_book_metadata(client, self.book_id, book_info)

    async def _build(self) -> Path:
        """Fetch chapters and assets, write metadata, and build the EPUB."""
        logger.info("Retrieving book chapters...")
        chapters = await fetch_chapters(self.client, self.book_id)
        logger.info("Found %d chapters.", len(chapters))

        collected = await self._process_chapters(self.client, chapters, self.book_paths)
        cover_src = await self._ensure_cover(chapters, collected[3])
        font_files = await self._download_assets(collected[:3])
        await self._write_epub_files(chapters, font_files, cover_src=cover_src)

        logger.info("Creating EPUB file...")
        self._notify("epub", 0, 1)
        epub_path = build_epub(self.book_paths, self._epub_output_path)
        self._notify("epub", 1, 1)
        return epub_path

    async def _ensure_cover(self, chapters: list[Chapter], cover_src: str | None) -> str | None:
        """Download a default cover when chapter parsing found none."""
        book_info = self.book_info
        if cover_src or not book_info.cover or _ChapterAssets.has_cover_chapter(chapters):
            return cover_src
        cover_filename = await fetch_default_cover(self.client, book_info, self.book_paths.images)
        if not cover_filename:
            return cover_src
        logger.info("Downloaded default cover: %s", cover_filename)
        return f"{_IMAGES_PREFIX}/{cover_filename}"

    async def _download_assets(self, urls: tuple[list[str], list[str], list[str]]) -> list[str]:
        """Download CSS, fonts, images, and videos. Returns discovered font files."""
        all_css, all_images, all_videos = urls

        logger.info("Downloading CSS... (%d files)", len(all_css))
        await download_css(
            self.client,
            all_css,
            self.book_paths.styles,
            self.book_id,
            progress_callback=self._make_callback("css"),
        )

        logger.info("Downloading fonts...")
        font_files = await download_fonts(
            self.client,
            self.book_paths.styles,
            self.book_id,
            progress_callback=self._make_callback("fonts"),
        )

        logger.info("Downloading images... (%d files)", len(all_images))
        await download_images(
            self.client,
            all_images,
            self.book_paths.images,
            self.book_id,
            max_size=self.config.image_max_size,
            quality=self.config.image_quality,
            progress_callback=self._make_callback("images"),
        )

        if all_videos:
            logger.info("Downloading videos... (%d files)", len(all_videos))
            await download_videos(
                self.client,
                all_videos,
                self.book_paths.videos,
                progress_callback=self._make_callback("videos"),
            )

        return font_files

    async def _write_epub_files(
        self,
        chapters: list[Chapter],
        font_files: list[str],
        *,
        cover_src: str | None,
    ) -> None:
        """Render and write content.opf and toc.ncx into the build directory."""
        book_paths = self.book_paths
        book_info = self.book_info

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
            content_opf.encode(_XML_ENCODING, _XML_ERRORS)
        )

        toc_url = _TOC_URL_TEMPLATE.format(self.book_id)
        toc_ncx = await render_toc_ncx(self.client, toc_url, book_info)
        (book_paths.oebps / "toc.ncx").write_bytes(toc_ncx.encode(_XML_ENCODING, _XML_ERRORS))


def _copy_to_library(library_dir: Path, epub_path: Path) -> None:
    """Copy the finished EPUB into the central library directory."""
    epubs_dir = library_dir / "epubs"
    epubs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(epub_path, epubs_dir / epub_path.name)
    logger.info("Copied EPUB to library: %s", epubs_dir / epub_path.name)


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
        builder = _BookBuilder(
            self.config,
            self.book_id,
            notify=self._notify_progress,
            make_callback=self._make_asset_callback,
            process_chapters=self._process_chapters,
        )
        async with ApiClient(self.config) as client:
            epub_path = await builder.run(client)
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
    ) -> _ChapterAssetsTuple:
        """Process all chapters: fetch, parse, write XHTML, and collect assets.

        Returns:
        -------
        tuple[list[str], list[str], list[str], str | None]
            ``(all_css, all_images, all_videos, cover_src)``

        """
        assets = _ChapterAssets()
        await self._process_from(client, chapters, book_paths, assets, index=0)
        return assets.as_tuple()

    async def _process_from(
        self,
        client: ApiClient,
        chapters: list[Chapter],
        book_paths: BookPaths,
        assets: "_ChapterAssets",
        *,
        index: int,
    ) -> None:
        """Recursively process chapters from *index* to the end, in order."""
        if index >= len(chapters):
            return
        await self._process_one_chapter(
            client, chapters[index], book_paths, assets, first_page=index == 0
        )
        self._notify_progress("chapters", index + 1, len(chapters))
        await self._process_from(client, chapters, book_paths, assets, index=index + 1)

    async def _process_one_chapter(
        self,
        client: ApiClient,
        chapter: Chapter,
        book_paths: BookPaths,
        assets: "_ChapterAssets",
        *,
        first_page: bool,
    ) -> None:
        """Fetch, parse, and write a single chapter, accumulating its assets."""
        assets.add_images(chapter)

        xhtml_filename = chapter.filename.replace(".html", ".xhtml")
        dest_path = book_paths.oebps / xhtml_filename
        if dest_path.is_file():
            logger.debug("Chapter already exists, skipping: %s", xhtml_filename)
            return

        root = await fetch_chapter_html(client, chapter.content_url)
        parsed = parse_chapter_html(
            root,
            _ChapterAssets.stylesheet_urls(chapter),
            assets.all_css,
            self.book_id,
            chapter.asset_base_url,
            first_page=first_page,
        )

        assets.add_parsed(parsed)
        write_chapter_html(
            dest_path,
            parsed.page_css,
            parsed.body_xhtml,
        )

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
        return _AssetProgressBridge(self._notify_progress, stage)


# ---------------------------------------------------------------------------
# Standalone helper functions
# ---------------------------------------------------------------------------

# Regex patterns for extract_book_id
_URL_BOOK_ID_RE = re.compile(r"https?://.*?/(\d{10,15})/?")
_BARE_BOOK_ID_RE = re.compile(r"(\d{10,15})$")
_URN_BOOK_ID_RE = re.compile(r"^urn:orm:book:(\d+)")
# Multiline variant: matches one URN per line in a newline-joined block, so a
# whole playlist's ``content`` ourns can be scanned with a single ``findall``.
_URN_BOOK_ID_LINE_RE = re.compile(r"^urn:orm:book:(\d+)", re.MULTILINE)


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

    # Decimal ID at end of string (search, not match: the pattern is $-anchored
    # so .match() would only ever fire on an all-digit string already handled above)
    id_match = _BARE_BOOK_ID_RE.search(input_str)
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
    try:
        payload = await client.get_json(f"{SAFARI_BASE_URL}/api/v2/collections/")
    except ApiError:
        logger.exception("Unable to retrieve playlists from the API")
        raise

    playlists = payload if isinstance(payload, list) else payload.get("results", [])  # type: ignore[unreachable]

    target = next(
        (pl for pl in playlists if playlist_id in {pl.get("uuid"), pl.get("slug")}),
        None,
    )
    if target is None:
        raise ApiError(f"Playlist '{playlist_id}' not found.")

    content_ourns = "\n".join(
        entry.get("ourn", entry.get("identifier", "")) for entry in target.get("content", [])
    )
    book_ids = _URN_BOOK_ID_LINE_RE.findall(content_ourns)
    logger.info("Found %d books in playlist '%s'.", len(book_ids), playlist_id)
    return book_ids
