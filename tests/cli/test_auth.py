"""Tests for the ``safari auth`` CLI command group."""

import json
from collections.abc import Iterable
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from safaribooks.cli import app
from safaribooks.cli.auth import _default_cookie_path, import_cookies
from safaribooks.core.config import AppConfig
from safaribooks.core.cookies import validate
from safaribooks.core.exceptions import CookieError

runner = CliRunner()

# Required cookies that satisfy the CookieSet validator.
VALID_COOKIES: MappingProxyType[str, str] = MappingProxyType({
    "groot_sessionid": "sess_abc123",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.test.payload",
    "csrf_access_token": "csrf_tok_value",
    "logged_in": "1",
})

_COOKIE_FILENAME = "cookies.json"
_DEFAULT_COOKIE_FILENAME = "default_cookies.json"
_SAVED_MESSAGE = "Cookies saved"
_FOUR_COOKIES_MESSAGE = "4 cookies"
_VALID_MESSAGE = "Valid"
_ERROR_MESSAGE = "Error"
_EXIT_OK = 0
_EXIT_FAIL = 1

# A plain ``dict`` copy of the read-only constant for callers that mutate or
# pass it where a concrete ``dict`` is required.
_VALID_COOKIES_DICT: dict[str, str] = dict(VALID_COOKIES)


def _invoke(*cli_args: object, expect: int | None = None):
    """Invoke the CLI with stringified arguments.

    When ``expect`` is provided, assert the resulting exit code matches it.
    """
    outcome = runner.invoke(app, [str(cli_arg) for cli_arg in cli_args])
    if expect is not None:
        assert outcome.exit_code == expect
    return outcome


def _assert_error_output(outcome) -> None:
    """Assert the command failed and surfaced an error message."""
    assert outcome.exit_code == _EXIT_FAIL
    assert _ERROR_MESSAGE in outcome.output


def _write_cookies(target: Path, payload: object) -> Path:
    """Write a JSON cookie payload to ``target`` and return it."""
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _read_saved(target: Path) -> dict[str, str]:
    """Read and parse a saved cookie file."""
    return json.loads(target.read_text(encoding="utf-8"))


def _cookie_header(pairs: Iterable[tuple[str, str]]) -> str:
    """Render cookie ``name=value`` pairs into a Cookie header value."""
    return "; ".join(f"{name}={cookie_value}" for name, cookie_value in pairs)


@pytest.fixture
def cookie_path(tmp_path: Path) -> Path:
    """Default cookie file path inside the per-test temp directory."""
    return tmp_path / _COOKIE_FILENAME


class TestAuthHelp:
    """Verify the auth sub-group surfaces in the CLI help."""

    def test_auth_help_shows_subcommands(self):
        outcome = _invoke("auth", "--help", expect=_EXIT_OK)
        for subcommand in ("setup", "extract", "import", "validate", "status"):
            assert subcommand in outcome.output


class TestAuthValidate:
    """Tests for ``safari auth validate``."""

    def test_validate_no_cookies_file(self, tmp_path: Path):
        """Fails gracefully when the cookie file does not exist."""
        missing = tmp_path / "nonexistent" / _COOKIE_FILENAME
        outcome = _invoke("auth", "validate", "--file", missing, expect=_EXIT_FAIL)
        assert "not found" in outcome.output.lower() or _ERROR_MESSAGE in outcome.output

    def test_validate_with_valid_cookies(self, cookie_path: Path):
        """Validates successfully when the cookie file contains all required cookies."""
        cookie_file = _write_cookies(cookie_path, _VALID_COOKIES_DICT)

        outcome = _invoke("auth", "validate", "--file", cookie_file, expect=_EXIT_OK)
        assert _VALID_MESSAGE in outcome.output
        assert _FOUR_COOKIES_MESSAGE in outcome.output

    def test_validate_with_invalid_cookies(self, cookie_path: Path):
        """Fails when cookie file is missing required cookies."""
        cookie_file = _write_cookies(cookie_path, {"foo": "bar"})

        outcome = _invoke("auth", "validate", "--file", cookie_file)
        _assert_error_output(outcome)

    def test_validate_truncates_long_values(self, cookie_path: Path):
        """Long cookie values are previewed with a trailing ellipsis."""
        jwt_padding = "a" * 60
        long_jwt = f"eyJ{jwt_padding}.sig.payload"
        cookies = {**VALID_COOKIES, "jwt": long_jwt}
        cookie_file = _write_cookies(cookie_path, cookies)

        outcome = _invoke("auth", "validate", "--file", cookie_file, expect=_EXIT_OK)
        assert "..." in outcome.output

    def test_validate_with_corrupt_json(self, cookie_path: Path):
        """Fails when cookie file contains invalid JSON."""
        cookie_path.write_text("not-valid-json{{{", encoding="utf-8")

        outcome = _invoke("auth", "validate", "--file", cookie_path)
        _assert_error_output(outcome)


