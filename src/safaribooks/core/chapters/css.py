"""Stylesheet discovery and ``<link>``/``<style>`` collection for chapters."""

import logging
from urllib.parse import urljoin

from lxml import etree, html

from safaribooks.core.exceptions import ParsingError

logger = logging.getLogger(__name__)

_NEWLINE = "\n"


def _style_link_tag(idx: int) -> str:
    """Return the ``<link>`` tag referencing the ``Style##.css`` at *idx*."""
    return f'<link href="Styles/Style{idx:02d}.css" rel="stylesheet" type="text/css" />{_NEWLINE}'


def _register_css(css_url: str, all_css: list[str], discovered_css: list[str]) -> int:
    """Register *css_url*, returning its stable index in *all_css*."""
    if css_url not in all_css:
        all_css.append(css_url)
        discovered_css.append(css_url)
        logger.debug("Found new CSS: %s", css_url)
    return all_css.index(css_url)


def _collect_link_css(
    chapter_stylesheets: list[str],
    all_css: list[str],
    discovered_css: list[str],
) -> str:
    """Build ``<link>`` tags for chapter-metadata stylesheets."""
    tags = [
        _style_link_tag(_register_css(css_url, all_css, discovered_css))
        for css_url in chapter_stylesheets
    ]
    return "".join(tags)


def _resolve_css_href(href: str, base_url: str) -> str:
    """Resolve a stylesheet ``href`` against *base_url* (or the https scheme)."""
    if href.startswith("//"):
        return urljoin("https:", href)
    return urljoin(base_url, href)


def _collect_html_link_css(  # type: ignore[no-any-unimported]
    root: html.HtmlElement,
    base_url: str,
    all_css: list[str],
    discovered_css: list[str],
) -> str:
    """Build ``<link>`` tags for in-page ``<link rel="stylesheet">`` elements."""
    tags: list[str] = []
    for link_el in root.xpath("//link[@rel='stylesheet']"):
        href = link_el.attrib.get("href", "")
        if not href:
            continue
        css_url = _resolve_css_href(href, base_url)
        tags.append(_style_link_tag(_register_css(css_url, all_css, discovered_css)))
    return "".join(tags)


def _collect_inline_css(root: html.HtmlElement) -> str:  # type: ignore[no-any-unimported]
    """Serialize inline ``<style>`` elements, applying any data templates."""
    fragments: list[str] = []
    for css_el in root.xpath("//style"):
        data_tpl = css_el.attrib.get("data-template", "")
        if data_tpl:
            css_el.text = data_tpl
            css_el.attrib.pop("data-template")
        try:
            serialized = html.tostring(css_el, method="xml", encoding="unicode")
        except (etree.ParseError, etree.ParserError) as exc:
            msg = f"Failed to serialize inline <style>: {exc}"
            raise ParsingError(msg) from exc
        fragments.append(f"{serialized}{_NEWLINE}")
    return "".join(fragments)


def _collect_page_css(  # type: ignore[no-any-unimported]
    root: html.HtmlElement,
    chapter_stylesheets: list[str],
    known_css: list[str],
    base_url: str,
    discovered_css: list[str],
) -> str:
    """Build the combined page CSS and record newly discovered stylesheets."""
    all_css: list[str] = list(known_css)
    page_css = _collect_link_css(chapter_stylesheets, all_css, discovered_css)
    page_css += _collect_html_link_css(root, base_url, all_css, discovered_css)
    return page_css + _collect_inline_css(root)
