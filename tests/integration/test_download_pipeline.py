"""End-to-end integration test for the BookDownloader pipeline with mocked API."""


import json
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from safaribooks.core.config import AppConfig
from safaribooks.core.downloader import BookDownloader

BOOK_ID = "9781234567890"

# ---------------------------------------------------------------------------
# Fixture data: realistic-looking API responses
# ---------------------------------------------------------------------------

BOOK_INFO_RESPONSE: dict = {
    "title": "Python Testing with pytest",
    "identifier": BOOK_ID,
    "isbn": BOOK_ID,
    "description": "A comprehensive guide to testing Python applications.",
    "web_url": f"https://learning.oreilly.com/library/view/-/{BOOK_ID}/",
    "rights": "Copyright 2024 O'Reilly Media, Inc.",
    "cover_url": f"https://learning.oreilly.com/covers/urn:orm:book:{BOOK_ID}/thumb/",
    "publication_date": "2024-01-15",
}

SEARCH_RESPONSE: dict = {
    "results": [
        {
            "isbn": BOOK_ID,
            "identifier": BOOK_ID,
            "authors": ["Brian Okken"],
            "publishers": "O'Reilly Media",
            "issued": "2024-01-15",
            "subjects": ["Python", "Testing", "Software Engineering"],
            "cover_url": f"https://learning.oreilly.com/covers/urn:orm:book:{BOOK_ID}/thumb/",
            "web_url": f"https://learning.oreilly.com/library/view/-/{BOOK_ID}/",
        },
    ],
}

CHAPTERS_RESPONSE: dict = {
    "results": [
        {
            "filename": "cover.html",
            "title": "Cover",
            "content_url": f"https://learning.oreilly.com/api/v2/epubs/urn:orm:book:{BOOK_ID}/chapter/cover.html",
            "images": [],
            "stylesheets": [],
            "site_styles": [],
        },
        {
            "filename": "ch01.html",
            "title": "Chapter 1: Getting Started",
            "content_url": f"https://learning.oreilly.com/api/v2/epubs/urn:orm:book:{BOOK_ID}/chapter/ch01.html",
            "images": ["images/fig01-01.png"],
            "stylesheets": [{"url": "https://learning.oreilly.com/files/style.css"}],
            "site_styles": [],
        },
        {
            "filename": "ch02.html",
            "title": "Chapter 2: Writing Tests",
            "content_url": f"https://learning.oreilly.com/api/v2/epubs/urn:orm:book:{BOOK_ID}/chapter/ch02.html",
            "images": [],
            "stylesheets": [{"url": "https://learning.oreilly.com/files/style.css"}],
            "site_styles": [],
        },
    ],
    "next": None,
}

TOC_RESPONSE: dict = {
    "children": [
        {
            "id": "toc-cover",
            "label": "Cover",
            "url": "cover.html",
        },
        {
            "id": "toc-ch01",
            "label": "Chapter 1: Getting Started",
            "url": "ch01.html",
            "children": [
                {
                    "id": "toc-ch01-s1",
                    "label": "Installation",
                    "url": "ch01.html#installation",
                },
            ],
        },
        {
            "id": "toc-ch02",
            "label": "Chapter 2: Writing Tests",
            "url": "ch02.html",
        },
    ],
}

COVER_HTML = """
<html>
<head><title>Cover</title></head>
<body>
<div id="sbo-rt-content">
  <div class="cover">
    <img id="cover-image" class="cover" src="images/cover.png" alt="Cover"/>
  </div>
</div>
</body>
</html>
"""

CH01_HTML = """
<html>
<head>
  <title>Chapter 1</title>
  <link rel="stylesheet" href="https://learning.oreilly.com/files/style.css"/>
</head>
<body>
<div id="sbo-rt-content">
  <h1>Chapter 1: Getting Started</h1>
  <p>Welcome to Python testing. This chapter covers the basics.</p>
  <img src="images/fig01-01.png" alt="Figure 1-1"/>
</div>
</body>
</html>
"""

