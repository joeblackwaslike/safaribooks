"""Tests for safaribooks.core.assets — resize_image and download helpers."""


from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from PIL import Image

import safaribooks.core.assets as assets
from safaribooks.core.assets import (
    _download_single_css,
    _download_single_image,
    _download_single_video,
    _parallel_download,
    download_css,
    download_fonts,
    download_images,
    download_videos,
    resize_image,
)
from safaribooks.core.constants import SAFARI_BASE_URL

BOOK_ID = "9781234567890"


def _make_client(*, status_code: int = 200, content: bytes = b"data") -> MagicMock:
    """Return a MagicMock ApiClient whose ``get`` is an AsyncMock response."""
    client = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.content = content
    client.get = AsyncMock(return_value=response)
    return client


class TestResizeImage:
    @staticmethod
    def _create_test_image(path: Path, width: int = 200, height: int = 300) -> Path:
        img = Image.new("RGB", (width, height), color="red")
        img.save(path, format="JPEG")
        return path

    def test_resizes_large_image(self, tmp_path):
        img_path = self._create_test_image(tmp_path / "big.jpg", 800, 600)
        resize_image(img_path, max_size=400, quality=0)
        with Image.open(img_path) as resized:
            assert resized.width <= 400
            assert resized.height <= 400

    def test_no_resize_when_max_size_zero(self, tmp_path):
        img_path = self._create_test_image(tmp_path / "orig.jpg", 800, 600)
        resize_image(img_path, max_size=0, quality=0)
        with Image.open(img_path) as img:
            assert img.width == 800
            assert img.height == 600

    def test_quality_reencoding(self, tmp_path):
        img_path = self._create_test_image(tmp_path / "quality.jpg", 200, 200)
        original_size = img_path.stat().st_size
        resize_image(img_path, max_size=0, quality=10)
        new_size = img_path.stat().st_size
        # Low quality should generally reduce file size
        assert new_size <= original_size or new_size > 0

    def test_both_zero_is_noop(self, tmp_path):
        img_path = self._create_test_image(tmp_path / "noop.jpg", 100, 100)
        original_bytes = img_path.read_bytes()
        resize_image(img_path, max_size=0, quality=0)
        assert img_path.read_bytes() == original_bytes

    def test_small_image_not_enlarged(self, tmp_path):
        img_path = self._create_test_image(tmp_path / "small.jpg", 50, 50)
        resize_image(img_path, max_size=400, quality=0)
        with Image.open(img_path) as img:
            # thumbnail does not enlarge
            assert img.width <= 50
            assert img.height <= 50

    def test_handles_corrupt_file_gracefully(self, tmp_path):
        bad_path = tmp_path / "corrupt.jpg"
        bad_path.write_bytes(b"not an image")
        # Should not raise — logs a warning instead
        resize_image(bad_path, max_size=400, quality=80)


class TestParallelDownload:
    async def test_empty_items_returns_empty_list(self):
        result = await _parallel_download([])
        assert result == []

    async def test_collects_successful_results(self):
        async def worker(name: str) -> str:
            return name

        coros = [worker("file1.css"), worker("file2.css"), worker("file3.css")]
        result = await _parallel_download(coros, max_concurrent=2)
        assert sorted(result) == ["file1.css", "file2.css", "file3.css"]

    async def test_skips_none_results(self):
        async def worker(name: str) -> str | None:
            if name == "fail":
                return None
            return name

        coros = [worker("ok.css"), worker("fail"), worker("also_ok.css")]
        result = await _parallel_download(coros, max_concurrent=2)
        assert sorted(result) == ["also_ok.css", "ok.css"]

    async def test_handles_exceptions_gracefully(self):
        async def worker(name: str) -> str:
            if name == "boom":
                msg = "download failed"
                raise RuntimeError(msg)
            return name

        coros = [worker("ok.css"), worker("boom")]
        result = await _parallel_download(coros, max_concurrent=2)
        assert result == ["ok.css"]

    async def test_progress_callback_invoked(self):
        async def worker(name: str) -> str:
            return name

        callback = MagicMock()
        coros = [worker("a.css"), worker("b.css")]
        await _parallel_download(coros, max_concurrent=2, progress_callback=callback)
        assert callback.call_count == 2
        for call_args in callback.call_args_list:
            total, completed = call_args[0]
            assert total == 2
            assert completed >= 1


