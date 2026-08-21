"""Production-level async structured logging with structlog."""

import asyncio
import json
import logging
import sys
from collections.abc import Awaitable, Callable, MutableMapping
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict

_logger = logging.getLogger(__name__)

_SHUTDOWN_TIMEOUT = 5.0
_MIN_FLUSH_TIMEOUT = 0.01
_NEWLINE = "\n"

_Record = dict[str, Any]
_WriteBatch = Callable[[list[_Record]], Awaitable[None]]


def _to_json_line(record: MutableMapping[str, Any]) -> str:
    """Serialize a record to a single newline-terminated JSON line."""
    return f"{json.dumps(dict(record), default=str)}{_NEWLINE}"


class _BatchWorker:
    """Drains a queue into batches and flushes them via a write callback.

    The worker is decoupled from any specific handler: it receives the queue,
    batching configuration, shutdown signal, and write callback explicitly so
    that it never reaches into another object's internals.
    """

    def __init__(
        self,
        queue: "asyncio.Queue[_Record]",
        batch_size: int,
        flush_interval: float,
        shutdown_event: asyncio.Event,
        write_batch: _WriteBatch,
    ) -> None:
        self._queue = queue
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._shutdown_event = shutdown_event
        self._write_batch = write_batch
        self._batch: list[_Record] = []
        self._last_flush: float

    async def run(self) -> None:
        """Process queued records until shutdown, flushing any remainder."""
        self._last_flush = asyncio.get_running_loop().time()
        try:
            await self._consume()
        except BaseException:
            await self._flush_remaining()
            raise
        else:
            await self._flush_remaining()

    async def _flush_remaining(self) -> None:
        """Drain the queue and write whatever records are still pending."""
        self._drain()
        if self._batch:
            await self._write_batch(self._batch)

    async def _consume(self) -> None:
        """Loop over the queue until the shutdown event is set."""
        while not self._shutdown_event.is_set():
            record = await self._await_record()
            if record is None:
                await self._maybe_flush(force=True)
            else:
                self._batch.append(record)
                await self._maybe_flush(force=False)

    async def _await_record(self) -> _Record | None:
        """Wait for a record, or ``None`` when the flush interval elapses."""
        elapsed = asyncio.get_running_loop().time() - self._last_flush
        timeout = max(self._flush_interval - elapsed, _MIN_FLUSH_TIMEOUT)
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def _maybe_flush(self, *, force: bool) -> None:
        """Flush when forced by the interval or the batch is full."""
        ready = force or len(self._batch) >= self._batch_size
        if ready and self._batch:
            await self._write_batch(self._batch)
            self._batch.clear()
            self._last_flush = asyncio.get_running_loop().time()

    def _drain(self) -> None:
        """Move any remaining queued records into the pending batch."""
        while not self._queue.empty():
            try:
                self._batch.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                return


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
        worker = _BatchWorker(
            self.queue,
            self.batch_size,
            self.flush_interval,
            self._shutdown_event,
            self._write_batch,
        )
        self._worker_task = asyncio.create_task(worker.run())

    async def stop(self) -> None:
        """Gracefully shutdown: flush remaining logs and stop worker."""
        self._shutdown_event.set()

        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=_SHUTDOWN_TIMEOUT)
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
            sys.stderr.write(_to_json_line(record))

    async def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        """Write a batch of logs (override for file/network I/O)."""
        for record in batch:
            sys.stderr.write(_to_json_line(record))
        sys.stderr.flush()


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
        self._stream: Any = None

    async def start(self) -> None:
        """Open file and start worker."""
        self._stream = self.filepath.open("a", buffering=1)
        await super().start()

    async def stop(self) -> None:
        """Stop worker and close file."""
        await super().stop()
        if self._stream:
            self._stream.close()

    async def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        """Write batch to file."""
        if not self._stream:
            return

        for record in batch:
            self._stream.write(_to_json_line(record))
        self._stream.flush()


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


class _QueueRenderer:
    """Structlog processor that routes events to async queue handlers."""

    def __init__(self, handlers: list[AsyncQueueHandler]) -> None:
        self._handlers = handlers

    def __call__(self, logger: Any, name: str, event_dict: EventDict) -> str:
        """Emit the event to every registered handler."""
        for queue_handler in self._handlers:
            queue_handler.emit(event_dict)
        return ""


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
            _QueueRenderer(handlers),
        ],
        context_class=dict,
        logger_factory=structlog.ReturnLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    logging.basicConfig(level=level, stream=sys.stderr, force=True)

    return handlers[0]
