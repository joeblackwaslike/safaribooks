"""Async download workers for CSS, image, and video assets."""

import logging
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin

from safaribooks.core.api import ApiClient
from safaribooks.core.assets.concurrency import _parallel_download
from safaribooks.core.constants import SAFARI_BASE_URL

logger = logging.getLogger(__name__)

_HTTP_OK = 200


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
    from safaribooks.core import assets

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

    assets.resize_image(image_path, max_size, quality)
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
