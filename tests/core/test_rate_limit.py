"""Tests for safaribooks.core.rate_limit."""

import asyncio
import time

from safaribooks.core.rate_limit import TokenBucketRateLimiter


class TestTokenBucketDisabled:
    async def test_disabled_when_rate_zero(self):
        limiter = TokenBucketRateLimiter(rate=0, burst=2)
        start = time.monotonic()
        for _ in range(100):
            await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    async def test_disabled_when_rate_negative(self):
        limiter = TokenBucketRateLimiter(rate=-1, burst=2)
        await limiter.acquire()


class TestTokenBucketBurst:
    async def test_initial_burst_no_wait(self):
        limiter = TokenBucketRateLimiter(rate=10, burst=3)
        start = time.monotonic()
        for _ in range(3):
            await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05

    async def test_blocks_after_burst_exhausted(self):
        limiter = TokenBucketRateLimiter(rate=10, burst=1)
        await limiter.acquire()
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.05


class TestTokenBucketRate:
    async def test_rate_limits_throughput(self):
        limiter = TokenBucketRateLimiter(rate=20, burst=1)
        await limiter.acquire()
        start = time.monotonic()
        for _ in range(5):
            await limiter.acquire()
        elapsed = time.monotonic() - start
        assert 0.15 <= elapsed <= 0.8


class TestTokenBucketProperties:
    def test_rate_property(self):
        limiter = TokenBucketRateLimiter(rate=5.0, burst=3)
        assert limiter.rate == 5.0

    def test_burst_property(self):
        limiter = TokenBucketRateLimiter(rate=5.0, burst=3)
        assert limiter.burst == 3


class TestTokenBucketConcurrency:
    async def test_concurrent_acquires_all_complete(self):
        limiter = TokenBucketRateLimiter(rate=10, burst=2)
        results: list[int] = []

        async def worker(worker_id: int) -> None:
            await limiter.acquire()
            results.append(worker_id)

        await asyncio.gather(*[worker(i) for i in range(5)])
        assert len(results) == 5
