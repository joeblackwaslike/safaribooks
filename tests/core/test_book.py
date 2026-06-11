"""Tests for safaribooks.core.book — normalize_chapter and helpers."""


from safaribooks.core.book import normalize_chapter
from safaribooks.core.constants import FILES_API_TEMPLATE

BOOK_ID = "9781234567890"


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
