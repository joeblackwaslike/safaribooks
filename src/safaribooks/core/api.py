"""Async HTTP client for the O'Reilly Learning API."""

import asyncio
import contextlib
import json
import logging
import re
import stat
import warnings
from pathlib import Path
from typing import Any, NamedTuple

import httpx

from safaribooks.core import cookies as cookie_mod
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
_HTTP_OK = 200
_ERROR_BODY_PREVIEW = 500
_DEFAULT_TIMEOUT = 30.0
_CONNECT_TIMEOUT = 10.0
_AUTH_FAILURE_CODES = (401, 403)
_TRANSIENT_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.PoolTimeout,
)


def _body_preview(response: httpx.Response) -> str:
    """Return a truncated preview of a response body for error messages."""
    return response.text[:_ERROR_BODY_PREVIEW]


def _parse_float_max_age_morsel(morsel: str) -> tuple[str, str] | None:
    """Parse a ``Set-Cookie`` morsel that carries a float ``max-age``.

    Returns the ``(key, value)`` pair for morsels matching the float
    ``max-age`` quirk, or ``None`` when the morsel does not match or is
    malformed (the latter case is logged at debug level).
    """
    if not _COOKIE_FLOAT_MAX_AGE_RE.search(morsel):
        return None
    cookie_pair = morsel.split(";")[0]
    try:
        cookie_key, cookie_value = cookie_pair.split("=", maxsplit=1)
    except ValueError:
        logger.debug("Malformed Set-Cookie morsel: %s", morsel)
        return None
    return cookie_key.strip(), cookie_value.strip()


def _read_cookie_file(cookies_path: Path) -> dict[str, str]:
    """Read and validate a JSON cookie file during session refresh.

    Raises :class:`AuthenticationError` when the file cannot be read or
    does not contain a JSON object.
    """
    try:
        raw_text = cookies_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AuthenticationError(f"Session expired and could not reload cookies: {exc}") from exc

    try:
        fresh = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AuthenticationError(f"Session expired and could not reload cookies: {exc}") from exc

    if not isinstance(fresh, dict):
        raise AuthenticationError("Cookie file does not contain a JSON object.")
    return fresh


def _load_cookie_dict(cookies_path: Path) -> dict[str, str]:
    """Read, parse, and validate the cookie file during initialisation.

    Raises :class:`CookieError` when the file cannot be read, is not valid
    JSON, or does not contain a JSON object.
    """
    try:
        raw_text = cookies_path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"Unable to read cookie file ({cookies_path}): {exc}"
        raise CookieError(msg) from exc

    try:
        cookie_data: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        msg = (
            f"Cookie file is corrupted ({cookies_path}): {exc}\n"
            "Re-extract with: safaribooks retrieve-cookies"
        )
        raise CookieError(msg) from exc

    if not isinstance(cookie_data, dict):
        msg = f"Expected a JSON object in {cookies_path}, got {type(cookie_data).__name__}"
        raise CookieError(msg)
    return cookie_data


class _PostPayload(NamedTuple):
    """Bundled POST body: form-encoded ``data`` and/or a JSON payload."""

    form_data: dict[str, Any] | None = None
    json_payload: dict[str, Any] | None = None

    def to_request_kwargs(self) -> dict[str, Any]:
        """Build the keyword arguments passed to the underlying HTTP request."""
        if self.json_payload is not None:
            return {"json": self.json_payload}
        if self.form_data is not None:
            return {"data": self.form_data}
        return {}


