"""Tests for safaribooks.core.api — cookie refresh, persistence, and keepalive."""
# ruff: noqa: SLF001

import asyncio
import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from safaribooks.core.api import ApiClient
from safaribooks.core.config import AppConfig
from safaribooks.core.constants import PROFILE_URL
from safaribooks.core.exceptions import ApiError, AuthenticationError, CookieError
from safaribooks.core.models import CookieSet
from safaribooks.core.retry import RetryConfig

VALID_COOKIES = MappingProxyType({
    "groot_sessionid": "abc123",
    "jwt": "tok",
    "csrf_access_token": "csrf",
    "logged_in": "y",
})

FRESH_COOKIES = MappingProxyType({
    "groot_sessionid": "fresh999",
    "jwt": "newtok",
    "csrf_access_token": "newcsrf",
    "logged_in": "y",
})

_HTTP_OK = 200
_HTTP_FOUND = 302
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_SERVER_ERROR = 500
_HTTP_UNAVAILABLE = 503

_NO_RATE_LIMIT = float(0)
_DEFAULT_KEEPALIVE = 300
_CUSTOM_KEEPALIVE = 600

TEST_URL = "https://example.test/api/thing"

_IDENTICAL_MATCH = "identical to the expired session"
_RELOAD_FAIL_MATCH = "could not reload cookies"
_AUTH_FAILED_MATCH = "authentication failed"
_FROM_BROWSER = "safaribooks.core.api.cookie_mod.from_browser"

_VALID_DICT = dict(VALID_COOKIES)
_FRESH_DICT = dict(FRESH_COOKIES)


def _async_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(cookies=httpx.Cookies(_VALID_DICT))


def _client(config: AppConfig) -> ApiClient:
    return ApiClient(config)


def _make_client(
    tmp_path: Path,
    *,
    auto_refresh_browser: str | None = None,
    connected: bool = False,
) -> ApiClient:
    cookies_file = tmp_path / "cookies.json"
    cookies_file.write_text(json.dumps(_VALID_DICT), encoding="utf-8")
    config = AppConfig(
        cookies_file=cookies_file,
        auto_refresh_browser=auto_refresh_browser,
    )
    client = _client(config)
    if connected:
        client._client = _async_client()
    return client


def _make_real_config(tmp_path: Path, **overrides) -> AppConfig:
    """Build an AppConfig with rate limiting disabled for deterministic tests."""
    cookies_file = tmp_path / "cookies.json"
    cookies_file.write_text(json.dumps(_VALID_DICT), encoding="utf-8")
    settings = {"cookies_file": cookies_file, "rate_limit": _NO_RATE_LIMIT}
    settings.update(overrides)
    return AppConfig(**settings)


def _read_saved_cookies(client: ApiClient) -> dict[str, str]:
    return json.loads(client.config.cookies_file.read_text(encoding="utf-8"))


def _read_client_property(client: ApiClient) -> httpx.AsyncClient:
    return client.client


def _make_response(status: int, **kwargs) -> httpx.Response:
    return httpx.Response(status, **kwargs)


def _mock_get(**kwargs):
    return respx.get(TEST_URL).mock(**kwargs)


def _mock_profile(**kwargs):
    return respx.get(PROFILE_URL).mock(**kwargs)


def _mock_post(**kwargs):
    return respx.post(TEST_URL).mock(**kwargs)


async def _get(client: ApiClient, **kwargs) -> httpx.Response:
    return await client.get(TEST_URL, **kwargs)


@pytest.fixture
def plain_client(tmp_path: Path) -> ApiClient:
    """A non-browser client that has not entered an async-client session."""
    return _make_client(tmp_path)


@pytest.fixture
def connected_client(tmp_path: Path) -> ApiClient:
    """A non-browser client already inside an async-client session."""
    return _make_client(tmp_path, connected=True)


@pytest.fixture
async def live_client(tmp_path: Path):
    """A client backed by a real (respx-mocked) httpx session."""
    config = _make_real_config(tmp_path)
    async with ApiClient(config) as client:
        yield client


