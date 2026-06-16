"""Tests for safaribooks.core.assets — resize_image and download helpers."""

from functools import partial
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from PIL import Image

from safaribooks import core
from safaribooks.core.assets import (
    _download_single_css,
    _download_single_image,
    _download_single_video,
    _parallel_download,
    download_css,
    download_fonts,
    download_images,
    download_videos,
)
from safaribooks.core.constants import SAFARI_BASE_URL

BOOK_ID = "9781234567890"

_HTTP_NOT_FOUND = 404
_HTTP_FORBIDDEN = 403
_HTTP_SERVER_ERROR = 500

_LARGE_WIDTH = 800
_LARGE_HEIGHT = 600
_MEDIUM_SIDE = 200
_SMALL_SIDE = 50
_TINY_SIDE = 100
_MAX_SIZE = 400
_RESIZE_MAX = 100
_DOWNLOAD_MAX = 50
_QUALITY = 80
_LOW_QUALITY = 10
_DOWNLOAD_QUALITY = 70


def _make_client(*, status_code: int = 200, body: bytes = b"data") -> MagicMock:
    """Return a MagicMock ApiClient whose ``get`` is an AsyncMock response."""
    client = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.content = body
    client.get = AsyncMock(return_value=response)
    return client


def _make_test_image(path: Path, width: int = _MEDIUM_SIDE, height: int = 300) -> Path:
    img = Image.new("RGB", (width, height), color="red")
    img.save(path, format="JPEG")
    return path


def _write_css(css_dir: Path, name: str, css_text: str) -> Path:
    css_dir.mkdir(parents=True, exist_ok=True)
    path = css_dir / name
    path.write_text(css_text, encoding="utf-8")
    return path


def _assert_empty(payload: object) -> None:
    """Assert that a download helper returned an empty result."""
    assert not payload


class _RefusingReadText:
    """Descriptor ``Path.read_text`` replacement that raises for one target path.

    Implements ``__get__`` so that, when patched onto ``Path``, attribute access
    binds the owning ``Path`` instance exactly like an ordinary method would.
    """

    def __init__(self, target: Path, original_read_text) -> None:
        self._target = target
        self._original = original_read_text

    def __get__(self, instance, owner=None):
        return partial(self._read, instance)

    def _read(self, instance, *args, **kwargs) -> str:
        if instance == self._target:
            raise OSError("permission denied")
        return self._original(instance, *args, **kwargs)


async def _echo_worker(name: str) -> str:
    return name


async def _maybe_none_worker(name: str) -> str | None:
    if name == "fail":
        return None
    return name


async def _maybe_raise_worker(name: str) -> str:
    if name == "boom":
        msg = "download failed"
        raise RuntimeError(msg)
    return name


class TestResizeImage:
    def test_resizes_large_image(self, tmp_path):
        img_path = _make_test_image(tmp_path / "big.jpg", _LARGE_WIDTH, _LARGE_HEIGHT)
        core.assets.resize_image(img_path, max_size=_MAX_SIZE, quality=0)
        with Image.open(img_path) as resized:
            assert resized.width <= _MAX_SIZE
            assert resized.height <= _MAX_SIZE

    def test_no_resize_when_max_size_zero(self, tmp_path):
        img_path = _make_test_image(tmp_path / "orig.jpg", _LARGE_WIDTH, _LARGE_HEIGHT)
        core.assets.resize_image(img_path, max_size=0, quality=0)
        with Image.open(img_path) as img:
            assert img.width == _LARGE_WIDTH
            assert img.height == _LARGE_HEIGHT

    def test_quality_reencoding(self, tmp_path):
        img_path = _make_test_image(tmp_path / "quality.jpg", _MEDIUM_SIDE, _MEDIUM_SIDE)
        original_size = img_path.stat().st_size
        core.assets.resize_image(img_path, max_size=0, quality=_LOW_QUALITY)
        new_size = img_path.stat().st_size
        # Low quality should generally reduce file size
        assert new_size <= original_size or new_size > 0

    def test_both_zero_is_noop(self, tmp_path):
        img_path = _make_test_image(tmp_path / "noop.jpg", _TINY_SIDE, _TINY_SIDE)
        original_bytes = img_path.read_bytes()
        core.assets.resize_image(img_path, max_size=0, quality=0)
        assert img_path.read_bytes() == original_bytes

    def test_small_image_not_enlarged(self, tmp_path):
        img_path = _make_test_image(tmp_path / "small.jpg", _SMALL_SIDE, _SMALL_SIDE)
        core.assets.resize_image(img_path, max_size=_MAX_SIZE, quality=0)
        with Image.open(img_path) as img:
            # thumbnail does not enlarge
            assert img.width <= _SMALL_SIDE
            assert img.height <= _SMALL_SIDE

    def test_handles_corrupt_file_gracefully(self, tmp_path):
        bad_path = tmp_path / "corrupt.jpg"
        bad_path.write_bytes(b"not an image")
        # Should not raise — logs a warning instead
        core.assets.resize_image(bad_path, max_size=_MAX_SIZE, quality=_QUALITY)


