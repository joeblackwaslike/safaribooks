"""Resolve and run the configured Markdown extension pipeline."""

from safaribooks.core.exceptions import UnknownExtensionError
from safaribooks.core.markdown import ir
from safaribooks.core.markdown.extensions.base import ExtCtx, MarkdownExtension
from safaribooks.core.markdown.extensions.discovery import discover


def resolve(names: list[str]) -> list[MarkdownExtension]:
    """Instantiate the named extensions in order, raising on unknown names."""
    registry = discover()
    resolved: list[MarkdownExtension] = []
    for name in names:
        extension_cls = registry.get(name)
        if extension_cls is None:
            raise UnknownExtensionError(name, sorted(registry))
        resolved.append(extension_cls())
    return resolved


def run(
    chapters: tuple[ir.ChapterIR, ...],
    ctx: ExtCtx,
    extensions: list[MarkdownExtension],
) -> tuple[ir.ChapterIR, ...]:
    """Apply each extension's per-chapter then book-level hooks, in order."""
    for extension in extensions:
        chapters = tuple(extension.transform_chapter(chapter, ctx) for chapter in chapters)
        chapters = tuple(extension.transform_book(chapters, ctx))
    return chapters
