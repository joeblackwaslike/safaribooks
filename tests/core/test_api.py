"""Tests for safaribooks.core.api — cookie refresh, persistence, and keepalive."""
# ruff: noqa: SLF001

import asyncio
import json
from pathlib import Path
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

VALID_COOKIES = {
    "groot_sessionid": "abc123",
    "jwt": "tok",
    "csrf_access_token": "csrf",
    "logged_in": "y",
}

FRESH_COOKIES = {
    "groot_sessionid": "fresh999",
    "jwt": "newtok",
    "csrf_access_token": "newcsrf",
    "logged_in": "y",
}


def _make_client(tmp_path: Path, *, auto_refresh_browser: str | None = None) -> ApiClient:
    cookies_file = tmp_path / "cookies.json"
    cookies_file.write_text(json.dumps(VALID_COOKIES), encoding="utf-8")
    config = AppConfig(
        cookies_file=cookies_file,
        auto_refresh_browser=auto_refresh_browser,
    )
    return ApiClient(config)


class TestTryCookieRefreshWithoutBrowser:
    def test_disk_reload_succeeds_when_cookies_differ(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        cookies_file = client.config.cookies_file
        cookies_file.write_text(json.dumps(FRESH_COOKIES), encoding="utf-8")

        assert client._try_cookie_refresh() is True
        assert dict(client.client.cookies) == FRESH_COOKIES

    def test_raises_when_disk_cookies_identical_and_no_browser(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        with pytest.raises(AuthenticationError, match="identical to the expired session"):
            client._try_cookie_refresh()

    def test_raises_on_second_attempt(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))
        client._cookie_refresh_attempted = True

        with pytest.raises(AuthenticationError, match="already attempted"):
            client._try_cookie_refresh()


class TestTryCookieRefreshWithBrowser:
    def test_browser_refresh_succeeds_when_disk_identical(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="chrome")
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        fresh_set = CookieSet(cookies=FRESH_COOKIES)
        with patch("safaribooks.core.api.cookie_mod.from_browser", return_value=fresh_set):
            assert client._try_cookie_refresh() is True

        assert dict(client.client.cookies) == FRESH_COOKIES
        saved = json.loads(client.config.cookies_file.read_text(encoding="utf-8"))
        assert saved == FRESH_COOKIES

    def test_browser_refresh_disabled_when_not_configured(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser=None)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        with pytest.raises(AuthenticationError, match="identical to the expired session"):
            client._try_cookie_refresh()

    def test_browser_refresh_falls_through_on_extraction_error(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="chrome")
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        with patch(
            "safaribooks.core.api.cookie_mod.from_browser",
            side_effect=CookieError("browser locked"),
        ), pytest.raises(AuthenticationError, match="identical to the expired session"):
            client._try_cookie_refresh()

    def test_raises_when_file_missing_and_no_browser(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser=None)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))
        client.config.cookies_file.unlink()

        with pytest.raises(AuthenticationError, match="cookie file not found"):
            client._try_cookie_refresh()

    def test_raises_when_disk_json_corrupt(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))
        client.config.cookies_file.write_text("{broken", encoding="utf-8")

        with pytest.raises(AuthenticationError, match="could not reload cookies"):
            client._try_cookie_refresh()

    def test_raises_when_disk_read_oserror(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        with patch.object(
            Path, "read_text", side_effect=OSError("io error")
        ), pytest.raises(AuthenticationError, match="could not reload cookies"):
            client._try_cookie_refresh()

    def test_raises_when_disk_not_a_dict(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))
        client.config.cookies_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        with pytest.raises(AuthenticationError, match="does not contain a JSON object"):
            client._try_cookie_refresh()

    def test_browser_refresh_when_cookie_file_missing(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="chrome")
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))
        client.config.cookies_file.unlink()

        fresh_set = CookieSet(cookies=FRESH_COOKIES)
        with patch("safaribooks.core.api.cookie_mod.from_browser", return_value=fresh_set):
            assert client._try_cookie_refresh() is True

        assert dict(client.client.cookies) == FRESH_COOKIES


