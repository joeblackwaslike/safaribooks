"""Tests for safaribooks.core.retry."""

import functools
import logging
from collections.abc import Callable

import httpx
import pytest
import tenacity

from safaribooks.core.retry import (
    RetryConfig,
    _make_wait_func,
    is_retryable_error,
    retry_asset,
    retry_request,
)

# HTTP status codes used across the suite.
_HTTP_BAD_REQUEST = 400
_HTTP_NOT_FOUND = 404
_HTTP_TIMEOUT = 408
_HTTP_TOO_MANY = 429
_HTTP_SERVER_ERROR = 500
_HTTP_BAD_GATEWAY = 502
_HTTP_UNAVAILABLE = 503
_HTTP_GATEWAY_TIMEOUT = 504
_HTTP_TEAPOT = 418

_DEFAULT_RETRYABLE_CODES = frozenset((
    _HTTP_TIMEOUT,
    _HTTP_TOO_MANY,
    _HTTP_SERVER_ERROR,
    _HTTP_BAD_GATEWAY,
    _HTTP_UNAVAILABLE,
    _HTTP_GATEWAY_TIMEOUT,
))

# RetryConfig default field values.
_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_BASE_DELAY = 1.0
_DEFAULT_MAX_DELAY = 60.0
_DEFAULT_RATE_LIMIT_MULTIPLIER = 2.0

# Common numeric fixtures.
_NO_DELAY = float(0)
_JITTER_LOW = 0.75
_JITTER_HIGH = 1.25
_JITTER_SAMPLES = 50
_SEEDED_JITTER = 0.1
_RETRY_AFTER_URL = "https://example.com/resource"
_UNPARSEABLE_LOG_FRAGMENT = "Unparseable Retry-After"

# RetryConfig values reused by the wait-function tests.
_MULTIPLIER_DOUBLE = 2.0
_MULTIPLIER_TRIPLE = 3.0
_BASE_DELAY_DOUBLE = 2.0
_BASE_DELAY_HALF = 0.5
_MAX_DELAY_SHORT = 3.0
_MAX_DELAY_TINY = 5.0
_MAX_DELAY_TEN = 10.0
_MAX_DELAY_HUNDRED = 100.0
_ASSET_MAX_DELAY = 30.0
_RETURN_SENTINEL = 42

# Expected wait outputs (seconds).
_EXPECTED_DOUBLED_THREE = 6.0
_EXPECTED_TRIPLED_FOUR = 12.0
_EXPECTED_PLAIN_FIVE = 5.0
_EXPECTED_BACKOFF_TWO = 2.0
_EXPECTED_BACKOFF_FOUR = 4.0
_EXPECTED_BACKOFF_EIGHT = 8.0
# attempt-1 backoff (2.0) scaled by the seeded jitter factor (1 + 0.1).
_EXPECTED_SEEDED = _EXPECTED_BACKOFF_TWO * (1 + _SEEDED_JITTER)


def _make_status_error(
    status_code: int,
    headers: dict[str, str] | None = None,
) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError with the given status and headers."""
    request = httpx.Request("GET", _RETRY_AFTER_URL)
    response = httpx.Response(status_code, headers=headers or {}, request=request)
    return httpx.HTTPStatusError("error", request=request, response=response)


def _retry_state(
    exc: BaseException | None,
    attempt_number: int,
) -> tenacity.RetryCallState:
    """Construct a tenacity RetryCallState whose outcome holds the given exception."""
    state = tenacity.RetryCallState(retry_object=None, fn=None, args=(), kwargs={})
    state.attempt_number = attempt_number
    if exc is None:
        state.set_result(None)
    else:
        state.set_exception((type(exc), exc, exc.__traceback__))
    return state


def _compute_wait(cfg: RetryConfig, exc: BaseException | None, attempt: int) -> float:
    """Run the config's wait function against a synthetic retry state."""
    wait_func = _make_wait_func(cfg)
    return wait_func(_retry_state(exc, attempt))