CH02_HTML = """
<html>
<head>
  <title>Chapter 2</title>
  <link rel="stylesheet" href="https://learning.oreilly.com/files/style.css"/>
</head>
<body>
<div id="sbo-rt-content">
  <h1>Chapter 2: Writing Tests</h1>
  <p>Learn to write effective tests with pytest.</p>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_routes(base: str, book_id: str) -> None:
    """Register all respx routes for the mock API.

    Named routes (specific URLs) are registered first. The catch-all
    must be registered LAST since respx matches in registration order.
    """
    # Profile check
    respx.get(f"{base}/profile/").mock(
        return_value=httpx.Response(
            200,
            text='<html>profile page user_type:"Active"</html>',
            headers={"Content-Type": "text/html"},
        )
    )

    # Book info
    respx.get(f"{base}/api/v2/epubs/urn:orm:book:{book_id}/").mock(
        return_value=httpx.Response(200, json=BOOK_INFO_RESPONSE)
    )

    # Search enrichment
    respx.get(url__startswith=f"{base}/api/v2/search/").mock(
        return_value=httpx.Response(200, json=SEARCH_RESPONSE)
    )

    # Chapters list
    respx.get(url__startswith=f"{base}/api/v2/epub-chapters/").mock(
        return_value=httpx.Response(200, json=CHAPTERS_RESPONSE)
    )

    # Chapter HTML content
    respx.get(f"{base}/api/v2/epubs/urn:orm:book:{book_id}/chapter/cover.html").mock(
        return_value=httpx.Response(200, text=COVER_HTML, headers={"Content-Type": "text/html"})
    )
    respx.get(f"{base}/api/v2/epubs/urn:orm:book:{book_id}/chapter/ch01.html").mock(
        return_value=httpx.Response(200, text=CH01_HTML, headers={"Content-Type": "text/html"})
    )
    respx.get(f"{base}/api/v2/epubs/urn:orm:book:{book_id}/chapter/ch02.html").mock(
        return_value=httpx.Response(200, text=CH02_HTML, headers={"Content-Type": "text/html"})
    )

    # TOC
    respx.get(f"{base}/api/v2/epubs/urn:orm:book:{book_id}/table-of-contents/").mock(
        return_value=httpx.Response(200, json=TOC_RESPONSE)
    )

    # Catch-all for CSS/images/fonts/any other URL — MUST be last
    respx.route().mock(
        return_value=httpx.Response(
            200,
            content=b"/* css placeholder */",
            headers={"Content-Type": "text/css"},
        )
    )


@pytest.fixture
def pipeline_config(tmp_path: Path) -> AppConfig:
    """Create an AppConfig pointing at tmp_path for all file I/O."""
    cookies_file = tmp_path / "cookies.json"
    cookies_file.write_text(
        json.dumps({
            "groot_sessionid": "test_session",
            "jwt": "test.jwt.token",
            "csrf_access_token": "test_csrf",
            "logged_in": "1",
        }),
        encoding="utf-8",
    )

    return AppConfig(
        cookies_file=cookies_file,
        output_dir=tmp_path / "Books",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFullDownloadPipeline:
    """Integration test that exercises the full BookDownloader pipeline."""

    @respx.mock
    async def test_full_pipeline_produces_valid_epub(
        self,
        pipeline_config: AppConfig,
        tmp_path: Path,
    ):
        """Mock the entire O'Reilly API and verify the EPUB output structure."""
        base = "https://learning.oreilly.com"
        _register_routes(base, BOOK_ID)

        downloader = BookDownloader(pipeline_config, BOOK_ID)
        epub_path = await downloader.run()

        # -- Verify output files exist --
        assert epub_path.exists(), f"EPUB file should exist at {epub_path}"
        assert epub_path.suffix == ".epub"

        # -- Verify EPUB is a valid ZIP --
        assert zipfile.is_zipfile(epub_path)

        with zipfile.ZipFile(epub_path) as zf:
            names = zf.namelist()

            # mimetype must be the first entry per EPUB spec
            assert names[0] == "mimetype"
            assert zf.read("mimetype") == b"application/epub+zip"

            # META-INF/container.xml must exist
            assert "META-INF/container.xml" in names
            container_xml = zf.read("META-INF/container.xml").decode("utf-8")
            assert "content.opf" in container_xml

            # content.opf must exist and reference our book
            assert "OEBPS/content.opf" in names
            content_opf = zf.read("OEBPS/content.opf").decode("utf-8")
            assert "Python Testing with pytest" in content_opf
            assert BOOK_ID in content_opf

            # Chapter XHTML files should exist
            assert "OEBPS/cover.xhtml" in names
            assert "OEBPS/ch01.xhtml" in names
            assert "OEBPS/ch02.xhtml" in names

            # toc.ncx should exist
            assert "OEBPS/toc.ncx" in names
            toc_ncx = zf.read("OEBPS/toc.ncx").decode("utf-8")
            assert "Chapter 1" in toc_ncx
            assert "Chapter 2" in toc_ncx

            # Verify chapter content
            ch01_content = zf.read("OEBPS/ch01.xhtml").decode("utf-8")
            assert "Getting Started" in ch01_content

    @respx.mock
    async def test_pipeline_with_progress_callback(
        self,
        pipeline_config: AppConfig,
        tmp_path: Path,
    ):
        """Verify that the progress callback is invoked during the pipeline."""
        base = "https://learning.oreilly.com"
        _register_routes(base, BOOK_ID)

        progress_calls: list[tuple[str, int, int]] = []

        def progress_cb(stage: str, current: int, total: int) -> None:
            progress_calls.append((stage, current, total))

        downloader = BookDownloader(
            pipeline_config,
            BOOK_ID,
            progress_callback=progress_cb,
        )
        await downloader.run()

        # Verify progress was reported for chapters and epub stages
        stages = {call[0] for call in progress_calls}
        assert "chapters" in stages
        assert "epub" in stages

    @respx.mock
    async def test_pipeline_directory_structure(
        self,
        pipeline_config: AppConfig,
        tmp_path: Path,
    ):
        """Verify the intermediate EPUB directory structure is created correctly."""
        base = "https://learning.oreilly.com"
        _register_routes(base, BOOK_ID)

        downloader = BookDownloader(pipeline_config, BOOK_ID)
        await downloader.run()

        # Verify the intermediate directory structure
        books_dir = tmp_path / "Books"
        assert books_dir.is_dir()

        # Find the book directory (sanitized title)
        book_dirs = list(books_dir.iterdir())
        assert len(book_dirs) == 1
        book_dir = book_dirs[0]

        assert (book_dir / "OEBPS").is_dir()
        assert (book_dir / "OEBPS" / "Styles").is_dir()
        assert (book_dir / "OEBPS" / "Images").is_dir()
        assert (book_dir / "META-INF").is_dir()

        # content.opf should be on disk
        content_opf_path = book_dir / "OEBPS" / "content.opf"
        assert content_opf_path.is_file()
        content = content_opf_path.read_text(encoding="utf-8")
        assert "Python Testing with pytest" in content

        # toc.ncx should be on disk
        toc_ncx_path = book_dir / "OEBPS" / "toc.ncx"
        assert toc_ncx_path.is_file()

    @respx.mock
    async def test_pipeline_enriches_metadata(
        self,
        pipeline_config: AppConfig,
        tmp_path: Path,
    ):
        """Verify that search API enrichment populates authors and subjects."""
        base = "https://learning.oreilly.com"
        _register_routes(base, BOOK_ID)

        downloader = BookDownloader(pipeline_config, BOOK_ID)
        epub_path = await downloader.run()

        with zipfile.ZipFile(epub_path) as zf:
            content_opf = zf.read("OEBPS/content.opf").decode("utf-8")
            # The search API response should have enriched the metadata
            assert "Brian Okken" in content_opf
            assert "O&#x27;Reilly Media" in content_opf or "O'Reilly Media" in content_opf
