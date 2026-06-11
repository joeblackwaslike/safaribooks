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


class TestAsyncQueueHandler:
    async def test_start_stop(self, capsys: pytest.CaptureFixture[str]) -> None:
        handler = AsyncQueueHandler(flush_interval=0.05)
        await handler.start()
        handler.emit({"message": "lifecycle"})
        await handler.stop()

        captured = capsys.readouterr()
        assert "lifecycle" in captured.out

    async def test_context_manager(self, capsys: pytest.CaptureFixture[str]) -> None:
        async with AsyncQueueHandler(flush_interval=0.05) as handler:
            handler.emit({"message": "ctx-mgr"})
        captured = capsys.readouterr()
        assert "ctx-mgr" in captured.out

    async def test_emit_and_flush(self, capsys: pytest.CaptureFixture[str]) -> None:
        handler = AsyncQueueHandler(flush_interval=0.05)
        await handler.start()

        handler.emit({"level": "INFO", "message": "hello"})
        await asyncio.sleep(0.15)
        await handler.stop()

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["message"] == "hello"

    async def test_batching(self, capsys: pytest.CaptureFixture[str]) -> None:
        handler = AsyncQueueHandler(batch_size=5, flush_interval=10.0)
        await handler.start()

        for i in range(5):
            handler.emit({"message": f"msg-{i}"})

        await asyncio.sleep(0.1)
        await handler.stop()

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 5

    async def test_queue_overflow_falls_back_to_stderr(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        handler = AsyncQueueHandler(queue_size=2, flush_interval=10.0)
        # Don't start the worker — queue will fill up
        for _ in range(5):
            handler.emit({"message": "overflow"})

        captured = capsys.readouterr()
        stderr_lines = [line for line in captured.err.strip().split("\n") if line]
        assert len(stderr_lines) >= 3  # at least 3 went to stderr (5 - 2 queue slots)

    async def test_flush_on_stop(self, capsys: pytest.CaptureFixture[str]) -> None:
        handler = AsyncQueueHandler(flush_interval=60.0, batch_size=1000)
        await handler.start()

        for i in range(10):
            handler.emit({"message": f"pending-{i}"})

        await handler.stop()

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 10


class TestAsyncFileHandler:
    async def test_writes_json_lines(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        handler = AsyncFileHandler(log_file, flush_interval=0.05)
        await handler.start()

        handler.emit({"level": "INFO", "message": "file-test"})
        handler.emit({"level": "WARNING", "message": "file-warn"})

        await asyncio.sleep(0.15)
        await handler.stop()

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

        parsed_first = json.loads(lines[0])
        assert parsed_first["message"] == "file-test"

        parsed_second = json.loads(lines[1])
        assert parsed_second["level"] == "WARNING"

    async def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        log_file = tmp_path / "nested" / "deep" / "test.log"
        handler = AsyncFileHandler(log_file)
        assert log_file.parent.is_dir()
        await handler.start()
        await handler.stop()


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

        result = renderer(None, "fallback", event_dict)

        assert result["level"] == "WARNING"
        assert result["logger"] == "mylogger"
        assert result["message"] == "something happened"
        assert result["timestamp"] == "2024-01-01T00:00:00Z"
        assert result["extra_key"] == "extra_value"

    def test_without_timestamp(self) -> None:
        renderer = JSONRenderer(include_timestamp=False)
        event_dict: dict[str, Any] = {
            "event": "no time",
            "log_level": "info",
        }

        result = renderer(None, "test", event_dict)
        assert "timestamp" not in result

    def test_defaults_when_fields_missing(self) -> None:
        renderer = JSONRenderer(include_timestamp=True)
        event_dict: dict[str, Any] = {}

        result = renderer(None, "fallback_name", event_dict)
        assert result["level"] == "INFO"
        assert result["logger"] == "fallback_name"
        assert result["message"] == ""


class TestConfigureAsyncLogging:
    def test_returns_handler(self) -> None:
        handler = configure_async_logging()
        assert isinstance(handler, AsyncQueueHandler)

    def test_configures_structlog(self) -> None:
        configure_async_logging()
        config = structlog.get_config()
        assert len(config["processors"]) > 0

    async def test_end_to_end(self, capsys: pytest.CaptureFixture[str]) -> None:
        handler = configure_async_logging()
        await handler.start()

        log = structlog.get_logger()
        log.info("e2e test", foo="bar")

        await asyncio.sleep(0.15)
        await handler.stop()

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) >= 1
        parsed = json.loads(lines[0])
        assert parsed["message"] == "e2e test"
        assert parsed["foo"] == "bar"