def _fast_config(**overrides: object) -> RetryConfig:
    """RetryConfig with delays zeroed so retry tests do not sleep."""
    settings: dict[str, object] = {
        "jitter": False,
        "base_delay": _NO_DELAY,
        "max_delay": _NO_DELAY,
    }
    settings.update(overrides)
    return RetryConfig(**settings)  # type: ignore[arg-type]


class _CallCounter:
    """Mutable call counter shared with decorated target callables."""

    def __init__(self) -> None:
        self.count = 0

    def tick(self) -> None:
        """Record one invocation."""
        self.count += 1


def _raise_until(
    counter: _CallCounter,
    succeed_after: int,
    success_value: str,
) -> str:
    """Raise a transient error until ``succeed_after`` calls have occurred."""
    counter.tick()
    if counter.count < succeed_after:
        raise httpx.ConnectError("transient")
    return success_value


def _always_raise_connect(counter: _CallCounter) -> None:
    """Always raise a retryable connection error, counting each call."""
    counter.tick()
    raise httpx.ConnectError("permanent")


def _always_raise_status(counter: _CallCounter, status_code: int) -> None:
    """Always raise an HTTP status error, counting each call."""
    counter.tick()
    raise _make_status_error(status_code)


def _always_raise_read_timeout(counter: _CallCounter) -> None:
    """Always raise a read timeout, counting each call."""
    counter.tick()
    raise httpx.ReadTimeout("slow")


def _return_value(counter: _CallCounter, payload: object) -> object:
    """Return ``payload`` immediately, counting the single call."""
    counter.tick()
    return payload


def _decorate(
    decorator: Callable[..., Callable[..., object]],
    target: Callable[..., object],
) -> Callable[..., object]:
    """Apply a tenacity retry decorator while preserving the wrapped signature."""
    return decorator(functools.wraps(target)(target))


class TestRetryConfigDefaults:
    def test_default_attempts_and_jitter(self):
        cfg = RetryConfig()
        assert cfg.max_attempts == _DEFAULT_MAX_ATTEMPTS
        assert cfg.jitter is True
        assert cfg.retryable_status_codes == _DEFAULT_RETRYABLE_CODES

    def test_default_delays(self):
        cfg = RetryConfig()
        assert cfg.base_delay == pytest.approx(_DEFAULT_BASE_DELAY)
        assert cfg.max_delay == pytest.approx(_DEFAULT_MAX_DELAY)
        assert cfg.rate_limit_multiplier == pytest.approx(
            _DEFAULT_RATE_LIMIT_MULTIPLIER,
        )

    def test_override_values(self):
        cfg = RetryConfig(max_attempts=2, base_delay=0.1, jitter=False)
        assert cfg.max_attempts == 2
        assert cfg.base_delay == pytest.approx(0.1)
        assert cfg.jitter is False


class TestIsRetryableErrorNetwork:
    def test_connect_error_is_retryable(self):
        exc = httpx.ConnectError("boom")
        assert is_retryable_error(exc) is True

    def test_connect_timeout_is_retryable(self):
        assert is_retryable_error(httpx.ConnectTimeout("t")) is True

    def test_read_timeout_is_retryable(self):
        assert is_retryable_error(httpx.ReadTimeout("t")) is True

    def test_pool_timeout_is_retryable(self):
        assert is_retryable_error(httpx.PoolTimeout("t")) is True

    def test_write_timeout_not_in_retryable_set(self):
        # WriteTimeout is intentionally excluded from the retryable network errors.
        assert is_retryable_error(httpx.WriteTimeout("w")) is False

    def test_unrelated_exception_not_retryable(self):
        assert is_retryable_error(ValueError("nope")) is False


class TestIsRetryableErrorStatus:
    def test_retryable_status_code_is_retryable(self):
        for code in sorted(_DEFAULT_RETRYABLE_CODES):
            assert is_retryable_error(_make_status_error(code)) is True

    def test_non_retryable_status_code(self):
        assert is_retryable_error(_make_status_error(_HTTP_NOT_FOUND)) is False
        assert is_retryable_error(_make_status_error(_HTTP_BAD_REQUEST)) is False

    def test_custom_status_codes_honored(self):
        # An explicit code set overrides the module default.
        codes = frozenset((_HTTP_TEAPOT,))
        assert is_retryable_error(_make_status_error(_HTTP_TEAPOT), codes) is True
        assert is_retryable_error(_make_status_error(_HTTP_UNAVAILABLE), codes) is False


