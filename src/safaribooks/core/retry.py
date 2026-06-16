"""Tenacity retry helpers for HTTP requests with rate-limit awareness."""

import functools
import logging
import random
from collections.abc import Callable
from typing import Any

import httpx
import tenacity
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_RETRYABLE_NETWORK_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.PoolTimeout,
)

_DEFAULT_RETRYABLE_STATUS_CODE_LIST = (408, 429, 500, 502, 503, 504)
_DEFAULT_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset(
    _DEFAULT_RETRYABLE_STATUS_CODE_LIST,
)

_RATE_LIMIT_STATUS_CODES = (429, 503)
_BACKOFF_BASE = 2
_JITTER_SPREAD = 0.25
_ASSET_MAX_ATTEMPTS = 3
_ASSET_BASE_DELAY = 0.5
_ASSET_MAX_DELAY = 30.0
_RETRY_AFTER_HEADER = "retry-after"
_UNPARSEABLE_RETRY_AFTER_MSG = "Unparseable Retry-After header: %r"


class RetryConfig(BaseModel):
    """Configuration for HTTP retry behaviour."""

    max_attempts: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True
    retryable_status_codes: frozenset[int] = _DEFAULT_RETRYABLE_STATUS_CODES
    rate_limit_multiplier: float = 2.0


def is_retryable_error(
    exc: BaseException,
    retryable_status_codes: frozenset[int] = _DEFAULT_RETRYABLE_STATUS_CODES,
) -> bool:
    """Tenacity retry predicate for transient HTTP errors.

    ``retryable_status_codes`` defaults to the module-level set; pass a custom
    set (e.g. from a :class:`RetryConfig`) so caller configuration is honoured.
    """
    if isinstance(exc, _RETRYABLE_NETWORK_ERRORS):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in retryable_status_codes
    return False


def _make_retry_predicate(cfg: "RetryConfig") -> Callable[[BaseException], bool]:
    """Build a tenacity predicate bound to ``cfg``'s retryable status codes."""
    return functools.partial(
        is_retryable_error,
        retryable_status_codes=cfg.retryable_status_codes,
    )


class _WaitFunc:
    """Tenacity wait callable closed over a :class:`RetryConfig`."""

    def __init__(self, config: RetryConfig) -> None:
        self._config = config

    def __call__(self, retry_state: tenacity.RetryCallState) -> float:
        """Compute wait time with Retry-After awareness and exponential backoff."""
        attempt = retry_state.attempt_number
        exc = self._exception(retry_state)

        if isinstance(exc, httpx.HTTPStatusError):
            retry_after_wait = self._retry_after_wait(exc, attempt)
            if retry_after_wait is not None:
                return retry_after_wait

        wait = self._backoff(attempt)
        if self._config.jitter:
            wait = self._apply_jitter(wait)
        return float(wait)

    def _exception(
        self,
        retry_state: tenacity.RetryCallState,
    ) -> BaseException | None:
        outcome = retry_state.outcome
        if outcome is None:
            return None
        return outcome.exception()

    def _backoff(self, attempt: int) -> float:
        """Capped exponential backoff for the given attempt number."""
        wait = self._config.base_delay * (_BACKOFF_BASE**attempt)
        return float(min(wait, self._config.max_delay))

    def _retry_after_wait(
        self,
        exc: httpx.HTTPStatusError,
        attempt: int,
    ) -> float | None:
        """Wait time derived from a ``Retry-After`` header, if usable.

        Returns ``None`` when the header is absent or unparseable so the caller
        falls back to exponential backoff.
        """
        retry_after = exc.response.headers.get(_RETRY_AFTER_HEADER)
        if retry_after is None:
            return None
        try:
            wait = float(retry_after)
        except ValueError:
            logger.warning(_UNPARSEABLE_RETRY_AFTER_MSG, retry_after)
            return None
        if exc.response.status_code in _RATE_LIMIT_STATUS_CODES:
            wait *= self._config.rate_limit_multiplier
        return min(wait, self._config.max_delay)

    def _apply_jitter(self, wait: float) -> float:
        """Apply symmetric jitter to a wait value."""
        spread = 1.0 + random.uniform(-_JITTER_SPREAD, _JITTER_SPREAD)  # noqa: S311
        return wait * spread


def _make_wait_func(config: RetryConfig) -> Callable[[tenacity.RetryCallState], float]:
    """Build a tenacity wait function closed over the given config."""
    return _WaitFunc(config)


def retry_request(config: RetryConfig | None = None) -> Callable[..., Any]:
    """Factory returning a tenacity retry decorator for API requests."""
    cfg = config or RetryConfig()
    return tenacity.retry(
        retry=tenacity.retry_if_exception(_make_retry_predicate(cfg)),
        wait=_make_wait_func(cfg),
        stop=tenacity.stop_after_attempt(cfg.max_attempts),
        before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def retry_asset(config: RetryConfig | None = None) -> Callable[..., Any]:
    """Lighter retry decorator tuned for asset downloads."""
    cfg = config or RetryConfig(
        max_attempts=_ASSET_MAX_ATTEMPTS,
        base_delay=_ASSET_BASE_DELAY,
        max_delay=_ASSET_MAX_DELAY,
    )
    return tenacity.retry(
        retry=tenacity.retry_if_exception(_make_retry_predicate(cfg)),
        wait=_make_wait_func(cfg),
        stop=tenacity.stop_after_attempt(cfg.max_attempts),
        before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
