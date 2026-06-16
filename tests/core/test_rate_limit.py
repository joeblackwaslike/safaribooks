"""Tests for safaribooks.core.rate_limit."""

import asyncio
import time

from safaribooks.core.rate_limit import TokenBucketRateLimiter

_FAST_ELAPSED = 0.1
_BURST_ELAPSED = 0.05
_THROUGHPUT_MIN = 0.15
_THROUGHPUT_MAX = 0.8
_THROUGHPUT_RATE = 20
_PROPERTY_RATE = 5.0
_WORKER_COUNT = 5


async def _acquire_n(limiter: TokenBucketRateLimiter, count: int) -> None:
    """Acquire *count* tokens sequentially without a ``for``-``await`` loop."""
    remaining = count
    while remaining > 0:
        await limiter.acquire()
        remaining -= 1


async def _record_acquire(
    limiter: TokenBucketRateLimiter,
    completed: list[int],
    worker_id: int,
) -> None:
    """Acquire a token then append *worker_id* to *completed*."""
    await limiter.acquire()
    completed.append(worker_id)


class TestTokenBucketDisabled:
    async def test_disabled_when_rate_zero(self):
        limiter = TokenBucketRateLimiter(rate=0, burst=2)
        start = time.monotonic()
        await _acquire_n(limiter, 100)
        elapsed = time.monotonic() - start
        assert elapsed < _FAST_ELAPSED

    async def test_disabled_when_rate_negative(self):
        limiter = TokenBucketRateLimiter(rate=-1, burst=2)
        await limiter.acquire()


class TestTokenBucketBurst:
    async def test_initial_burst_no_wait(self):
        limiter = TokenBucketRateLimiter(rate=10, burst=3)
        start = time.monotonic()
        await _acquire_n(limiter, 3)
        elapsed = time.monotonic() - start
        assert elapsed < _BURST_ELAPSED

    async def test_blocks_after_burst_exhausted(self):
        limiter = TokenBucketRateLimiter(rate=10, burst=1)
        await limiter.acquire()
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= _BURST_ELAPSED


class TestTokenBucketRate:
    async def test_rate_limits_throughput(self):
        limiter = TokenBucketRateLimiter(rate=_THROUGHPUT_RATE, burst=1)
        await limiter.acquire()
        start = time.monotonic()
        await _acquire_n(limiter, 5)
        elapsed = time.monotonic() - start
        assert _THROUGHPUT_MIN <= elapsed <= _THROUGHPUT_MAX


class TestTokenBucketProperties:
    def test_rate_property(self):
        limiter = TokenBucketRateLimiter(rate=_PROPERTY_RATE, burst=3)
        assert limiter.rate == _PROPERTY_RATE

    def test_burst_property(self):
        limiter = TokenBucketRateLimiter(rate=_PROPERTY_RATE, burst=3)
        assert limiter.burst == 3


class TestTokenBucketConcurrency:
    async def test_concurrent_acquires_all_complete(self):
        limiter = TokenBucketRateLimiter(rate=10, burst=2)
        completed: list[int] = []

        await asyncio.gather(
            *[_record_acquire(limiter, completed, idx) for idx in range(_WORKER_COUNT)],
        )
        assert len(completed) == _WORKER_COUNT