class TestWaitFuncRetryAfter:
    def test_too_many_applies_multiplier(self):
        cfg = RetryConfig(
            jitter=False,
            rate_limit_multiplier=_MULTIPLIER_DOUBLE,
            max_delay=_DEFAULT_MAX_DELAY,
        )
        exc = _make_status_error(_HTTP_TOO_MANY, {"retry-after": "3"})
        wait_seconds = _compute_wait(cfg, exc, attempt=1)
        assert wait_seconds == pytest.approx(_EXPECTED_DOUBLED_THREE)  # 3 * 2.0

    def test_unavailable_applies_multiplier(self):
        cfg = RetryConfig(
            jitter=False,
            rate_limit_multiplier=_MULTIPLIER_TRIPLE,
            max_delay=_MAX_DELAY_HUNDRED,
        )
        exc = _make_status_error(_HTTP_UNAVAILABLE, {"retry-after": "4"})
        wait_seconds = _compute_wait(cfg, exc, attempt=1)
        assert wait_seconds == pytest.approx(_EXPECTED_TRIPLED_FOUR)  # 4 * 3.0

    def test_non_rate_limit_no_multiplier(self):
        cfg = RetryConfig(
            jitter=False,
            rate_limit_multiplier=_MULTIPLIER_DOUBLE,
            max_delay=_DEFAULT_MAX_DELAY,
        )
        exc = _make_status_error(_HTTP_SERVER_ERROR, {"retry-after": "5"})
        wait_seconds = _compute_wait(cfg, exc, attempt=1)
        assert wait_seconds == pytest.approx(_EXPECTED_PLAIN_FIVE)  # no multiplier

    def test_retry_after_capped_at_max_delay(self):
        cfg = RetryConfig(
            jitter=False,
            rate_limit_multiplier=_MULTIPLIER_DOUBLE,
            max_delay=_MAX_DELAY_TEN,
        )
        exc = _make_status_error(_HTTP_TOO_MANY, {"retry-after": "100"})
        wait_seconds = _compute_wait(cfg, exc, attempt=1)
        assert wait_seconds == pytest.approx(_MAX_DELAY_TEN)  # min(200, 10)

    def test_unparseable_falls_back_to_backoff(self, caplog):
        cfg = RetryConfig(
            jitter=False,
            base_delay=_DEFAULT_BASE_DELAY,
            max_delay=_DEFAULT_MAX_DELAY,
        )
        headers = {"retry-after": "Wed, 21 Oct 2099 07:28:00 GMT"}
        exc = _make_status_error(_HTTP_TOO_MANY, headers)
        with caplog.at_level(logging.WARNING):
            wait_seconds = _compute_wait(cfg, exc, attempt=2)
        # falls back to base_delay * 2**attempt = 1 * 4 = 4, capped at max_delay
        assert wait_seconds == pytest.approx(_EXPECTED_BACKOFF_FOUR)
        assert any(_UNPARSEABLE_LOG_FRAGMENT in record.message for record in caplog.records)

    def test_unparseable_capped_at_max_delay(self):
        cfg = RetryConfig(
            jitter=False,
            base_delay=_DEFAULT_BASE_DELAY,
            max_delay=_MAX_DELAY_SHORT,
        )
        exc = _make_status_error(_HTTP_TOO_MANY, {"retry-after": "garbage"})
        wait_seconds = _compute_wait(cfg, exc, attempt=5)
        # base_delay * 2**5 = 32, but capped at 3.0
        assert wait_seconds == pytest.approx(_MAX_DELAY_SHORT)