class TestTryCookieRefreshWithoutBrowser:
    def test_disk_reload_succeeds_when_cookies_differ(self, connected_client):
        client = connected_client
        cookies_file = client.config.cookies_file
        cookies_file.write_text(json.dumps(_FRESH_DICT), encoding="utf-8")

        assert client._try_cookie_refresh() is True
        assert dict(client.client.cookies) == _FRESH_DICT

    def test_raises_when_disk_identical_no_browser(self, connected_client):
        with pytest.raises(AuthenticationError, match=_IDENTICAL_MATCH):
            connected_client._try_cookie_refresh()

    def test_raises_on_second_attempt(self, connected_client):
        client = connected_client
        client._cookie_refresh_attempted = True

        with pytest.raises(AuthenticationError, match="already attempted"):
            client._try_cookie_refresh()


class TestTryCookieRefreshWithBrowser:
    def test_browser_refresh_when_disk_identical(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="chrome", connected=True)

        fresh_set = CookieSet(cookies=_FRESH_DICT)
        with patch(_FROM_BROWSER, return_value=fresh_set):
            assert client._try_cookie_refresh() is True

        assert dict(client.client.cookies) == _FRESH_DICT
        assert _read_saved_cookies(client) == _FRESH_DICT

    def test_browser_disabled_when_unconfigured(self, connected_client):
        with pytest.raises(AuthenticationError, match=_IDENTICAL_MATCH):
            connected_client._try_cookie_refresh()

    def test_browser_falls_through_on_error(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="chrome", connected=True)

        with (
            patch(
                _FROM_BROWSER,
                side_effect=CookieError("browser locked"),
            ),
            pytest.raises(AuthenticationError, match=_IDENTICAL_MATCH),
        ):
            client._try_cookie_refresh()

    def test_browser_refresh_when_cookie_file_missing(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="chrome", connected=True)
        client.config.cookies_file.unlink()

        fresh_set = CookieSet(cookies=_FRESH_DICT)
        with patch(_FROM_BROWSER, return_value=fresh_set):
            assert client._try_cookie_refresh() is True

        assert dict(client.client.cookies) == _FRESH_DICT


class TestTryCookieRefreshDiskErrors:
    def test_raises_when_file_missing_and_no_browser(self, connected_client):
        connected_client.config.cookies_file.unlink()

        with pytest.raises(AuthenticationError, match="cookie file not found"):
            connected_client._try_cookie_refresh()

    def test_raises_when_disk_json_corrupt(self, connected_client):
        connected_client.config.cookies_file.write_text("{broken", encoding="utf-8")

        with pytest.raises(AuthenticationError, match=_RELOAD_FAIL_MATCH):
            connected_client._try_cookie_refresh()

    def test_raises_when_disk_read_oserror(self, connected_client):
        with (
            patch.object(Path, "read_text", side_effect=OSError("io error")),
            pytest.raises(AuthenticationError, match=_RELOAD_FAIL_MATCH),
        ):
            connected_client._try_cookie_refresh()

    def test_raises_when_disk_not_a_dict(self, connected_client):
        connected_client.config.cookies_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        with pytest.raises(AuthenticationError, match="does not contain a JSON object"):
            connected_client._try_cookie_refresh()


class TestTryBrowserRefresh:
    def test_returns_false_when_disabled(self, connected_client):
        assert connected_client._try_browser_refresh() is False

    def test_returns_false_on_cookie_error(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="firefox", connected=True)

        with patch(
            _FROM_BROWSER,
            side_effect=CookieError("no cookies"),
        ):
            assert client._try_browser_refresh() is False

    def test_false_when_browser_cookies_same(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="chrome", connected=True)

        same_set = CookieSet(cookies=_VALID_DICT)
        with patch(_FROM_BROWSER, return_value=same_set):
            assert client._try_browser_refresh() is False

    def test_updates_and_saves_on_fresh_cookies(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="chrome", connected=True)

        fresh_set = CookieSet(cookies=_FRESH_DICT)
        with patch(_FROM_BROWSER, return_value=fresh_set):
            assert client._try_browser_refresh() is True

        assert dict(client.client.cookies) == _FRESH_DICT
        assert _read_saved_cookies(client) == _FRESH_DICT


class TestHandleCookieUpdatePersistence:
    def test_saves_when_cookies_change(self, connected_client):
        connected_client._handle_cookie_update(["newkey=newval; max-age=3600.0; path=/"])
        assert _read_saved_cookies(connected_client)["newkey"] == "newval"

    def test_does_not_save_when_no_change(self, connected_client):
        original_mtime = connected_client.config.cookies_file.stat().st_mtime
        connected_client._handle_cookie_update([])
        assert connected_client.config.cookies_file.stat().st_mtime == original_mtime


