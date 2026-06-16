"""Asset downloading: CSS, images, fonts, and videos with async concurrency."""

import asyncio
import logging
import re
from collections.abc import Callable, Coroutine
from pathlib import Path
from urllib.parse import urljoin

from safaribooks.core.api import ApiClient
from safaribooks.core.constants import SAFARI_BASE_URL

logger = logging.getLogger(__name__)

_HAS_PILLOW = True
try:
    from PIL import Image
except ImportError:  # pragma: no cover
    _HAS_PILLOW = False

# Default number of concurrent download workers.
_DEFAULT_WORKERS = 4

# HTTP status code indicating a successful response.
_HTTP_OK = 200

# Regex to find font URLs inside CSS files.
_FONT_URL_RE = re.compile(r"url\(['\"]?([^)]*\.(?:otf|ttf|woff|woff2))['\"]?\)")

# Font URL prefixes that point at remote/inline data rather than packaged files.
_REMOTE_FONT_PREFIXES = ("data:", "http://", "https://")

# Files-API URL template for fetching a packaged font by name.
_FONT_FILES_URL_TEMPLATE = "{base}/api/v2/epubs/urn:orm:book:{book_id}/files/{font}"


# ---------------------------------------------------------------------------
# Image resizing
# ---------------------------------------------------------------------------


def resize_image(path: Path, max_size: int, quality: int) -> None:
    """Resize an image if it exceeds *max_size* and/or re-encode at *quality*.

    Requires Pillow. If Pillow is not installed this function is a no-op.

    Parameters
    ----------
    path:
        Path to the image file.
    max_size:
        Maximum width/height in pixels. ``0`` means no resize.
    quality:
        JPEG quality (1-95). ``0`` means keep original encoding.

    """
    if not _HAS_PILLOW:
        return
    if max_size == 0 and quality == 0:
        return

    try:
        with Image.open(path) as image:
            if max_size > 0:
                image.thumbnail((max_size, max_size))
            if quality > 0:
                image.save(path, quality=quality)
            else:
                image.save(path)
    except (OSError, ValueError):
        logger.warning("Could not resize image %s", path, exc_info=True)


# ---------------------------------------------------------------------------
# Individual async download workers
# ---------------------------------------------------------------------------


async def _download_single_css(
    client: ApiClient,
    url: str,
    css_dir: Path,
    index: int,
) -> str | None:
    """Download a single CSS file. Returns the saved filename or ``None``."""
    css_name = f"Style{index:0>2}.css"
    css_path = css_dir / css_name

    if css_path.is_file():
        logger.debug("CSS already exists, skipping: %s", css_name)
        return css_name

    try:
        response = await client.get(url)
    except Exception:
        logger.exception("Error downloading CSS from %s", url)
        return None

    if response.status_code != _HTTP_OK:
        logger.error("HTTP %d downloading CSS: %s", response.status_code, url)
        return None

    css_path.write_bytes(response.content)
    return css_name


async def _download_single_image(
    client: ApiClient,
    url: str,
    images_dir: Path,
    *,
    max_size: int = 0,
    quality: int = 0,
) -> str | None:
    """Download a single image file. Returns the saved filename or ``None``."""
    image_name = url.split("/")[-1]
    image_path = images_dir / image_name

    if image_path.is_file():
        logger.debug("Image already exists, skipping: %s", image_name)
        return image_name

    try:
        response = await client.get(urljoin(SAFARI_BASE_URL, url))
    except Exception:
        logger.exception("Error downloading image from %s", url)
        return None

    if response.status_code != _HTTP_OK:
        logger.error("HTTP %d downloading image: %s", response.status_code, image_name)
        return None

    image_path.write_bytes(response.content)

    resize_image(image_path, max_size, quality)
    return image_name


async def _download_single_video(
    client: ApiClient,
    url: str,
    videos_dir: Path,
) -> str | None:
    """Download a single video file. Returns the saved filename or ``None``."""
    video_name = url.split("/")[-1]
    video_path = videos_dir / video_name

    if video_path.is_file():
        logger.debug("Video already exists, skipping: %s", video_name)
        return video_name

    try:
        response = await client.get(urljoin(SAFARI_BASE_URL, url))
    except Exception:
        logger.exception("Error downloading video from %s", url)
        return None

    if response.status_code != _HTTP_OK:
        logger.error("HTTP %d downloading video: %s", response.status_code, video_name)
        return None

    video_path.write_bytes(response.content)

    return video_name