class TestWaitFuncBackoff:
    def test_no_retry_after_header_exponential(self):
        cfg = RetryConfig(
            jitter=False,
            base_delay=_DEFAULT_BASE_DELAY,
            max_delay=_DEFAULT_MAX_DELAY,
        )
        exc = _make_status_error(_HTTP_SERVER_ERROR)  # retryable, no retry-after
        wait_seconds = _compute_wait(cfg, exc, attempt=3)
        assert wait_seconds == pytest.approx(_EXPECTED_BACKOFF_EIGHT)  # 1 * 2**3

    def test_network_error_uses_backoff(self):
        cfg = RetryConfig(
            jitter=False,
            base_delay=_BASE_DELAY_DOUBLE,
            max_delay=_MAX_DELAY_HUNDRED,
        )
        exc = httpx.ConnectError("down")
        wait_seconds = _compute_wait(cfg, exc, attempt=2)
        assert wait_seconds == pytest.approx(_EXPECTED_BACKOFF_EIGHT)  # 2 * 2**2

    def test_backoff_capped_at_max_delay(self):
        cfg = RetryConfig(
            jitter=False,
            base_delay=_DEFAULT_BASE_DELAY,
            max_delay=_MAX_DELAY_TINY,
        )
        exc = httpx.ConnectError("down")
        wait_seconds = _compute_wait(cfg, exc, attempt=10)
        assert wait_seconds == pytest.approx(_MAX_DELAY_TINY)

    def test_no_outcome_uses_backoff(self):
        cfg = RetryConfig(
            jitter=False,
            base_delay=_DEFAULT_BASE_DELAY,
            max_delay=_DEFAULT_MAX_DELAY,
        )
        wait_func = _make_wait_func(cfg)
        state = tenacity.RetryCallState(
            retry_object=None,
            fn=None,
            args=(),
            kwargs={},
        )
        state.attempt_number = 1
        # outcome left as None
        assert state.outcome is None
        assert wait_func(state) == pytest.approx(_EXPECTED_BACKOFF_TWO)  # 1 * 2**1

    def test_successful_outcome_uses_backoff(self):
        cfg = RetryConfig(
            jitter=False,
            base_delay=_DEFAULT_BASE_DELAY,
            max_delay=_DEFAULT_MAX_DELAY,
        )
        wait_seconds = _compute_wait(cfg, None, attempt=2)
        assert wait_seconds == pytest.approx(_EXPECTED_BACKOFF_FOUR)  # 1 * 2**2

    def test_non_status_exception_uses_backoff(self):
        cfg = RetryConfig(
            jitter=False,
            base_delay=_DEFAULT_BASE_DELAY,
            max_delay=_DEFAULT_MAX_DELAY,
        )
        exc = httpx.ReadTimeout("slow")
        wait_seconds = _compute_wait(cfg, exc, attempt=1)
        assert wait_seconds == pytest.approx(_EXPECTED_BACKOFF_TWO)

    def test_status_error_without_header_uses_backoff(self):
        cfg = RetryConfig(
            jitter=False,
            base_delay=_DEFAULT_BASE_DELAY,
            max_delay=_DEFAULT_MAX_DELAY,
        )
        exc = _make_status_error(_HTTP_UNAVAILABLE)  # rate-limit code, no header
        wait_seconds = _compute_wait(cfg, exc, attempt=1)
        assert wait_seconds == pytest.approx(_EXPECTED_BACKOFF_TWO)


class TestWaitFuncJitter:
    def test_jitter_within_bounds(self):
        cfg = RetryConfig(
            jitter=True,
            base_delay=_DEFAULT_BASE_DELAY,
            max_delay=_DEFAULT_MAX_DELAY,
        )
        exc = httpx.ConnectError("down")
        base = _EXPECTED_BACKOFF_FOUR  # base_delay * 2**2 for attempt 2
        for _ in range(_JITTER_SAMPLES):
            wait_seconds = _compute_wait(cfg, exc, attempt=2)
            assert base * _JITTER_LOW <= wait_seconds <= base * _JITTER_HIGH

    def test_jitter_deterministic_with_seeded_random(self, monkeypatch):
        cfg = RetryConfig(
            jitter=True,
            base_delay=_DEFAULT_BASE_DELAY,
            max_delay=_DEFAULT_MAX_DELAY,
        )
        monkeypatch.setattr(
            "safaribooks.core.retry.random.uniform",
            lambda low, high: _SEEDED_JITTER,
        )
        exc = httpx.ConnectError("down")
        wait_seconds = _compute_wait(cfg, exc, attempt=1)
        assert wait_seconds == pytest.approx(_EXPECTED_SEEDED)  # 2 * (1 + 0.1)


