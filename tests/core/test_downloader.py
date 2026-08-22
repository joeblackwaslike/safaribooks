"""Tests for safaribooks.core.downloader — orchestration, chapter loop, and helpers."""
# ruff: noqa: SLF001

from unittest.mock import AsyncMock, MagicMock

import pytest

from safaribooks.core import downloader as dl
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

_ROOT_HTML = "<r/>"
_OPF_BYTES = b"<opf/>"
_NCX_BYTES = b"<ncx/>"


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
        stylesheets=[Stylesheet(url=href) for href in (stylesheets or [])],
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


def _make_downloader(config: AppConfig, *, callback=None) -> BookDownloader:
    return BookDownloader(config, BOOK_ID, progress_callback=callback)


@pytest.fixture
def config(tmp_path) -> AppConfig:
    return AppConfig(
        cookies_file=tmp_path / "cookies.json",
        output_dir=tmp_path / "Books",
        library_dir=tmp_path / "library",
    )


@pytest.fixture
def downloader(config: AppConfig) -> BookDownloader:
    return _make_downloader(config)


def _make_api_client() -> MagicMock:
    client = MagicMock(name="ApiClient")
    client.check_login = AsyncMock(return_value=True)
    client.start_keepalive = AsyncMock()
    client.stop_keepalive = AsyncMock()
    client.save_cookies = MagicMock()
    client.get_json = AsyncMock(return_value={})
    return client


def _make_api_factory(client: MagicMock) -> MagicMock:
    api_ctx = MagicMock(name="ApiClientCtx")
    api_ctx.__aenter__ = AsyncMock(return_value=client)
    api_ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=api_ctx)


class _SequentialParse:
    """Side effect that returns queued parse results, then a default."""

    def __init__(self, parse_results: list[ParseResult] | None) -> None:
        self._pending = list(parse_results or [])

    def __call__(self, *args, **kwargs) -> ParseResult:
        return self._pending.pop(0) if self._pending else _make_parse_result()


def _sequential_parser(parse_results: list[ParseResult] | None) -> MagicMock:
    return MagicMock(side_effect=_SequentialParse(parse_results))


def _patch_metadata(monkeypatch, *, book_info: BookInfo, chapters: list[Chapter]):
    monkeypatch.setattr(dl, "fetch_book_info", AsyncMock(return_value=book_info))
    monkeypatch.setattr(dl, "enrich_book_metadata", AsyncMock(return_value=book_info))
    monkeypatch.setattr(dl, "fetch_chapters", AsyncMock(return_value=chapters))


def _patch_chapter_pipeline(monkeypatch, *, parse_results):
    monkeypatch.setattr(dl, "fetch_chapter_html", AsyncMock(return_value="<root/>"))
    monkeypatch.setattr(dl, "parse_chapter_html", _sequential_parser(parse_results))
    monkeypatch.setattr(dl, "write_chapter_html", MagicMock())


def _patch_asset_downloads(monkeypatch, mocks, *, download_fonts_return):
    monkeypatch.setattr(dl, "download_css", AsyncMock())
    monkeypatch.setattr(dl, "download_fonts", AsyncMock(return_value=download_fonts_return or []))
    mocks["download_images"] = AsyncMock()
    monkeypatch.setattr(dl, "download_images", mocks["download_images"])
    mocks["download_videos"] = AsyncMock()
    monkeypatch.setattr(dl, "download_videos", mocks["download_videos"])


def _patch_rendering(monkeypatch):
    monkeypatch.setattr(dl, "render_content_opf", MagicMock(return_value="<opf/>"))
    monkeypatch.setattr(dl, "render_toc_ncx", AsyncMock(return_value="<ncx/>"))


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
    mocks: dict = {}

    client = _make_api_client()
    mocks["client"] = client
    mocks["api_factory"] = _make_api_factory(client)
    monkeypatch.setattr(dl, "ApiClient", mocks["api_factory"])

    _patch_metadata(monkeypatch, book_info=book_info, chapters=chapters)

    mocks["fetch_default_cover"] = AsyncMock(return_value=fetch_default_cover_return)
    monkeypatch.setattr(dl, "fetch_default_cover", mocks["fetch_default_cover"])

    _patch_chapter_pipeline(monkeypatch, parse_results=parse_results)
    _patch_asset_downloads(monkeypatch, mocks, download_fonts_return=download_fonts_return)
    _patch_rendering(monkeypatch)

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

    async def test_skips_non_matching_before_match(self):
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
        downloader = _make_downloader(config, callback=cb)
        downloader._notify_progress("chapters", 1, 5)
        cb.assert_called_once_with("chapters", 1, 5)

    def test_notify_progress_no_callback_is_noop(self, downloader):
        # Should not raise.
        downloader._notify_progress("chapters", 1, 5)

    def test_make_asset_callback_none_no_callback(self, downloader):
        assert downloader._make_asset_callback("css") is None

    def test_make_asset_callback_bridges_arg_order(self, config):
        cb = MagicMock()
        downloader = _make_downloader(config, callback=cb)
        bridge = downloader._make_asset_callback("images")
        assert bridge is not None
        # Asset callbacks are (total, completed); public API is (stage, current, total).
        bridge(10, 3)
        cb.assert_called_once_with("images", 3, 10)