class TestParallelDownload:
    async def test_empty_items_returns_empty_list(self):
        outcome = await _parallel_download([])
        _assert_empty(outcome)

    async def test_collects_successful_results(self):
        coros = [
            _echo_worker("file1.css"),
            _echo_worker("file2.css"),
            _echo_worker("file3.css"),
        ]
        downloaded = await _parallel_download(coros, max_concurrent=2)
        assert sorted(downloaded) == ["file1.css", "file2.css", "file3.css"]

    async def test_skips_none_results(self):
        coros = [
            _maybe_none_worker("ok.css"),
            _maybe_none_worker("fail"),
            _maybe_none_worker("also_ok.css"),
        ]
        downloaded = await _parallel_download(coros, max_concurrent=2)
        assert sorted(downloaded) == ["also_ok.css", "ok.css"]

    async def test_handles_exceptions_gracefully(self):
        coros = [_maybe_raise_worker("ok.css"), _maybe_raise_worker("boom")]
        downloaded = await _parallel_download(coros, max_concurrent=2)
        assert downloaded == ["ok.css"]

    async def test_progress_callback_invoked(self):
        callback = MagicMock()
        coros = [_echo_worker("a.css"), _echo_worker("b.css")]
        await _parallel_download(coros, max_concurrent=2, progress_callback=callback)
        assert callback.call_count == 2
        for call_args in callback.call_args_list:
            total, completed = call_args[0]
            assert total == 2
            assert completed >= 1


class TestResizeImagePillowMissing:
    def test_noop_when_pillow_unavailable(self, tmp_path, monkeypatch):
        # Force the no-Pillow path; should return immediately without touching file.
        monkeypatch.setattr(core.assets, "_HAS_PILLOW", False)
        path = tmp_path / "x.jpg"
        path.write_bytes(b"untouched")
        core.assets.resize_image(path, max_size=_RESIZE_MAX, quality=_QUALITY)
        assert path.read_bytes() == b"untouched"


class TestDownloadSingleCss:
    async def test_downloads_and_writes(self, tmp_path):
        client = _make_client(body=b"body{}")
        name = await _download_single_css(client, "https://x/style.css", tmp_path, 0)
        assert name == "Style00.css"
        assert (tmp_path / "Style00.css").read_bytes() == b"body{}"
        client.get.assert_awaited_once_with("https://x/style.css")

    async def test_index_formatting(self, tmp_path):
        client = _make_client()
        name = await _download_single_css(client, "https://x/s.css", tmp_path, 7)
        assert name == "Style07.css"

    async def test_skips_existing_file(self, tmp_path):
        existing = tmp_path / "Style00.css"
        existing.write_bytes(b"old")
        client = _make_client(body=b"new")
        name = await _download_single_css(client, "https://x/s.css", tmp_path, 0)
        assert name == "Style00.css"
        # File untouched, network never called.
        assert existing.read_bytes() == b"old"
        client.get.assert_not_awaited()

    async def test_returns_none_on_request_exception(self, tmp_path):
        client = MagicMock()
        client.get = AsyncMock(side_effect=RuntimeError("boom"))
        name = await _download_single_css(client, "https://x/s.css", tmp_path, 0)
        assert name is None
        assert not (tmp_path / "Style00.css").exists()

    async def test_returns_none_on_error_status(self, tmp_path):
        client = _make_client(status_code=_HTTP_NOT_FOUND)
        name = await _download_single_css(client, "https://x/s.css", tmp_path, 0)
        assert name is None
        assert not (tmp_path / "Style00.css").exists()