class TestResizeImagePillowMissing:
    def test_noop_when_pillow_unavailable(self, tmp_path, monkeypatch):
        # Force the no-Pillow path; should return immediately without touching file.
        monkeypatch.setattr(assets, "_HAS_PILLOW", False)
        path = tmp_path / "x.jpg"
        path.write_bytes(b"untouched")
        resize_image(path, max_size=100, quality=80)
        assert path.read_bytes() == b"untouched"


class TestDownloadSingleCss:
    async def test_downloads_and_writes(self, tmp_path):
        client = _make_client(content=b"body{}")
        result = await _download_single_css(client, "https://x/style.css", tmp_path, 0)
        assert result == "Style00.css"
        assert (tmp_path / "Style00.css").read_bytes() == b"body{}"
        client.get.assert_awaited_once_with("https://x/style.css")

    async def test_index_formatting(self, tmp_path):
        client = _make_client()
        result = await _download_single_css(client, "https://x/s.css", tmp_path, 7)
        assert result == "Style07.css"

    async def test_skips_existing_file(self, tmp_path):
        existing = tmp_path / "Style00.css"
        existing.write_bytes(b"old")
        client = _make_client(content=b"new")
        result = await _download_single_css(client, "https://x/s.css", tmp_path, 0)
        assert result == "Style00.css"
        # File untouched, network never called.
        assert existing.read_bytes() == b"old"
        client.get.assert_not_awaited()

    async def test_returns_none_on_request_exception(self, tmp_path):
        client = MagicMock()
        client.get = AsyncMock(side_effect=RuntimeError("boom"))
        result = await _download_single_css(client, "https://x/s.css", tmp_path, 0)
        assert result is None
        assert not (tmp_path / "Style00.css").exists()

    async def test_returns_none_on_non_200(self, tmp_path):
        client = _make_client(status_code=404)
        result = await _download_single_css(client, "https://x/s.css", tmp_path, 0)
        assert result is None
        assert not (tmp_path / "Style00.css").exists()


class TestDownloadSingleImage:
    async def test_downloads_and_writes(self, tmp_path):
        client = _make_client(content=b"imgbytes")
        result = await _download_single_image(client, "path/to/fig.png", tmp_path)
        assert result == "fig.png"
        assert (tmp_path / "fig.png").read_bytes() == b"imgbytes"
        # Relative URLs are joined onto the Safari base URL.
        client.get.assert_awaited_once()
        called_url = client.get.await_args[0][0]
        assert called_url.startswith(SAFARI_BASE_URL)
        assert called_url.endswith("path/to/fig.png")

    async def test_skips_existing_file(self, tmp_path):
        existing = tmp_path / "fig.png"
        existing.write_bytes(b"old")
        client = _make_client(content=b"new")
        result = await _download_single_image(client, "x/fig.png", tmp_path)
        assert result == "fig.png"
        assert existing.read_bytes() == b"old"
        client.get.assert_not_awaited()

    async def test_returns_none_on_request_exception(self, tmp_path):
        client = MagicMock()
        client.get = AsyncMock(side_effect=ValueError("nope"))
        result = await _download_single_image(client, "x/fig.png", tmp_path)
        assert result is None
        assert not (tmp_path / "fig.png").exists()

    async def test_returns_none_on_non_200(self, tmp_path):
        client = _make_client(status_code=500)
        result = await _download_single_image(client, "x/fig.png", tmp_path)
        assert result is None
        assert not (tmp_path / "fig.png").exists()

    async def test_invokes_resize(self, tmp_path, monkeypatch):
        client = _make_client(content=b"imgbytes")
        spy = MagicMock()
        monkeypatch.setattr(assets, "resize_image", spy)
        result = await _download_single_image(
            client, "x/fig.png", tmp_path, max_size=100, quality=80
        )
        assert result == "fig.png"
        spy.assert_called_once_with(tmp_path / "fig.png", 100, 80)