class TestAutoRefreshBrowserConfig:
    def test_defaults_to_none(self):
        config = AppConfig()
        assert config.auto_refresh_browser is None

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_AUTO_REFRESH_BROWSER", "chrome")
        config = AppConfig()
        assert config.auto_refresh_browser == "chrome"

    def test_from_env_firefox(self, monkeypatch):
        monkeypatch.setenv("SAFARI_AUTO_REFRESH_BROWSER", "firefox")
        config = AppConfig()
        assert config.auto_refresh_browser == "firefox"


class TestKeepaliveConfig:
    def test_default_interval(self):
        config = AppConfig()
        assert config.keepalive_interval == _DEFAULT_KEEPALIVE

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_KEEPALIVE_INTERVAL", "600")
        config = AppConfig()
        assert config.keepalive_interval == _CUSTOM_KEEPALIVE

    def test_disable_with_zero(self, monkeypatch):
        monkeypatch.setenv("SAFARI_KEEPALIVE_INTERVAL", "0")
        config = AppConfig()
        assert config.keepalive_interval == 0


class TestKeepalive:
    @pytest.mark.asyncio
    async def test_start_creates_task(self, connected_client):
        await connected_client.start_keepalive()
        assert connected_client._keepalive_task is not None
        assert not connected_client._keepalive_task.done()

        await connected_client.stop_keepalive()
        assert connected_client._keepalive_task.done()

    @pytest.mark.asyncio
    async def test_start_skipped_when_interval_zero(self, tmp_path):
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text(json.dumps(_VALID_DICT), encoding="utf-8")
        config = AppConfig(cookies_file=cookies_file, keepalive_interval=0)
        client = _client(config)
        client._client = _async_client()

        await client.start_keepalive()
        assert client._keepalive_task is None

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, connected_client):
        await connected_client.stop_keepalive()
        await connected_client.stop_keepalive()

    @pytest.mark.asyncio
    async def test_aexit_stops_keepalive(self, tmp_path):
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text(json.dumps(_VALID_DICT), encoding="utf-8")
        config = AppConfig(cookies_file=cookies_file)

        async with ApiClient(config) as client:
            await client.start_keepalive()
            task = client._keepalive_task

        assert task is not None
        assert task.done()


# ---------------------------------------------------------------------------
# __init__ / client property
# ---------------------------------------------------------------------------


class TestClientProperty:
    def test_raises_when_not_in_context(self, tmp_path):
        client = _make_client(tmp_path)
        with pytest.raises(RuntimeError, match="async context manager"):
            _read_client_property(client)

    @pytest.mark.asyncio
    async def test_aenter_creates_client(self, tmp_path):
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            assert isinstance(client.client, httpx.AsyncClient)
        assert client._client is None

    @pytest.mark.asyncio
    async def test_aexit_without_client_is_safe(self, tmp_path):
        # __aexit__ with no underlying client takes the early-exit branch.
        client = _make_client(tmp_path)
        assert client._client is None
        await client.__aexit__(None, None, None)
        assert client._client is None


# ---------------------------------------------------------------------------
# _load_cookies (called eagerly in __init__)
# ---------------------------------------------------------------------------


class TestLoadCookies:
    def test_raises_when_file_missing(self, tmp_path):
        config = AppConfig(cookies_file=tmp_path / "missing.json")
        with pytest.raises(CookieError, match="Cookie file not found"):
            _client(config)

    def test_raises_on_corrupt_json(self, tmp_path):
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text("{not valid json", encoding="utf-8")
        config = AppConfig(cookies_file=cookies_file)
        with pytest.raises(CookieError, match="corrupted"):
            _client(config)

    def test_raises_when_not_a_dict(self, tmp_path):
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text(json.dumps(["a", "b"]), encoding="utf-8")
        config = AppConfig(cookies_file=cookies_file)
        with pytest.raises(CookieError, match="Expected a JSON object"):
            _client(config)

    def test_raises_on_os_error(self, tmp_path):
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text(json.dumps(_VALID_DICT), encoding="utf-8")
        config = AppConfig(cookies_file=cookies_file)
        with (
            patch.object(Path, "read_text", side_effect=OSError("permission denied")),
            pytest.raises(CookieError, match="Unable to read cookie file"),
        ):
            _client(config)

    def test_loads_valid_cookies(self, tmp_path):
        client = _make_client(tmp_path)
        assert client._cookie_dict == _VALID_DICT