class TestTryBrowserRefresh:
    def test_returns_false_when_disabled(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser=None)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))
        assert client._try_browser_refresh() is False

    def test_returns_false_on_cookie_error(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="firefox")
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        with patch(
            "safaribooks.core.api.cookie_mod.from_browser",
            side_effect=CookieError("no cookies"),
        ):
            assert client._try_browser_refresh() is False

    def test_returns_false_when_browser_cookies_identical(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="chrome")
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        same_set = CookieSet(cookies=VALID_COOKIES)
        with patch("safaribooks.core.api.cookie_mod.from_browser", return_value=same_set):
            assert client._try_browser_refresh() is False

    def test_updates_and_saves_on_fresh_cookies(self, tmp_path):
        client = _make_client(tmp_path, auto_refresh_browser="chrome")
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        fresh_set = CookieSet(cookies=FRESH_COOKIES)
        with patch("safaribooks.core.api.cookie_mod.from_browser", return_value=fresh_set):
            assert client._try_browser_refresh() is True

        assert dict(client.client.cookies) == FRESH_COOKIES
        saved = json.loads(client.config.cookies_file.read_text(encoding="utf-8"))
        assert saved == FRESH_COOKIES


class TestHandleCookieUpdatePersistence:
    def test_saves_when_cookies_change(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        client._handle_cookie_update(["newkey=newval; max-age=3600.0; path=/"])
        saved = json.loads(client.config.cookies_file.read_text(encoding="utf-8"))
        assert saved["newkey"] == "newval"

    def test_does_not_save_when_no_change(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        original_mtime = client.config.cookies_file.stat().st_mtime
        client._handle_cookie_update([])
        assert client.config.cookies_file.stat().st_mtime == original_mtime


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
        assert config.keepalive_interval == 300

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_KEEPALIVE_INTERVAL", "600")
        config = AppConfig()
        assert config.keepalive_interval == 600

    def test_disable_with_zero(self, monkeypatch):
        monkeypatch.setenv("SAFARI_KEEPALIVE_INTERVAL", "0")
        config = AppConfig()
        assert config.keepalive_interval == 0


class TestKeepalive:
    @pytest.mark.asyncio
    async def test_start_creates_task(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        await client.start_keepalive()
        assert client._keepalive_task is not None
        assert not client._keepalive_task.done()

        await client.stop_keepalive()
        assert client._keepalive_task.done()

    @pytest.mark.asyncio
    async def test_start_skipped_when_interval_zero(self, tmp_path):
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text(json.dumps(VALID_COOKIES), encoding="utf-8")
        config = AppConfig(cookies_file=cookies_file, keepalive_interval=0)
        client = ApiClient(config)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        await client.start_keepalive()
        assert client._keepalive_task is None

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        await client.stop_keepalive()
        await client.stop_keepalive()

    @pytest.mark.asyncio
    async def test_aexit_stops_keepalive(self, tmp_path):
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text(json.dumps(VALID_COOKIES), encoding="utf-8")
        config = AppConfig(cookies_file=cookies_file)

        async with ApiClient(config) as client:
            await client.start_keepalive()
            task = client._keepalive_task

        assert task is not None
        assert task.done()


# ---------------------------------------------------------------------------
# Helpers for request-level tests (real httpx mocked via respx)
# ---------------------------------------------------------------------------

TEST_URL = "https://example.test/api/thing"


def _make_real_config(tmp_path: Path, **overrides) -> AppConfig:
    """Build an AppConfig with rate limiting disabled for deterministic tests."""
    cookies_file = tmp_path / "cookies.json"
    cookies_file.write_text(json.dumps(VALID_COOKIES), encoding="utf-8")
    params = {"cookies_file": cookies_file, "rate_limit": 0.0}
    params.update(overrides)
    return AppConfig(**params)


# ---------------------------------------------------------------------------
# __init__ / client property
# ---------------------------------------------------------------------------


class TestClientProperty:
    def test_raises_when_not_in_context(self, tmp_path):
        client = _make_client(tmp_path)
        with pytest.raises(RuntimeError, match="async context manager"):
            _ = client.client

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
            ApiClient(config)

    def test_raises_on_corrupt_json(self, tmp_path):
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text("{not valid json", encoding="utf-8")
        config = AppConfig(cookies_file=cookies_file)
        with pytest.raises(CookieError, match="corrupted"):
            ApiClient(config)

    def test_raises_when_not_a_dict(self, tmp_path):
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text(json.dumps(["a", "b"]), encoding="utf-8")
        config = AppConfig(cookies_file=cookies_file)
        with pytest.raises(CookieError, match="Expected a JSON object"):
            ApiClient(config)

    def test_raises_on_os_error(self, tmp_path):
        cookies_file = tmp_path / "cookies.json"
        cookies_file.write_text(json.dumps(VALID_COOKIES), encoding="utf-8")
        config = AppConfig(cookies_file=cookies_file)
        with patch.object(
            Path, "read_text", side_effect=OSError("permission denied")
        ), pytest.raises(CookieError, match="Unable to read cookie file"):
            ApiClient(config)

    def test_loads_valid_cookies(self, tmp_path):
        client = _make_client(tmp_path)
        assert client._cookie_dict == VALID_COOKIES


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
    def test_warns_deprecation(self, tmp_path):
        client = _make_client(tmp_path)
        with pytest.warns(DeprecationWarning, match="no longer supported"):
            client.do_login("a@b.com", "pw")


# ---------------------------------------------------------------------------
# save_cookies
# ---------------------------------------------------------------------------


class TestSaveCookies:
    def test_persists_cookies(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(FRESH_COOKIES))
        client.save_cookies()
        saved = json.loads(client.config.cookies_file.read_text(encoding="utf-8"))
        assert saved == FRESH_COOKIES

    def test_chmod_failure_is_tolerated(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(FRESH_COOKIES))
        with patch.object(Path, "chmod", side_effect=OSError("no chmod")):
            client.save_cookies()
        saved = json.loads(client.config.cookies_file.read_text(encoding="utf-8"))
        assert saved == FRESH_COOKIES


# ---------------------------------------------------------------------------
# _handle_cookie_update edge cases
# ---------------------------------------------------------------------------


class TestHandleCookieUpdateEdgeCases:
    def test_ignores_non_float_max_age(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))
        original_mtime = client.config.cookies_file.stat().st_mtime
        # Integer max-age does not match the float regex -> no change.
        client._handle_cookie_update(["k=v; max-age=3600; path=/"])
        assert client.config.cookies_file.stat().st_mtime == original_mtime

    def test_malformed_morsel_logged_and_skipped(self, tmp_path):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))
        original_mtime = client.config.cookies_file.stat().st_mtime
        # Float max-age triggers the branch, but no "=" in the pair -> ValueError.
        client._handle_cookie_update(["novalue; max-age=10.0"])
        assert client.config.cookies_file.stat().st_mtime == original_mtime


