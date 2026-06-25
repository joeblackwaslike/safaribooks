"""URL classification predicates for chapter assets."""

import pathlib
from urllib.parse import urlparse

_IMAGE_EXTENSIONS: frozenset[str] = frozenset(("jpg", "jpeg", "png", "gif"))
_VIDEO_EXTENSIONS: frozenset[str] = frozenset(("mp4",))
_HTML_EXTENSIONS: frozenset[str] = frozenset(("html", "xhtml", "htm"))
_IMAGE_PATH_HINTS: tuple[str, ...] = ("cover", "images", "graphics")

_FRAGMENT_SEP = "#"
_QUERY_SEP = "?"


def _strip_query_and_fragment(url: str) -> str:
    """Return *url* without its query string or fragment identifier."""
    without_query = url.split(_QUERY_SEP)[0]
    return without_query.split(_FRAGMENT_SEP)[0]


def is_absolute_url(url: str) -> bool:
    """Return ``True`` if *url* has a network location (scheme + host)."""
    return bool(urlparse(url).netloc)


def is_image_link(url: str) -> bool:
    """Return ``True`` if *url* points to a known image extension."""
    return pathlib.Path(url).suffix[1:].lower() in _IMAGE_EXTENSIONS


def is_video_link(url: str) -> bool:
    """Return ``True`` if *url* points to a known video extension."""
    clean = _strip_query_and_fragment(url)
    return pathlib.Path(clean).suffix[1:].lower() in _VIDEO_EXTENSIONS


def is_html_link(url: str) -> bool:
    """Return ``True`` if *url* points to a known HTML extension."""
    clean = _strip_query_and_fragment(url)
    return pathlib.Path(clean).suffix[1:].lower() in _HTML_EXTENSIONS


def is_image_implied(url: str) -> bool:
    """Return ``True`` if *url* contains path hints suggesting an image."""
    return any(hint in url for hint in _IMAGE_PATH_HINTS)


def is_possible_image(url: str) -> bool:
    """Return ``True`` if *url* is an image link or an implied image."""
    implied = not is_html_link(url) and is_image_implied(url)
    return is_image_link(url) or implied