# ---------------------------------------------------------------------------
# _process_chapters
# ---------------------------------------------------------------------------


def _collect_assets_chapters() -> list[Chapter]:
    return [
        _make_chapter(
            filename="ch01.html",
            images=["img/local.png", "https://cdn.example.com/abs.png"],
            stylesheets=["s/main.css"],
            site_styles=["s/site.css"],
        ),
        _make_chapter(filename="ch02.html", images=["img/two.png"]),
    ]


def _collect_assets_results() -> list[ParseResult]:
    return [
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


def _assert_collected_images(collected) -> None:
    _css, all_images, _videos, _cover = collected
    # absolute image kept as-is; relative prefixed with asset_base_url
    assert "img/local.png" not in all_images
    assert "https://example.com/files/img/local.png" in all_images
    assert "https://cdn.example.com/abs.png" in all_images


def _assert_no_assets_collected(collected) -> None:
    all_css, _images, _videos, cover_src = collected
    assert all_css == []
    assert cover_src is None


def _assert_collected_dedup(collected) -> None:
    all_css, _images, all_videos, cover_src = collected
    # dedup of css and videos
    assert all_css == ["https://cdn/a.css", "https://cdn/b.css"]
    assert all_videos == ["v/clip.mp4", "v/two.mp4"]
    # first non-None cover_src wins
    assert cover_src == "Images/cover.png"


class TestProcessChapters:
    async def test_collects_assets_and_writes(self, config, monkeypatch, tmp_path):
        monkeypatch.setattr(dl, "fetch_chapter_html", AsyncMock(return_value=_ROOT_HTML))
        monkeypatch.setattr(dl, "parse_chapter_html", _sequential_parser(_collect_assets_results()))
        monkeypatch.setattr(dl, "write_chapter_html", MagicMock())

        cb = MagicMock()
        collected = await _make_downloader(config, callback=cb)._process_chapters(
            MagicMock(),  # client unused (parse mocked)
            _collect_assets_chapters(),
            ensure_book_dirs(tmp_path / "build"),
        )

        _assert_collected_images(collected)
        _assert_collected_dedup(collected)
        # write + progress fired per chapter
        assert dl.write_chapter_html.call_count == 2
        assert cb.call_count == 2

    async def test_resume_skips_existing_xhtml(self, downloader, monkeypatch, tmp_path):
        monkeypatch.setattr(dl, "fetch_chapter_html", AsyncMock(return_value=_ROOT_HTML))
        monkeypatch.setattr(dl, "parse_chapter_html", MagicMock())
        monkeypatch.setattr(dl, "write_chapter_html", MagicMock())

        book_paths = ensure_book_dirs(tmp_path / "build")
        # Pre-create the destination xhtml so the chapter is skipped.
        (book_paths.oebps / "ch01.xhtml").write_text("existing", encoding="utf-8")

        collected = await downloader._process_chapters(
            MagicMock(), [_make_chapter(filename="ch01.html")], book_paths
        )

        dl.fetch_chapter_html.assert_not_called()
        _assert_no_assets_collected(collected)

    async def test_empty_chapters_returns_empty(self, downloader, tmp_path):
        book_paths = ensure_book_dirs(tmp_path / "build")
        collected = await downloader._process_chapters(MagicMock(), [], book_paths)
        assert collected == ([], [], [], None)


# ---------------------------------------------------------------------------
# run() — full orchestration
# ---------------------------------------------------------------------------


def _assert_lifecycle(client) -> None:
    # auth + keepalive lifecycle
    client.check_login.assert_awaited_once()
    client.start_keepalive.assert_awaited_once()
    client.stop_keepalive.assert_awaited_once()
    client.save_cookies.assert_called_once()


class TestRunHappyPath:
    async def test_returns_epub_and_copies_to_library(self, config, monkeypatch):
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=_make_book_info(title="My Book", cover="https://c/cover.jpg"),
            chapters=[_make_chapter(filename="ch01.html")],
            parse_results=[_make_parse_result(cover_src="Images/cover.png")],
        )

        cb = MagicMock()
        epub_path = await _make_downloader(config, callback=cb).run()

        assert epub_path.suffix == ".epub"
        assert epub_path.exists()
        # Copied to library/epubs
        copied = config.library_dir / "epubs" / epub_path.name
        assert copied.exists()
        _assert_lifecycle(mocks["client"])
        # epub progress notified
        cb.assert_any_call("epub", 0, 1)
        cb.assert_any_call("epub", 1, 1)