def _is_auth_failure(response: httpx.Response, redirect_location: str) -> bool:
    """Return ``True`` when the response indicates an authentication failure."""
    if response.status_code in _AUTH_FAILURE_CODES:
        return True
    return response.is_redirect and "/login" in redirect_location


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
        self._keepalive_task: asyncio.Task[None] | None = None
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

    # ------------------------------------------------------------------
    # Public request methods
    # ------------------------------------------------------------------

    async def get(
        self,
        url: str,
        *,
        update_cookies: bool = True,
    ) -> httpx.Response:
        """Make a GET request with cookie management and redirect handling.

        Parameters
        ----------
        url:
            The URL to request.
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
        return await self._request(url, is_post=False, update_cookies=update_cookies)

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
        return await self._request(
            url,
            is_post=True,
            payload=_PostPayload(form_data=data, json_payload=json_payload),
        )

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

        if response.status_code != _HTTP_OK or "/login" in str(response.url):
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

    @classmethod
    def parse_cred(cls, cred: str) -> tuple[str, str] | None:
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
            f"{json.dumps(dict(self.client.cookies), indent=2)}\n",
            encoding="utf-8",
        )
        try:
            cookies_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            logger.debug("Could not restrict permissions on %s", cookies_path)
        logger.debug("Saved cookies to %s", cookies_path)

    # ------------------------------------------------------------------
    # Session keepalive
    # ------------------------------------------------------------------

    async def start_keepalive(self) -> None:
        """Start a background task that pings the profile endpoint periodically."""
        interval = self.config.keepalive_interval
        if interval <= 0:
            return
        self._keepalive_task = asyncio.create_task(self._keepalive_loop(interval))
        logger.debug("Session keepalive started (every %ds).", interval)

    async def stop_keepalive(self) -> None:
        """Cancel the keepalive background task if running."""
        task = self._keepalive_task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            logger.debug("Session keepalive stopped.")

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
        preview = _body_preview(response)
        if response.status_code != _HTTP_OK:
            msg = f"API returned status {response.status_code}: {preview}"
            logger.warning(msg)
            raise ApiError(msg)

        content_type = response.headers.get("Content-Type", "")
        if "json" not in content_type and "javascript" not in content_type:
            msg = f"Unexpected content type {content_type!r}: {preview}"
            logger.warning(msg)
            raise ApiError(msg)

        try:
            parsed = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            msg = f"JSON parse error: {preview}"
            logger.warning(msg)
            raise ApiError(msg) from exc
        else:
            parsed_body: dict[str, Any] = parsed
            return parsed_body

    # ------------------------------------------------------------------
    # Cookie management
    # ------------------------------------------------------------------

    def _handle_cookie_update(self, set_cookie_headers: list[str]) -> None:
        """Update client cookies from ``Set-Cookie`` response headers.

        Handles the O'Reilly API quirk where ``max-age`` values can be
        floats, which the standard cookie parser rejects.  Persists to
        disk when cookies change so refreshed values survive crashes.
        """
        before = dict(self.client.cookies)
        for morsel in set_cookie_headers:
            parsed = _parse_float_max_age_morsel(morsel)
            if parsed is not None:
                cookie_key, cookie_value = parsed
                self.client.cookies.set(cookie_key, cookie_value)
        if dict(self.client.cookies) != before:
            self.save_cookies()

    def _try_cookie_refresh(self) -> bool:
        """Try to reload cookies from disk, then browser, if the session has expired.

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
            return self._refresh_from_browser_or_fail(
                f"Session expired and cookie file not found: {cookies_path}\n"
                "Re-extract cookies with: safaribooks retrieve-cookies"
            )

        fresh = _read_cookie_file(cookies_path)
        if fresh != dict(self.client.cookies):
            self.client.cookies.update(fresh)
            logger.info("Reloaded cookies from disk.")
            return True

        return self._refresh_from_browser_or_fail(
            "Session expired. Cookies on disk are identical to the expired session.\n"
            "Re-extract cookies with: safaribooks retrieve-cookies"
        )

    def _refresh_from_browser_or_fail(self, failure_message: str) -> bool:
        """Attempt a browser refresh, raising ``AuthenticationError`` on failure."""
        if self._try_browser_refresh():
            return True
        raise AuthenticationError(failure_message)

    def _try_browser_refresh(self) -> bool:
        """Try to re-extract cookies from the browser.

        Returns ``True`` if fresh cookies were loaded and differ from
        the current session.  Returns ``False`` when auto-refresh is
        disabled or extraction fails.
        """
        browser = self.config.auto_refresh_browser
        if not browser:
            return False

        try:
            cookie_set = cookie_mod.from_browser(browser)
        except (CookieError, Exception) as exc:
            logger.warning("Auto-refresh from %s failed: %s", browser, exc)
            return False

        fresh = cookie_set.cookies
        if fresh == dict(self.client.cookies):
            return False

        self.client.cookies.update(dict(fresh))
        self.save_cookies()
        logger.info("Auto-refreshed cookies from %s.", browser)
        return True

    async def _keepalive_loop(self, interval: int) -> None:
        """Periodically hit the profile endpoint to extend the session."""
        while True:
            await asyncio.sleep(interval)
            try:
                await self.get(PROFILE_URL, update_cookies=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("Keepalive ping failed: %s", exc)
            else:
                logger.debug("Keepalive ping OK.")

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

        cookie_data = _load_cookie_dict(cookies_path)
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
        payload: _PostPayload | None = None,
        update_cookies: bool = True,
        _redirect_count: int = 0,
    ) -> httpx.Response:
        """Core request method with redirect, cookie, and auth handling."""
        if _redirect_count > _MAX_REDIRECTS:
            msg = f"Too many redirects ({_MAX_REDIRECTS}) for {url}"
            raise ApiError(msg)

        method = "POST" if is_post else "GET"
        request_kwargs = payload.to_request_kwargs() if is_post and payload else {}
        response: httpx.Response = await self._do_request(method, url, **request_kwargs)

        if update_cookies:
            self._handle_cookie_update(response.headers.get_list("set-cookie"))

        logger.debug("%s %s -> %d", method, url, response.status_code)
        redirect_location = response.headers.get("location", "")

        # Handle auth failures -- attempt cookie refresh then retry once.
        if _is_auth_failure(response, redirect_location) and self._try_cookie_refresh():
            self._cookie_refresh_attempted = False
            return await self._request(
                url,
                is_post=is_post,
                payload=payload,
                update_cookies=update_cookies,
                _redirect_count=_redirect_count,
            )

        # Follow redirects manually (mirrors legacy behaviour).
        if response.is_redirect and redirect_location:
            return await self._request(
                str(response.url.join(redirect_location)),
                is_post=is_post,
                update_cookies=update_cookies,
                _redirect_count=_redirect_count + 1,
            )

        return response

    @retry_request()
    async def _do_request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Execute a single HTTP request with tenacity retry on transient errors."""
        await self._rate_limiter.acquire()
        try:
            response = await self.client.request(method, url, **kwargs)
        except _TRANSIENT_HTTP_ERRORS:
            raise
        except httpx.HTTPError as exc:
            msg = f"Request failed for {url}: {exc}"
            raise ApiError(msg) from exc

        # Raise on transient/retryable status codes *inside* the retried call so
        # tenacity (via is_retryable_error) sees the HTTPStatusError and retries,
        # honouring any Retry-After header. Auth codes (401/403) are not in the
        # retryable set, so they fall through to the cookie-refresh handling in
        # _request.
        retryable = (self._retry_config or RetryConfig()).retryable_status_codes
        if response.status_code in retryable:
            response.raise_for_status()
        return response