# ---------------------------------------------------------------------------
# Static credential parsing helper
# ---------------------------------------------------------------------------


class TestParseCred:
    def test_valid(self):
        assert ApiClient.parse_cred("user@x.com:pw") == ("user@x.com", "pw")

    def test_strips_quotes(self):
        assert ApiClient.parse_cred("'user@x.com':pw") == ("user@x.com", "pw")

    def test_no_colon_returns_none(self):
        assert ApiClient.parse_cred("noseparator") is None

    def test_no_at_returns_none(self):
        assert ApiClient.parse_cred("notanemail:pw") is None

    def test_password_may_contain_colon(self):
        assert ApiClient.parse_cred("user@x.com:pw:extra") == ("user@x.com", "pw:extra")


# ---------------------------------------------------------------------------
# Deprecated direct login path
# ---------------------------------------------------------------------------


class TestDoLogin:
    def test_warns_deprecation(self, plain_client):
        with pytest.warns(DeprecationWarning, match="no longer supported"):
            plain_client.do_login("a@b.com", "pw")


# ---------------------------------------------------------------------------
# save_cookies
# ---------------------------------------------------------------------------


class TestSaveCookies:
    def test_persists_cookies(self, plain_client):
        plain_client._client = httpx.AsyncClient(cookies=httpx.Cookies(_FRESH_DICT))
        plain_client.save_cookies()
        assert _read_saved_cookies(plain_client) == _FRESH_DICT

    def test_chmod_failure_is_tolerated(self, plain_client):
        plain_client._client = httpx.AsyncClient(cookies=httpx.Cookies(_FRESH_DICT))
        with patch.object(Path, "chmod", side_effect=OSError("no chmod")):
            plain_client.save_cookies()
        assert _read_saved_cookies(plain_client) == _FRESH_DICT


# ---------------------------------------------------------------------------
# _handle_cookie_update edge cases
# ---------------------------------------------------------------------------


class TestHandleCookieUpdateEdgeCases:
    def test_ignores_non_float_max_age(self, connected_client):
        original_mtime = connected_client.config.cookies_file.stat().st_mtime
        # Integer max-age does not match the float regex -> no change.
        connected_client._handle_cookie_update(["k=v; max-age=3600; path=/"])
        assert connected_client.config.cookies_file.stat().st_mtime == original_mtime

    def test_malformed_morsel_logged_and_skipped(self, connected_client):
        original_mtime = connected_client.config.cookies_file.stat().st_mtime
        # Float max-age triggers the branch, but no "=" in the pair -> ValueError.
        connected_client._handle_cookie_update(["novalue; max-age=10.0"])
        assert connected_client.config.cookies_file.stat().st_mtime == original_mtime


# ---------------------------------------------------------------------------
# parse_json_response
# ---------------------------------------------------------------------------


class TestParseJsonResponse:
    def test_parses_valid_json(self, plain_client):
        resp = httpx.Response(_HTTP_OK, json={"ok": True}, request=httpx.Request("GET", TEST_URL))
        assert plain_client.parse_json_response(resp) == {"ok": True}

    def test_accepts_javascript_content_type(self, plain_client):
        resp = httpx.Response(
            _HTTP_OK,
            content=b'{"ok": 1}',
            headers={"Content-Type": "application/javascript"},
            request=httpx.Request("GET", TEST_URL),
        )
        assert plain_client.parse_json_response(resp) == {"ok": 1}

    def test_raises_on_non_ok(self, plain_client):
        resp = httpx.Response(
            _HTTP_SERVER_ERROR, text="boom", request=httpx.Request("GET", TEST_URL)
        )
        with pytest.raises(ApiError, match="status 500"):
            plain_client.parse_json_response(resp)

    def test_raises_on_unexpected_content_type(self, plain_client):
        resp = httpx.Response(
            _HTTP_OK,
            text="<html></html>",
            headers={"Content-Type": "text/html"},
            request=httpx.Request("GET", TEST_URL),
        )
        with pytest.raises(ApiError, match="Unexpected content type"):
            plain_client.parse_json_response(resp)

    def test_raises_on_invalid_json_body(self, plain_client):
        resp = httpx.Response(
            _HTTP_OK,
            content=b"not json",
            headers={"Content-Type": "application/json"},
            request=httpx.Request("GET", TEST_URL),
        )
        with pytest.raises(ApiError, match="JSON parse error"):
            plain_client.parse_json_response(resp)


