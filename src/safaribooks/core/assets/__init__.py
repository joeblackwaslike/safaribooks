"""Asset downloading: CSS, images, fonts, and videos with async concurrency."""
# This package re-exports its full public API so callers keep using
# `from safaribooks.core.assets import Thing` after the WPS202 split.

from safaribooks.core.assets.concurrency import _parallel_download
from safaribooks.core.assets.download import (
    _download_single_css,
    _download_single_image,
    _download_single_video,
    download_css,
    download_images,
    download_videos,
)
from safaribooks.core.assets.fonts import download_fonts
from safaribooks.core.assets.resize import _HAS_PILLOW, resize_image

__all__ = [  # noqa: WPS410  -- public re-export surface for the assets package
    "_HAS_PILLOW",
    "_download_single_css",
    "_download_single_image",
    "_download_single_video",
    "_parallel_download",
    "download_css",
    "download_fonts",
    "download_images",
    "download_videos",
    "resize_image",
]
