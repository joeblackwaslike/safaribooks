"""Tenacity retry helpers for HTTP requests with rate-limit awareness."""


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


class RetryConfig(BaseModel):
    """Configuration for HTTP retry behaviour."""

    max_attempts: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True
    retryable_status_codes: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})
    rate_limit_multiplier: float = 2.0


def is_retryable_error(exc: BaseException) -> bool:
    """Tenacity retry predicate for transient HTTP errors."""
    if isinstance(exc, _RETRYABLE_NETWORK_ERRORS):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RetryConfig().retryable_status_codes
    return False


def _make_wait_func(config: RetryConfig) -> Callable[[tenacity.RetryCallState], float]:
    """Build a tenacity wait function closed over the given config."""

    def wait_for_retry(retry_state: tenacity.RetryCallState) -> float:
        """Compute wait time with Retry-After awareness and exponential backoff."""
        outcome = retry_state.outcome
        exc = outcome.exception() if outcome is not None else None
        attempt = retry_state.attempt_number

        if isinstance(exc, httpx.HTTPStatusError):
            retry_after = exc.response.headers.get("retry-after")
            if retry_after is not None:
                try:
                    wait = float(retry_after)
                except ValueError:
                    logger.warning("Unparseable Retry-After header: %r", retry_after)
                    wait = config.base_delay * (2**attempt)
                else:
                    if exc.response.status_code in (429, 503):
                        wait *= config.rate_limit_multiplier
                    return min(wait, config.max_delay)

        wait = config.base_delay * (2**attempt)
        wait = min(wait, config.max_delay)

        if config.jitter:
            wait *= 1.0 + random.uniform(-0.25, 0.25)  # noqa: S311

        return float(wait)

    return wait_for_retry


def retry_request(config: RetryConfig | None = None) -> Callable[..., Any]:
    """Factory returning a tenacity retry decorator for API requests."""
    cfg = config or RetryConfig()
    return tenacity.retry(
        retry=tenacity.retry_if_exception(is_retryable_error),
        wait=_make_wait_func(cfg),
        stop=tenacity.stop_after_attempt(cfg.max_attempts),
        before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def retry_asset(config: RetryConfig | None = None) -> Callable[..., Any]:
    """Lighter retry decorator tuned for asset downloads."""
    cfg = config or RetryConfig(max_attempts=3, base_delay=0.5, max_delay=30.0)
    return tenacity.retry(
        retry=tenacity.retry_if_exception(is_retryable_error),
        wait=_make_wait_func(cfg),
        stop=tenacity.stop_after_attempt(cfg.max_attempts),
        before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