# ---------------------------------------------------------------------------
# check_login
# ---------------------------------------------------------------------------


class TestCheckLogin:
    @pytest.mark.asyncio
    @respx.mock
    async def test_success(self, live_client):
        _mock_profile(return_value=_make_response(_HTTP_OK, json={"user_type": "Active"}))
        assert await live_client.check_login() is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_on_non_ok(self, live_client):
        _mock_profile(return_value=_make_response(_HTTP_NOT_FOUND))
        with pytest.raises(AuthenticationError, match=_AUTH_FAILED_MATCH):
            await live_client.check_login()

    @pytest.mark.asyncio
    async def test_raises_when_final_url_is_login(self, tmp_path):
        # A 200 response whose final URL contains /login -> auth failed.
        client = _make_client(tmp_path)
        login_resp = httpx.Response(
            _HTTP_OK,
            json={},
            request=httpx.Request("GET", "https://example.test/login/"),
        )
        with (
            patch.object(client, "get", AsyncMock(return_value=login_resp)),
            pytest.raises(AuthenticationError, match=_AUTH_FAILED_MATCH),
        ):
            await client.check_login()

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_on_expired_subscription(self, live_client):
        _mock_profile(
            return_value=_make_response(
                _HTTP_OK,
                text='{"user_type":"Expired"}',
                headers={"Content-Type": "application/json"},
            )
        )
        with pytest.raises(AuthenticationError, match="subscription has expired"):
            await live_client.check_login()


# ---------------------------------------------------------------------------
# get / post / get_json / _request / _do_request
# ---------------------------------------------------------------------------


class TestSimpleRequests:
    @pytest.mark.asyncio
    @respx.mock
    async def test_get_returns_response(self, live_client):
        _mock_get(return_value=_make_response(_HTTP_OK, text="hi"))
        resp = await live_client.get(TEST_URL)
        assert resp.status_code == _HTTP_OK
        assert resp.text == "hi"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_json(self, live_client):
        _mock_get(return_value=_make_response(_HTTP_OK, json={"a": 1}))
        assert await live_client.get_json(TEST_URL) == {"a": 1}

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_without_cookie_update(self, live_client):
        # update_cookies=False skips the Set-Cookie handling branch.
        route = _mock_get(
            return_value=_make_response(
                _HTTP_OK, text="ok", headers={"set-cookie": "k=v; max-age=10.0"}
            )
        )
        resp = await _get(live_client, update_cookies=False)
        assert resp.status_code == _HTTP_OK
        assert route.called
        # The float-max-age cookie was NOT applied because update was skipped.
        assert "k" not in dict(live_client._cookie_dict)


class TestPostRequests:
    @pytest.mark.asyncio
    @respx.mock
    async def test_post_json_payload(self, live_client):
        route = _mock_post(return_value=_make_response(_HTTP_OK, json={}))
        await live_client.post(TEST_URL, json_payload={"x": 1})
        assert route.called
        assert json.loads(route.calls.last.request.content) == {"x": 1}

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_form_data(self, live_client):
        route = _mock_post(return_value=_make_response(_HTTP_OK, json={}))
        await live_client.post(TEST_URL, data={"field": "val"})
        assert route.called
        assert b"field=val" in route.calls.last.request.content

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_without_payload(self, live_client):
        # is_post True but neither data nor json_payload -> empty body branch.
        route = _mock_post(return_value=_make_response(_HTTP_OK, json={}))
        await live_client.post(TEST_URL)
        assert route.called
        assert route.calls.last.request.content == b""


class TestRedirectRequests:
    @pytest.mark.asyncio
    @respx.mock
    async def test_follows_redirect(self, live_client):
        _mock_get(
            return_value=_make_response(
                _HTTP_FOUND, headers={"location": "https://example.test/final"}
            )
        )
        respx.get("https://example.test/final").mock(
            return_value=_make_response(_HTTP_OK, text="arrived")
        )
        resp = await _get(live_client)
        assert resp.status_code == _HTTP_OK
        assert resp.text == "arrived"

    @pytest.mark.asyncio
    @respx.mock
    async def test_too_many_redirects_raises(self, live_client):
        # Always redirects back to itself -> exceeds _MAX_REDIRECTS.
        _mock_get(return_value=_make_response(_HTTP_FOUND, headers={"location": TEST_URL}))
        with pytest.raises(ApiError, match="Too many redirects"):
            await _get(live_client)