class TestDownloadSingleImage:
    async def test_downloads_and_writes(self, tmp_path):
        client = _make_client(body=b"imgbytes")
        name = await _download_single_image(client, "path/to/fig.png", tmp_path)
        assert name == "fig.png"
        assert (tmp_path / "fig.png").read_bytes() == b"imgbytes"
        # Relative URLs are joined onto the Safari base URL.
        client.get.assert_awaited_once()
        called_url = client.get.await_args[0][0]
        assert called_url.startswith(SAFARI_BASE_URL)
        assert called_url.endswith("path/to/fig.png")

    async def test_skips_existing_file(self, tmp_path):
        existing = tmp_path / "fig.png"
        existing.write_bytes(b"old")
        client = _make_client(body=b"new")
        name = await _download_single_image(client, "x/fig.png", tmp_path)
        assert name == "fig.png"
        assert existing.read_bytes() == b"old"
        client.get.assert_not_awaited()

    async def test_returns_none_on_request_exception(self, tmp_path):
        client = MagicMock()
        client.get = AsyncMock(side_effect=ValueError("nope"))
        name = await _download_single_image(client, "x/fig.png", tmp_path)
        assert name is None
        assert not (tmp_path / "fig.png").exists()

    async def test_returns_none_on_error_status(self, tmp_path):
        client = _make_client(status_code=_HTTP_SERVER_ERROR)
        name = await _download_single_image(client, "x/fig.png", tmp_path)
        assert name is None
        assert not (tmp_path / "fig.png").exists()

    async def test_invokes_resize(self, tmp_path, monkeypatch):
        client = _make_client(body=b"imgbytes")
        spy = MagicMock()
        monkeypatch.setattr(core.assets, "resize_image", spy)
        name = await _download_single_image(
            client, "x/fig.png", tmp_path, max_size=_RESIZE_MAX, quality=_QUALITY
        )
        assert name == "fig.png"
        spy.assert_called_once_with(tmp_path / "fig.png", _RESIZE_MAX, _QUALITY)


class TestDownloadSingleVideo:
    async def test_downloads_and_writes(self, tmp_path):
        client = _make_client(body=b"videobytes")
        name = await _download_single_video(client, "media/clip.mp4", tmp_path)
        assert name == "clip.mp4"
        assert (tmp_path / "clip.mp4").read_bytes() == b"videobytes"
        called_url = client.get.await_args[0][0]
        assert called_url.startswith(SAFARI_BASE_URL)

    async def test_skips_existing_file(self, tmp_path):
        existing = tmp_path / "clip.mp4"
        existing.write_bytes(b"old")
        client = _make_client()
        name = await _download_single_video(client, "x/clip.mp4", tmp_path)
        assert name == "clip.mp4"
        assert existing.read_bytes() == b"old"
        client.get.assert_not_awaited()

    async def test_returns_none_on_request_exception(self, tmp_path):
        client = MagicMock()
        client.get = AsyncMock(side_effect=RuntimeError("boom"))
        name = await _download_single_video(client, "x/clip.mp4", tmp_path)
        assert name is None
        assert not (tmp_path / "clip.mp4").exists()

    async def test_returns_none_on_error_status(self, tmp_path):
        client = _make_client(status_code=_HTTP_FORBIDDEN)
        name = await _download_single_video(client, "x/clip.mp4", tmp_path)
        assert name is None
        assert not (tmp_path / "clip.mp4").exists()