# ---------------------------------------------------------------------------
# parse_json_response
# ---------------------------------------------------------------------------


class TestParseJsonResponse:
    def _client(self, tmp_path):
        return _make_client(tmp_path)

    def test_parses_valid_json(self, tmp_path):
        client = self._client(tmp_path)
        resp = httpx.Response(
            200, json={"ok": True}, request=httpx.Request("GET", TEST_URL)
        )
        assert client.parse_json_response(resp) == {"ok": True}

    def test_accepts_javascript_content_type(self, tmp_path):
        client = self._client(tmp_path)
        resp = httpx.Response(
            200,
            content=b'{"ok": 1}',
            headers={"Content-Type": "application/javascript"},
            request=httpx.Request("GET", TEST_URL),
        )
        assert client.parse_json_response(resp) == {"ok": 1}

    def test_raises_on_non_200(self, tmp_path):
        client = self._client(tmp_path)
        resp = httpx.Response(
            500, text="boom", request=httpx.Request("GET", TEST_URL)
        )
        with pytest.raises(ApiError, match="status 500"):
            client.parse_json_response(resp)

    def test_raises_on_unexpected_content_type(self, tmp_path):
        client = self._client(tmp_path)
        resp = httpx.Response(
            200,
            text="<html></html>",
            headers={"Content-Type": "text/html"},
            request=httpx.Request("GET", TEST_URL),
        )
        with pytest.raises(ApiError, match="Unexpected content type"):
            client.parse_json_response(resp)

    def test_raises_on_invalid_json_body(self, tmp_path):
        client = self._client(tmp_path)
        resp = httpx.Response(
            200,
            content=b"not json",
            headers={"Content-Type": "application/json"},
            request=httpx.Request("GET", TEST_URL),
        )
        with pytest.raises(ApiError, match="JSON parse error"):
            client.parse_json_response(resp)


