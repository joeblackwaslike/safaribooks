"""Tests for safaribooks.core.book — normalize_chapter and helpers."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from safaribooks.core.book import (
    enrich_book_metadata,
    fetch_book_info,
    fetch_chapters,
    fetch_default_cover,
    normalize_chapter,
)
from safaribooks.core.constants import FILES_API_TEMPLATE, SAFARI_BASE_URL
from safaribooks.core.exceptions import ApiError
from safaribooks.core.models import BookInfo, Publisher

BOOK_ID = "9781234567890"

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_SERVER_ERROR = 500

_THUMB_COVER = "https://img.com/thumb/x.jpg"
_LEGACY_COVER = "https://example.com/legacy-cover.jpg"


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.get_json = AsyncMock()
    client.get = AsyncMock()
    return client


def _base_book_info(**overrides: object) -> BookInfo:
    defaults: dict[str, object] = {
        "title": "A Book",
        "identifier": BOOK_ID,
        "isbn": BOOK_ID,
        "description": "desc",
        "web_url": f"{SAFARI_BASE_URL}/library/view/-/{BOOK_ID}/",
        "rights": "",
        "cover": None,
        "authors": [],
        "publishers": [],
        "subjects": [],
        "issued": None,
    }
    defaults.update(overrides)
    return BookInfo(**defaults)  # type: ignore[arg-type]


def _make_response(
    status_code: int = _HTTP_OK,
    body: bytes = b"binary-cover-data",
    content_type: str = "image/jpeg",
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        headers={"Content-Type": content_type},
        content=body,
    )


def _names(models) -> list[str]:
    """Extract the ``name`` attribute from each model in a sequence."""
    return [model.name for model in models]


def _filenames(chapters) -> list[str]:
    """Extract the ``filename`` attribute from each chapter."""
    return [chapter.filename for chapter in chapters]


_STRIPPED_IMAGE_URL = "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:123/files/img/fig.png"
_ASSET_BASE = FILES_API_TEMPLATE.format(BOOK_ID)


class TestNormalizeChapterBasic:
    def test_basic_chapter(self):
        raw = {
            "filename": "ch01.xhtml",
            "title": "Chapter 1",
            "content_url": (
                "https://learning.oreilly.com/api/v2/epubs/"
                "urn:orm:book:9781234567890/files/ch01.xhtml"
            ),
            "images": ["img/fig1.png", "img/fig2.png"],
            "stylesheets": ["style/main.css"],
            "site_styles": ["style/site.css"],
        }
        chapter = normalize_chapter(raw, BOOK_ID)
        assert chapter.filename == "ch01.xhtml"
        assert chapter.title == "Chapter 1"
        assert chapter.images == ["img/fig1.png", "img/fig2.png"]
        assert chapter.site_styles == ["style/site.css"]
        assert "/files" in chapter.asset_base_url

    @pytest.mark.parametrize(
        ("raw", "attribute", "expected"),
        [
            # Empty images list is preserved as-is.
            (
                {
                    "filename": "ch02.xhtml",
                    "content_url": "http://example.com/ch02",
                    "images": [],
                    "stylesheets": [],
                },
                "images",
                [],
            ),
            # related_assets is used when top-level images are absent.
            (
                {
                    "filename": "ch03.xhtml",
                    "content_url": "http://example.com/ch03",
                    "related_assets": {"images": ["img/a.png", "img/b.jpg"]},
                },
                "images",
                ["img/a.png", "img/b.jpg"],
            ),
            # Top-level images win over related_assets.
            (
                {
                    "filename": "ch04.xhtml",
                    "content_url": "http://example.com/ch04",
                    "images": ["top.png"],
                    "related_assets": {"images": ["fallback.png"]},
                },
                "images",
                ["top.png"],
            ),
            # Absolute /files/ image URLs are stripped to relative paths.
            (
                {
                    "filename": "ch05.xhtml",
                    "content_url": "http://example.com/ch05",
                    "images": [_STRIPPED_IMAGE_URL, "img/local.png"],
                },
                "images",
                ["img/fig.png", "img/local.png"],
            ),
            # ourn provides the filename when no explicit filename is given.
            (
                {
                    "ourn": "urn:orm:book:123:ch07.html",
                    "content_url": "http://example.com/ch07",
                },
                "filename",
                "ch07.html",
            ),
            # reference_id provides the basename fallback.
            (
                {
                    "reference_id": "path/to/chapter9.html",
                    "content_url": "http://example.com/ch09",
                },
                "filename",
                "chapter9.html",
            ),
            # Percent-encoded filenames are decoded.
            (
                {
                    "filename": "ch%2010.xhtml",
                    "content_url": "http://example.com/ch10",
                },
                "filename",
                "ch 10.xhtml",
            ),
            # asset_base_url is derived from the files API template.
            (
                {"filename": "ch01.xhtml", "content_url": "http://example.com/ch01"},
                "asset_base_url",
                _ASSET_BASE,
            ),
            # content falls back to the legacy content field.
            (
                {"filename": "ch01.xhtml", "content": "http://example.com/ch01-via-content"},
                "content_url",
                "http://example.com/ch01-via-content",
            ),
            # Missing title defaults to an empty string.
            (
                {"filename": "ch01.xhtml", "content_url": "http://example.com/ch01"},
                "title",
                "",
            ),
        ],
    )
    def test_single_attribute(
        self,
        raw: dict[str, object],
        attribute: str,
        expected: object,
    ):
        chapter = normalize_chapter(raw, BOOK_ID)
        assert getattr(chapter, attribute) == expected

    def test_missing_filename_generates_hash(self):
        raw = {
            "content_url": "http://example.com/some-chapter",
        }
        chapter = normalize_chapter(raw, BOOK_ID)
        assert chapter.filename.startswith("chapter_")
        assert chapter.filename.endswith(".html")


class TestNormalizeChapterStylesheets:
    def test_related_assets_styles(self):
        raw = {
            "filename": "ch03.xhtml",
            "content_url": "http://example.com/ch03",
            "related_assets": {
                "stylesheets": ["css/style.css"],
                "site_styles": ["css/site.css"],
            },
        }
        chapter = normalize_chapter(raw, BOOK_ID)
        assert len(chapter.stylesheets) == 1
        assert chapter.stylesheets[0].url == "css/style.css"
        assert chapter.site_styles == ["css/site.css"]

    def test_string_stylesheets_wrapped_in_model(self):
        raw = {
            "filename": "ch06.xhtml",
            "content_url": "http://example.com/ch06",
            "stylesheets": ["style.css", "extra.css"],
        }
        chapter = normalize_chapter(raw, BOOK_ID)
        assert len(chapter.stylesheets) == 2
        assert chapter.stylesheets[0].url == "style.css"
        assert chapter.stylesheets[1].url == "extra.css"

    def test_dict_stylesheets_passed_through(self):
        raw = {
            "filename": "ch06b.xhtml",
            "content_url": "http://example.com/ch06b",
            "stylesheets": [{"url": "style.css"}],
        }
        chapter = normalize_chapter(raw, BOOK_ID)
        assert chapter.stylesheets[0].url == "style.css"


class TestFetchBookInfo:
    async def test_basic_metadata_fields(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "title": "Real Book",
            "identifier": BOOK_ID,
            "isbn": "9990000000001",
            "description": "A description",
            "web_url": "https://example.com/book",
            "rights": "All rights",
            "cover_url": "https://example.com/cover.jpg",
            "publication_date": "2024-01-01",
        }

        book = await fetch_book_info(mock_client, BOOK_ID)

        assert isinstance(book, BookInfo)
        actual = {
            "title": book.title,
            "isbn": book.isbn,
            "description": book.description,
            "cover": book.cover,
            "issued": book.issued,
        }
        assert actual == {
            "title": "Real Book",
            "isbn": "9990000000001",
            "description": "A description",
            "cover": "https://example.com/cover.jpg",
            "issued": "2024-01-01",
        }

    async def test_basic_metadata_requests_v2_url(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "title": "Real Book",
            "identifier": BOOK_ID,
        }

        await fetch_book_info(mock_client, BOOK_ID)

        # Correct v2 API URL was requested.
        url = mock_client.get_json.call_args[0][0]
        assert url == f"{SAFARI_BASE_URL}/api/v2/epubs/urn:orm:book:{BOOK_ID}/"

    @pytest.mark.parametrize(
        ("descriptions", "expected"),
        [
            (
                {"text/plain": "plain text desc", "text/html": "<p>html desc</p>"},
                "plain text desc",
            ),
            ({"text/html": "<p>html desc</p>"}, "<p>html desc</p>"),
        ],
    )
    async def test_descriptions_selection(
        self,
        mock_client: MagicMock,
        descriptions: dict[str, str],
        expected: str,
    ):
        mock_client.get_json.return_value = {
            "title": "Book",
            "description": "fallback",
            "descriptions": descriptions,
        }

        book = await fetch_book_info(mock_client, BOOK_ID)
        assert book.description == expected

    async def test_defaults_when_fields_absent(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {"title": "Bare Book"}

        book = await fetch_book_info(mock_client, BOOK_ID)
        assert book.identifier == BOOK_ID
        assert book.isbn == ""
        assert book.description == ""
        assert book.web_url == f"{SAFARI_BASE_URL}/library/view/-/{BOOK_ID}/"
        assert book.cover is None

    async def test_cover_falls_back_to_cover_field(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "title": "Book",
            "cover": _LEGACY_COVER,
        }

        book = await fetch_book_info(mock_client, BOOK_ID)
        assert book.cover == _LEGACY_COVER

    @pytest.mark.parametrize(
        "payload",
        [
            {"identifier": BOOK_ID},
            ["not", "a", "dict"],
        ],
    )
    async def test_invalid_response_raises_api_error(
        self,
        mock_client: MagicMock,
        payload: object,
    ):
        mock_client.get_json.return_value = payload

        with pytest.raises(ApiError, match="unexpected data"):
            await fetch_book_info(mock_client, BOOK_ID)


class TestEnrichBookMetadataFields:
    async def test_enriches_simple_fields(self, mock_client: MagicMock):
        book = _base_book_info(web_url="")
        mock_client.get_json.return_value = {
            "results": [
                {
                    "isbn": BOOK_ID,
                    "issued": "2023-05-05",
                    "cover_url": "https://example.com/c.jpg",
                    "web_url": "https://example.com/web",
                }
            ]
        }

        enriched = await enrich_book_metadata(mock_client, BOOK_ID, book)

        assert enriched.issued == "2023-05-05"
        assert enriched.cover == "https://example.com/c.jpg"
        assert enriched.web_url == "https://example.com/web"

    async def test_enriches_collection_fields(self, mock_client: MagicMock):
        book = _base_book_info(web_url="")
        mock_client.get_json.return_value = {
            "results": [
                {
                    "isbn": BOOK_ID,
                    "authors": ["Jane Doe", "John Smith"],
                    "publishers": "No Starch Press",
                    "subjects": ["Python", "Testing"],
                }
            ]
        }

        enriched = await enrich_book_metadata(mock_client, BOOK_ID, book)

        assert _names(enriched.authors) == ["Jane Doe", "John Smith"]
        assert enriched.publishers == [Publisher(name="No Starch Press")]
        assert _names(enriched.subjects) == ["Python", "Testing"]


class TestEnrichBookMetadataPublishers:
    @pytest.mark.parametrize(
        ("publishers", "expected"),
        [
            (["Pub A", "Pub B"], [Publisher(name="Pub A"), Publisher(name="Pub B")]),
            ([{"name": "Pub Dict"}], [Publisher(name="Pub Dict")]),
            # Neither str nor list -> no update applied.
            ({"name": "ignored-dict"}, []),
        ],
    )
    async def test_publisher_coercion(
        self,
        mock_client: MagicMock,
        publishers: object,
        expected: list[Publisher],
    ):
        book = _base_book_info()
        mock_client.get_json.return_value = {
            "results": [{"isbn": BOOK_ID, "publishers": publishers}]
        }

        enriched = await enrich_book_metadata(mock_client, BOOK_ID, book)
        assert enriched.publishers == expected


class TestEnrichBookMetadataFallbacks:
    async def test_issued_falls_back_to_date_added(self, mock_client: MagicMock):
        book = _base_book_info()
        mock_client.get_json.return_value = {
            "results": [{"isbn": BOOK_ID, "date_added": "2020-02-02"}]
        }

        enriched = await enrich_book_metadata(mock_client, BOOK_ID, book)
        assert enriched.issued == "2020-02-02"

    async def test_cover_not_overwritten_when_already_set(self, mock_client: MagicMock):
        book = _base_book_info(cover="https://existing.com/cover.jpg")
        mock_client.get_json.return_value = {
            "results": [{"isbn": BOOK_ID, "cover_url": "https://new.com/cover.jpg"}]
        }

        enriched = await enrich_book_metadata(mock_client, BOOK_ID, book)
        assert enriched.cover == "https://existing.com/cover.jpg"


class TestEnrichBookMetadataMatching:
    @pytest.mark.parametrize(
        "payload",
        [
            # No results at all -> the original object is returned.
            {"results": []},
            # A result that matches no identifier -> unchanged, authors empty.
            {"results": [{"isbn": "0000000000000", "archive_id": "different", "authors": ["X"]}]},
            # A matching result with no enrichable fields -> unchanged.
            {"results": [{"isbn": BOOK_ID}]},
            # The lookup raising is swallowed and the original is returned.
            ApiError("boom"),
        ],
    )
    async def test_returns_unchanged(
        self,
        mock_client: MagicMock,
        payload: object,
    ):
        book = _base_book_info()
        if isinstance(payload, Exception):
            mock_client.get_json.side_effect = payload
        else:
            mock_client.get_json.return_value = payload

        enriched = await enrich_book_metadata(mock_client, BOOK_ID, book)
        assert enriched is book
        assert enriched.authors == []

    @pytest.mark.parametrize(
        "result_entry",
        [
            {"isbn": "0000000000000", "archive_id": BOOK_ID, "authors": ["Match"]},
            {"identifier": BOOK_ID, "authors": ["Match"]},
        ],
    )
    async def test_matches_via_alternate_keys(
        self,
        mock_client: MagicMock,
        result_entry: dict[str, object],
    ):
        book = _base_book_info()
        mock_client.get_json.return_value = {"results": [result_entry]}

        enriched = await enrich_book_metadata(mock_client, BOOK_ID, book)
        assert _names(enriched.authors) == ["Match"]


class TestFetchChapters:
    async def test_single_page(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "results": [
                {"filename": "ch01.xhtml", "title": "One", "content_url": "u1"},
                {"filename": "ch02.xhtml", "title": "Two", "content_url": "u2"},
            ],
            "next": None,
        }

        chapters = await fetch_chapters(mock_client, BOOK_ID)
        assert _filenames(chapters) == ["ch01.xhtml", "ch02.xhtml"]

    async def test_pagination_followed(self, mock_client: MagicMock):
        page1 = {
            "results": [{"filename": "ch01.xhtml", "title": "One", "content_url": "u1"}],
            "next": "https://next.page/",
        }
        page2 = {
            "results": [{"filename": "ch02.xhtml", "title": "Two", "content_url": "u2"}],
            "next": None,
        }
        mock_client.get_json.side_effect = [page1, page2]

        chapters = await fetch_chapters(mock_client, BOOK_ID)
        assert set(_filenames(chapters)) == {"ch01.xhtml", "ch02.xhtml"}
        assert mock_client.get_json.call_count == 2

    async def test_empty_page_after_content_breaks(self, mock_client: MagicMock):
        page1 = {
            "results": [{"filename": "ch01.xhtml", "title": "One", "content_url": "u1"}],
            "next": "https://next.page/",
        }
        page2 = {"results": [], "next": None}
        mock_client.get_json.side_effect = [page1, page2]

        chapters = await fetch_chapters(mock_client, BOOK_ID)
        assert _filenames(chapters) == ["ch01.xhtml"]

    async def test_cover_chapters_reordered_first(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "results": [
                {"filename": "ch01.xhtml", "title": "Intro", "content_url": "u1"},
                {"filename": "cover.xhtml", "title": "Cover Page", "content_url": "u2"},
                {"filename": "ch02.xhtml", "title": "Body", "content_url": "u3"},
            ],
            "next": None,
        }

        chapters = await fetch_chapters(mock_client, BOOK_ID)
        assert chapters[0].filename == "cover.xhtml"
        assert _filenames(chapters[1:]) == ["ch01.xhtml", "ch02.xhtml"]

    async def test_cover_detected_by_title(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "results": [
                {"filename": "a.xhtml", "title": "Body", "content_url": "u1"},
                {"filename": "b.xhtml", "title": "The Cover", "content_url": "u2"},
            ],
            "next": None,
        }

        chapters = await fetch_chapters(mock_client, BOOK_ID)
        assert chapters[0].filename == "b.xhtml"

    async def test_no_chapters_raises(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {"results": [], "next": None}

        with pytest.raises(ApiError, match="no chapters"):
            await fetch_chapters(mock_client, BOOK_ID)


class TestFetchDefaultCover:
    async def test_no_cover_url_returns_none(self, mock_client: MagicMock, tmp_path: Path):
        book = _base_book_info(cover=None)

        cover_name = await fetch_default_cover(mock_client, book, tmp_path)
        assert cover_name is None
        mock_client.get.assert_not_called()

    async def test_downloads_first_successful_variant(self, mock_client: MagicMock, tmp_path: Path):
        book = _base_book_info(cover=_THUMB_COVER)
        mock_client.get.return_value = _make_response(body=b"jpegbytes")

        cover_name = await fetch_default_cover(mock_client, book, tmp_path)
        assert cover_name == "default_cover.jpeg"
        saved = tmp_path / "default_cover.jpeg"
        assert saved.read_bytes() == b"jpegbytes"
        # First attempt is the /orig/ variant.
        call_args = mock_client.get.call_args_list[0][0]
        assert "/orig/" in call_args[0]

    async def test_content_type_determines_extension(self, mock_client: MagicMock, tmp_path: Path):
        book = _base_book_info(cover="https://img.com/cover.png")
        mock_client.get.return_value = _make_response(content_type="image/png")

        cover_name = await fetch_default_cover(mock_client, book, tmp_path)
        assert cover_name == "default_cover.png"

    async def test_falls_back_through_variants_on_failure(
        self, mock_client: MagicMock, tmp_path: Path
    ):
        book = _base_book_info(cover=_THUMB_COVER)
        # First three variants 404, last one (raw cover_url) succeeds.
        mock_client.get.side_effect = [
            _make_response(status_code=_HTTP_NOT_FOUND),
            _make_response(status_code=_HTTP_NOT_FOUND),
            _make_response(status_code=_HTTP_NOT_FOUND),
            _make_response(status_code=_HTTP_OK, body=b"ok"),
        ]

        cover_name = await fetch_default_cover(mock_client, book, tmp_path)
        assert cover_name == "default_cover.jpeg"
        assert (tmp_path / "default_cover.jpeg").read_bytes() == b"ok"

    async def test_api_error_skips_to_next_variant(self, mock_client: MagicMock, tmp_path: Path):
        book = _base_book_info(cover=_THUMB_COVER)
        mock_client.get.side_effect = [
            ApiError("fail orig"),
            _make_response(status_code=_HTTP_OK, body=b"second"),
        ]

        cover_name = await fetch_default_cover(mock_client, book, tmp_path)
        assert cover_name == "default_cover.jpeg"
        assert (tmp_path / "default_cover.jpeg").read_bytes() == b"second"

    async def test_all_variants_fail_returns_none(self, mock_client: MagicMock, tmp_path: Path):
        book = _base_book_info(cover=_THUMB_COVER)
        mock_client.get.return_value = _make_response(status_code=_HTTP_SERVER_ERROR)

        cover_name = await fetch_default_cover(mock_client, book, tmp_path)
        assert cover_name is None
        assert list(tmp_path.iterdir()) == []

    async def test_all_variants_raise_returns_none(self, mock_client: MagicMock, tmp_path: Path):
        book = _base_book_info(cover=_THUMB_COVER)
        mock_client.get.side_effect = ApiError("always fails")

        cover_name = await fetch_default_cover(mock_client, book, tmp_path)
        assert cover_name is None


class TestNullFieldCoalescing:
    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            # Explicit JSON nulls must not crash BookInfo construction;
            # required string fields coalesce to safe defaults.
            (
                {
                    "title": "ok",
                    "identifier": None,
                    "isbn": None,
                    "description": None,
                    "web_url": None,
                    "rights": None,
                },
                {
                    "isbn": "",
                    "rights": "",
                    "description": "",
                    "identifier": BOOK_ID,
                },
            ),
            # Present string fields are passed through verbatim.
            (
                {"title": "ok", "isbn": "123", "rights": "r"},
                {"isbn": "123", "rights": "r"},
            ),
        ],
    )
    async def test_field_coalescing(
        self,
        mock_client: MagicMock,
        payload: dict[str, object],
        expected: dict[str, str],
    ):
        mock_client.get_json.return_value = payload

        book = await fetch_book_info(mock_client, BOOK_ID)
        for attribute, expected_value in expected.items():
            assert getattr(book, attribute) == expected_value
        # Defaulted web_url always reflects the requested book id.
        assert book.web_url.endswith(f"/{BOOK_ID}/")
