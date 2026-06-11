"""Token bucket rate limiter using asyncio primitives."""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Async token bucket rate limiter.

    Tokens are added at a fixed rate up to a maximum burst capacity.
    Calling :meth:`acquire` blocks until a token is available.

    When *rate* is ``0`` or negative, the limiter is disabled and
    :meth:`acquire` returns immediately.
    """

    def __init__(self, rate: float = 1.0, burst: int = 2) -> None:
        """Initialise the limiter with the given *rate* and *burst* capacity."""
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()
        self._disabled = rate <= 0

    @property
    def rate(self) -> float:
        """Tokens added per second."""
        return self._rate

    @property
    def burst(self) -> int:
        """Maximum bucket capacity."""
        return self._burst

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def acquire(self) -> None:
        """Wait until a token is available, then consume one."""
        if self._disabled:
            return

        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            deficit = 1.0 - self._tokens
            wait_time = deficit / self._rate
            logger.debug("Rate limiter: waiting %.3fs for token", wait_time)

        await asyncio.sleep(wait_time)

        async with self._lock:
            self._refill()
            self._tokens = max(0.0, self._tokens - 1.0)
