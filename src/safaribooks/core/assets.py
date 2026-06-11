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

try:
    from PIL import Image

    _HAS_PILLOW = True
except ImportError:  # pragma: no cover
    _HAS_PILLOW = False

# Default number of concurrent download workers.
_DEFAULT_WORKERS = 4

# Regex to find font URLs inside CSS files.
_FONT_URL_RE = re.compile(r"url\(['\"]?([^)]*\.(?:otf|ttf|woff|woff2))['\"]?\)")


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

    if response.status_code != 200:
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

    if response.status_code != 200:
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

    if response.status_code != 200:
        logger.error("HTTP %d downloading video: %s", response.status_code, video_name)
        return None

    video_path.write_bytes(response.content)

    return video_name


# ---------------------------------------------------------------------------
# Async parallel download orchestrator
# ---------------------------------------------------------------------------


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

    semaphore = asyncio.Semaphore(max_concurrent)
    total = len(coros)
    completed_count = 0
    results: list[str] = []

    async def _limited(coro: Coroutine[object, object, str | None]) -> str | None:
        nonlocal completed_count
        async with semaphore:
            result = await coro
        completed_count += 1
        if progress_callback is not None:
            progress_callback(total, completed_count)
        return result

    gathered = await asyncio.gather(*[_limited(c) for c in coros], return_exceptions=True)
    for item in gathered:
        if isinstance(item, BaseException):
            logger.exception("Download worker raised an exception", exc_info=item)
        elif item is not None:
            results.append(item)
    return results


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
    font_urls: set[str] = set()

    if not css_dir.is_dir():
        return []

    for css_file in css_dir.iterdir():
        if css_file.suffix != ".css":
            continue
        try:
            content = css_file.read_text(errors="ignore")
        except OSError:
            logger.warning("Could not read CSS file for font scanning: %s", css_file, exc_info=True)
            continue

        for match in _FONT_URL_RE.finditer(content):
            font_name = match.group(1).strip("'\"")
            if font_name.startswith(("data:", "http://", "https://")):
                continue
            font_urls.add(font_name)

    if not font_urls:
        return []

    logger.info("Found %d font references in CSS files", len(font_urls))

    results: list[str] = []
    total = len(font_urls)
    completed = 0

    for font_name in sorted(font_urls):
        completed += 1
        basename = Path(font_name).name
        font_path = css_dir / basename

        if font_path.is_file():
            logger.debug("Font already exists, skipping: %s", basename)
            results.append(basename)
            if progress_callback is not None:
                progress_callback(total, completed)
            continue

        url = f"{SAFARI_BASE_URL}/api/v2/epubs/urn:orm:book:{book_id}/files/{font_name}"
        try:
            response = await client.get(url)
        except Exception:
            logger.exception("Error downloading font: %s", font_name)
            if progress_callback is not None:
                progress_callback(total, completed)
            continue

        if response.status_code != 200:
            logger.error("HTTP %d downloading font: %s", response.status_code, font_name)
            if progress_callback is not None:
                progress_callback(total, completed)
            continue

        font_path.write_bytes(response.content)

        results.append(basename)
        if progress_callback is not None:
            progress_callback(total, completed)

    return results


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
