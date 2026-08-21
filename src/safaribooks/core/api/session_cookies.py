"""Session-cookie persistence and refresh (disk reload, then browser re-extraction)."""

import json
import logging
import re
import stat
from pathlib import Path
from typing import Any

from safaribooks.core import cookies as cookie_mod
from safaribooks.core.api.connection import ConnectionMixin
from safaribooks.core.exceptions import AuthenticationError, CookieError

logger = logging.getLogger(__name__)

_COOKIE_FLOAT_MAX_AGE_RE = re.compile(r"(max-age=\d*\.\d*)", re.IGNORECASE)


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


class CookieMixin(ConnectionMixin):
    """Persists session cookies to disk and refreshes them when the session expires."""

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
