"""Tests for safaribooks.core.book — normalize_chapter and helpers."""

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
    status_code: int = 200,
    content: bytes = b"binary-cover-data",
    content_type: str = "image/jpeg",
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        headers={"Content-Type": content_type},
        content=content,
    )


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
        result = normalize_chapter(raw, BOOK_ID)
        assert result.filename == "ch01.xhtml"
        assert result.title == "Chapter 1"
        assert result.images == ["img/fig1.png", "img/fig2.png"]
        assert len(result.stylesheets) == 1
        assert result.stylesheets[0].url == "style/main.css"
        assert result.site_styles == ["style/site.css"]
        assert "/files" in result.asset_base_url

    def test_empty_images_list(self):
        raw = {
            "filename": "ch02.xhtml",
            "content_url": "http://example.com/ch02",
            "images": [],
            "stylesheets": [],
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.images == []


class TestNormalizeChapterRelatedAssetsFallback:
    def test_images_from_related_assets(self):
        raw = {
            "filename": "ch03.xhtml",
            "content_url": "http://example.com/ch03",
            "related_assets": {
                "images": ["img/a.png", "img/b.jpg"],
                "stylesheets": ["css/style.css"],
                "site_styles": ["css/site.css"],
            },
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.images == ["img/a.png", "img/b.jpg"]
        assert len(result.stylesheets) == 1
        assert result.stylesheets[0].url == "css/style.css"
        assert result.site_styles == ["css/site.css"]

    def test_top_level_images_take_precedence(self):
        raw = {
            "filename": "ch04.xhtml",
            "content_url": "http://example.com/ch04",
            "images": ["top.png"],
            "related_assets": {
                "images": ["fallback.png"],
            },
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.images == ["top.png"]


class TestNormalizeChapterImageURLStripping:
    def test_full_urls_stripped_to_relative(self):
        raw = {
            "filename": "ch05.xhtml",
            "content_url": "http://example.com/ch05",
            "images": [
                "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:123/files/img/fig.png",
                "img/local.png",
            ],
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.images == ["img/fig.png", "img/local.png"]


class TestNormalizeChapterFilenameFallbacks:
    def test_filename_from_ourn(self):
        raw = {
            "ourn": "urn:orm:book:123:ch07.html",
            "content_url": "http://example.com/ch07",
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.filename == "ch07.html"

    def test_filename_from_reference_id(self):
        raw = {
            "reference_id": "path/to/chapter9.html",
            "content_url": "http://example.com/ch09",
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.filename == "chapter9.html"

    def test_missing_filename_generates_hash(self):
        raw = {
            "content_url": "http://example.com/some-chapter",
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.filename.startswith("chapter_")
        assert result.filename.endswith(".html")

    def test_encoded_filename_is_decoded(self):
        raw = {
            "filename": "ch%2010.xhtml",
            "content_url": "http://example.com/ch10",
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.filename == "ch 10.xhtml"


class TestNormalizeChapterStylesheetWrapping:
    def test_string_stylesheets_wrapped_in_model(self):
        raw = {
            "filename": "ch06.xhtml",
            "content_url": "http://example.com/ch06",
            "stylesheets": ["style.css", "extra.css"],
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert len(result.stylesheets) == 2
        assert result.stylesheets[0].url == "style.css"
        assert result.stylesheets[1].url == "extra.css"

    def test_dict_stylesheets_passed_through(self):
        raw = {
            "filename": "ch06b.xhtml",
            "content_url": "http://example.com/ch06b",
            "stylesheets": [{"url": "style.css"}],
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.stylesheets[0].url == "style.css"


class TestNormalizeChapterAssetBaseUrl:
    def test_asset_base_url_uses_files_api_template(self):
        raw = {
            "filename": "ch01.xhtml",
            "content_url": "http://example.com/ch01",
        }
        result = normalize_chapter(raw, BOOK_ID)
        expected = FILES_API_TEMPLATE.format(BOOK_ID)
        assert result.asset_base_url == expected

    def test_content_url_fallback_to_content_field(self):
        raw = {
            "filename": "ch01.xhtml",
            "content": "http://example.com/ch01-via-content",
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.content_url == "http://example.com/ch01-via-content"

    def test_missing_title_defaults_to_empty(self):
        raw = {
            "filename": "ch01.xhtml",
            "content_url": "http://example.com/ch01",
        }
        result = normalize_chapter(raw, BOOK_ID)
        assert result.title == ""


class TestFetchBookInfo:
    async def test_basic_metadata(self, mock_client: MagicMock):
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

        info = await fetch_book_info(mock_client, BOOK_ID)

        assert isinstance(info, BookInfo)
        assert info.title == "Real Book"
        assert info.isbn == "9990000000001"
        assert info.description == "A description"
        assert info.cover == "https://example.com/cover.jpg"
        assert info.issued == "2024-01-01"
        # Correct v2 API URL was requested.
        url = mock_client.get_json.call_args[0][0]
        assert url == f"{SAFARI_BASE_URL}/api/v2/epubs/urn:orm:book:{BOOK_ID}/"

    async def test_descriptions_plaintext_preferred(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "title": "Book",
            "description": "fallback",
            "descriptions": {
                "text/plain": "plain text desc",
                "text/html": "<p>html desc</p>",
            },
        }

        info = await fetch_book_info(mock_client, BOOK_ID)
        assert info.description == "plain text desc"

    async def test_descriptions_html_when_no_plaintext(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "title": "Book",
            "description": "fallback",
            "descriptions": {"text/html": "<p>html desc</p>"},
        }

        info = await fetch_book_info(mock_client, BOOK_ID)
        assert info.description == "<p>html desc</p>"

    async def test_defaults_when_fields_absent(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {"title": "Bare Book"}

        info = await fetch_book_info(mock_client, BOOK_ID)
        assert info.identifier == BOOK_ID
        assert info.isbn == ""
        assert info.description == ""
        assert info.web_url == f"{SAFARI_BASE_URL}/library/view/-/{BOOK_ID}/"
        assert info.cover is None

    async def test_cover_falls_back_to_cover_field(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "title": "Book",
            "cover": "https://example.com/legacy-cover.jpg",
        }

        info = await fetch_book_info(mock_client, BOOK_ID)
        assert info.cover == "https://example.com/legacy-cover.jpg"

    async def test_missing_title_key_raises_api_error(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {"identifier": BOOK_ID}

        with pytest.raises(ApiError, match="unexpected data"):
            await fetch_book_info(mock_client, BOOK_ID)

    async def test_non_dict_response_raises_api_error(self, mock_client: MagicMock):
        mock_client.get_json.return_value = ["not", "a", "dict"]

        with pytest.raises(ApiError, match="unexpected data"):
            await fetch_book_info(mock_client, BOOK_ID)


class TestEnrichBookMetadata:
    async def test_enriches_all_fields(self, mock_client: MagicMock):
        info = _base_book_info(web_url="")
        mock_client.get_json.return_value = {
            "results": [
                {
                    "isbn": BOOK_ID,
                    "authors": ["Jane Doe", "John Smith"],
                    "publishers": "No Starch Press",
                    "issued": "2023-05-05",
                    "subjects": ["Python", "Testing"],
                    "cover_url": "https://example.com/c.jpg",
                    "web_url": "https://example.com/web",
                }
            ]
        }

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)

        assert [a.name for a in result.authors] == ["Jane Doe", "John Smith"]
        assert result.publishers == [Publisher(name="No Starch Press")]
        assert result.issued == "2023-05-05"
        assert [s.name for s in result.subjects] == ["Python", "Testing"]
        assert result.cover == "https://example.com/c.jpg"
        assert result.web_url == "https://example.com/web"

    async def test_publishers_list_of_strings(self, mock_client: MagicMock):
        info = _base_book_info()
        mock_client.get_json.return_value = {
            "results": [{"isbn": BOOK_ID, "publishers": ["Pub A", "Pub B"]}]
        }

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert result.publishers == [Publisher(name="Pub A"), Publisher(name="Pub B")]

    async def test_publishers_list_of_dicts(self, mock_client: MagicMock):
        info = _base_book_info()
        mock_client.get_json.return_value = {
            "results": [{"isbn": BOOK_ID, "publishers": [{"name": "Pub Dict"}]}]
        }

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert result.publishers == [Publisher(name="Pub Dict")]

    async def test_publishers_unrecognized_type_skipped(self, mock_client: MagicMock):
        info = _base_book_info()
        # publishers present but neither str nor list -> no update applied.
        mock_client.get_json.return_value = {
            "results": [{"isbn": BOOK_ID, "publishers": {"name": "ignored-dict"}}]
        }

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert result.publishers == []

    async def test_issued_falls_back_to_date_added(self, mock_client: MagicMock):
        info = _base_book_info()
        mock_client.get_json.return_value = {
            "results": [{"isbn": BOOK_ID, "date_added": "2020-02-02"}]
        }

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert result.issued == "2020-02-02"

    async def test_cover_not_overwritten_when_already_set(self, mock_client: MagicMock):
        info = _base_book_info(cover="https://existing.com/cover.jpg")
        mock_client.get_json.return_value = {
            "results": [{"isbn": BOOK_ID, "cover_url": "https://new.com/cover.jpg"}]
        }

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert result.cover == "https://existing.com/cover.jpg"

    async def test_no_results_returns_unchanged(self, mock_client: MagicMock):
        info = _base_book_info()
        mock_client.get_json.return_value = {"results": []}

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert result is info

    async def test_mismatched_result_returns_unchanged(self, mock_client: MagicMock):
        info = _base_book_info()
        mock_client.get_json.return_value = {
            "results": [{"isbn": "0000000000000", "archive_id": "different", "authors": ["X"]}]
        }

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert result is info
        assert result.authors == []

    async def test_matches_via_archive_id(self, mock_client: MagicMock):
        info = _base_book_info()
        mock_client.get_json.return_value = {
            "results": [{"isbn": "0000000000000", "archive_id": BOOK_ID, "authors": ["Match"]}]
        }

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert [a.name for a in result.authors] == ["Match"]

    async def test_matches_via_identifier_fallback(self, mock_client: MagicMock):
        info = _base_book_info()
        # No isbn -> falls back to identifier field for matching.
        mock_client.get_json.return_value = {
            "results": [{"identifier": BOOK_ID, "authors": ["Ident"]}]
        }

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert [a.name for a in result.authors] == ["Ident"]

    async def test_no_updates_returns_same_info(self, mock_client: MagicMock):
        info = _base_book_info()
        # Matching result but no enrichable fields.
        mock_client.get_json.return_value = {"results": [{"isbn": BOOK_ID}]}

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert result is info

    async def test_exception_returns_original(self, mock_client: MagicMock):
        info = _base_book_info()
        mock_client.get_json.side_effect = ApiError("boom")

        result = await enrich_book_metadata(mock_client, BOOK_ID, info)
        assert result is info


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
        assert [c.filename for c in chapters] == ["ch01.xhtml", "ch02.xhtml"]

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
        assert {c.filename for c in chapters} == {"ch01.xhtml", "ch02.xhtml"}
        assert mock_client.get_json.call_count == 2

    async def test_empty_page_after_content_breaks(self, mock_client: MagicMock):
        page1 = {
            "results": [{"filename": "ch01.xhtml", "title": "One", "content_url": "u1"}],
            "next": "https://next.page/",
        }
        page2 = {"results": [], "next": None}
        mock_client.get_json.side_effect = [page1, page2]

        chapters = await fetch_chapters(mock_client, BOOK_ID)
        assert [c.filename for c in chapters] == ["ch01.xhtml"]

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
        assert [c.filename for c in chapters[1:]] == ["ch01.xhtml", "ch02.xhtml"]

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
    async def test_no_cover_url_returns_none(self, mock_client: MagicMock, tmp_path):
        info = _base_book_info(cover=None)

        result = await fetch_default_cover(mock_client, info, tmp_path)
        assert result is None
        mock_client.get.assert_not_called()

    async def test_downloads_first_successful_variant(self, mock_client: MagicMock, tmp_path):
        info = _base_book_info(cover="https://img.com/thumb/x.jpg")
        mock_client.get.return_value = _make_response(content=b"jpegbytes")

        result = await fetch_default_cover(mock_client, info, tmp_path)
        assert result == "default_cover.jpeg"
        saved = tmp_path / "default_cover.jpeg"
        assert saved.read_bytes() == b"jpegbytes"
        # First attempt is the /orig/ variant.
        first_url = mock_client.get.call_args_list[0][0][0]
        assert "/orig/" in first_url

    async def test_content_type_determines_extension(self, mock_client: MagicMock, tmp_path):
        info = _base_book_info(cover="https://img.com/cover.png")
        mock_client.get.return_value = _make_response(content_type="image/png")

        result = await fetch_default_cover(mock_client, info, tmp_path)
        assert result == "default_cover.png"

    async def test_falls_back_through_variants_on_non_200(
        self, mock_client: MagicMock, tmp_path
    ):
        info = _base_book_info(cover="https://img.com/thumb/x.jpg")
        # First three variants 404, last one (raw cover_url) succeeds.
        mock_client.get.side_effect = [
            _make_response(status_code=404),
            _make_response(status_code=404),
            _make_response(status_code=404),
            _make_response(status_code=200, content=b"ok"),
        ]

        result = await fetch_default_cover(mock_client, info, tmp_path)
        assert result == "default_cover.jpeg"
        assert (tmp_path / "default_cover.jpeg").read_bytes() == b"ok"

    async def test_api_error_skips_to_next_variant(self, mock_client: MagicMock, tmp_path):
        info = _base_book_info(cover="https://img.com/thumb/x.jpg")
        mock_client.get.side_effect = [
            ApiError("fail orig"),
            _make_response(status_code=200, content=b"second"),
        ]

        result = await fetch_default_cover(mock_client, info, tmp_path)
        assert result == "default_cover.jpeg"
        assert (tmp_path / "default_cover.jpeg").read_bytes() == b"second"

    async def test_all_variants_fail_returns_none(self, mock_client: MagicMock, tmp_path):
        info = _base_book_info(cover="https://img.com/thumb/x.jpg")
        mock_client.get.return_value = _make_response(status_code=500)

        result = await fetch_default_cover(mock_client, info, tmp_path)
        assert result is None
        assert list(tmp_path.iterdir()) == []

    async def test_all_variants_raise_returns_none(self, mock_client: MagicMock, tmp_path):
        info = _base_book_info(cover="https://img.com/thumb/x.jpg")
        mock_client.get.side_effect = ApiError("always fails")

        result = await fetch_default_cover(mock_client, info, tmp_path)
        assert result is None


class TestNullFieldCoalescing:
    async def test_explicit_null_fields_coalesce_to_defaults(self, mock_client: MagicMock):
        # An API response with explicit JSON nulls must not crash BookInfo
        # construction; required string fields coalesce to safe defaults.
        mock_client.get_json.return_value = {
            "title": "ok",
            "identifier": None,
            "isbn": None,
            "description": None,
            "web_url": None,
            "rights": None,
        }

        info = await fetch_book_info(mock_client, BOOK_ID)
        assert info.isbn == ""
        assert info.rights == ""
        assert info.description == ""
        assert info.identifier == BOOK_ID
        assert info.web_url.endswith(f"/{BOOK_ID}/")

    async def test_present_fields_preserved(self, mock_client: MagicMock):
        mock_client.get_json.return_value = {
            "title": "ok",
            "isbn": "123",
            "rights": "r",
        }

        info = await fetch_book_info(mock_client, BOOK_ID)
        assert info.isbn == "123"
        assert info.rights == "r"