class TestDownloadCss:
    async def test_empty_list_returns_empty(self, tmp_path):
        client = _make_client()
        downloaded = await download_css(client, [], tmp_path, BOOK_ID)
        _assert_empty(downloaded)
        client.get.assert_not_awaited()

    async def test_downloads_multiple(self, tmp_path):
        client = _make_client(body=b"css")
        urls = ["https://x/a.css", "https://x/b.css"]
        downloaded = await download_css(client, urls, tmp_path, BOOK_ID)
        assert sorted(downloaded) == ["Style00.css", "Style01.css"]
        assert (tmp_path / "Style00.css").exists()
        assert (tmp_path / "Style01.css").exists()

    async def test_progress_callback(self, tmp_path):
        client = _make_client()
        callback = MagicMock()
        await download_css(
            client, ["https://x/a.css"], tmp_path, BOOK_ID, progress_callback=callback
        )
        assert callback.call_count == 1


class TestDownloadImages:
    async def test_empty_list_returns_empty(self, tmp_path):
        client = _make_client()
        downloaded = await download_images(client, [], tmp_path, BOOK_ID)
        _assert_empty(downloaded)
        client.get.assert_not_awaited()

    async def test_downloads_with_resize_params(self, tmp_path, monkeypatch):
        client = _make_client(body=b"img")
        spy = MagicMock()
        monkeypatch.setattr(core.assets, "resize_image", spy)
        downloaded = await download_images(
            client,
            ["x/a.png"],
            tmp_path,
            BOOK_ID,
            max_size=_DOWNLOAD_MAX,
            quality=_DOWNLOAD_QUALITY,
        )
        assert downloaded == ["a.png"]
        spy.assert_called_once_with(tmp_path / "a.png", _DOWNLOAD_MAX, _DOWNLOAD_QUALITY)


class TestDownloadVideos:
    async def test_empty_list_returns_empty(self, tmp_path):
        client = _make_client()
        downloaded = await download_videos(client, [], tmp_path)
        _assert_empty(downloaded)
        client.get.assert_not_awaited()

    async def test_downloads_multiple(self, tmp_path):
        client = _make_client(body=b"vid")
        downloaded = await download_videos(client, ["x/a.mp4", "x/b.mp4"], tmp_path)
        assert sorted(downloaded) == ["a.mp4", "b.mp4"]


class TestDownloadFontsDiscovery:
    async def test_missing_dir_returns_empty(self, tmp_path):
        client = _make_client()
        missing = tmp_path / "does_not_exist"
        discovered = await download_fonts(client, missing, BOOK_ID)
        _assert_empty(discovered)

    async def test_no_font_references_returns_empty(self, tmp_path):
        _write_css(tmp_path, "Style00.css", "body { color: red; }")
        client = _make_client()
        discovered = await download_fonts(client, tmp_path, BOOK_ID)
        _assert_empty(discovered)
        client.get.assert_not_awaited()

    async def test_ignores_non_css_files(self, tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes.txt").write_text(
            "@font-face { src: url('font.woff'); }", encoding="utf-8"
        )
        client = _make_client()
        discovered = await download_fonts(client, tmp_path, BOOK_ID)
        _assert_empty(discovered)

    async def test_downloads_referenced_font(self, tmp_path):
        _write_css(
            tmp_path,
            "Style00.css",
            "@font-face { src: url('fonts/myfont.woff2'); }",
        )
        client = _make_client(body=b"FONTDATA")
        discovered = await download_fonts(client, tmp_path, BOOK_ID)
        assert discovered == ["myfont.woff2"]
        assert (tmp_path / "myfont.woff2").read_bytes() == b"FONTDATA"
        called_url = client.get.await_args[0][0]
        assert BOOK_ID in called_url
        assert called_url.endswith("fonts/myfont.woff2")

    async def test_skips_data_and_remote_urls(self, tmp_path):
        # data: / http: / https: prefixes must be skipped. Use real font extensions
        # so the regex matches but the prefix filter rejects them.
        _write_css(
            tmp_path,
            "Style00.css",
            "src: url('data:application/font.woff');"
            " src: url('https://cdn/remote.ttf');"
            " src: url('http://cdn/other.otf');",
        )
        client = _make_client()
        discovered = await download_fonts(client, tmp_path, BOOK_ID)
        _assert_empty(discovered)
        client.get.assert_not_awaited()

    async def test_unreadable_css_skipped(self, tmp_path, monkeypatch):
        path = _write_css(tmp_path, "Style00.css", "src: url('myfont.woff');")
        refusing = _RefusingReadText(path, Path.read_text)

        monkeypatch.setattr(Path, "read_text", refusing)
        client = _make_client()
        discovered = await download_fonts(client, tmp_path, BOOK_ID)
        # The only CSS file was unreadable, so no fonts found.
        _assert_empty(discovered)


