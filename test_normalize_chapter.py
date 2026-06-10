import unittest
from unittest.mock import MagicMock

from safaribooks import SafariBooks


def make_instance(book_id="9781234567890"):
    """Create a minimal SafariBooks instance for testing _normalize_chapter."""
    sb = object.__new__(SafariBooks)
    sb.book_id = book_id
    return sb


class TestNormalizeChapterTopLevelImages(unittest.TestCase):
    def test_basic_chapter(self):
        sb = make_instance()
        v2 = {
            "filename": "ch01.xhtml",
            "title": "Chapter 1",
            "content_url": "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:9781234567890/files/ch01.xhtml",
            "images": ["img/fig1.png", "img/fig2.png"],
            "stylesheets": ["style/main.css"],
            "site_styles": ["style/site.css"],
        }
        result = sb._normalize_chapter(v2)
        self.assertEqual(result["filename"], "ch01.xhtml")
        self.assertEqual(result["title"], "Chapter 1")
        self.assertEqual(result["images"], ["img/fig1.png", "img/fig2.png"])
        self.assertEqual(result["stylesheets"], [{"url": "style/main.css"}])
        self.assertEqual(result["site_styles"], ["style/site.css"])
        self.assertIn("/files", result["asset_base_url"])

    def test_empty_images_list(self):
        sb = make_instance()
        v2 = {
            "filename": "ch02.xhtml",
            "content_url": "http://example.com/ch02",
            "images": [],
            "stylesheets": [],
        }
        result = sb._normalize_chapter(v2)
        self.assertEqual(result["images"], [])


class TestNormalizeChapterRelatedAssetsFallback(unittest.TestCase):
    def test_images_from_related_assets(self):
        sb = make_instance()
        v2 = {
            "filename": "ch03.xhtml",
            "content_url": "http://example.com/ch03",
            "related_assets": {
                "images": ["img/a.png", "img/b.jpg"],
                "stylesheets": ["css/style.css"],
                "site_styles": ["css/site.css"],
            },
        }
        result = sb._normalize_chapter(v2)
        self.assertEqual(result["images"], ["img/a.png", "img/b.jpg"])
        self.assertEqual(result["stylesheets"], [{"url": "css/style.css"}])
        self.assertEqual(result["site_styles"], ["css/site.css"])

    def test_top_level_images_take_precedence(self):
        sb = make_instance()
        v2 = {
            "filename": "ch04.xhtml",
            "content_url": "http://example.com/ch04",
            "images": ["top.png"],
            "related_assets": {
                "images": ["fallback.png"],
            },
        }
        result = sb._normalize_chapter(v2)
        self.assertEqual(result["images"], ["top.png"])


class TestNormalizeChapterImageURLStripping(unittest.TestCase):
    def test_full_urls_stripped_to_relative(self):
        sb = make_instance()
        v2 = {
            "filename": "ch05.xhtml",
            "content_url": "http://example.com/ch05",
            "images": [
                "https://learning.oreilly.com/api/v2/epubs/urn:orm:book:123/files/img/fig.png",
                "img/local.png",
            ],
        }
        result = sb._normalize_chapter(v2)
        self.assertEqual(result["images"], ["img/fig.png", "img/local.png"])


class TestNormalizeChapterFilenameFallbacks(unittest.TestCase):
    def test_filename_from_ourn(self):
        sb = make_instance()
        v2 = {
            "ourn": "urn:orm:book:123:ch07.html",
            "content_url": "http://example.com/ch07",
        }
        result = sb._normalize_chapter(v2)
        self.assertEqual(result["filename"], "ch07.html")

    def test_filename_from_reference_id(self):
        sb = make_instance()
        v2 = {
            "reference_id": "path/to/chapter9.html",
            "content_url": "http://example.com/ch09",
        }
        result = sb._normalize_chapter(v2)
        self.assertEqual(result["filename"], "chapter9.html")

    def test_missing_filename_generates_hash(self):
        sb = make_instance()
        v2 = {
            "content_url": "http://example.com/some-chapter",
        }
        result = sb._normalize_chapter(v2)
        self.assertTrue(result["filename"].startswith("chapter_"))
        self.assertTrue(result["filename"].endswith(".html"))

    def test_encoded_filename_is_decoded(self):
        sb = make_instance()
        v2 = {
            "filename": "ch%2010.xhtml",
            "content_url": "http://example.com/ch10",
        }
        result = sb._normalize_chapter(v2)
        self.assertEqual(result["filename"], "ch 10.xhtml")


class TestNormalizeChapterStylesheetWrapping(unittest.TestCase):
    def test_string_stylesheets_wrapped_in_dict(self):
        sb = make_instance()
        v2 = {
            "filename": "ch06.xhtml",
            "content_url": "http://example.com/ch06",
            "stylesheets": ["style.css", "extra.css"],
        }
        result = sb._normalize_chapter(v2)
        self.assertEqual(result["stylesheets"], [{"url": "style.css"}, {"url": "extra.css"}])

    def test_dict_stylesheets_passed_through(self):
        sb = make_instance()
        v2 = {
            "filename": "ch06b.xhtml",
            "content_url": "http://example.com/ch06b",
            "stylesheets": [{"url": "style.css", "type": "text/css"}],
        }
        result = sb._normalize_chapter(v2)
        self.assertEqual(result["stylesheets"], [{"url": "style.css", "type": "text/css"}])


if __name__ == "__main__":
    unittest.main()
