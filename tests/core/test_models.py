"""Tests for safaribooks.core.models."""


import pytest
from pydantic import ValidationError

from safaribooks.core.models import (
    Author,
    BookInfo,
    Chapter,
    CookieSet,
    ParseResult,
    Publisher,
    SearchResponse,
    SearchResult,
    Stylesheet,
    Subject,
    TocEntry,
)


class TestBookInfo:
    def test_creation_with_valid_data(self):
        info = BookInfo(
            title="Python Cookbook",
            identifier="9781234567890",
            isbn="9781234567890",
            description="A book about Python",
            web_url="https://learning.oreilly.com/library/view/-/9781234567890/",
            rights="Copyright 2024",
            cover="https://example.com/cover.jpg",
            authors=[Author(name="Guido van Rossum")],
            publishers=[Publisher(name="O'Reilly")],
            subjects=[Subject(name="Python"), Subject(name="Programming")],
            issued="2024-01-01",
        )
        assert info.title == "Python Cookbook"
        assert info.isbn == "9781234567890"
        assert len(info.authors) == 1
        assert info.authors[0].name == "Guido van Rossum"
        assert len(info.subjects) == 2

    def test_creation_with_optional_defaults(self):
        info = BookInfo(
            title="Minimal Book",
            identifier="123",
            isbn="123",
            description="",
            web_url="https://example.com",
            rights="",
            authors=[],
            publishers=[],
            subjects=[],
        )
        assert info.cover is None
        assert info.issued is None
        assert info.authors == []


class TestChapter:
    def test_creation_with_stylesheets(self):
        ch = Chapter(
            filename="ch01.xhtml",
            title="Chapter 1",
            content_url="https://example.com/ch01",
            asset_base_url="https://example.com/files",
            images=["img/fig1.png"],
            stylesheets=[Stylesheet(url="style.css")],
            site_styles=["site.css"],
        )
        assert ch.filename == "ch01.xhtml"
        assert ch.stylesheets[0].url == "style.css"
        assert ch.site_styles == ["site.css"]

    def test_creation_with_empty_assets(self):
        ch = Chapter(
            filename="ch02.xhtml",
            title="Chapter 2",
            content_url="https://example.com/ch02",
            asset_base_url="https://example.com/files",
            images=[],
            stylesheets=[],
            site_styles=[],
        )
        assert ch.images == []
        assert ch.stylesheets == []


class TestTocEntry:
    def test_creation_without_children(self):
        entry = TocEntry(
            depth=0,
            fragment="intro",
            id="toc_0_0",
            label="Introduction",
            href="intro.html#intro",
        )
        assert entry.depth == 0
        assert entry.fragment == "intro"
        assert entry.children == []

    def test_nested_children(self):
        child = TocEntry(
            depth=1,
            fragment="section1",
            id="toc_1_0",
            label="Section 1",
            href="ch01.html#section1",
        )
        parent = TocEntry(
            depth=0,
            fragment="",
            id="toc_0_0",
            label="Chapter 1",
            href="ch01.html",
            children=[child],
        )
        assert len(parent.children) == 1
        assert parent.children[0].label == "Section 1"
        assert parent.children[0].depth == 1

    def test_deeply_nested_children(self):
        grandchild = TocEntry(
            depth=2, fragment="sub", id="gc", label="Subsection", href="ch.html#sub"
        )
        child = TocEntry(
            depth=1,
            fragment="sec",
            id="c",
            label="Section",
            href="ch.html#sec",
            children=[grandchild],
        )
        parent = TocEntry(
            depth=0,
            fragment="",
            id="p",
            label="Chapter",
            href="ch.html",
            children=[child],
        )
        assert parent.children[0].children[0].label == "Subsection"


class TestCookieSet:
    def test_valid_cookies_pass(self):
        cookies = {
            "groot_sessionid": "abc123",
            "jwt": "token.value.here",
            "csrf_access_token": "csrf_tok",
            "logged_in": "1",
        }
        cs = CookieSet(cookies=cookies)
        assert cs.cookies["jwt"] == "token.value.here"

    def test_extra_cookies_allowed(self):
        cookies = {
            "groot_sessionid": "abc",
            "jwt": "tok",
            "csrf_access_token": "csrf",
            "logged_in": "1",
            "extra_cookie": "val",
        }
        cs = CookieSet(cookies=cookies)
        assert "extra_cookie" in cs.cookies

    def test_missing_required_cookies_raises(self):
        with pytest.raises(ValidationError, match="Missing required cookies"):
            CookieSet(cookies={"jwt": "tok"})

    def test_empty_cookies_raises(self):
        with pytest.raises(ValidationError, match="Missing required cookies"):
            CookieSet(cookies={})


class TestSearchResult:
    def test_book_id_prefers_archive_id(self):
        r = SearchResult(title="Test", archive_id="12345", isbn="67890", identifier="abc")
        assert r.book_id == "12345"

    def test_book_id_falls_back_to_isbn(self):
        r = SearchResult(title="Test", isbn="67890", identifier="abc")
        assert r.book_id == "67890"

    def test_book_id_falls_back_to_identifier(self):
        r = SearchResult(title="Test", identifier="abc")
        assert r.book_id == "abc"

    def test_book_id_empty_when_no_ids(self):
        r = SearchResult(title="Test")
        assert r.book_id == ""

    def test_creation_with_defaults(self):
        r = SearchResult(title="Minimal")
        assert r.isbn == ""
        assert r.authors == []
        assert r.publishers == ""
        assert r.issued == ""

    def test_creation_with_all_fields(self):
        r = SearchResult(
            title="Full Book",
            isbn="9781234567890",
            archive_id="9781234567890",
            identifier="urn:orm:book:9781234567890",
            authors=["Author A", "Author B"],
            publishers="O'Reilly",
            cover_url="https://example.com/cover.jpg",
            web_url="https://example.com/book",
            issued="2024-01-01",
            description="A full book",
        )
        assert r.title == "Full Book"
        assert len(r.authors) == 2


class TestSearchResponse:
    def test_creation_with_results(self):
        resp = SearchResponse(
            results=[SearchResult(title="Book 1"), SearchResult(title="Book 2")],
            count=2,
            total=10,
        )
        assert len(resp.results) == 2
        assert resp.count == 2
        assert resp.total == 10

    def test_creation_empty(self):
        resp = SearchResponse()
        assert resp.results == []
        assert resp.count == 0
        assert resp.next is None

    def test_pagination_fields(self):
        resp = SearchResponse(
            results=[],
            next="https://example.com/next",
            previous="https://example.com/prev",
        )
        assert resp.next == "https://example.com/next"
        assert resp.previous == "https://example.com/prev"


class TestParseResult:
    def test_creation(self):
        pr = ParseResult(
            page_css='<link href="Styles/Style00.css" />',
            body_xhtml="<div>Hello</div>",
            discovered_css=["https://example.com/style.css"],
            discovered_images=["img/fig.png"],
            discovered_videos=[],
            cover_src=None,
        )
        assert pr.body_xhtml == "<div>Hello</div>"
        assert pr.cover_src is None
        assert len(pr.discovered_css) == 1

    def test_creation_with_cover(self):
        pr = ParseResult(
            page_css="",
            body_xhtml="<div></div>",
            discovered_css=[],
            discovered_images=[],
            discovered_videos=[],
            cover_src="Images/cover.png",
        )
        assert pr.cover_src == "Images/cover.png"