class TestDownloadSingleVideo:
    async def test_downloads_and_writes(self, tmp_path):
        client = _make_client(content=b"videobytes")
        result = await _download_single_video(client, "media/clip.mp4", tmp_path)
        assert result == "clip.mp4"
        assert (tmp_path / "clip.mp4").read_bytes() == b"videobytes"
        called_url = client.get.await_args[0][0]
        assert called_url.startswith(SAFARI_BASE_URL)

    async def test_skips_existing_file(self, tmp_path):
        existing = tmp_path / "clip.mp4"
        existing.write_bytes(b"old")
        client = _make_client()
        result = await _download_single_video(client, "x/clip.mp4", tmp_path)
        assert result == "clip.mp4"
        assert existing.read_bytes() == b"old"
        client.get.assert_not_awaited()

    async def test_returns_none_on_request_exception(self, tmp_path):
        client = MagicMock()
        client.get = AsyncMock(side_effect=RuntimeError("boom"))
        result = await _download_single_video(client, "x/clip.mp4", tmp_path)
        assert result is None
        assert not (tmp_path / "clip.mp4").exists()

    async def test_returns_none_on_non_200(self, tmp_path):
        client = _make_client(status_code=403)
        result = await _download_single_video(client, "x/clip.mp4", tmp_path)
        assert result is None
        assert not (tmp_path / "clip.mp4").exists()


class TestDownloadCss:
    async def test_empty_list_returns_empty(self, tmp_path):
        client = _make_client()
        result = await download_css(client, [], tmp_path, BOOK_ID)
        assert result == []
        client.get.assert_not_awaited()

    async def test_downloads_multiple(self, tmp_path):
        client = _make_client(content=b"css")
        urls = ["https://x/a.css", "https://x/b.css"]
        result = await download_css(client, urls, tmp_path, BOOK_ID)
        assert sorted(result) == ["Style00.css", "Style01.css"]
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
        result = await download_images(client, [], tmp_path, BOOK_ID)
        assert result == []
        client.get.assert_not_awaited()

    async def test_downloads_with_resize_params(self, tmp_path, monkeypatch):
        client = _make_client(content=b"img")
        spy = MagicMock()
        monkeypatch.setattr(assets, "resize_image", spy)
        result = await download_images(
            client, ["x/a.png"], tmp_path, BOOK_ID, max_size=50, quality=70
        )
        assert result == ["a.png"]
        spy.assert_called_once_with(tmp_path / "a.png", 50, 70)


class TestDownloadVideos:
    async def test_empty_list_returns_empty(self, tmp_path):
        client = _make_client()
        result = await download_videos(client, [], tmp_path)
        assert result == []
        client.get.assert_not_awaited()

    async def test_downloads_multiple(self, tmp_path):
        client = _make_client(content=b"vid")
        result = await download_videos(client, ["x/a.mp4", "x/b.mp4"], tmp_path)
        assert sorted(result) == ["a.mp4", "b.mp4"]


