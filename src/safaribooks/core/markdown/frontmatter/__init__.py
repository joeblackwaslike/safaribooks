"""Build the YAML front matter with per-chapter line and byte offsets."""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from safaribooks.core.markdown.frontmatter.document import build, render
from safaribooks.core.markdown.frontmatter.numbers import NUMERIC_WIDTH, pad_number
from safaribooks.core.markdown.frontmatter.ranges import ChapterRange
from safaribooks.core.markdown.frontmatter.yaml import yaml_inline_string

__all__ = [
    "NUMERIC_WIDTH",
    "ChapterRange",
    "build",
    "pad_number",
    "render",
    "yaml_inline_string",
]
