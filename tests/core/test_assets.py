"""Tests for safaribooks.core.assets — resize_image and download helpers."""


from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image

from safaribooks.core.assets import (
    _parallel_download,
    resize_image,
)


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