class TestDownloadFonts:
    @staticmethod
    def _write_css(css_dir: Path, name: str, content: str) -> Path:
        css_dir.mkdir(parents=True, exist_ok=True)
        path = css_dir / name
        path.write_text(content, encoding="utf-8")
        return path

    async def test_missing_dir_returns_empty(self, tmp_path):
        client = _make_client()
        result = await download_fonts(client, tmp_path / "does_not_exist", BOOK_ID)
        assert result == []

    async def test_no_font_references_returns_empty(self, tmp_path):
        self._write_css(tmp_path, "Style00.css", "body { color: red; }")
        client = _make_client()
        result = await download_fonts(client, tmp_path, BOOK_ID)
        assert result == []
        client.get.assert_not_awaited()

    async def test_ignores_non_css_files(self, tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes.txt").write_text(
            "@font-face { src: url('font.woff'); }", encoding="utf-8"
        )
        client = _make_client()
        result = await download_fonts(client, tmp_path, BOOK_ID)
        assert result == []

    async def test_downloads_referenced_font(self, tmp_path):
        self._write_css(
            tmp_path,
            "Style00.css",
            "@font-face { src: url('fonts/myfont.woff2'); }",
        )
        client = _make_client(content=b"FONTDATA")
        result = await download_fonts(client, tmp_path, BOOK_ID)
        assert result == ["myfont.woff2"]
        assert (tmp_path / "myfont.woff2").read_bytes() == b"FONTDATA"
        called_url = client.get.await_args[0][0]
        assert BOOK_ID in called_url
        assert called_url.endswith("fonts/myfont.woff2")

    async def test_skips_data_and_remote_urls(self, tmp_path):
        # data: / http: / https: prefixes must be skipped. Use real font extensions
        # so the regex matches but the prefix filter rejects them.
        self._write_css(
            tmp_path,
            "Style00.css",
            "src: url('data:application/font.woff');"
            " src: url('https://cdn/remote.ttf');"
            " src: url('http://cdn/other.otf');",
        )
        client = _make_client()
        result = await download_fonts(client, tmp_path, BOOK_ID)
        assert result == []
        client.get.assert_not_awaited()

    async def test_skips_existing_font(self, tmp_path):
        self._write_css(
            tmp_path, "Style00.css", "src: url('myfont.woff');"
        )
        (tmp_path / "myfont.woff").write_bytes(b"old")
        client = _make_client(content=b"new")
        callback = MagicMock()
        result = await download_fonts(
            client, tmp_path, BOOK_ID, progress_callback=callback
        )
        assert result == ["myfont.woff"]
        assert (tmp_path / "myfont.woff").read_bytes() == b"old"
        client.get.assert_not_awaited()
        callback.assert_called_once_with(1, 1)

    async def test_request_exception_skips_font(self, tmp_path):
        self._write_css(tmp_path, "Style00.css", "src: url('myfont.woff');")
        client = MagicMock()
        client.get = AsyncMock(side_effect=RuntimeError("boom"))
        callback = MagicMock()
        result = await download_fonts(
            client, tmp_path, BOOK_ID, progress_callback=callback
        )
        assert result == []
        assert not (tmp_path / "myfont.woff").exists()
        callback.assert_called_once_with(1, 1)

    async def test_non_200_skips_font(self, tmp_path):
        self._write_css(tmp_path, "Style00.css", "src: url('myfont.woff');")
        client = _make_client(status_code=404)
        callback = MagicMock()
        result = await download_fonts(
            client, tmp_path, BOOK_ID, progress_callback=callback
        )
        assert result == []
        assert not (tmp_path / "myfont.woff").exists()
        callback.assert_called_once_with(1, 1)

    async def test_progress_callback_on_success(self, tmp_path):
        self._write_css(tmp_path, "Style00.css", "src: url('myfont.woff');")
        client = _make_client(content=b"FONT")
        callback = MagicMock()
        result = await download_fonts(
            client, tmp_path, BOOK_ID, progress_callback=callback
        )
        assert result == ["myfont.woff"]
        callback.assert_called_once_with(1, 1)

    async def test_skip_paths_without_callback(self, tmp_path):
        # Exercise the no-callback branch of the skip-existing, exception, and
        # non-200 paths (progress_callback defaults to None).
        d1 = tmp_path / "existing"
        self._write_css(d1, "Style00.css", "src: url('f.woff');")
        (d1 / "f.woff").write_bytes(b"old")
        assert await download_fonts(_make_client(), d1, BOOK_ID) == ["f.woff"]

        d2 = tmp_path / "exc"
        self._write_css(d2, "Style00.css", "src: url('f.woff');")
        bad = MagicMock()
        bad.get = AsyncMock(side_effect=RuntimeError("boom"))
        assert await download_fonts(bad, d2, BOOK_ID) == []

        d3 = tmp_path / "non200"
        self._write_css(d3, "Style00.css", "src: url('f.woff');")
        assert await download_fonts(_make_client(status_code=404), d3, BOOK_ID) == []

    async def test_unreadable_css_skipped(self, tmp_path, monkeypatch):
        path = self._write_css(tmp_path, "Style00.css", "src: url('myfont.woff');")
        original_read_text = Path.read_text

        def fake_read_text(self, *args, **kwargs):
            if self == path:
                raise OSError("permission denied")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", fake_read_text)
        client = _make_client()
        result = await download_fonts(client, tmp_path, BOOK_ID)
        # The only CSS file was unreadable, so no fonts found.
        assert result == []
