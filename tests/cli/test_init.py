"""Tests for the top-level ``safari`` CLI app (``safaribooks.cli``)."""

from unittest.mock import patch

from typer.testing import CliRunner

from safaribooks.cli import app

runner = CliRunner()


class TestVersion:
    """Tests for the ``--version`` / ``-v`` eager option."""

    def test_version_long_flag(self):
        """``--version`` prints the package version and exits cleanly."""
        with patch("safaribooks.cli._pkg_version", return_value="9.9.9") as mock_ver:
            result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "safari" in result.output
        assert "9.9.9" in result.output
        mock_ver.assert_called_once_with("safaribookshelf")

    def test_version_short_flag(self):
        """``-v`` is an alias for ``--version``."""
        with patch("safaribooks.cli._pkg_version", return_value="1.2.3"):
            result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "1.2.3" in result.output

    def test_version_does_not_invoke_subcommand(self):
        """Passing ``--version`` exits before any subcommand runs."""
        with patch("safaribooks.cli.fetch._fetch_async") as mock_fetch, patch(
            "safaribooks.cli._pkg_version", return_value="0.0.1"
        ):
            result = runner.invoke(app, ["--version", "fetch", "12345"])
        assert result.exit_code == 0
        mock_fetch.assert_not_called()


class TestRootHelp:
    """Tests for the root help / no-args behavior."""

    def test_no_args_shows_help(self):
        """``no_args_is_help=True`` surfaces help when invoked with no args."""
        result = runner.invoke(app, [])
        # Typer exits with code 0 (or 2) when showing help for no args; help text present.
        assert "fetch" in result.output
        assert "auth" in result.output

    def test_help_flag(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "fetch" in result.output
        assert "auth" in result.output


class TestDebugCallback:
    """Tests for the default callback path that stores the debug flag.

    The root ``main`` callback writes ``ctx.obj["debug"]``; ``fetch_cmd`` then
    reads it into the ``AppConfig`` it builds. We patch ``_fetch_async`` (the
    network-bound pipeline) so we can inspect the resulting config without I/O.
    """

    @staticmethod
    def _run_and_capture_config(args: list[str], env: dict[str, str] | None = None):
        from unittest.mock import AsyncMock

        mock = AsyncMock()
        with patch("safaribooks.cli.fetch._fetch_async", mock):
            result = runner.invoke(app, args, env=env)
        return result, mock

    def test_debug_flag_stored_in_context(self):
        """The ``--debug`` flag flows into the built ``AppConfig``."""
        result, mock = self._run_and_capture_config(["--debug", "fetch", "12345"])
        assert result.exit_code == 0
        config = mock.call_args.args[0]
        assert config.debug is True

    def test_debug_defaults_false(self):
        """Without ``--debug`` the context records ``debug=False``."""
        result, mock = self._run_and_capture_config(["fetch", "12345"])
        assert result.exit_code == 0
        config = mock.call_args.args[0]
        assert config.debug is False

    def test_debug_envvar(self):
        """``SAFARI_DEBUG`` env var toggles the debug flag."""
        result, mock = self._run_and_capture_config(
            ["fetch", "12345"], env={"SAFARI_DEBUG": "1"}
        )
        assert result.exit_code == 0
        config = mock.call_args.args[0]
        assert config.debug is True


class TestAppRegistration:
    """Sanity checks on app wiring."""

    def test_subcommands_registered(self):
        """Both the ``auth`` group and ``fetch`` command are registered."""
        result = runner.invoke(app, ["--help"])
        assert "auth" in result.output
        assert "fetch" in result.output
