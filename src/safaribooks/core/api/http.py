"""HTTP request machinery: GET/POST, JSON parsing, retries, and redirects."""

import json
import logging
from typing import Any, NamedTuple

import httpx

from safaribooks.core.api.connection import ConnectionMixin
from safaribooks.core.exceptions import ApiError
from safaribooks.core.retry import RetryConfig, retry_request

logger = logging.getLogger(__name__)

_MAX_REDIRECTS = 10
_HTTP_OK = 200
_ERROR_BODY_PREVIEW = 500
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


def _is_auth_failure(response: httpx.Response, redirect_location: str) -> bool:
    """Return ``True`` when the response indicates an authentication failure."""
    if response.status_code in _AUTH_FAILURE_CODES:
        return True
    return response.is_redirect and "/login" in redirect_location


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


class HttpMixin(ConnectionMixin):
    """GET/POST requests with cookie management, redirects, retry, and JSON parsing."""

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
        form_data: dict[str, Any] | None = None,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make a POST request with cookie management.

        Parameters
        ----------
        url:
            The URL to POST to.
        form_data:
            Form-encoded data payload.
        json_payload:
            JSON-encoded payload (mutually exclusive with *form_data*).

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
            payload=_PostPayload(form_data=form_data, json_payload=json_payload),
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
