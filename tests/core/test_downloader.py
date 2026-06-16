"""Tests for safaribooks.core.downloader — orchestration, chapter loop, and helpers."""
# ruff: noqa: SLF001

from unittest.mock import AsyncMock, MagicMock

import pytest

from safaribooks.core.config import AppConfig
from safaribooks.core.downloader import (
    BookDownloader,
    extract_book_id,
    fetch_playlist_book_ids,
)
from safaribooks.core.epub import build_epub, ensure_book_dirs
from safaribooks.core.exceptions import ApiError
from safaribooks.core.models import (
    Author,
    BookInfo,
    Chapter,
    ParseResult,
    Publisher,
    Stylesheet,
    Subject,
)

BOOK_ID = "9781234567890"


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _make_book_info(*, title: str = "Test Book", cover: str | None = None) -> BookInfo:
    return BookInfo(
        title=title,
        identifier=BOOK_ID,
        isbn=BOOK_ID,
        description="desc",
        web_url="https://learning.oreilly.com/library/view/test/",
        rights="all rights",
        cover=cover,
        authors=[Author(name="Jane Doe")],
        publishers=[Publisher(name="O'Reilly")],
        subjects=[Subject(name="Python")],
    )


def _make_chapter(
    *,
    filename: str = "ch01.html",
    title: str = "Chapter 1",
    images: list[str] | None = None,
    stylesheets: list[str] | None = None,
    site_styles: list[str] | None = None,
) -> Chapter:
    return Chapter(
        filename=filename,
        title=title,
        content_url=f"https://example.com/{filename}",
        asset_base_url="https://example.com/files",
        images=images or [],
        stylesheets=[Stylesheet(url=u) for u in (stylesheets or [])],
        site_styles=site_styles or [],
    )


def _make_parse_result(
    *,
    page_css: str = "",
    body_xhtml: str = "<p>body</p>",
    discovered_css: list[str] | None = None,
    discovered_videos: list[str] | None = None,
    cover_src: str | None = None,
) -> ParseResult:
    return ParseResult(
        page_css=page_css,
        body_xhtml=body_xhtml,
        discovered_css=discovered_css or [],
        discovered_images=[],
        discovered_videos=discovered_videos or [],
        cover_src=cover_src,
    )


@pytest.fixture
def config(tmp_path) -> AppConfig:
    return AppConfig(
        cookies_file=tmp_path / "cookies.json",
        output_dir=tmp_path / "Books",
        library_dir=tmp_path / "library",
    )


def _patch_pipeline(
    monkeypatch,
    *,
    book_info: BookInfo,
    chapters: list[Chapter],
    parse_results: list[ParseResult] | None = None,
    fetch_default_cover_return: str | None = None,
    download_fonts_return: list[str] | None = None,
):
    """Patch all module-level dependencies of downloader.run().

    Returns a dict of the installed mocks for assertions.
    """
    import safaribooks.core.downloader as dl

    mocks: dict = {}

    # --- ApiClient async context manager ---
    client = MagicMock(name="ApiClient")
    client.check_login = AsyncMock(return_value=True)
    client.start_keepalive = AsyncMock()
    client.stop_keepalive = AsyncMock()
    client.save_cookies = MagicMock()
    client.get_json = AsyncMock(return_value={})

    api_ctx = MagicMock(name="ApiClientCtx")
    api_ctx.__aenter__ = AsyncMock(return_value=client)
    api_ctx.__aexit__ = AsyncMock(return_value=False)
    api_factory = MagicMock(return_value=api_ctx)
    monkeypatch.setattr(dl, "ApiClient", api_factory)
    mocks["client"] = client
    mocks["api_factory"] = api_factory

    monkeypatch.setattr(dl, "fetch_book_info", AsyncMock(return_value=book_info))
    monkeypatch.setattr(dl, "enrich_book_metadata", AsyncMock(return_value=book_info))
    monkeypatch.setattr(dl, "fetch_chapters", AsyncMock(return_value=chapters))

    fetch_cover_mock = AsyncMock(return_value=fetch_default_cover_return)
    monkeypatch.setattr(dl, "fetch_default_cover", fetch_cover_mock)
    mocks["fetch_default_cover"] = fetch_cover_mock

    # Chapter fetch/parse
    monkeypatch.setattr(dl, "fetch_chapter_html", AsyncMock(return_value="<root/>"))
    results = list(parse_results or [])

    def _parse(*args, **kwargs):
        return results.pop(0) if results else _make_parse_result()

    monkeypatch.setattr(dl, "parse_chapter_html", MagicMock(side_effect=_parse))
    monkeypatch.setattr(dl, "write_chapter_html", MagicMock())

    # Asset downloads
    monkeypatch.setattr(dl, "download_css", AsyncMock())
    monkeypatch.setattr(
        dl, "download_fonts", AsyncMock(return_value=download_fonts_return or [])
    )
    download_images_mock = AsyncMock()
    monkeypatch.setattr(dl, "download_images", download_images_mock)
    mocks["download_images"] = download_images_mock
    download_videos_mock = AsyncMock()
    monkeypatch.setattr(dl, "download_videos", download_videos_mock)
    mocks["download_videos"] = download_videos_mock

    # EPUB rendering — real epub build so a real file is produced
    monkeypatch.setattr(dl, "render_content_opf", MagicMock(return_value="<opf/>"))
    monkeypatch.setattr(dl, "render_toc_ncx", AsyncMock(return_value="<ncx/>"))

    return mocks


