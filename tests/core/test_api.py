"""Tests for safaribooks.core.api — cookie refresh, persistence, and keepalive."""
# ruff: noqa: SLF001

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from safaribooks.core.api import ApiClient
from safaribooks.core.config import AppConfig
from safaribooks.core.exceptions import AuthenticationError, CookieError
from safaribooks.core.models import CookieSet

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
