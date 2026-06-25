"""Shared helpers for the Markdown-export tests: minimal EPUB builders."""

import zipfile
from dataclasses import dataclass
from pathlib import Path

_CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_CHAPTER_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>{title}</title></head>
  <body><div id="sbo-rt-content">{body}</div></body>
</html>
"""


@dataclass(frozen=True)
class ChapterSpec:
    """A chapter to embed in a generated EPUB."""

    title: str
    body: str


def _content_opf(title: str, isbn: str, specs: list[ChapterSpec]) -> str:
    """Render a minimal content.opf with metadata, manifest, and spine."""
    items = "\n".join(
        f'    <item id="ch{i}" href="ch{i}.xhtml" media-type="application/xhtml+xml"/>'
        for i, _ in enumerate(specs)
    )
    refs = "\n".join(f'    <itemref idref="ch{i}"/>' for i, _ in enumerate(specs))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>Ada Lovelace</dc:creator>
    <dc:publisher>O'Reilly Media, Inc.</dc:publisher>
    <dc:date>2024-01-02</dc:date>
    <dc:language>en</dc:language>
    <dc:identifier id="bookid">{isbn}</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
{items}
  </manifest>
  <spine toc="ncx">
{refs}
  </spine>
</package>
"""


def _toc_ncx(specs: list[ChapterSpec]) -> str:
    """Render a minimal toc.ncx mapping chapter files to nav labels."""
    points = "\n".join(
        f"""    <navPoint id="n{i}" playOrder="{i + 1}">
      <navLabel><text>{spec.title}</text></navLabel>
      <content src="ch{i}.xhtml"/>
    </navPoint>"""
        for i, spec in enumerate(specs)
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
{points}
  </navMap>
</ncx>
"""


def build_epub(path: Path, title: str, specs: list[ChapterSpec], *, isbn: str = "9781234567890") -> Path:
    """Write a minimal but valid EPUB to *path* and return it."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", _content_opf(title, isbn, specs))
        zf.writestr("OEBPS/toc.ncx", _toc_ncx(specs))
        for index, spec in enumerate(specs):
            xhtml = _CHAPTER_TEMPLATE.format(title=spec.title, body=spec.body)
            zf.writestr(f"OEBPS/ch{index}.xhtml", xhtml)
    return path