# ---------------------------------------------------------------------------
# extract_book_id
# ---------------------------------------------------------------------------


class TestExtractBookId:
    def test_full_url(self):
        url = "https://learning.oreilly.com/library/view/x/9781234567890/"
        assert extract_book_id(url) == "9781234567890"

    def test_urn(self):
        assert extract_book_id("urn:orm:book:9781234567890") == "9781234567890"

    def test_bare_decimal(self):
        assert extract_book_id("9781234567890") == "9781234567890"

    def test_prefixed_id_extracted(self):
        # A trailing decimal id on a non-decimal string is extracted via
        # re.search against the $-anchored pattern.
        assert extract_book_id("book-9781234567890") == "9781234567890"

    def test_unparseable_returns_none(self):
        assert extract_book_id("not-a-book-id") is None

    def test_empty_string_returns_none(self):
        assert extract_book_id("") is None


# ---------------------------------------------------------------------------
# fetch_playlist_book_ids
# ---------------------------------------------------------------------------


class TestFetchPlaylistBookIds:
    async def test_match_by_uuid_extracts_book_ids(self):
        client = MagicMock()
        client.get_json = AsyncMock(
            return_value={
                "results": [
                    {
                        "uuid": "pl-1",
                        "slug": "my-list",
                        "content": [
                            {"ourn": "urn:orm:book:9781234567890"},
                            {"identifier": "urn:orm:book:1112223334445"},
                            {"ourn": "not-a-book"},
                        ],
                    }
                ]
            }
        )
        ids = await fetch_playlist_book_ids(client, "pl-1")
        assert ids == ["9781234567890", "1112223334445"]

    async def test_skips_non_matching_playlists_before_match(self):
        # First entry does not match -> loop continues to the matching one.
        client = MagicMock()
        client.get_json = AsyncMock(
            return_value={
                "results": [
                    {"uuid": "other", "slug": "nope", "content": []},
                    {
                        "uuid": "pl-1",
                        "content": [{"ourn": "urn:orm:book:5556667778"}],
                    },
                ]
            }
        )
        ids = await fetch_playlist_book_ids(client, "pl-1")
        assert ids == ["5556667778"]

    async def test_match_by_slug(self):
        client = MagicMock()
        client.get_json = AsyncMock(
            return_value={
                "results": [
                    {"uuid": "pl-1", "slug": "my-list", "content": []},
                ]
            }
        )
        ids = await fetch_playlist_book_ids(client, "my-list")
        assert ids == []

    async def test_top_level_list_response(self):
        client = MagicMock()
        client.get_json = AsyncMock(
            return_value=[
                {
                    "uuid": "pl-9",
                    "content": [{"ourn": "urn:orm:book:9999999999"}],
                }
            ]
        )
        ids = await fetch_playlist_book_ids(client, "pl-9")
        assert ids == ["9999999999"]

    async def test_playlist_not_found_raises(self):
        client = MagicMock()
        client.get_json = AsyncMock(return_value={"results": []})
        with pytest.raises(ApiError, match="not found"):
            await fetch_playlist_book_ids(client, "missing")

    async def test_api_error_propagates(self):
        client = MagicMock()
        client.get_json = AsyncMock(side_effect=ApiError("boom"))
        with pytest.raises(ApiError, match="boom"):
            await fetch_playlist_book_ids(client, "pl-1")


# ---------------------------------------------------------------------------
# progress helpers
# ---------------------------------------------------------------------------