class TestRetryRequestDecorator:
    def test_eventually_succeeds_after_retries(self):
        decorator = retry_request(_fast_config(max_attempts=5))
        counter = _CallCounter()
        flaky = _decorate(
            decorator,
            functools.partial(_raise_until, counter, 3, "ok"),
        )
        assert flaky() == "ok"
        assert counter.count == 3

    def test_reraises_after_max_attempts(self):
        decorator = retry_request(_fast_config(max_attempts=2))
        counter = _CallCounter()
        always_fails = _decorate(
            decorator,
            functools.partial(_always_raise_connect, counter),
        )
        with pytest.raises(httpx.ConnectError):
            always_fails()
        assert counter.count == 2  # reraise=True, stops after max_attempts

    def test_non_retryable_error_raised_immediately(self):
        decorator = retry_request(_fast_config(max_attempts=5))
        counter = _CallCounter()
        bad_request = _decorate(
            decorator,
            functools.partial(_always_raise_status, counter, _HTTP_NOT_FOUND),
        )
        with pytest.raises(httpx.HTTPStatusError):
            bad_request()
        assert counter.count == 1  # not retried

    def test_default_config_when_none(self):
        decorator = retry_request()
        counter = _CallCounter()
        ok = _decorate(
            decorator,
            functools.partial(_return_value, counter, _RETURN_SENTINEL),
        )
        assert ok() == _RETURN_SENTINEL
        assert counter.count == 1

    def test_config_status_codes_retry_custom(self):
        # retry_request must build its predicate from the config's codes: a
        # custom 418 retries because it is listed.
        cfg = _fast_config(
            retryable_status_codes=frozenset((_HTTP_TEAPOT,)),
            max_attempts=3,
        )
        decorator = retry_request(cfg)
        counter = _CallCounter()
        teapot = _decorate(
            decorator,
            functools.partial(_always_raise_status, counter, _HTTP_TEAPOT),
        )
        with pytest.raises(httpx.HTTPStatusError):
            teapot()
        assert counter.count == 3  # 418 retried because config lists it

    def test_honors_config_status_codes_skips_default(self):
        # 503 is a module default but absent from the custom set, so it is not
        # retried.
        cfg = _fast_config(
            retryable_status_codes=frozenset((_HTTP_TEAPOT,)),
            max_attempts=3,
        )
        decorator = retry_request(cfg)
        counter = _CallCounter()
        unavailable = _decorate(
            decorator,
            functools.partial(_always_raise_status, counter, _HTTP_UNAVAILABLE),
        )
        with pytest.raises(httpx.HTTPStatusError):
            unavailable()
        assert counter.count == 1  # 503 not in the custom set -> not retried


class TestRetryAssetDecorator:
    def test_default_config_lighter_settings(self):
        cfg = RetryConfig(
            max_attempts=3,
            base_delay=_BASE_DELAY_HALF,
            max_delay=_ASSET_MAX_DELAY,
        )
        assert cfg.max_attempts == 3

    def test_asset_reraises_after_three_attempts(self):
        decorator = retry_asset(_fast_config(max_attempts=3))
        counter = _CallCounter()
        always_fails = _decorate(
            decorator,
            functools.partial(_always_raise_read_timeout, counter),
        )
        with pytest.raises(httpx.ReadTimeout):
            always_fails()
        assert counter.count == 3

    def test_asset_default_config_when_none(self):
        decorator = retry_asset()
        counter = _CallCounter()
        ok = _decorate(decorator, functools.partial(_return_value, counter, "asset"))
        assert ok() == "asset"
        assert counter.count == 1
