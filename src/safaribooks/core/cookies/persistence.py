"""Validation and on-disk persistence of O'Reilly cookie sets."""

import json
import logging
import os
import sys
from pathlib import Path

from safaribooks.core.constants import REQUIRED_COOKIES
from safaribooks.core.exceptions import CookieError
from safaribooks.core.models import CookieSet

logger = logging.getLogger(__name__)

_OWNER_ONLY_MODE = 0o600
_MIN_EXPECTED_COOKIES = 3


class _Validator:
    """Validate raw cookie dicts and surface friendly failure messages."""

    def validate(self, cookies: dict[str, str]) -> CookieSet:
        """Validate a raw cookie dict and return a ``CookieSet``."""
        if not cookies:
            raise CookieError("No cookies provided.")

        self._warn_on_suspicious(cookies)

        cookie_set_cls = self._cookie_set_cls()
        try:
            return cookie_set_cls(cookies=cookies)
        except ValueError as exc:
            raise CookieError(self._error_message(cookies, exc)) from exc

    def _cookie_set_cls(self) -> type[CookieSet]:
        """Resolve ``CookieSet`` from the package so test patches apply."""
        cookie_pkg = sys.modules["safaribooks.core.cookies"]
        return cookie_pkg.CookieSet

    def _warn_on_suspicious(self, cookies: dict[str, str]) -> None:
        """Emit soft warnings for sparse or empty-valued cookie dicts."""
        if len(cookies) < _MIN_EXPECTED_COOKIES:
            logger.warning(
                "Only %d cookie(s) found — extraction may be incomplete.",
                len(cookies),
            )

        empty_keys = [name for name, cookie_value in cookies.items() if not cookie_value]
        if empty_keys:
            logger.warning("Empty values for cookies: %s", ", ".join(empty_keys))

    def _error_message(self, cookies: dict[str, str], exc: ValueError) -> str:
        """Build a user-facing message for a failed ``CookieSet`` validation."""
        missing = REQUIRED_COOKIES - cookies.keys()
        if missing:
            missing_names = ", ".join(sorted(missing))
            return f"Missing required cookies: {missing_names}"
        return str(exc)


def validate(cookies: dict[str, str]) -> CookieSet:
    """Validate a raw cookie dict and return a ``CookieSet``."""
    return _Validator().validate(cookies)


def save(cookies: CookieSet, output: Path) -> None:
    """Write a validated cookie set to a JSON file with restricted permissions."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = f"{json.dumps(dict(cookies.cookies), indent=2)}\n"

    descriptor = os.open(
        output,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        _OWNER_ONLY_MODE,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as cookie_stream:
        cookie_stream.write(payload)

    try:
        output.chmod(_OWNER_ONLY_MODE)
    except OSError:
        logger.debug("Could not set permissions on %s", output)

    logger.info("Saved %d cookies to %s", len(cookies.cookies), output)