class TestAuthStatus:
    """Tests for ``safari auth status``."""

    def test_status_no_cookies(self, tmp_path: Path):
        """Shows guidance when no cookie file exists."""
        fake_path = tmp_path / "nonexistent_cookies.json"

        with patch(
            "safaribooks.cli.auth._default_cookie_path",
            return_value=fake_path,
        ):
            outcome = _invoke("auth", "status", expect=_EXIT_OK)

        assert "No cookie file found" in outcome.output or "not found" in outcome.output.lower()

    def test_status_with_valid_cookies(self, cookie_path: Path):
        """Shows cookie count when a valid cookie file exists."""
        cookie_file = _write_cookies(cookie_path, _VALID_COOKIES_DICT)

        with patch(
            "safaribooks.cli.auth._default_cookie_path",
            return_value=cookie_file,
        ):
            outcome = _invoke("auth", "status", expect=_EXIT_OK)

        assert _VALID_MESSAGE in outcome.output
        assert _FOUR_COOKIES_MESSAGE in outcome.output

    def test_status_with_corrupt_file(self, cookie_path: Path):
        """Shows error status when cookie file is unreadable."""
        cookie_path.write_text("<<<broken>>>", encoding="utf-8")

        with patch(
            "safaribooks.cli.auth._default_cookie_path",
            return_value=cookie_path,
        ):
            outcome = _invoke("auth", "status", expect=_EXIT_OK)  # status never exits 1

        lowered_output = outcome.output.lower()
        assert "Invalid" in outcome.output or "error" in lowered_output


class TestAuthImportSources:
    """Tests for ``safari auth import`` accepting cookie sources."""

    def test_import_no_source_fails(self):
        """Fails when neither --file nor --header is provided."""
        outcome = _invoke("auth", "import", expect=_EXIT_FAIL)
        assert "Provide --file or --header" in outcome.output

    def test_import_from_file(self, tmp_path: Path):
        """Imports cookies from a JSON file and saves to the output location."""
        source = _write_cookies(tmp_path / "source_cookies.json", _VALID_COOKIES_DICT)

        dest = tmp_path / "output" / _COOKIE_FILENAME
        outcome = _invoke("auth", "import", "--file", source, "--output", dest, expect=_EXIT_OK)
        assert _SAVED_MESSAGE in outcome.output
        assert dest.is_file()

        assert _read_saved(dest)["jwt"] == VALID_COOKIES["jwt"]

    def test_import_from_header(self, cookie_path: Path):
        """Imports cookies from a Cookie header string."""
        header = _cookie_header(VALID_COOKIES.items())
        dest = cookie_path

        outcome = _invoke("auth", "import", "--header", header, "--output", dest, expect=_EXIT_OK)
        assert _SAVED_MESSAGE in outcome.output
        assert dest.is_file()

        saved = _read_saved(dest)
        for key in VALID_COOKIES:
            assert key in saved

    def test_import_from_header_with_prefix(self, cookie_path: Path):
        """Handles the ``Cookie:`` prefix in the header string."""
        header = f"Cookie: {_cookie_header(VALID_COOKIES.items())}"
        dest = cookie_path

        outcome = _invoke("auth", "import", "--header", header, "--output", dest, expect=_EXIT_OK)
        assert _SAVED_MESSAGE in outcome.output


class TestAuthImportErrors:
    """Tests for ``safari auth import`` failure paths."""

    def test_import_from_file_missing_required(self, tmp_path: Path):
        """Fails when imported file lacks required cookies."""
        source = _write_cookies(tmp_path / "bad_cookies.json", {"random_key": "random_val"})

        dest = tmp_path / "output_cookies.json"
        outcome = _invoke("auth", "import", "--file", source, "--output", dest)
        _assert_error_output(outcome)

    def test_import_from_nonexistent_file(self, tmp_path: Path):
        """Fails when the source file does not exist."""
        missing = tmp_path / "nope.json"
        dest = tmp_path / "out.json"
        outcome = _invoke("auth", "import", "--file", missing, "--output", dest)
        _assert_error_output(outcome)

    def test_import_from_empty_header(self, cookie_path: Path):
        """Fails when the header string yields no parseable cookies."""
        dest = cookie_path
        outcome = _invoke("auth", "import", "--header", "", "--output", dest)
        _assert_error_output(outcome)

    def test_import_no_source_guard_runs_first(self):
        """The outer line-96 guard catches the no-source case and exits 1.

        This documents *why* the inner ``header is None`` fallback
        (auth.py:105-107) is unreachable: the outer guard always fires first,
        so we never reach the defensive branch. Calling the command function
        directly with no source raises ``typer.Exit(1)`` from the guard.
        """
        with pytest.raises(typer.Exit) as excinfo:
            import_cookies(import_file=None, header=None)
        assert excinfo.value.exit_code == _EXIT_FAIL


