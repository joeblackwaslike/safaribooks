"""HTML parsing, link processing, and TOC normalization for chapters."""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from safaribooks.core.chapters.cover import find_cover_image as find_cover_image
from safaribooks.core.chapters.parsing import fetch_chapter_html as fetch_chapter_html
from safaribooks.core.chapters.parsing import parse_chapter_html as parse_chapter_html
from safaribooks.core.chapters.rewrite import rewrite_link as rewrite_link
from safaribooks.core.chapters.toc import normalize_toc as normalize_toc
from safaribooks.core.chapters.urls import is_absolute_url as is_absolute_url
from safaribooks.core.chapters.urls import is_html_link as is_html_link
from safaribooks.core.chapters.urls import is_image_implied as is_image_implied
from safaribooks.core.chapters.urls import is_image_link as is_image_link
from safaribooks.core.chapters.urls import is_possible_image as is_possible_image
from safaribooks.core.chapters.urls import is_video_link as is_video_link