# ---------------------------------------------------------------------------
# check_login
# ---------------------------------------------------------------------------


class TestCheckLogin:
    @pytest.mark.asyncio
    @respx.mock
    async def test_success(self, tmp_path):
        respx.get(PROFILE_URL).mock(
            return_value=httpx.Response(200, json={"user_type": "Active"})
        )
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            assert await client.check_login() is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_on_non_200(self, tmp_path):
        respx.get(PROFILE_URL).mock(return_value=httpx.Response(404))
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            with pytest.raises(AuthenticationError, match="authentication failed"):
                await client.check_login()

    @pytest.mark.asyncio
    async def test_raises_when_final_url_is_login(self, tmp_path):
        # A 200 response whose final URL contains /login -> auth failed.
        client = _make_client(tmp_path)
        login_resp = httpx.Response(
            200,
            json={},
            request=httpx.Request("GET", "https://example.test/login/"),
        )
        with patch.object(client, "get", AsyncMock(return_value=login_resp)), \
                pytest.raises(AuthenticationError, match="authentication failed"):
            await client.check_login()

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_on_expired_subscription(self, tmp_path):
        respx.get(PROFILE_URL).mock(
            return_value=httpx.Response(
                200,
                text='{"user_type":"Expired"}',
                headers={"Content-Type": "application/json"},
            )
        )
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            with pytest.raises(AuthenticationError, match="subscription has expired"):
                await client.check_login()


# ---------------------------------------------------------------------------
# get / post / get_json / _request / _do_request
# ---------------------------------------------------------------------------


class TestRequests:
    @pytest.mark.asyncio
    @respx.mock
    async def test_get_returns_response(self, tmp_path):
        respx.get(TEST_URL).mock(return_value=httpx.Response(200, text="hi"))
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            resp = await client.get(TEST_URL)
        assert resp.status_code == 200
        assert resp.text == "hi"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_json(self, tmp_path):
        respx.get(TEST_URL).mock(return_value=httpx.Response(200, json={"a": 1}))
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            assert await client.get_json(TEST_URL) == {"a": 1}

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_json_payload(self, tmp_path):
        route = respx.post(TEST_URL).mock(return_value=httpx.Response(200, json={}))
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            await client.post(TEST_URL, json_payload={"x": 1})
        assert route.called
        assert json.loads(route.calls.last.request.content) == {"x": 1}

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_form_data(self, tmp_path):
        route = respx.post(TEST_URL).mock(return_value=httpx.Response(200, json={}))
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            await client.post(TEST_URL, data={"field": "val"})
        assert route.called
        assert b"field=val" in route.calls.last.request.content

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_without_payload(self, tmp_path):
        # is_post True but neither data nor json_payload -> empty body branch.
        route = respx.post(TEST_URL).mock(return_value=httpx.Response(200, json={}))
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            await client.post(TEST_URL)
        assert route.called
        assert route.calls.last.request.content == b""

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_without_cookie_update(self, tmp_path):
        # update_cookies=False skips the Set-Cookie handling branch.
        route = respx.get(TEST_URL).mock(
            return_value=httpx.Response(
                200, text="ok", headers={"set-cookie": "k=v; max-age=10.0"}
            )
        )
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            resp = await client.get(TEST_URL, update_cookies=False)
        assert resp.status_code == 200
        assert route.called
        # The float-max-age cookie was NOT applied because update was skipped.
        assert "k" not in dict(client._cookie_dict)

    @pytest.mark.asyncio
    @respx.mock
    async def test_follows_redirect(self, tmp_path):
        respx.get(TEST_URL).mock(
            return_value=httpx.Response(
                302, headers={"location": "https://example.test/final"}
            )
        )
        respx.get("https://example.test/final").mock(
            return_value=httpx.Response(200, text="arrived")
        )
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            resp = await client.get(TEST_URL)
        assert resp.status_code == 200
        assert resp.text == "arrived"

    @pytest.mark.asyncio
    @respx.mock
    async def test_too_many_redirects_raises(self, tmp_path):
        # Always redirects back to itself -> exceeds _MAX_REDIRECTS.
        respx.get(TEST_URL).mock(
            return_value=httpx.Response(302, headers={"location": TEST_URL})
        )
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            with pytest.raises(ApiError, match="Too many redirects"):
                await client.get(TEST_URL)

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error_wrapped_in_api_error(self, tmp_path):
        # A non-retryable httpx.HTTPError is wrapped in ApiError.
        respx.get(TEST_URL).mock(side_effect=httpx.HTTPError("generic failure"))
        config = _make_real_config(tmp_path)
        retry = RetryConfig(max_attempts=1)
        async with ApiClient(config, retry_config=retry) as client:
            with pytest.raises(ApiError, match="Request failed"):
                await client.get(TEST_URL)

    @pytest.mark.asyncio
    async def test_connect_error_propagates(self, tmp_path, monkeypatch):
        # ConnectError is retryable; after exhausting attempts it reraises.
        # Patch asyncio.sleep so tenacity backoff does not actually wait.
        monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            with patch.object(
                client.client,
                "request",
                AsyncMock(side_effect=httpx.ConnectError("no route")),
            ), pytest.raises(httpx.ConnectError):
                await client.get(TEST_URL)

    @pytest.mark.asyncio
    @respx.mock
    async def test_retryable_status_raises_for_status(self, tmp_path, monkeypatch):
        # 503 is retryable -> raise_for_status inside _do_request; after
        # exhausting retries the HTTPStatusError reraises.
        monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
        respx.get(TEST_URL).mock(return_value=httpx.Response(503))
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            with pytest.raises(httpx.HTTPStatusError):
                await client.get(TEST_URL)