# ---------------------------------------------------------------------------
# Async parallel download orchestrator
# ---------------------------------------------------------------------------


class _LimitedRunner:
    """Run download coroutines under a shared semaphore with progress reporting."""

    def __init__(
        self,
        *,
        semaphore: asyncio.Semaphore,
        total: int,
        progress_callback: Callable[[int, int], None] | None,
    ) -> None:
        self._semaphore = semaphore
        self._total = total
        self._progress_callback = progress_callback
        self._completed = 0

    async def run(
        self,
        coro: Coroutine[object, object, str | None],
    ) -> str | None:
        """Await *coro* under the semaphore, then report progress."""
        async with self._semaphore:
            outcome = await coro
        self._completed += 1
        if self._progress_callback is not None:
            self._progress_callback(self._total, self._completed)
        return outcome

    def collect_successful(self, gathered: list[str | None | BaseException]) -> list[str]:
        """Filter gathered outcomes into successful filenames, logging exceptions."""
        collected: list[str] = []
        for outcome in gathered:
            if isinstance(outcome, BaseException):
                logger.exception("Download worker raised an exception", exc_info=outcome)
            elif outcome is not None:
                collected.append(outcome)
        return collected


async def _parallel_download(
    coros: list[Coroutine[object, object, str | None]],
    *,
    max_concurrent: int = _DEFAULT_WORKERS,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[str]:
    """Run coroutines concurrently with a semaphore limit.

    Parameters
    ----------
    coros:
        A list of coroutines that each return a filename or ``None``.
    max_concurrent:
        Maximum number of concurrent downloads.
    progress_callback:
        Optional ``(total, completed)`` callback invoked after each item.

    Returns:
    -------
    list[str]
        Filenames of successfully downloaded assets.

    """
    if not coros:
        return []

    runner = _LimitedRunner(
        semaphore=asyncio.Semaphore(max_concurrent),
        total=len(coros),
        progress_callback=progress_callback,
    )
    gathered = await asyncio.gather(
        *[runner.run(coro) for coro in coros],
        return_exceptions=True,
    )
    return runner.collect_successful(gathered)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def download_css(
    client: ApiClient,
    css_urls: list[str],
    css_dir: Path,
    book_id: str,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[str]:
    """Download all CSS stylesheets for a book.

    Parameters
    ----------
    client:
        Authenticated API client.
    css_urls:
        List of CSS URLs to download.
    css_dir:
        Destination ``Styles/`` directory.
    book_id:
        Book identifier (unused directly, reserved for future use).
    progress_callback:
        Optional ``(total, completed)`` progress callback.

    Returns:
    -------
    list[str]
        Filenames of successfully downloaded CSS files.

    """
    if not css_urls:
        return []

    coros = [_download_single_css(client, url, css_dir, idx) for idx, url in enumerate(css_urls)]
    return await _parallel_download(coros, progress_callback=progress_callback)


async def download_images(
    client: ApiClient,
    image_urls: list[str],
    images_dir: Path,
    book_id: str,
    *,
    max_size: int = 0,
    quality: int = 0,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[str]:
    """Download all images for a book.

    Parameters
    ----------
    client:
        Authenticated API client.
    image_urls:
        List of image URLs to download.
    images_dir:
        Destination ``Images/`` directory.
    book_id:
        Book identifier (unused directly, reserved for future use).
    max_size:
        Maximum image dimension in pixels (0 = no resize).
    quality:
        JPEG quality (0 = keep original).
    progress_callback:
        Optional ``(total, completed)`` progress callback.

    Returns:
    -------
    list[str]
        Filenames of successfully downloaded images.

    """
    if not image_urls:
        return []

    coros = [
        _download_single_image(client, url, images_dir, max_size=max_size, quality=quality)
        for url in image_urls
    ]
    return await _parallel_download(coros, progress_callback=progress_callback)


class _FontDownloader:
    """Scan CSS for font references and fetch them sequentially."""

    def __init__(
        self,
        client: ApiClient,
        css_dir: Path,
        book_id: str,
        *,
        progress_callback: Callable[[int, int], None] | None,
    ) -> None:
        self._client = client
        self._css_dir = css_dir
        self._book_id = book_id
        self._progress_callback = progress_callback
        self._total = 0
        self._completed = 0

    def scan(self) -> set[str]:
        """Scan every ``.css`` file in the directory for local font references."""
        font_urls: set[str] = set()
        for css_file in self._css_dir.iterdir():
            if css_file.suffix != ".css":
                continue
            css_text = self._read_css(css_file)
            if css_text is not None:
                font_urls.update(self._extract_local(css_text))
        return font_urls

    async def fetch_all(self, font_urls: set[str]) -> list[str]:
        """Download every font sequentially, reporting progress per font."""
        downloaded: list[str] = []
        self._total = len(font_urls)
        self._completed = 0
        pending = iter(sorted(font_urls))
        font_name = next(pending, None)
        while font_name is not None:
            basename = await self._step(font_name)
            if basename is not None:
                downloaded.append(basename)
            font_name = next(pending, None)
        return downloaded

    async def _step(self, font_name: str) -> str | None:
        """Fetch one font and report progress regardless of the outcome."""
        basename = await self._fetch_one(font_name)
        self._completed += 1
        if self._progress_callback is not None:
            self._progress_callback(self._total, self._completed)
        return basename

    def _read_css(self, css_file: Path) -> str | None:
        """Read a CSS file, returning ``None`` (with a warning) if unreadable."""
        try:
            return css_file.read_text(errors="ignore")
        except OSError:
            logger.warning(
                "Could not read CSS file for font scanning: %s",
                css_file,
                exc_info=True,
            )
            return None

    def _extract_local(self, css_text: str) -> set[str]:
        """Return local (non-remote, non-data) font names in *css_text*."""
        found: set[str] = set()
        for match in _FONT_URL_RE.finditer(css_text):
            font_name = match.group(1).strip("'\"")
            if not font_name.startswith(_REMOTE_FONT_PREFIXES):
                found.add(font_name)
        return found

    async def _fetch_one(self, font_name: str) -> str | None:
        """Download a single font, returning its basename or ``None``."""
        basename = Path(font_name).name
        font_path = self._css_dir / basename

        if font_path.is_file():
            logger.debug("Font already exists, skipping: %s", basename)
            return basename

        url = _FONT_FILES_URL_TEMPLATE.format(
            base=SAFARI_BASE_URL,
            book_id=self._book_id,
            font=font_name,
        )
        try:
            response = await self._client.get(url)
        except Exception:
            logger.exception("Error downloading font: %s", font_name)
            return None

        if response.status_code != _HTTP_OK:
            logger.error("HTTP %d downloading font: %s", response.status_code, font_name)
            return None

        font_path.write_bytes(response.content)
        return basename


async def download_fonts(
    client: ApiClient,
    css_dir: Path,
    book_id: str,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[str]:
    """Parse CSS files for font references and download them.

    Scans every ``.css`` file in *css_dir* for ``url()`` references to
    font files (otf, ttf, woff, woff2), then downloads them from the
    O'Reilly files API.

    Parameters
    ----------
    client:
        Authenticated API client.
    css_dir:
        The ``Styles/`` directory containing CSS files.
    book_id:
        Book identifier for the files API URL.
    progress_callback:
        Optional ``(total, completed)`` progress callback.

    Returns:
    -------
    list[str]
        Filenames of successfully downloaded font files.

    """
    if not css_dir.is_dir():
        return []

    downloader = _FontDownloader(
        client,
        css_dir,
        book_id,
        progress_callback=progress_callback,
    )
    font_urls = downloader.scan()
    if not font_urls:
        return []

    logger.info("Found %d font references in CSS files", len(font_urls))
    return await downloader.fetch_all(font_urls)


async def download_videos(
    client: ApiClient,
    video_urls: list[str],
    videos_dir: Path,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[str]:
    """Download all video files for a book.

    Parameters
    ----------
    client:
        Authenticated API client.
    video_urls:
        List of video URLs to download.
    videos_dir:
        Destination ``Video/`` directory.
    progress_callback:
        Optional ``(total, completed)`` progress callback.

    Returns:
    -------
    list[str]
        Filenames of successfully downloaded videos.

    """
    if not video_urls:
        return []

    coros = [_download_single_video(client, url, videos_dir) for url in video_urls]
    return await _parallel_download(coros, progress_callback=progress_callback)
