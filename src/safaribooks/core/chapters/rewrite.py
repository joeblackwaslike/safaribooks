"""Rewrite chapter-internal links to their EPUB-local equivalents."""

from safaribooks.core.chapters.urls import (
    is_absolute_url,
    is_possible_image,
    is_video_link,
)


def _rewrite_relative(link: str) -> str:
    """Rewrite a relative chapter link to its EPUB-local equivalent."""
    filename = link.split("/")[-1]
    if is_video_link(link):
        return f"Video/{filename}"
    if is_possible_image(link):
        return f"Images/{filename}"
    return link.replace(".html", ".xhtml")


def rewrite_link(link: str, book_id: str) -> str:
    """Rewrite a chapter-internal link for EPUB packaging.

    Relative video links become ``Video/<filename>``, relative image links
    become ``Images/<filename>``, and HTML links get their extension changed
    to ``.xhtml``. Absolute links that contain *book_id* are recursively
    rewritten as relative.
    """
    if not link or link.startswith("mailto"):
        return link

    if is_absolute_url(link):
        if book_id in link:
            return rewrite_link(link.split(book_id)[-1], book_id)
        return link

    return _rewrite_relative(link)
