"""Discover available Markdown extensions (built-ins + entry-points).

Built-in names are reserved: a third-party entry-point that reuses a built-in
name is ignored (with a warning), so installed packages cannot silently shadow
shipped behaviour. Third-party extensions execute arbitrary code on load — only
install trusted packages.
"""

import logging
from importlib.metadata import entry_points

from safaribooks.core.markdown.extensions.base import MarkdownExtension
from safaribooks.core.markdown.extensions.fix_broken_links import FixBrokenLinks
from safaribooks.core.markdown.extensions.fix_headings import FixHeadings
from safaribooks.core.markdown.extensions.reformat_toc import ReformatToc
from safaribooks.core.markdown.extensions.remove_footnotes import RemoveFootnotes

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "safaribooks.markdown_extensions"

_BUILTINS: tuple[type[MarkdownExtension], ...] = (
    FixHeadings,
    RemoveFootnotes,
    FixBrokenLinks,
    ReformatToc,
)


def _builtin_registry() -> dict[str, type[MarkdownExtension]]:
    """Return the built-in extension registry keyed by name."""
    return {extension_cls.name: extension_cls for extension_cls in _BUILTINS}


def discover() -> dict[str, type[MarkdownExtension]]:
    """Return all available extensions, merging built-ins and entry-points."""
    registry = _builtin_registry()
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        if entry.name in registry:
            logger.warning("Ignoring entry-point %r: reserved built-in name", entry.name)
            continue
        try:
            registry[entry.name] = entry.load()
        except Exception:
            logger.exception("Failed to load markdown extension %r", entry.name)
    return registry
