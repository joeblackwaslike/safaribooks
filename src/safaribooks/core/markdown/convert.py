"""Top-level EPUB -> Markdown conversion entry point.

Pipeline: read EPUB -> assemble IR -> run extension pipeline -> render body +
record offsets -> build two-pass front matter -> write ``<dest>.md``.
"""

from pathlib import Path

from safaribooks.core.markdown import assemble, frontmatter, ir
from safaribooks.core.markdown.extensions import ExtCtx, pipeline
from safaribooks.core.markdown.reader import read_epub
from safaribooks.core.markdown.render import Renderer


def convert_epub(
    epub_path: Path,
    dest_path: Path,
    *,
    extensions: list[str] | None = None,
    force: bool = False,
) -> Path:
    """Convert the EPUB at *epub_path* to a Markdown file at *dest_path*.

    Parameters
    ----------
    epub_path:
        Path to the source ``.epub``.
    dest_path:
        Destination ``.md`` path.
    extensions:
        Ordered extension names to run (pipeline order). Defaults to none.
    force:
        Overwrite *dest_path* if it already exists.

    Returns:
    -------
    Path
        The written Markdown file path.

    Raises:
    ------
    EpubReadError
        When the EPUB cannot be read.
    UnknownExtensionError
        When a configured extension name is not registered.
    FileExistsError
        When *dest_path* exists and *force* is ``False``.

    """
    if dest_path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {dest_path}")

    meta, chapters = assemble.assemble(read_epub(epub_path))
    chapters = _apply_extensions(meta, chapters, extensions or [])

    rendered = Renderer().render(chapters)
    front_matter, _ranges = frontmatter.build(
        meta,
        [chapter.title for chapter in chapters],
        rendered.offsets,
        rendered.body,
    )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(f"{front_matter}{rendered.body}", encoding="utf-8")
    return dest_path


def _apply_extensions(
    meta: ir.BookMeta,
    chapters: tuple[ir.ChapterIR, ...],
    extensions: list[str],
) -> tuple[ir.ChapterIR, ...]:
    """Resolve and run the configured extension pipeline over *chapters*."""
    resolved = pipeline.resolve(extensions)
    anchors = frozenset(note.identifier for chapter in chapters for note in chapter.footnotes)
    ctx = ExtCtx(book=meta, anchors=anchors)
    return pipeline.run(chapters, ctx, resolved)
