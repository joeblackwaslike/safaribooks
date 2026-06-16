"""Tests for the async structured logging module."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
import structlog

from safaribooks.core.log import (
    AsyncFileHandler,
    AsyncQueueHandler,
    JSONRenderer,
    configure_async_logging,
)

_FAST_FLUSH = 0.05
_SLOW_FLUSH = 10.0
_VERY_SLOW_FLUSH = 60.0
_WORKER_WAIT = 0.15
_BATCH_WAIT = 0.1
_BATCH_SIZE = 5
_LARGE_BATCH_SIZE = 1000
_OVERFLOW_QUEUE_SIZE = 2
_OVERFLOW_EMITS = 5
_MIN_OVERFLOW_TO_STDERR = 3
_PENDING_EMITS = 10


class TestAsyncQueueHandler:
    async def test_start_stop(self, capsys: pytest.CaptureFixture[str]) -> None:
        queue_handler = AsyncQueueHandler(flush_interval=_FAST_FLUSH)
        await queue_handler.start()
        queue_handler.emit({"message": "lifecycle"})
        await queue_handler.stop()

        captured = capsys.readouterr()
        assert "lifecycle" in captured.out

    async def test_context_manager(self, capsys: pytest.CaptureFixture[str]) -> None:
        async with AsyncQueueHandler(flush_interval=_FAST_FLUSH) as queue_handler:
            queue_handler.emit({"message": "ctx-mgr"})
        captured = capsys.readouterr()
        assert "ctx-mgr" in captured.out

    async def test_emit_and_flush(self, capsys: pytest.CaptureFixture[str]) -> None:
        queue_handler = AsyncQueueHandler(flush_interval=_FAST_FLUSH)
        await queue_handler.start()

        queue_handler.emit({"level": "INFO", "message": "hello"})
        await asyncio.sleep(_WORKER_WAIT)
        await queue_handler.stop()

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["message"] == "hello"

    async def test_batching(self, capsys: pytest.CaptureFixture[str]) -> None:
        queue_handler = AsyncQueueHandler(
            batch_size=_BATCH_SIZE,
            flush_interval=_SLOW_FLUSH,
        )
        await queue_handler.start()

        for index in range(_BATCH_SIZE):
            queue_handler.emit({"message": f"msg-{index}"})

        await asyncio.sleep(_BATCH_WAIT)
        await queue_handler.stop()

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == _BATCH_SIZE

    async def test_queue_overflow_falls_back_to_stderr(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        queue_handler = AsyncQueueHandler(
            queue_size=_OVERFLOW_QUEUE_SIZE,
            flush_interval=_SLOW_FLUSH,
        )
        # Don't start the worker — queue will fill up
        for _ in range(_OVERFLOW_EMITS):
            queue_handler.emit({"message": "overflow"})

        captured = capsys.readouterr()
        stderr_lines = [line for line in captured.err.strip().split("\n") if line]
        # at least 3 went to stderr (5 - 2 queue slots)
        assert len(stderr_lines) >= _MIN_OVERFLOW_TO_STDERR

    async def test_flush_on_stop(self, capsys: pytest.CaptureFixture[str]) -> None:
        queue_handler = AsyncQueueHandler(
            flush_interval=_VERY_SLOW_FLUSH,
            batch_size=_LARGE_BATCH_SIZE,
        )
        await queue_handler.start()

        for index in range(_PENDING_EMITS):
            queue_handler.emit({"message": f"pending-{index}"})

        await queue_handler.stop()

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == _PENDING_EMITS


class TestAsyncFileHandler:
    async def test_writes_json_lines(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        file_handler = AsyncFileHandler(log_file, flush_interval=_FAST_FLUSH)
        await file_handler.start()

        file_handler.emit({"level": "INFO", "message": "file-test"})
        file_handler.emit({"level": "WARNING", "message": "file-warn"})

        await asyncio.sleep(_WORKER_WAIT)
        await file_handler.stop()

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

        parsed_first = json.loads(lines[0])
        assert parsed_first["message"] == "file-test"

        parsed_second = json.loads(lines[1])
        assert parsed_second["level"] == "WARNING"

    async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        log_file = tmp_path / "nested" / "deep" / "test.log"
        file_handler = AsyncFileHandler(log_file)
        assert log_file.parent.is_dir()
        await file_handler.start()
        await file_handler.stop()


class TestJSONRenderer:
    def test_output_format(self) -> None:
        renderer = JSONRenderer(include_timestamp=True)
        event_dict: dict[str, Any] = {
            "event": "something happened",
            "log_level": "warning",
            "log_namespace": "mylogger",
            "_timestamp": "2024-01-01T00:00:00Z",
            "extra_key": "extra_value",
        }

        rendered = renderer(None, "fallback", event_dict)

        assert rendered["level"] == "WARNING"
        assert rendered["logger"] == "mylogger"
        assert rendered["message"] == "something happened"
        assert rendered["timestamp"] == "2024-01-01T00:00:00Z"
        assert rendered["extra_key"] == "extra_value"

    def test_without_timestamp(self) -> None:
        renderer = JSONRenderer(include_timestamp=False)
        event_dict: dict[str, Any] = {
            "event": "no time",
            "log_level": "info",
        }

        rendered = renderer(None, "test", event_dict)
        assert "timestamp" not in rendered

    def test_defaults_when_fields_missing(self) -> None:
        renderer = JSONRenderer(include_timestamp=True)
        event_dict: dict[str, Any] = {}

        rendered = renderer(None, "fallback_name", event_dict)
        assert rendered["level"] == "INFO"
        assert rendered["logger"] == "fallback_name"
        assert rendered["message"] == ""


class TestConfigureAsyncLogging:
    def test_returns_handler(self) -> None:
        log_handler = configure_async_logging()
        assert isinstance(log_handler, AsyncQueueHandler)

    def test_configures_structlog(self) -> None:
        configure_async_logging()
        config = structlog.get_config()
        assert len(config["processors"]) > 0

    async def test_end_to_end(self, capsys: pytest.CaptureFixture[str]) -> None:
        log_handler = configure_async_logging()
        await log_handler.start()

        log = structlog.get_logger()
        log.info("e2e test", foo="bar")

        await asyncio.sleep(_WORKER_WAIT)
        await log_handler.stop()

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) >= 1
        parsed = json.loads(lines[0])
        assert parsed["message"] == "e2e test"
        assert parsed["foo"] == "bar"