class TestRunCover:
    async def test_default_cover_fetched_when_no_cover_src(self, downloader, monkeypatch):
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=_make_book_info(cover="https://c/cover.jpg"),
            chapters=[_make_chapter(filename="ch01.html", title="Chapter 1")],
            parse_results=[_make_parse_result(cover_src=None)],
            fetch_default_cover_return="cover.jpg",
        )
        await downloader.run()
        mocks["fetch_default_cover"].assert_awaited_once()

    async def test_default_cover_skipped_when_cover_chapter(self, downloader, monkeypatch):
        # A chapter whose title contains "cover" suppresses the default cover fetch.
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=_make_book_info(cover="https://c/cover.jpg"),
            chapters=[_make_chapter(filename="ch01.html", title="Cover Page")],
            parse_results=[_make_parse_result(cover_src=None)],
        )
        await downloader.run()
        mocks["fetch_default_cover"].assert_not_awaited()

    async def test_default_cover_skipped_when_no_book_cover(self, downloader, monkeypatch):
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=_make_book_info(cover=None),
            chapters=[_make_chapter(filename="ch01.html", title="Chapter 1")],
            parse_results=[_make_parse_result(cover_src=None)],
        )
        await downloader.run()
        mocks["fetch_default_cover"].assert_not_awaited()

    async def test_default_cover_fetch_returns_none(self, downloader, monkeypatch):
        # fetch_default_cover returns None -> cover_src stays None, no crash.
        _patch_pipeline(
            monkeypatch,
            book_info=_make_book_info(cover="https://c/cover.jpg"),
            chapters=[_make_chapter(filename="ch01.html", title="Chapter 1")],
            parse_results=[_make_parse_result(cover_src=None)],
            fetch_default_cover_return=None,
        )
        epub_path = await downloader.run()
        assert epub_path.exists()


class TestRunVideos:
    async def test_videos_downloaded_when_present(self, downloader, monkeypatch):
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=_make_book_info(),
            chapters=[_make_chapter(filename="ch01.html")],
            parse_results=[_make_parse_result(discovered_videos=["v/clip.mp4"])],
        )
        await downloader.run()
        mocks["download_videos"].assert_awaited_once()

    async def test_videos_not_downloaded_when_absent(self, downloader, monkeypatch):
        mocks = _patch_pipeline(
            monkeypatch,
            book_info=_make_book_info(),
            chapters=[_make_chapter(filename="ch01.html")],
            parse_results=[_make_parse_result(discovered_videos=[])],
        )
        await downloader.run()
        mocks["download_videos"].assert_not_awaited()


class TestRunArtifacts:
    async def test_writes_opf_and_ncx_files(self, downloader, monkeypatch):
        # Verify the build dir actually receives content.opf / toc.ncx by
        # intercepting build_epub and inspecting book_paths.
        _patch_pipeline(
            monkeypatch,
            book_info=_make_book_info(),
            chapters=[_make_chapter(filename="ch01.html")],
        )

        captured: dict = {}
        monkeypatch.setattr(dl, "build_epub", _BuildSpy(captured))

        await downloader.run()
        assert captured["opf"] == _OPF_BYTES
        assert captured["ncx"] == _NCX_BYTES


class _BuildSpy:
    """Captures opf/ncx bytes from the build dir, then runs the real build."""

    def __init__(self, captured: dict) -> None:
        self._captured = captured

    def __call__(self, book_paths, out):
        self._captured["opf"] = (book_paths.oebps / "content.opf").read_bytes()
        self._captured["ncx"] = (book_paths.oebps / "toc.ncx").read_bytes()
        return build_epub(book_paths, out)


def _md_config(tmp_path, **flags) -> AppConfig:
    return AppConfig(
        cookies_file=tmp_path / "cookies.json",
        output_dir=tmp_path / "Books",
        library_dir=tmp_path / "library",
        **flags,
    )


def _write_placeholder_markdown(_epub, dest, **_kwargs):
    """Write a placeholder .md file, standing in for a real ``convert_epub`` call."""
    dest.write_text("md", encoding="utf-8")
    return dest


def _stub_convert(monkeypatch) -> MagicMock:
    """Stub convert_epub to write a placeholder .md and return its path."""
    convert = MagicMock(side_effect=_write_placeholder_markdown)
    monkeypatch.setattr(dl, "convert_epub", convert)
    return convert


class TestRunMarkdown:
    async def test_markdown_writes_md_beside_epub(self, tmp_path, monkeypatch):
        config = _md_config(tmp_path, markdown=True)
        _patch_pipeline(
            monkeypatch,
            book_info=_make_book_info(title="My Book"),
            chapters=[_make_chapter()],
            parse_results=[_make_parse_result()],
        )
        convert = _stub_convert(monkeypatch)

        downloaded_path = await _make_downloader(config).run()

        assert downloaded_path.suffix == ".epub"
        assert downloaded_path.exists()
        md_path = config.output_dir / f"{downloaded_path.stem}.md"
        assert md_path.exists()
        convert.assert_called_once()

    async def test_markdown_only_writes_only_md(self, tmp_path, monkeypatch):
        config = _md_config(tmp_path, markdown=True, markdown_only=True)
        _patch_pipeline(
            monkeypatch,
            book_info=_make_book_info(title="My Book"),
            chapters=[_make_chapter()],
            parse_results=[_make_parse_result()],
        )
        _stub_convert(monkeypatch)

        downloaded_path = await _make_downloader(config).run()

        assert downloaded_path.suffix == ".md"
        assert downloaded_path.exists()
        assert not list(config.output_dir.glob("*.epub"))