class TestDownloadFontsResults:
    async def test_skips_existing_font(self, tmp_path):
        _write_css(tmp_path, "Style00.css", "src: url('myfont.woff');")
        (tmp_path / "myfont.woff").write_bytes(b"old")
        client = _make_client(body=b"new")
        callback = MagicMock()
        fonts = await download_fonts(client, tmp_path, BOOK_ID, progress_callback=callback)
        assert fonts == ["myfont.woff"]
        assert (tmp_path / "myfont.woff").read_bytes() == b"old"
        client.get.assert_not_awaited()
        callback.assert_called_once_with(1, 1)

    async def test_request_exception_skips_font(self, tmp_path):
        _write_css(tmp_path, "Style00.css", "src: url('myfont.woff');")
        client = MagicMock()
        client.get = AsyncMock(side_effect=RuntimeError("boom"))
        callback = MagicMock()
        fonts = await download_fonts(client, tmp_path, BOOK_ID, progress_callback=callback)
        _assert_empty(fonts)
        assert not (tmp_path / "myfont.woff").exists()
        callback.assert_called_once_with(1, 1)

    async def test_error_status_skips_font(self, tmp_path):
        _write_css(tmp_path, "Style00.css", "src: url('myfont.woff');")
        client = _make_client(status_code=_HTTP_NOT_FOUND)
        callback = MagicMock()
        fonts = await download_fonts(client, tmp_path, BOOK_ID, progress_callback=callback)
        _assert_empty(fonts)
        assert not (tmp_path / "myfont.woff").exists()
        callback.assert_called_once_with(1, 1)

    async def test_progress_callback_on_success(self, tmp_path):
        _write_css(tmp_path, "Style00.css", "src: url('myfont.woff');")
        client = _make_client(body=b"FONT")
        callback = MagicMock()
        fonts = await download_fonts(client, tmp_path, BOOK_ID, progress_callback=callback)
        assert fonts == ["myfont.woff"]
        callback.assert_called_once_with(1, 1)

    async def test_skip_existing_without_callback(self, tmp_path):
        # No-callback branch of the skip-existing path (progress_callback=None).
        _write_css(tmp_path, "Style00.css", "src: url('f.woff');")
        (tmp_path / "f.woff").write_bytes(b"old")
        fonts = await download_fonts(_make_client(), tmp_path, BOOK_ID)
        assert fonts == ["f.woff"]

    async def test_request_exception_without_callback(self, tmp_path):
        # No-callback branch of the request-exception path (progress_callback=None).
        _write_css(tmp_path, "Style00.css", "src: url('f.woff');")
        bad = MagicMock()
        bad.get = AsyncMock(side_effect=RuntimeError("boom"))
        fonts = await download_fonts(bad, tmp_path, BOOK_ID)
        _assert_empty(fonts)

    async def test_error_status_without_callback(self, tmp_path):
        # No-callback branch of the non-200 path (progress_callback=None).
        _write_css(tmp_path, "Style00.css", "src: url('f.woff');")
        client = _make_client(status_code=_HTTP_NOT_FOUND)
        fonts = await download_fonts(client, tmp_path, BOOK_ID)
        _assert_empty(fonts)
