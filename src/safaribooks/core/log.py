"""Production-level async structured logging with structlog."""

import asyncio
import json
import logging
import sys
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict, Processor

_logger = logging.getLogger(__name__)


class AsyncQueueHandler:
    """Non-blocking async logging handler using a queue.

    Decouples log production from I/O to avoid blocking the event loop.

    Args:
        queue_size: Maximum number of log records to buffer.
        batch_size: Number of records to write per batch.
        flush_interval: Seconds between automatic flushes.
    """

    def __init__(  # noqa: D107
        self,
        queue_size: int = 10000,
        batch_size: int = 100,
        flush_interval: float = 1.0,
    ) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=queue_size)
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._worker_task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the background worker task."""
        self._shutdown_event.clear()
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """Gracefully shutdown: flush remaining logs and stop worker."""
        self._shutdown_event.set()

        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except TimeoutError:
                _logger.exception("Async log handler shutdown timeout")
                self._worker_task.cancel()

    async def __aenter__(self) -> "AsyncQueueHandler":
        """Start the handler when used as an async context manager."""
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Stop the handler on context manager exit."""
        await self.stop()

    def emit(self, record: MutableMapping[str, Any]) -> None:
        """Queue a log record (non-blocking)."""
        try:
            self.queue.put_nowait(dict(record))
        except asyncio.QueueFull:
            sys.stderr.write(json.dumps(dict(record), default=str) + "\n")

    async def _worker(self) -> None:
        """Background worker that processes batched logs."""
        batch: list[dict[str, Any]] = []
        last_flush = asyncio.get_event_loop().time()

        try:
            while not self._shutdown_event.is_set():
                try:
                    timeout = self.flush_interval - (
                        asyncio.get_event_loop().time() - last_flush
                    )
                    timeout = max(timeout, 0.01)

                    record = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=timeout,
                    )
                    batch.append(record)

                except TimeoutError:
                    if batch:
                        await self._write_batch(batch)
                        batch.clear()
                        last_flush = asyncio.get_event_loop().time()
                    continue

                if len(batch) >= self.batch_size:
                    await self._write_batch(batch)
                    batch.clear()
                    last_flush = asyncio.get_event_loop().time()

        finally:
            while not self.queue.empty():
                try:
                    record = self.queue.get_nowait()
                    batch.append(record)
                except asyncio.QueueEmpty:
                    break

            if batch:
                await self._write_batch(batch)

    async def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        """Write a batch of logs (override for file/network I/O)."""
        for record in batch:
            sys.stdout.write(json.dumps(record, default=str) + "\n")
        sys.stdout.flush()


class AsyncFileHandler(AsyncQueueHandler):
    """Async handler that writes to a file.

    Args:
        filepath: Path to the log file.
        queue_size: Maximum number of log records to buffer.
        batch_size: Number of records to write per batch.
        flush_interval: Seconds between automatic flushes.
    """

    def __init__(  # noqa: D107
        self,
        filepath: str | Path,
        queue_size: int = 10000,
        batch_size: int = 100,
        flush_interval: float = 1.0,
    ) -> None:
        super().__init__(queue_size, batch_size, flush_interval)
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._file: Any = None

    async def start(self) -> None:
        """Open file and start worker."""
        self._file = self.filepath.open("a", buffering=1)
        await super().start()

    async def stop(self) -> None:
        """Stop worker and close file."""
        await super().stop()
        if self._file:
            self._file.close()

    async def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        """Write batch to file."""
        if not self._file:
            return

        for record in batch:
            self._file.write(json.dumps(record, default=str) + "\n")
        self._file.flush()


class JSONRenderer:
    """Structlog renderer that outputs JSON with sensible defaults.

    Args:
        include_timestamp: Whether to include the timestamp field.
    """

    def __init__(self, *, include_timestamp: bool = True) -> None:  # noqa: D107
        self.include_timestamp = include_timestamp

    def __call__(
        self,
        logger: Any,
        name: str,
        event_dict: EventDict,
    ) -> dict[str, Any]:
        """Render event to JSON-serializable dict."""
        output: dict[str, Any] = {
            "level": event_dict.pop("log_level", "info").upper(),
            "logger": event_dict.pop("log_namespace", name),
            "message": event_dict.pop("event", ""),
        }

        if self.include_timestamp:
            output["timestamp"] = event_dict.pop("_timestamp", None)

        output.update(event_dict)

        return output


def configure_async_logging(
    level: int = logging.INFO,
) -> AsyncQueueHandler:
    """Configure structlog with async, non-blocking handlers.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        AsyncQueueHandler instance (call ``.start()`` and ``.stop()`` on it).

    """
    handlers: list[AsyncQueueHandler] = [AsyncQueueHandler()]

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.dict_tracebacks,
            JSONRenderer(include_timestamp=True),
            _queue_renderer(handlers),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    logging.basicConfig(level=level, stream=sys.stderr, force=True)

    return handlers[0]


def _queue_renderer(handlers: list[AsyncQueueHandler]) -> Processor:
    """Processor that routes logs to async queue handlers."""

    def renderer(
        logger: Any,
        name: str,
        event_dict: EventDict,
    ) -> str:
        for handler in handlers:
            handler.emit(event_dict)
        return ""

    return renderer