# ---------------------------------------------------------------------------
# Auth-failure handling inside _request (401/403/redirect to /login)
# ---------------------------------------------------------------------------


class TestRequestAuthFailure:
    @pytest.mark.asyncio
    @respx.mock
    async def test_401_triggers_refresh_then_retry(self, tmp_path):
        # First call 401, refresh reloads fresh cookies from disk, retry 200.
        route = respx.get(TEST_URL).mock(
            side_effect=[
                httpx.Response(401),
                httpx.Response(200, text="ok"),
            ]
        )
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            # Make disk cookies differ so refresh succeeds.
            config.cookies_file.write_text(json.dumps(FRESH_COOKIES), encoding="utf-8")
            resp = await client.get(TEST_URL)
        assert resp.status_code == 200
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_403_refresh_fails_raises_auth_error(self, tmp_path):
        respx.get(TEST_URL).mock(return_value=httpx.Response(403))
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            # Disk identical to current -> refresh raises.
            with pytest.raises(AuthenticationError):
                await client.get(TEST_URL)

    @pytest.mark.asyncio
    @respx.mock
    async def test_redirect_to_login_triggers_refresh(self, tmp_path):
        route = respx.get(TEST_URL).mock(
            side_effect=[
                httpx.Response(302, headers={"location": "https://x.test/login"}),
                httpx.Response(200, text="ok"),
            ]
        )
        config = _make_real_config(tmp_path)
        async with ApiClient(config) as client:
            config.cookies_file.write_text(json.dumps(FRESH_COOKIES), encoding="utf-8")
            resp = await client.get(TEST_URL)
        assert resp.status_code == 200
        assert route.call_count == 2


# ---------------------------------------------------------------------------
# Keepalive loop body
# ---------------------------------------------------------------------------


class TestKeepaliveLoop:
    @pytest.mark.asyncio
    async def test_loop_pings_then_handles_error(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        sleeps: list[int] = []

        async def fake_sleep(interval):
            sleeps.append(interval)
            # Two iterations run their get(); the third sleep cancels the loop.
            if len(sleeps) >= 3:
                raise asyncio.CancelledError

        # First get OK, second get raises generic error (caught & logged).
        get_mock = AsyncMock(side_effect=[httpx.Response(200), RuntimeError("boom")])
        monkeypatch.setattr(client, "get", get_mock)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)

        with pytest.raises(asyncio.CancelledError):
            await client._keepalive_loop(5)

        assert get_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_loop_propagates_cancellation_from_get(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path)
        client._client = httpx.AsyncClient(cookies=httpx.Cookies(VALID_COOKIES))

        async def fake_sleep(_interval):
            return None

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(
            client, "get", AsyncMock(side_effect=asyncio.CancelledError)
        )

        with pytest.raises(asyncio.CancelledError):
            await client._keepalive_loop(5)
