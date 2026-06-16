"""End-to-end integration test for the BookDownloader pipeline with mocked API."""

import json
import zipfile
from pathlib import Path
from types import MappingProxyType

import httpx
import pytest
import respx

from safaribooks.core.config import AppConfig
from safaribooks.core.downloader import BookDownloader

BOOK_ID = "9781234567890"

_HTTP_OK = 200
_BASE_URL = "https://learning.oreilly.com"
_HTML_HEADERS = MappingProxyType({"Content-Type": "text/html"})

# ---------------------------------------------------------------------------
# Fixture data: realistic-looking API responses
# ---------------------------------------------------------------------------

BOOK_INFO_RESPONSE = MappingProxyType({
    "title": "Python Testing with pytest",
    "identifier": BOOK_ID,
    "isbn": BOOK_ID,
    "description": "A comprehensive guide to testing Python applications.",
    "web_url": f"https://learning.oreilly.com/library/view/-/{BOOK_ID}/",
    "rights": "Copyright 2024 O'Reilly Media, Inc.",
    "cover_url": f"https://learning.oreilly.com/covers/urn:orm:book:{BOOK_ID}/thumb/",
    "publication_date": "2024-01-15",
})

SEARCH_RESPONSE = MappingProxyType({
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
})

CHAPTERS_RESPONSE = MappingProxyType({
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
})

TOC_RESPONSE = MappingProxyType({
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
})

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


def _json_response(payload: MappingProxyType) -> httpx.Response:
    """Build a 200 JSON response from an immutable payload mapping."""
    return httpx.Response(_HTTP_OK, json=dict(payload))


def _html_response(text: str) -> httpx.Response:
    """Build a 200 HTML response with the right content type."""
    return httpx.Response(_HTTP_OK, text=text, headers=dict(_HTML_HEADERS))


def _register_metadata_routes(base: str, book_id: str) -> None:
    """Register profile, book-info, search, and chapter-list routes."""
    respx.get(f"{base}/profile/").mock(
        return_value=httpx.Response(
            _HTTP_OK,
            text='<html>profile page user_type:"Active"</html>',
            headers=dict(_HTML_HEADERS),
        )
    )
    respx.get(f"{base}/api/v2/epubs/urn:orm:book:{book_id}/").mock(
        return_value=_json_response(BOOK_INFO_RESPONSE)
    )
    respx.get(url__startswith=f"{base}/api/v2/search/").mock(
        return_value=_json_response(SEARCH_RESPONSE)
    )
    respx.get(url__startswith=f"{base}/api/v2/epub-chapters/").mock(
        return_value=_json_response(CHAPTERS_RESPONSE)
    )


def _register_content_routes(base: str, book_id: str) -> None:
    """Register chapter HTML, TOC, and the catch-all fallback route."""
    chapter_base = f"{base}/api/v2/epubs/urn:orm:book:{book_id}/chapter"
    respx.get(f"{chapter_base}/cover.html").mock(return_value=_html_response(COVER_HTML))
    respx.get(f"{chapter_base}/ch01.html").mock(return_value=_html_response(CH01_HTML))
    respx.get(f"{chapter_base}/ch02.html").mock(return_value=_html_response(CH02_HTML))

    respx.get(f"{base}/api/v2/epubs/urn:orm:book:{book_id}/table-of-contents/").mock(
        return_value=_json_response(TOC_RESPONSE)
    )

    # Catch-all for CSS/images/fonts/any other URL — MUST be last.
    respx.route().mock(
        return_value=httpx.Response(
            _HTTP_OK,
            content=b"/* css placeholder */",
            headers={"Content-Type": "text/css"},
        )
    )


def _register_routes(base: str, book_id: str) -> None:
    """Register all respx routes for the mock API.

    Named routes (specific URLs) are registered first. The catch-all
    must be registered LAST since respx matches in registration order.
    """
    _register_metadata_routes(base, book_id)
    _register_content_routes(base, book_id)


def _assert_epub_container(archive: zipfile.ZipFile) -> None:
    """Assert mimetype and META-INF/container.xml are spec-compliant."""
    names = archive.namelist()

    # mimetype must be the first entry per EPUB spec
    assert names[0] == "mimetype"
    assert archive.read("mimetype") == b"application/epub+zip"

    # META-INF/container.xml must exist
    assert "META-INF/container.xml" in names
    container_xml = archive.read("META-INF/container.xml").decode("utf-8")
    assert "content.opf" in container_xml