class TestProgressHelpers:
    def test_notify_progress_invokes_callback(self, config):
        cb = MagicMock()
        d = BookDownloader(config, BOOK_ID, progress_callback=cb)
        d._notify_progress("chapters", 1, 5)
        cb.assert_called_once_with("chapters", 1, 5)

    def test_notify_progress_no_callback_is_noop(self, config):
        d = BookDownloader(config, BOOK_ID)
        # Should not raise.
        d._notify_progress("chapters", 1, 5)

    def test_make_asset_callback_none_without_callback(self, config):
        d = BookDownloader(config, BOOK_ID)
        assert d._make_asset_callback("css") is None

    def test_make_asset_callback_bridges_arg_order(self, config):
        cb = MagicMock()
        d = BookDownloader(config, BOOK_ID, progress_callback=cb)
        bridge = d._make_asset_callback("images")
        assert bridge is not None
        # Asset callbacks are (total, completed); public API is (stage, current, total).
        bridge(10, 3)
        cb.assert_called_once_with("images", 3, 10)


# ---------------------------------------------------------------------------
# _process_chapters
# ---------------------------------------------------------------------------


class TestProcessChapters:
    async def test_collects_assets_and_writes(self, config, monkeypatch, tmp_path):
        import safaribooks.core.downloader as dl

        chapters = [
            _make_chapter(
                filename="ch01.html",
                images=["img/local.png", "https://cdn.example.com/abs.png"],
                stylesheets=["s/main.css"],
                site_styles=["s/site.css"],
            ),
            _make_chapter(filename="ch02.html", images=["img/two.png"]),
        ]
        results = [
            _make_parse_result(
                discovered_css=["https://cdn/a.css"],
                discovered_videos=["v/clip.mp4"],
                cover_src="Images/cover.png",
            ),
            _make_parse_result(
                discovered_css=["https://cdn/a.css", "https://cdn/b.css"],
                discovered_videos=["v/clip.mp4", "v/two.mp4"],
                cover_src="Images/other.png",
            ),
        ]
        monkeypatch.setattr(dl, "fetch_chapter_html", AsyncMock(return_value="<r/>"))
        it = iter(results)
        monkeypatch.setattr(
            dl, "parse_chapter_html", MagicMock(side_effect=lambda *a, **k: next(it))
        )
        write_mock = MagicMock()
        monkeypatch.setattr(dl, "write_chapter_html", write_mock)

        cb = MagicMock()
        d = BookDownloader(config, BOOK_ID, progress_callback=cb)
        book_paths = ensure_book_dirs(tmp_path / "build")

        all_css, all_images, all_videos, cover_src = await d._process_chapters(
            dl.ApiClient if False else MagicMock(),  # client unused (parse mocked)
            chapters,
            book_paths,
        )

        # absolute image kept as-is; relative prefixed with asset_base_url
        assert "img/local.png" not in all_images
        assert "https://example.com/files/img/local.png" in all_images
        assert "https://cdn.example.com/abs.png" in all_images
        # dedup of css and videos
        assert all_css == ["https://cdn/a.css", "https://cdn/b.css"]
        assert all_videos == ["v/clip.mp4", "v/two.mp4"]
        # first non-None cover_src wins
        assert cover_src == "Images/cover.png"
        assert write_mock.call_count == 2
        # progress fired per chapter
        assert cb.call_count == 2

    async def test_resume_skips_existing_xhtml(self, config, monkeypatch, tmp_path):
        import safaribooks.core.downloader as dl

        chapters = [_make_chapter(filename="ch01.html")]
        fetch_mock = AsyncMock(return_value="<r/>")
        monkeypatch.setattr(dl, "fetch_chapter_html", fetch_mock)
        monkeypatch.setattr(dl, "parse_chapter_html", MagicMock())
        monkeypatch.setattr(dl, "write_chapter_html", MagicMock())

        d = BookDownloader(config, BOOK_ID)
        book_paths = ensure_book_dirs(tmp_path / "build")
        # Pre-create the destination xhtml so the chapter is skipped.
        (book_paths.oebps / "ch01.xhtml").write_text("existing", encoding="utf-8")

        all_css, all_images, all_videos, cover_src = await d._process_chapters(
            MagicMock(), chapters, book_paths
        )

        fetch_mock.assert_not_called()
        assert all_css == []
        assert cover_src is None

    async def test_empty_chapters_returns_empty(self, config, tmp_path):
        d = BookDownloader(config, BOOK_ID)
        book_paths = ensure_book_dirs(tmp_path / "build")
        result = await d._process_chapters(MagicMock(), [], book_paths)
        assert result == ([], [], [], None)


# ---------------------------------------------------------------------------
# run() — full orchestration
# ---------------------------------------------------------------------------


