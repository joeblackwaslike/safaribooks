"""URL classification and link rewriting for chapter assets."""

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


class _LinkClassifier:
    """Predicates that classify a chapter link by its target type."""

    @staticmethod
    def is_absolute_url(url: str) -> bool:
        """Return ``True`` if *url* has a network location (scheme + host)."""
        return bool(urlparse(url).netloc)

    @staticmethod
    def is_image_link(url: str) -> bool:
        """Return ``True`` if *url* points to a known image extension."""
        return pathlib.Path(url).suffix[1:].lower() in _IMAGE_EXTENSIONS

    @staticmethod
    def is_video_link(url: str) -> bool:
        """Return ``True`` if *url* points to a known video extension."""
        clean = _strip_query_and_fragment(url)
        return pathlib.Path(clean).suffix[1:].lower() in _VIDEO_EXTENSIONS

    @staticmethod
    def is_html_link(url: str) -> bool:
        """Return ``True`` if *url* points to a known HTML extension."""
        clean = _strip_query_and_fragment(url)
        return pathlib.Path(clean).suffix[1:].lower() in _HTML_EXTENSIONS

    @staticmethod
    def is_image_implied(url: str) -> bool:
        """Return ``True`` if *url* contains path hints suggesting an image."""
        return any(hint in url for hint in _IMAGE_PATH_HINTS)

    @classmethod
    def is_possible_image(cls, url: str) -> bool:
        """Return ``True`` if *url* is an image link or an implied image."""
        implied = not cls.is_html_link(url) and cls.is_image_implied(url)
        return cls.is_image_link(url) or implied


class _LinkRewriter:
    """Rewrites chapter-internal links to their EPUB-local equivalents."""

    @staticmethod
    def _rewrite_relative(link: str) -> str:
        """Rewrite a relative chapter link to its EPUB-local equivalent."""
        filename = link.split("/")[-1]
        if _LinkClassifier.is_video_link(link):
            return f"Video/{filename}"
        if _LinkClassifier.is_possible_image(link):
            return f"Images/{filename}"
        return link.replace(".html", ".xhtml")

    @classmethod
    def rewrite(cls, link: str, book_id: str) -> str:
        """Rewrite a chapter-internal link for EPUB packaging.

        Relative video links become ``Video/<filename>``, relative image
        links become ``Images/<filename>``, and HTML links get their
        extension changed to ``.xhtml``.  Absolute links that contain the
        *book_id* are recursively rewritten as relative.

        Parameters
        ----------
        link:
            The original ``href`` or ``src`` attribute value.
        book_id:
            The O'Reilly book identifier for detecting self-references.

        Returns:
        -------
        str
            The rewritten link.

        """
        if not link or link.startswith("mailto"):
            return link

        if _LinkClassifier.is_absolute_url(link):
            if book_id in link:
                return cls.rewrite(link.split(book_id)[-1], book_id)
            return link

        return cls._rewrite_relative(link)


is_absolute_url = _LinkClassifier.is_absolute_url
is_image_link = _LinkClassifier.is_image_link
is_video_link = _LinkClassifier.is_video_link
is_html_link = _LinkClassifier.is_html_link
is_image_implied = _LinkClassifier.is_image_implied
is_possible_image = _LinkClassifier.is_possible_image
rewrite_link = _LinkRewriter.rewrite
