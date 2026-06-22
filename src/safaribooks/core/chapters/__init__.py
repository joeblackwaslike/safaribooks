"""HTML parsing, link processing, and TOC normalization for chapters."""
# flake8: noqa: WPS412 -- public re-export surface for the chapters package

from lxml import html

from safaribooks.core.chapters.cover import find_cover_image
from safaribooks.core.chapters.parsing import fetch_chapter_html, parse_chapter_html
from safaribooks.core.chapters.toc import normalize_toc
from safaribooks.core.chapters.urls import (
    is_absolute_url,
    is_html_link,
    is_image_implied,
    is_image_link,
    is_possible_image,
    is_video_link,
    rewrite_link,
)

__all__ = [
    "fetch_chapter_html",
    "find_cover_image",
    "html",
    "is_absolute_url",
    "is_html_link",
    "is_image_implied",
    "is_image_link",
    "is_possible_image",
    "is_video_link",
    "normalize_toc",
    "parse_chapter_html",
    "rewrite_link",
]
