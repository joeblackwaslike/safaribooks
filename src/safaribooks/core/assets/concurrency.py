"""Bounded-concurrency runner for asset download coroutines."""

import asyncio
import logging
from collections.abc import Callable, Coroutine

logger = logging.getLogger(__name__)

_DEFAULT_WORKERS = 4


class _LimitedRunner:
    """Run download coroutines under a shared semaphore with progress reporting."""

    def __init__(
        self,
        *,
        semaphore: asyncio.Semaphore,
        total: int,
        progress_callback: Callable[[int, int], None] | None,
    ) -> None:
        self._semaphore = semaphore
        self._total = total
        self._progress_callback = progress_callback
        self._completed = 0

    async def run(
        self,
        coro: Coroutine[object, object, str | None],
    ) -> str | None:
        """Await *coro* under the semaphore, then report progress."""
        async with self._semaphore:
            outcome = await coro
        self._completed += 1
        if self._progress_callback is not None:
            self._progress_callback(self._total, self._completed)
        return outcome

    def collect_successful(self, gathered: list[str | None | BaseException]) -> list[str]:
        """Filter gathered outcomes into successful filenames, logging exceptions."""
        collected: list[str] = []
        for outcome in gathered:
            if isinstance(outcome, BaseException):
                logger.exception("Download worker raised an exception", exc_info=outcome)
            elif outcome is not None:
                collected.append(outcome)
        return collected


async def _parallel_download(
    coros: list[Coroutine[object, object, str | None]],
    *,
    max_concurrent: int = _DEFAULT_WORKERS,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[str]:
    """Run coroutines concurrently with a semaphore limit.

    Parameters
    ----------
    coros:
        A list of coroutines that each return a filename or ``None``.
    max_concurrent:
        Maximum number of concurrent downloads.
    progress_callback:
        Optional ``(total, completed)`` callback invoked after each item.

    Returns:
    -------
    list[str]
        Filenames of successfully downloaded assets.

    """
    if not coros:
        return []

    runner = _LimitedRunner(
        semaphore=asyncio.Semaphore(max_concurrent),
        total=len(coros),
        progress_callback=progress_callback,
    )
    gathered = await asyncio.gather(
        *[runner.run(coro) for coro in coros],
        return_exceptions=True,
    )
    return runner.collect_successful(gathered)
