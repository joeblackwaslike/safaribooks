"""Image resizing and re-encoding via Pillow."""

import logging
from pathlib import Path

from safaribooks.core import assets

logger = logging.getLogger(__name__)

_HAS_PILLOW = True
try:
    from PIL import Image
except ImportError:  # pragma: no cover
    _HAS_PILLOW = False


def _pillow_available() -> bool:
    """Report whether Pillow is importable, honoring runtime monkeypatching."""
    return bool(getattr(assets, "_HAS_PILLOW", _HAS_PILLOW))


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
    if not _pillow_available():
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