def _assert_opf_metadata(archive: zipfile.ZipFile) -> None:
    """Assert content.opf exists and references the expected book."""
    assert "OEBPS/content.opf" in archive.namelist()
    content_opf = archive.read("OEBPS/content.opf").decode("utf-8")
    assert "Python Testing with pytest" in content_opf
    assert BOOK_ID in content_opf


def _assert_chapter_files(archive: zipfile.ZipFile) -> None:
    """Assert the expected chapter XHTML files exist with real content."""
    names = archive.namelist()
    assert "OEBPS/cover.xhtml" in names
    assert "OEBPS/ch01.xhtml" in names
    assert "OEBPS/ch02.xhtml" in names

    ch01_content = archive.read("OEBPS/ch01.xhtml").decode("utf-8")
    assert "Getting Started" in ch01_content


def _assert_toc(archive: zipfile.ZipFile) -> None:
    """Assert toc.ncx exists and lists both chapters."""
    assert "OEBPS/toc.ncx" in archive.namelist()
    toc_ncx = archive.read("OEBPS/toc.ncx").decode("utf-8")
    assert "Chapter 1" in toc_ncx
    assert "Chapter 2" in toc_ncx


def _assert_epub_content(archive: zipfile.ZipFile) -> None:
    """Assert OPF metadata, chapter files, TOC, and chapter content."""
    _assert_opf_metadata(archive)
    _assert_chapter_files(archive)
    _assert_toc(archive)


def _assert_single_clean_epub(books_dir: Path, epub_path: Path) -> None:
    """Assert one cleanly named EPUB exists with no per-book subdirectory."""
    # EPUB should be directly in Books/, not in a subdirectory
    epub_files = list(books_dir.glob("*.epub"))
    assert len(epub_files) == 1
    epub_file = epub_files[0]

    assert epub_file.name == "Python Testing with pytest.epub"
    assert BOOK_ID not in epub_file.name
    assert epub_file == epub_path

    # No per-book subdirectory should remain
    subdirs = [entry for entry in books_dir.iterdir() if entry.is_dir()]
    assert not subdirs


class _ProgressRecorder:
    """Collect progress callback invocations for later inspection."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def __call__(self, stage: str, current: int, total: int) -> None:
        self.calls.append((stage, current, total))

    @property
    def stages(self) -> set[str]:
        """Return the set of distinct stage names that were reported."""
        return {call[0] for call in self.calls}


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
        _register_routes(_BASE_URL, BOOK_ID)

        downloader = BookDownloader(pipeline_config, BOOK_ID)
        epub_path = await downloader.run()

        # -- Verify output files exist --
        assert epub_path.exists(), f"EPUB file should exist at {epub_path}"
        assert epub_path.suffix == ".epub"

        # -- Verify EPUB is a valid ZIP --
        assert zipfile.is_zipfile(epub_path)

        with zipfile.ZipFile(epub_path) as archive:
            _assert_epub_container(archive)
            _assert_epub_content(archive)

    @respx.mock
    async def test_pipeline_with_progress_callback(
        self,
        pipeline_config: AppConfig,
        tmp_path: Path,
    ):
        """Verify that the progress callback is invoked during the pipeline."""
        _register_routes(_BASE_URL, BOOK_ID)

        recorder = _ProgressRecorder()

        downloader = BookDownloader(
            pipeline_config,
            BOOK_ID,
            progress_callback=recorder,
        )
        await downloader.run()

        # Verify progress was reported for chapters and epub stages
        assert "chapters" in recorder.stages
        assert "epub" in recorder.stages

    @respx.mock
    async def test_pipeline_directory_structure(
        self,
        pipeline_config: AppConfig,
        tmp_path: Path,
    ):
        """Verify the EPUB is saved directly in the output directory with a clean name."""
        _register_routes(_BASE_URL, BOOK_ID)

        downloader = BookDownloader(pipeline_config, BOOK_ID)
        epub_path = await downloader.run()

        books_dir = tmp_path / "Books"
        assert books_dir.is_dir()

        _assert_single_clean_epub(books_dir, epub_path)

    @respx.mock
    async def test_pipeline_enriches_metadata(
        self,
        pipeline_config: AppConfig,
        tmp_path: Path,
    ):
        """Verify that search API enrichment populates authors and subjects."""
        _register_routes(_BASE_URL, BOOK_ID)

        downloader = BookDownloader(pipeline_config, BOOK_ID)
        epub_path = await downloader.run()

        with zipfile.ZipFile(epub_path) as archive:
            content_opf = archive.read("OEBPS/content.opf").decode("utf-8")
            # The search API response should have enriched the metadata
            assert "Brian Okken" in content_opf
            assert "O&#x27;Reilly Media" in content_opf or "O'Reilly Media" in content_opf