class TestRun:
    async def test_happy_path_returns_epub_and_copies_to_library(
        self, config, monkeypatch
    ):
        book_info = _make_book_info(title="My Book", cover="https://c/cover.jpg")
        chapters = [_make_chapter(filename="ch01.html")]
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=book_info,
            chapters=chapters,
            parse_results=[_make_parse_result(cover_src="Images/cover.png")],
        )

        cb = MagicMock()
        d = BookDownloader(config, BOOK_ID, progress_callback=cb)
        epub_path = await d.run()

        assert epub_path.suffix == ".epub"
        assert epub_path.exists()
        # Copied to library/epubs
        copied = config.library_dir / "epubs" / epub_path.name
        assert copied.exists()
        # auth + keepalive lifecycle
        mocks["client"].check_login.assert_awaited_once()
        mocks["client"].start_keepalive.assert_awaited_once()
        mocks["client"].stop_keepalive.assert_awaited_once()
        mocks["client"].save_cookies.assert_called_once()
        # epub progress notified
        cb.assert_any_call("epub", 0, 1)
        cb.assert_any_call("epub", 1, 1)

    async def test_default_cover_fetched_when_no_cover_src(self, config, monkeypatch):
        book_info = _make_book_info(cover="https://c/cover.jpg")
        chapters = [_make_chapter(filename="ch01.html", title="Chapter 1")]
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=book_info,
            chapters=chapters,
            parse_results=[_make_parse_result(cover_src=None)],
            fetch_default_cover_return="cover.jpg",
        )
        d = BookDownloader(config, BOOK_ID)
        await d.run()
        mocks["fetch_default_cover"].assert_awaited_once()

    async def test_default_cover_skipped_when_cover_chapter_exists(
        self, config, monkeypatch
    ):
        book_info = _make_book_info(cover="https://c/cover.jpg")
        # A chapter whose title contains "cover" suppresses the default cover fetch.
        chapters = [_make_chapter(filename="ch01.html", title="Cover Page")]
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=book_info,
            chapters=chapters,
            parse_results=[_make_parse_result(cover_src=None)],
        )
        d = BookDownloader(config, BOOK_ID)
        await d.run()
        mocks["fetch_default_cover"].assert_not_awaited()

    async def test_default_cover_skipped_when_book_has_no_cover(
        self, config, monkeypatch
    ):
        book_info = _make_book_info(cover=None)
        chapters = [_make_chapter(filename="ch01.html", title="Chapter 1")]
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=book_info,
            chapters=chapters,
            parse_results=[_make_parse_result(cover_src=None)],
        )
        d = BookDownloader(config, BOOK_ID)
        await d.run()
        mocks["fetch_default_cover"].assert_not_awaited()

    async def test_default_cover_fetch_returns_none(self, config, monkeypatch):
        # fetch_default_cover returns None -> cover_src stays None, no crash.
        book_info = _make_book_info(cover="https://c/cover.jpg")
        chapters = [_make_chapter(filename="ch01.html", title="Chapter 1")]
        _patch_pipeline(
            monkeypatch,
            book_info=book_info,
            chapters=chapters,
            parse_results=[_make_parse_result(cover_src=None)],
            fetch_default_cover_return=None,
        )
        d = BookDownloader(config, BOOK_ID)
        epub_path = await d.run()
        assert epub_path.exists()

    async def test_videos_downloaded_when_present(self, config, monkeypatch):
        book_info = _make_book_info()
        chapters = [_make_chapter(filename="ch01.html")]
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=book_info,
            chapters=chapters,
            parse_results=[_make_parse_result(discovered_videos=["v/clip.mp4"])],
        )
        d = BookDownloader(config, BOOK_ID)
        await d.run()
        mocks["download_videos"].assert_awaited_once()

    async def test_videos_not_downloaded_when_absent(self, config, monkeypatch):
        book_info = _make_book_info()
        chapters = [_make_chapter(filename="ch01.html")]
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=book_info,
            chapters=chapters,
            parse_results=[_make_parse_result(discovered_videos=[])],
        )
        d = BookDownloader(config, BOOK_ID)
        await d.run()
        mocks["download_videos"].assert_not_awaited()

    async def test_writes_opf_and_ncx_files(self, config, monkeypatch):
        book_info = _make_book_info()
        chapters = [_make_chapter(filename="ch01.html")]
        # Verify the build dir actually receives content.opf / toc.ncx by
        # intercepting build_epub and inspecting book_paths.
        import safaribooks.core.downloader as dl

        _patch_pipeline(monkeypatch, book_info=book_info, chapters=chapters)

        captured: dict = {}
        real_build = build_epub

        def _spy_build(book_paths, out):
            captured["opf"] = (book_paths.oebps / "content.opf").read_bytes()
            captured["ncx"] = (book_paths.oebps / "toc.ncx").read_bytes()
            return real_build(book_paths, out)

        monkeypatch.setattr(dl, "build_epub", _spy_build)

        d = BookDownloader(config, BOOK_ID)
        await d.run()
        assert captured["opf"] == b"<opf/>"
        assert captured["ncx"] == b"<ncx/>"
