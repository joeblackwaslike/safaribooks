"""Convert EPUB chapter XHTML (lxml tree) into the Markdown IR."""
# flake8: noqa: WPS412 -- this package __init__ is a pure public-API re-export surface

from safaribooks.core.markdown.extract.container import blocks_from_element

__all__ = ["blocks_from_element"]