class TestRequestErrors:
    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error_wrapped_in_api_error(self, tmp_path):
        # A non-retryable httpx.HTTPError is wrapped in ApiError.
        _mock_get(side_effect=httpx.HTTPError("generic failure"))
        config = _make_real_config(tmp_path)
        retry = RetryConfig(max_attempts=1)
        async with ApiClient(config, retry_config=retry) as client:
            with pytest.raises(ApiError, match="Request failed"):
                await _get(client)

    @pytest.mark.asyncio
    async def test_connect_error_propagates(self, live_client, monkeypatch):
        # ConnectError is retryable; after exhausting attempts it reraises.
        # Patch asyncio.sleep so tenacity backoff does not actually wait.
        monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
        with (
            patch.object(
                live_client.client,
                "request",
                AsyncMock(side_effect=httpx.ConnectError("no route")),
            ),
            pytest.raises(httpx.ConnectError),
        ):
            await _get(live_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_retryable_status_raises_for_status(self, live_client, monkeypatch):
        # 503 is retryable -> raise_for_status inside _do_request; after
        # exhausting retries the HTTPStatusError reraises.
        monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
        _mock_get(return_value=_make_response(_HTTP_UNAVAILABLE))
        with pytest.raises(httpx.HTTPStatusError):
            await _get(live_client)


# ---------------------------------------------------------------------------
# Auth-failure handling inside _request (401/403/redirect to /login)
# ---------------------------------------------------------------------------


class TestRequestAuthFailure:
    @pytest.mark.asyncio
    @respx.mock
    async def test_unauthorized_then_retry(self, live_client):
        # First call 401, refresh reloads fresh cookies from disk, retry 200.
        route = _mock_get(
            side_effect=[
                httpx.Response(_HTTP_UNAUTHORIZED),
                httpx.Response(_HTTP_OK, text="ok"),
            ]
        )
        # Make disk cookies differ so refresh succeeds.
        live_client.config.cookies_file.write_text(json.dumps(_FRESH_DICT), encoding="utf-8")
        resp = await _get(live_client)
        assert resp.status_code == _HTTP_OK
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_forbidden_refresh_fails(self, live_client):
        _mock_get(return_value=_make_response(_HTTP_FORBIDDEN))
        # Disk identical to current -> refresh raises.
        with pytest.raises(AuthenticationError):
            await _get(live_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_redirect_to_login_triggers_refresh(self, live_client):
        route = _mock_get(
            side_effect=[
                httpx.Response(_HTTP_FOUND, headers={"location": "https://x.test/login"}),
                httpx.Response(_HTTP_OK, text="ok"),
            ]
        )
        live_client.config.cookies_file.write_text(json.dumps(_FRESH_DICT), encoding="utf-8")
        resp = await _get(live_client)
        assert resp.status_code == _HTTP_OK
        assert route.call_count == 2


# ---------------------------------------------------------------------------
# Keepalive loop body
# ---------------------------------------------------------------------------


class _CancelAfter:
    """Fake asyncio.sleep that records intervals and cancels after a limit."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.sleeps: list[int] = []

    async def __call__(self, interval) -> None:
        self.sleeps.append(interval)
        if len(self.sleeps) >= self.limit:
            raise asyncio.CancelledError


async def _noop_sleep(_interval) -> None:
    """Replacement for asyncio.sleep that yields immediately."""


class TestKeepaliveLoop:
    @pytest.mark.asyncio
    async def test_loop_pings_then_handles_error(self, connected_client, monkeypatch):
        # Two iterations run their get(); the third sleep cancels the loop.
        sleeper = _CancelAfter(limit=3)

        # First get OK, second get raises generic error (caught & logged).
        get_mock = AsyncMock(side_effect=[httpx.Response(_HTTP_OK), RuntimeError("boom")])
        monkeypatch.setattr(connected_client, "get", get_mock)
        monkeypatch.setattr(asyncio, "sleep", sleeper)

        with pytest.raises(asyncio.CancelledError):
            await connected_client._keepalive_loop(5)

        assert get_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_loop_propagates_cancellation_from_get(self, connected_client, monkeypatch):
        monkeypatch.setattr(asyncio, "sleep", _noop_sleep)
        monkeypatch.setattr(connected_client, "get", AsyncMock(side_effect=asyncio.CancelledError))

        with pytest.raises(asyncio.CancelledError):
            await connected_client._keepalive_loop(5)
