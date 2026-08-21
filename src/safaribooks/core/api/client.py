"""The composed ``ApiClient`` -- combines every concern mixin into one class."""

from safaribooks.core.api.auth import AuthMixin
from safaribooks.core.api.http import HttpMixin
from safaribooks.core.api.keepalive import KeepaliveMixin
from safaribooks.core.api.session_cookies import CookieMixin


class _SessionMixin(AuthMixin, KeepaliveMixin):
    """Auth checks and keepalive pings: both periodic calls through ``get``."""


class ApiClient(HttpMixin, CookieMixin, _SessionMixin):
    """Async HTTP client for the O'Reilly Learning API.

    Wraps :mod:`httpx` with cookie management, automatic redirect
    handling, and tenacity-based retry for transient failures.

    Must be used as an async context manager::

        async with ApiClient(config) as client:
            response = await client.get(url)

    Composed from concern-based mixins (connection lifecycle, HTTP
    requests, auth, session-cookie management, keepalive) so that no
    single class carries more than a handful of methods; see
    ``safaribooks.core.api._state.ApiClientState`` for how the mixins
    are typed against each other.
    """
