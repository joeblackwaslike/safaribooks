"""Tests for the ``safari auth`` CLI command group."""


import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from safaribooks.cli import app

runner = CliRunner()

# Required cookies that satisfy the CookieSet validator.
VALID_COOKIES: dict[str, str] = {
    "groot_sessionid": "sess_abc123",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.test.payload",
    "csrf_access_token": "csrf_tok_value",
    "logged_in": "1",
}


class TestAuthHelp:
    """Verify the auth sub-group surfaces in the CLI help."""

    def test_auth_help_shows_subcommands(self):
        result = runner.invoke(app, ["auth", "--help"])
        assert result.exit_code == 0
        assert "setup" in result.output
        assert "extract" in result.output
        assert "import" in result.output
        assert "validate" in result.output
        assert "status" in result.output


class TestAuthValidate:
    """Tests for ``safari auth validate``."""

    def test_validate_no_cookies_file(self, tmp_path: Path):
        """Fails gracefully when the cookie file does not exist."""
        missing = tmp_path / "nonexistent" / "cookies.json"
        result = runner.invoke(app, ["auth", "validate", "--file", str(missing)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "Error" in result.output

    def test_validate_with_valid_cookies(self, tmp_path: Path):
        """Validates successfully when the cookie file contains all required cookies."""
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(VALID_COOKIES), encoding="utf-8")

        result = runner.invoke(app, ["auth", "validate", "--file", str(cookie_file)])
        assert result.exit_code == 0
        assert "Valid" in result.output
        assert "4 cookies" in result.output

    def test_validate_with_invalid_cookies(self, tmp_path: Path):
        """Fails when cookie file is missing required cookies."""
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")

        result = runner.invoke(app, ["auth", "validate", "--file", str(cookie_file)])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_validate_with_corrupt_json(self, tmp_path: Path):
        """Fails when cookie file contains invalid JSON."""
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("not-valid-json{{{", encoding="utf-8")

        result = runner.invoke(app, ["auth", "validate", "--file", str(cookie_file)])
        assert result.exit_code == 1
        assert "Error" in result.output


class TestAuthStatus:
    """Tests for ``safari auth status``."""

    def test_status_no_cookies(self, tmp_path: Path):
        """Shows guidance when no cookie file exists."""
        fake_path = tmp_path / "nonexistent_cookies.json"

        with patch(
            "safaribooks.cli.auth._default_cookie_path",
            return_value=fake_path,
        ):
            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "No cookie file found" in result.output or "not found" in result.output.lower()

    def test_status_with_valid_cookies(self, tmp_path: Path):
        """Shows cookie count when a valid cookie file exists."""
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(VALID_COOKIES), encoding="utf-8")

        with patch(
            "safaribooks.cli.auth._default_cookie_path",
            return_value=cookie_file,
        ):
            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "Valid" in result.output
        assert "4 cookies" in result.output

    def test_status_with_corrupt_file(self, tmp_path: Path):
        """Shows error status when cookie file is unreadable."""
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text("<<<broken>>>", encoding="utf-8")

        with patch(
            "safaribooks.cli.auth._default_cookie_path",
            return_value=cookie_file,
        ):
            result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0  # status never exits 1
        assert "Invalid" in result.output or "Error" in result.output or "error" in result.output


class TestAuthImport:
    """Tests for ``safari auth import``."""

    def test_import_no_source_fails(self):
        """Fails when neither --file nor --header is provided."""
        result = runner.invoke(app, ["auth", "import"])
        assert result.exit_code == 1
        assert "Provide --file or --header" in result.output

    def test_import_from_file(self, tmp_path: Path):
        """Imports cookies from a JSON file and saves to the output location."""
        source = tmp_path / "source_cookies.json"
        source.write_text(json.dumps(VALID_COOKIES), encoding="utf-8")

        dest = tmp_path / "output" / "cookies.json"
        result = runner.invoke(
            app,
            ["auth", "import", "--file", str(source), "--output", str(dest)],
        )
        assert result.exit_code == 0
        assert "Cookies saved" in result.output
        assert dest.is_file()

        saved = json.loads(dest.read_text(encoding="utf-8"))
        assert saved["jwt"] == VALID_COOKIES["jwt"]

    def test_import_from_header(self, tmp_path: Path):
        """Imports cookies from a Cookie header string."""
        header = "; ".join(f"{k}={v}" for k, v in VALID_COOKIES.items())
        dest = tmp_path / "cookies.json"

        result = runner.invoke(
            app,
            ["auth", "import", "--header", header, "--output", str(dest)],
        )
        assert result.exit_code == 0
        assert "Cookies saved" in result.output
        assert dest.is_file()

        saved = json.loads(dest.read_text(encoding="utf-8"))
        for key in VALID_COOKIES:
            assert key in saved

    def test_import_from_header_with_prefix(self, tmp_path: Path):
        """Handles the ``Cookie:`` prefix in the header string."""
        header = "Cookie: " + "; ".join(f"{k}={v}" for k, v in VALID_COOKIES.items())
        dest = tmp_path / "cookies.json"

        result = runner.invoke(
            app,
            ["auth", "import", "--header", header, "--output", str(dest)],
        )
        assert result.exit_code == 0
        assert "Cookies saved" in result.output

    def test_import_from_file_missing_required_cookies(self, tmp_path: Path):
        """Fails when imported file lacks required cookies."""
        source = tmp_path / "bad_cookies.json"
        source.write_text(json.dumps({"random_key": "random_val"}), encoding="utf-8")

        dest = tmp_path / "output_cookies.json"
        result = runner.invoke(
            app,
            ["auth", "import", "--file", str(source), "--output", str(dest)],
        )
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_import_from_nonexistent_file(self, tmp_path: Path):
        """Fails when the source file does not exist."""
        missing = tmp_path / "nope.json"
        dest = tmp_path / "out.json"
        result = runner.invoke(
            app,
            ["auth", "import", "--file", str(missing), "--output", str(dest)],
        )
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_import_from_empty_header(self, tmp_path: Path):
        """Fails when the header string yields no parseable cookies."""
        dest = tmp_path / "cookies.json"
        result = runner.invoke(
            app,
            ["auth", "import", "--header", "", "--output", str(dest)],
        )
        assert result.exit_code == 1
        assert "Error" in result.output
