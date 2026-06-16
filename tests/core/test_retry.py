"""Tests for safaribooks.core.retry."""

import logging

import httpx
import tenacity

from safaribooks.core.retry import (
    RetryConfig,
    _make_wait_func,
    is_retryable_error,
    retry_asset,
    retry_request,
)


def _make_status_error(status_code: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError with the given status and headers."""
    request = httpx.Request("GET", "https://example.com/resource")
    response = httpx.Response(status_code, headers=headers or {}, request=request)
    return httpx.HTTPStatusError("error", request=request, response=response)


def _retry_state(exc: BaseException | None, attempt_number: int) -> tenacity.RetryCallState:
    """Construct a tenacity RetryCallState whose outcome holds the given exception."""
    state = tenacity.RetryCallState(
        retry_object=None, fn=None, args=(), kwargs={}
    )
    state.attempt_number = attempt_number
    if exc is None:
        # outcome with a successful (non-exception) result
        state.set_result(None)
    else:
        state.set_exception((type(exc), exc, exc.__traceback__))
    return state


class TestRetryConfigDefaults:
    def test_default_values(self):
        cfg = RetryConfig()
        assert cfg.max_attempts == 5
        assert cfg.base_delay == 1.0
        assert cfg.max_delay == 60.0
        assert cfg.jitter is True
        assert cfg.rate_limit_multiplier == 2.0
        assert cfg.retryable_status_codes == frozenset({408, 429, 500, 502, 503, 504})

    def test_override_values(self):
        cfg = RetryConfig(max_attempts=2, base_delay=0.1, jitter=False)
        assert cfg.max_attempts == 2
        assert cfg.base_delay == 0.1
        assert cfg.jitter is False


class TestIsRetryableError:
    def test_connect_error_is_retryable(self):
        exc = httpx.ConnectError("boom")
        assert is_retryable_error(exc) is True

    def test_connect_timeout_is_retryable(self):
        assert is_retryable_error(httpx.ConnectTimeout("t")) is True

    def test_read_timeout_is_retryable(self):
        assert is_retryable_error(httpx.ReadTimeout("t")) is True

    def test_pool_timeout_is_retryable(self):
        assert is_retryable_error(httpx.PoolTimeout("t")) is True

    def test_retryable_status_code_is_retryable(self):
        for code in (408, 429, 500, 502, 503, 504):
            assert is_retryable_error(_make_status_error(code)) is True

    def test_non_retryable_status_code(self):
        assert is_retryable_error(_make_status_error(404)) is False
        assert is_retryable_error(_make_status_error(400)) is False

    def test_unrelated_exception_not_retryable(self):
        assert is_retryable_error(ValueError("nope")) is False

    def test_write_timeout_not_in_retryable_set(self):
        # WriteTimeout is intentionally excluded from the retryable network errors.
        assert is_retryable_error(httpx.WriteTimeout("w")) is False


class TestWaitFuncRetryAfter:
    def test_retry_after_numeric_429_applies_multiplier(self):
        cfg = RetryConfig(jitter=False, rate_limit_multiplier=2.0, max_delay=60.0)
        wait = _make_wait_func(cfg)
        exc = _make_status_error(429, {"retry-after": "3"})
        result = wait(_retry_state(exc, attempt_number=1))
        assert result == 6.0  # 3 * 2.0

    def test_retry_after_numeric_503_applies_multiplier(self):
        cfg = RetryConfig(jitter=False, rate_limit_multiplier=3.0, max_delay=100.0)
        wait = _make_wait_func(cfg)
        exc = _make_status_error(503, {"retry-after": "4"})
        result = wait(_retry_state(exc, attempt_number=1))
        assert result == 12.0  # 4 * 3.0

    def test_retry_after_numeric_non_rate_limit_no_multiplier(self):
        cfg = RetryConfig(jitter=False, rate_limit_multiplier=2.0, max_delay=60.0)
        wait = _make_wait_func(cfg)
        exc = _make_status_error(500, {"retry-after": "5"})
        result = wait(_retry_state(exc, attempt_number=1))
        assert result == 5.0  # no multiplier for 500

    def test_retry_after_capped_at_max_delay(self):
        cfg = RetryConfig(jitter=False, rate_limit_multiplier=2.0, max_delay=10.0)
        wait = _make_wait_func(cfg)
        exc = _make_status_error(429, {"retry-after": "100"})
        result = wait(_retry_state(exc, attempt_number=1))
        assert result == 10.0  # min(200, 10)

    def test_retry_after_unparseable_falls_back_to_backoff(self, caplog):
        cfg = RetryConfig(jitter=False, base_delay=1.0, max_delay=60.0)
        wait = _make_wait_func(cfg)
        exc = _make_status_error(429, {"retry-after": "Wed, 21 Oct 2099 07:28:00 GMT"})
        with caplog.at_level(logging.WARNING):
            result = wait(_retry_state(exc, attempt_number=2))
        # falls back to base_delay * 2**attempt = 1 * 4 = 4, capped at max_delay
        assert result == 4.0
        assert any("Unparseable Retry-After" in r.message for r in caplog.records)

    def test_retry_after_unparseable_capped_at_max_delay(self):
        cfg = RetryConfig(jitter=False, base_delay=1.0, max_delay=3.0)
        wait = _make_wait_func(cfg)
        exc = _make_status_error(429, {"retry-after": "garbage"})
        result = wait(_retry_state(exc, attempt_number=5))
        # base_delay * 2**5 = 32, but capped at 3.0
        assert result == 3.0


class TestWaitFuncBackoff:
    def test_no_retry_after_header_exponential(self):
        cfg = RetryConfig(jitter=False, base_delay=1.0, max_delay=60.0)
        wait = _make_wait_func(cfg)
        exc = _make_status_error(500)  # retryable, no retry-after header
        result = wait(_retry_state(exc, attempt_number=3))
        assert result == 8.0  # 1 * 2**3

    def test_network_error_uses_backoff(self):
        cfg = RetryConfig(jitter=False, base_delay=2.0, max_delay=100.0)
        wait = _make_wait_func(cfg)
        exc = httpx.ConnectError("down")
        result = wait(_retry_state(exc, attempt_number=2))
        assert result == 8.0  # 2 * 2**2

    def test_backoff_capped_at_max_delay(self):
        cfg = RetryConfig(jitter=False, base_delay=1.0, max_delay=5.0)
        wait = _make_wait_func(cfg)
        exc = httpx.ConnectError("down")
        result = wait(_retry_state(exc, attempt_number=10))
        assert result == 5.0

    def test_no_outcome_uses_backoff(self):
        cfg = RetryConfig(jitter=False, base_delay=1.0, max_delay=60.0)
        wait = _make_wait_func(cfg)
        state = tenacity.RetryCallState(retry_object=None, fn=None, args=(), kwargs={})
        state.attempt_number = 1
        # outcome left as None
        assert state.outcome is None
        result = wait(state)
        assert result == 2.0  # 1 * 2**1

    def test_successful_outcome_no_exception_uses_backoff(self):
        cfg = RetryConfig(jitter=False, base_delay=1.0, max_delay=60.0)
        wait = _make_wait_func(cfg)
        result = wait(_retry_state(None, attempt_number=2))
        assert result == 4.0  # 1 * 2**2

    def test_non_status_exception_skips_retry_after_branch(self):
        cfg = RetryConfig(jitter=False, base_delay=1.0, max_delay=60.0)
        wait = _make_wait_func(cfg)
        exc = httpx.ReadTimeout("slow")
        result = wait(_retry_state(exc, attempt_number=1))
        assert result == 2.0

    def test_status_error_without_retry_after_header_uses_backoff(self):
        cfg = RetryConfig(jitter=False, base_delay=1.0, max_delay=60.0)
        wait = _make_wait_func(cfg)
        exc = _make_status_error(503)  # rate-limit code but no retry-after header
        result = wait(_retry_state(exc, attempt_number=1))
        assert result == 2.0


class TestWaitFuncJitter:
    def test_jitter_within_bounds(self):
        cfg = RetryConfig(jitter=True, base_delay=1.0, max_delay=60.0)
        wait = _make_wait_func(cfg)
        exc = httpx.ConnectError("down")
        base = 1.0 * (2**2)  # 4.0 for attempt 2
        for _ in range(50):
            result = wait(_retry_state(exc, attempt_number=2))
            assert base * 0.75 <= result <= base * 1.25

    def test_jitter_deterministic_with_seeded_random(self, monkeypatch):
        cfg = RetryConfig(jitter=True, base_delay=1.0, max_delay=60.0)
        wait = _make_wait_func(cfg)
        monkeypatch.setattr(
            "safaribooks.core.retry.random.uniform", lambda a, b: 0.1
        )
        exc = httpx.ConnectError("down")
        result = wait(_retry_state(exc, attempt_number=1))
        assert result == 2.0 * 1.1  # 1 * 2**1 * (1 + 0.1)


class TestRetryRequestDecorator:
    def test_eventually_succeeds_after_retryable_errors(self, monkeypatch):
        cfg = RetryConfig(max_attempts=5, jitter=False, base_delay=0.0, max_delay=0.0)
        decorator = retry_request(cfg)
        calls = {"n": 0}

        @decorator
        def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ConnectError("transient")
            return "ok"

        assert flaky() == "ok"
        assert calls["n"] == 3

    def test_reraises_after_max_attempts(self):
        cfg = RetryConfig(max_attempts=2, jitter=False, base_delay=0.0, max_delay=0.0)
        decorator = retry_request(cfg)
        calls = {"n": 0}

        @decorator
        def always_fails() -> None:
            calls["n"] += 1
            raise httpx.ConnectError("permanent")

        try:
            always_fails()
            raise AssertionError("expected ConnectError")
        except httpx.ConnectError:
            pass
        assert calls["n"] == 2  # reraise=True, stops after max_attempts

    def test_non_retryable_error_raised_immediately(self):
        cfg = RetryConfig(max_attempts=5, jitter=False, base_delay=0.0, max_delay=0.0)
        decorator = retry_request(cfg)
        calls = {"n": 0}

        @decorator
        def bad_request() -> None:
            calls["n"] += 1
            raise _make_status_error(404)

        try:
            bad_request()
            raise AssertionError("expected HTTPStatusError")
        except httpx.HTTPStatusError:
            pass
        assert calls["n"] == 1  # not retried

    def test_default_config_when_none(self):
        decorator = retry_request()
        calls = {"n": 0}

        @decorator
        def ok() -> int:
            calls["n"] += 1
            return 42

        assert ok() == 42
        assert calls["n"] == 1


class TestRetryAssetDecorator:
    def test_default_config_lighter_settings(self):
        cfg = RetryConfig(max_attempts=3, base_delay=0.5, max_delay=30.0)
        assert cfg.max_attempts == 3

    def test_asset_reraises_after_three_attempts(self):
        cfg = RetryConfig(max_attempts=3, jitter=False, base_delay=0.0, max_delay=0.0)
        decorator = retry_asset(cfg)
        calls = {"n": 0}

        @decorator
        def always_fails() -> None:
            calls["n"] += 1
            raise httpx.ReadTimeout("slow")

        try:
            always_fails()
            raise AssertionError("expected ReadTimeout")
        except httpx.ReadTimeout:
            pass
        assert calls["n"] == 3

    def test_asset_default_config_when_none(self):
        decorator = retry_asset()
        calls = {"n": 0}

        @decorator
        def ok() -> str:
            calls["n"] += 1
            return "asset"

        assert ok() == "asset"
        assert calls["n"] == 1