class TestDefaultCookiePath:
    """Tests for the ``_default_cookie_path`` helper."""

    def test_returns_appconfig_cookies_file(self):
        """Returns the path configured on AppConfig."""
        resolved = _default_cookie_path()
        assert isinstance(resolved, Path)
        assert resolved == AppConfig().cookies_file


class TestAuthSetup:
    """Tests for ``safari auth setup`` (interactive paste)."""

    def test_setup_saves_pasted_cookies(self, tmp_path: Path):
        """Persists cookies returned by ``from_paste`` to the output path."""
        dest = tmp_path / "out" / _COOKIE_FILENAME
        cookie_set = validate(_VALID_COOKIES_DICT)

        with patch(
            "safaribooks.cli.auth.cookie_mod.from_paste",
            return_value=cookie_set,
        ):
            outcome = _invoke("auth", "setup", "--output", dest, expect=_EXIT_OK)

        assert _SAVED_MESSAGE in outcome.output
        assert _FOUR_COOKIES_MESSAGE in outcome.output
        assert dest.is_file()
        assert _read_saved(dest)["jwt"] == VALID_COOKIES["jwt"]

    def test_setup_uses_default_path_when_no_output(self, tmp_path: Path):
        """Falls back to ``_default_cookie_path`` when no --output is given."""
        dest = tmp_path / _DEFAULT_COOKIE_FILENAME
        cookie_set = validate(_VALID_COOKIES_DICT)

        with (
            patch("safaribooks.cli.auth.cookie_mod.from_paste", return_value=cookie_set),
            patch(
                "safaribooks.cli.auth._default_cookie_path",
                return_value=dest,
            ),
        ):
            _invoke("auth", "setup", expect=_EXIT_OK)

        assert dest.is_file()

    def test_setup_cookie_error_exits_nonzero(self, cookie_path: Path):
        """Surfaces a CookieError as a friendly message and exit code 1."""
        dest = cookie_path

        with patch(
            "safaribooks.cli.auth.cookie_mod.from_paste",
            side_effect=CookieError("nothing pasted"),
        ):
            outcome = _invoke("auth", "setup", "--output", dest)

        _assert_error_output(outcome)
        assert "nothing pasted" in outcome.output
        assert not dest.exists()


class TestAuthExtract:
    """Tests for ``safari auth extract`` (browser extraction)."""

    def test_extract_saves_browser_cookies(self, tmp_path: Path):
        """Persists cookies returned by ``from_browser`` to the output path."""
        dest = tmp_path / "out" / _COOKIE_FILENAME
        cookie_set = validate(_VALID_COOKIES_DICT)

        with patch(
            "safaribooks.cli.auth.cookie_mod.from_browser",
            return_value=cookie_set,
        ) as mock_browser:
            outcome = _invoke(
                "auth",
                "extract",
                "--browser",
                "firefox",
                "--output",
                dest,
                expect=_EXIT_OK,
            )
            mock_browser.assert_called_once_with("firefox")

        assert _SAVED_MESSAGE in outcome.output
        assert _FOUR_COOKIES_MESSAGE in outcome.output
        assert dest.is_file()

    def test_extract_defaults_to_chrome(self, cookie_path: Path):
        """Defaults the browser option to chrome."""
        dest = cookie_path
        cookie_set = validate(_VALID_COOKIES_DICT)

        with patch(
            "safaribooks.cli.auth.cookie_mod.from_browser",
            return_value=cookie_set,
        ) as mock_browser:
            _invoke("auth", "extract", "--output", dest, expect=_EXIT_OK)
            mock_browser.assert_called_once_with("chrome")

    def test_extract_uses_default_path_when_no_output(self, tmp_path: Path):
        """Falls back to ``_default_cookie_path`` when no --output is given."""
        dest = tmp_path / _DEFAULT_COOKIE_FILENAME
        cookie_set = validate(_VALID_COOKIES_DICT)

        with (
            patch("safaribooks.cli.auth.cookie_mod.from_browser", return_value=cookie_set),
            patch(
                "safaribooks.cli.auth._default_cookie_path",
                return_value=dest,
            ),
        ):
            _invoke("auth", "extract", expect=_EXIT_OK)

        assert dest.is_file()

    def test_extract_cookie_error_exits_nonzero(self, cookie_path: Path):
        """Surfaces a CookieError (e.g. unsupported browser) and exit code 1."""
        dest = cookie_path

        with patch(
            "safaribooks.cli.auth.cookie_mod.from_browser",
            side_effect=CookieError("Unsupported browser 'opera'"),
        ):
            outcome = _invoke("auth", "extract", "--browser", "opera", "--output", dest)

        _assert_error_output(outcome)
        assert "Unsupported browser" in outcome.output
        assert not dest.exists()
