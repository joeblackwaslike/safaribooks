"""Async HTTP client for the O'Reilly Learning API."""


import json
import logging
import re
import stat
import warnings
from typing import Any

import httpx

from safaribooks.core.config import AppConfig
from safaribooks.core.constants import (
    HEADERS,
    PROFILE_URL,
)
from safaribooks.core.exceptions import ApiError, AuthenticationError, CookieError
from safaribooks.core.rate_limit import TokenBucketRateLimiter
from safaribooks.core.retry import RetryConfig, retry_request

logger = logging.getLogger(__name__)

_COOKIE_FLOAT_MAX_AGE_RE = re.compile(r"(max-age=\d*\.\d*)", re.IGNORECASE)

_MAX_REDIRECTS = 10


class ApiClient:
    """Async HTTP client for the O'Reilly Learning API.

    Wraps :mod:`httpx` with cookie management, automatic redirect
    handling, and tenacity-based retry for transient failures.

    Must be used as an async context manager::

        async with ApiClient(config) as client:
            response = await client.get(url)
    """

    def __init__(self, config: AppConfig, retry_config: RetryConfig | None = None) -> None:
        """Initialise the client with the given application configuration."""
        self.config = config
        self._retry_config = retry_config
        self._cookie_dict = self._load_cookies()
        self._client: httpx.AsyncClient | None = None
        self._cookie_refresh_attempted = False
        self._rate_limiter = TokenBucketRateLimiter(
            rate=config.rate_limit,
            burst=config.rate_burst,
        )

    async def __aenter__(self) -> "ApiClient":
        """Create the underlying async HTTP client."""
        self._client = httpx.AsyncClient(
            headers=HEADERS,
            cookies=httpx.Cookies(self._cookie_dict),
            follow_redirects=False,
            verify=not self.config.ssl_skip,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Close the underlying async HTTP client."""
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

    # ------------------------------------------------------------------
    # Public request methods
    # ------------------------------------------------------------------

    async def get(
        self,
        url: str,
        *,
        stream: bool = False,
        update_cookies: bool = True,
    ) -> httpx.Response:
        """Make a GET request with cookie management and redirect handling.

        Parameters
        ----------
        url:
            The URL to request.
        stream:
            If ``True``, the response body is not immediately downloaded.
        update_cookies:
            If ``True`` (default), update client cookies from the response.

        Returns:
        -------
        httpx.Response
            The final response after following redirects.

        Raises:
        ------
        ApiError
            On connection errors or request failures.
        AuthenticationError
            When the session is expired and cannot be refreshed.

        """
        return await self._request(url, is_post=False, stream=stream, update_cookies=update_cookies)

    async def post(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make a POST request with cookie management.

        Parameters
        ----------
        url:
            The URL to POST to.
        data:
            Form-encoded data payload.
        json_payload:
            JSON-encoded payload (mutually exclusive with *data*).

        Returns:
        -------
        httpx.Response
            The response.

        Raises:
        ------
        ApiError
            On connection errors or request failures.
        AuthenticationError
            When the session is expired and cannot be refreshed.

        """
        return await self._request(url, is_post=True, data=data, json_payload=json_payload)

    async def get_json(self, url: str) -> dict[str, Any]:
        """GET a URL and parse the JSON response.

        Combines :meth:`get` with JSON parsing and validation.

        Raises:
        ------
        ApiError
            When the response is not valid JSON or the status is non-200.

        """
        response = await self.get(url)
        return self.parse_json_response(response)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def check_login(self) -> bool:
        """Verify that the current cookies grant access to the profile page.

        Returns:
        -------
        bool
            ``True`` when the session is valid.

        Raises:
        ------
        AuthenticationError
            When the session cannot access the profile.

        """
        response = await self.get(PROFILE_URL)

        if response.status_code != 200 or "/login" in str(response.url):
            raise AuthenticationError("Unable to access profile page -- authentication failed.")

        if 'user_type":"Expired"' in response.text:
            raise AuthenticationError("Account subscription has expired.")

        logger.info("Successfully authenticated.")
        return True

    def do_login(self, email: str, password: str) -> None:
        """Attempt direct email/password login (deprecated).

        O'Reilly has blocked direct credential-based login.  This method
        exists only for backwards compatibility and will always raise a
        deprecation warning directing users to cookie-based auth.
        """
        warnings.warn(
            "Direct email/password login is no longer supported by O'Reilly. "
            "Use cookie-based authentication instead: safaribooks retrieve-cookies",
            DeprecationWarning,
            stacklevel=2,
        )
        logger.warning(
            "do_login() called but direct login is blocked by O'Reilly. "
            "Use cookie-based authentication instead."
        )

    @staticmethod
    def parse_cred(cred: str) -> tuple[str, str] | None:
        """Parse an ``email:password`` credential string.

        Returns:
        -------
        tuple[str, str] | None
            ``(email, password)`` on success, ``None`` if the format is invalid.

        """
        if ":" not in cred:
            return None

        sep = cred.index(":")
        email = cred[:sep].strip("'").strip('"')
        if "@" not in email:
            return None

        password = cred[sep + 1 :]
        return email, password

    # ------------------------------------------------------------------
    # Cookie management
    # ------------------------------------------------------------------

    def save_cookies(self) -> None:
        """Persist current client cookies back to the cookies file."""
        cookies_path = self.config.cookies_file
        cookies_path.parent.mkdir(parents=True, exist_ok=True)
        cookies_path.write_text(
            json.dumps(dict(self.client.cookies), indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            cookies_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            logger.debug("Could not restrict permissions on %s", cookies_path)
        logger.debug("Saved cookies to %s", cookies_path)

    def _handle_cookie_update(self, set_cookie_headers: list[str]) -> None:
        """Update client cookies from ``Set-Cookie`` response headers.

        Handles the O'Reilly API quirk where ``max-age`` values can be
        floats, which the standard cookie parser rejects.
        """
        for morsel in set_cookie_headers:
            if _COOKIE_FLOAT_MAX_AGE_RE.search(morsel):
                try:
                    cookie_pair = morsel.split(";")[0]
                    key, value = cookie_pair.split("=", maxsplit=1)
                    self.client.cookies.set(key.strip(), value.strip())
                except ValueError:
                    logger.debug("Malformed Set-Cookie morsel: %s", morsel)

    def _try_cookie_refresh(self) -> bool:
        """Try to reload cookies from disk if the session has expired.

        Returns ``True`` if fresh cookies were loaded successfully.
        Raises :class:`AuthenticationError` if refresh is not possible.
        """
        if self._cookie_refresh_attempted:
            raise AuthenticationError(
                "Session expired and cookie refresh already attempted. "
                "Re-extract cookies with: safaribooks retrieve-cookies"
            )
        self._cookie_refresh_attempted = True

        cookies_path = self.config.cookies_file
        if not cookies_path.is_file():
            raise AuthenticationError(
                f"Session expired and cookie file not found: {cookies_path}\n"
                "Re-extract cookies with: safaribooks retrieve-cookies"
            )

        try:
            raw = cookies_path.read_text(encoding="utf-8")
            fresh = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            raise AuthenticationError(
                f"Session expired and could not reload cookies: {exc}"
            ) from exc

        if not isinstance(fresh, dict):
            raise AuthenticationError("Cookie file does not contain a JSON object.")

        if fresh != dict(self.client.cookies):
            self.client.cookies.update(fresh)
            logger.info("Reloaded cookies from disk.")
            return True

        raise AuthenticationError(
            "Session expired. Cookies on disk are identical to the expired session.\n"
            "Re-extract cookies with: safaribooks retrieve-cookies"
        )

    # ------------------------------------------------------------------
    # JSON response parsing
    # ------------------------------------------------------------------

    def parse_json_response(self, response: httpx.Response) -> dict[str, Any]:
        """Parse a JSON API response with validation.

        Parameters
        ----------
        response:
            The HTTP response to parse.

        Returns:
        -------
        dict[str, Any]
            The parsed JSON body.

        Raises:
        ------
        ApiError
            When the response status is non-200, the content type is
            unexpected, or the body is not valid JSON.

        """
        if response.status_code != 200:
            msg = f"API returned status {response.status_code}: {response.text[:500]}"
            logger.warning(msg)
            raise ApiError(msg)

        content_type = response.headers.get("Content-Type", "")
        if "json" not in content_type and "javascript" not in content_type:
            msg = f"Unexpected content type {content_type!r}: {response.text[:500]}"
            logger.warning(msg)
            raise ApiError(msg)

        try:
            parsed = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            msg = f"JSON parse error: {response.text[:500]}"
            logger.warning(msg)
            raise ApiError(msg) from exc
        else:
            result: dict[str, Any] = parsed
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_cookies(self) -> dict[str, str]:
        """Load cookies from the configured JSON file and return as a dict.

        Called eagerly during ``__init__`` so that cookie errors surface
        before entering the async context manager.
        """
        cookies_path = self.config.cookies_file
        if not cookies_path.is_file():
            msg = (
                f"Cookie file not found: {cookies_path}\n"
                "Extract cookies with: safaribooks retrieve-cookies"
            )
            raise CookieError(msg)

        try:
            raw = cookies_path.read_text(encoding="utf-8")
            cookie_data: Any = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = (
                f"Cookie file is corrupted ({cookies_path}): {exc}\n"
                "Re-extract with: safaribooks retrieve-cookies"
            )
            raise CookieError(msg) from exc
        except OSError as exc:
            msg = f"Unable to read cookie file ({cookies_path}): {exc}"
            raise CookieError(msg) from exc

        if not isinstance(cookie_data, dict):
            msg = f"Expected a JSON object in {cookies_path}, got {type(cookie_data).__name__}"
            raise CookieError(msg)

        logger.debug("Loaded %d cookies from %s", len(cookie_data), cookies_path)
        return cookie_data

    # ------------------------------------------------------------------
    # Internal request machinery
    # ------------------------------------------------------------------

    async def _request(
        self,
        url: str,
        *,
        is_post: bool = False,
        data: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        stream: bool = False,
        update_cookies: bool = True,
        _redirect_count: int = 0,
    ) -> httpx.Response:
        """Core request method with redirect, cookie, and auth handling."""
        if _redirect_count > _MAX_REDIRECTS:
            msg = f"Too many redirects ({_MAX_REDIRECTS}) for {url}"
            raise ApiError(msg)

        method = "POST" if is_post else "GET"
        kwargs: dict[str, Any] = {}
        if is_post:
            if json_payload is not None:
                kwargs["json"] = json_payload
            elif data is not None:
                kwargs["data"] = data
        if stream:
            kwargs["stream"] = True

        response: httpx.Response = await self._do_request(method, url, **kwargs)

        if update_cookies:
            self._handle_cookie_update(response.headers.get_list("set-cookie"))

        logger.debug(
            "%s %s -> %d",
            method,
            url,
            response.status_code,
        )

        retryable = (self._retry_config or RetryConfig()).retryable_status_codes
        if response.status_code in retryable:
            response.raise_for_status()

        # Handle auth failures -- attempt cookie refresh then retry once.
        redirect_location = response.headers.get("location", "")
        is_auth_failure = response.status_code in (401, 403) or (
            response.is_redirect and "/login" in redirect_location
        )
        if is_auth_failure and self._try_cookie_refresh():
            self._cookie_refresh_attempted = False
            return await self._request(
                url,
                is_post=is_post,
                data=data,
                json_payload=json_payload,
                stream=stream,
                update_cookies=update_cookies,
                _redirect_count=_redirect_count,
            )

        # Follow redirects manually (mirrors legacy behaviour).
        if response.is_redirect and redirect_location:
            next_url = str(response.url.join(redirect_location))
            return await self._request(
                next_url,
                is_post=is_post,
                stream=stream,
                update_cookies=update_cookies,
                _redirect_count=_redirect_count + 1,
            )

        return response

    @retry_request()
    async def _do_request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Execute a single HTTP request with tenacity retry on transient errors."""
        await self._rate_limiter.acquire()
        try:
            return await self.client.request(method, url, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout):
            raise
        except httpx.HTTPError as exc:
            msg = f"Request failed for {url}: {exc}"
            raise ApiError(msg) from exc
