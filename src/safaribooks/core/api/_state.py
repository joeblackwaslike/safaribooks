"""Shared typing contract for ApiClient's concern-based mixins.

All shared *instance state* (config, the httpx client, the rate
limiter, keepalive task, etc.) is owned by ``ConnectionMixin`` alone,
and every other concern mixin subclasses it directly -- so attribute
types are inherited for real, with no ambiguity for mypy to resolve.

What a single, linear ancestor can't give the other mixins is each
other's *methods*: several concerns call into a sibling concern (the
HTTP mixin calls the cookie mixin's refresh methods; the keepalive and
auth mixins call the HTTP mixin's ``get``). Since every mixin is
combined into a single ``ApiClient`` via multiple inheritance (not
delegation) so that every method stays directly callable on ``self`` --
existing callers and tests reach private methods like
``client._try_cookie_refresh()`` directly -- mypy can't otherwise see
methods defined on a sibling mixin. Each mixin that calls into a
sibling explicitly subclasses this ``Protocol`` so type checking sees
that method without introducing any runtime behavior of its own.
"""

from typing import Protocol

import httpx


class ApiClientState(Protocol):
    """Cross-mixin method contract for ``ApiClient``.

    ``client`` is not listed here: it's a real property on
    ``ConnectionMixin``, which every other mixin inherits directly, so
    mypy already sees it without a protocol stub.
    """

    async def get(
        self,
        url: str,
        *,
        update_cookies: bool = True,
    ) -> httpx.Response:
        """Make a GET request with cookie management and redirect handling."""
        ...

    async def stop_keepalive(self) -> None:
        """Cancel the keepalive background task if running."""
        ...

    def _handle_cookie_update(self, set_cookie_headers: list[str]) -> None:
        """Update client cookies from ``Set-Cookie`` response headers."""
        ...

    def _try_cookie_refresh(self) -> bool:
        """Try to reload cookies from disk, then browser, if the session expired."""
        ...

    def _load_cookies(self) -> dict[str, str]:
        """Load cookies from the configured JSON file and return as a dict."""
        ...
