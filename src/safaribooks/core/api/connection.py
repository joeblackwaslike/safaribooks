"""Connection lifecycle: construction, async context manager, and the httpx client."""

import asyncio
from typing import Any, Self

import httpx

from safaribooks.core.api._state import ApiClientState
from safaribooks.core.config import AppConfig
from safaribooks.core.constants import HEADERS
from safaribooks.core.rate_limit import TokenBucketRateLimiter
from safaribooks.core.retry import RetryConfig

_DEFAULT_TIMEOUT = 30.0
_CONNECT_TIMEOUT = 10.0


class ConnectionMixin(ApiClientState):
    """Owns the underlying ``httpx.AsyncClient`` and instance state."""

    def __init__(self, config: AppConfig, retry_config: RetryConfig | None = None) -> None:
        """Initialise the client with the given application configuration."""
        self.config = config
        self._retry_config = retry_config
        self._cookie_dict = self._load_cookies()
        self._client: httpx.AsyncClient | None = None
        self._cookie_refresh_attempted: bool = False
        self._keepalive_task: asyncio.Task[None] | None = None
        self._rate_limiter = TokenBucketRateLimiter(
            rate=config.rate_limit,
            burst=config.rate_burst,
        )

    async def __aenter__(self) -> Self:
        """Create the underlying async HTTP client."""
        self._client = httpx.AsyncClient(
            headers=HEADERS,
            cookies=httpx.Cookies(self._cookie_dict),
            follow_redirects=False,
            verify=not self.config.ssl_skip,
            timeout=httpx.Timeout(_DEFAULT_TIMEOUT, connect=_CONNECT_TIMEOUT),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Stop keepalive and close the underlying async HTTP client."""
        await self.stop_keepalive()
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Return the active client, raising if not inside a context manager."""
        if self._client is None:
            msg = "ApiClient must be used as an async context manager"
            raise RuntimeError(msg)
        return self._client
