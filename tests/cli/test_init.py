"""Tests for the top-level ``safari`` CLI app (``safaribooks.cli``)."""

from collections.abc import Sequence
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from safaribooks.cli import app

runner = CliRunner()

_EXIT_OK = 0

_FETCH_ARGS = ("fetch", "12345")
_DEBUG_FETCH_ARGS = ("--debug", *_FETCH_ARGS)


def _run_and_capture_config(args: Sequence[str], env: dict[str, str] | None = None):
    """Invoke the CLI and return the result plus the patched ``_fetch_async`` mock.

    The root ``main`` callback writes ``ctx.obj["debug"]``; ``fetch_cmd`` then
    reads it into the ``AppConfig`` it builds. We patch ``_fetch_async`` (the
    network-bound pipeline) so we can inspect the resulting config without I/O.
    """
    mock = AsyncMock()
    with patch("safaribooks.cli.fetch._fetch_async", mock):
        outcome = runner.invoke(app, args, env=env)
    return outcome, mock


class TestVersion:
    """Tests for the ``--version`` / ``-v`` eager option."""

    def test_version_long_flag(self):
        """``--version`` prints the package version and exits cleanly."""
        with patch("safaribooks.cli._pkg_version", return_value="9.9.9") as mock_ver:
            outcome = runner.invoke(app, ["--version"])
            mock_ver.assert_called_once_with("safaribookshelf")
        assert outcome.exit_code == _EXIT_OK
        assert "safari" in outcome.output
        assert "9.9.9" in outcome.output

    def test_version_short_flag(self):
        """``-v`` is an alias for ``--version``."""
        with patch("safaribooks.cli._pkg_version", return_value="1.2.3"):
            outcome = runner.invoke(app, ["-v"])
        assert outcome.exit_code == _EXIT_OK
        assert "1.2.3" in outcome.output

    def test_version_does_not_invoke_subcommand(self):
        """Passing ``--version`` exits before any subcommand runs."""
        with (
            patch("safaribooks.cli.fetch._fetch_async") as mock_fetch,
            patch("safaribooks.cli._pkg_version", return_value="0.0.1"),
        ):
            outcome = runner.invoke(app, ["--version", "fetch", "12345"])
            mock_fetch.assert_not_called()
        assert outcome.exit_code == _EXIT_OK


class TestRootHelp:
    """Tests for the root help / no-args behavior."""

    def test_no_args_shows_help(self):
        """``no_args_is_help=True`` surfaces help when invoked with no args."""
        outcome = runner.invoke(app, [])
        # Typer exits with code 0 (or 2) when showing help for no args; help text present.
        assert "fetch" in outcome.output
        assert "auth" in outcome.output

    def test_help_flag(self):
        outcome = runner.invoke(app, ["--help"])
        assert outcome.exit_code == _EXIT_OK
        assert "fetch" in outcome.output
        assert "auth" in outcome.output


class TestDebugCallback:
    """Tests for the default callback path that stores the debug flag."""

    def test_debug_flag_stored_in_context(self):
        """The ``--debug`` flag flows into the built ``AppConfig``."""
        outcome, mock = _run_and_capture_config(_DEBUG_FETCH_ARGS)
        assert outcome.exit_code == _EXIT_OK
        config = mock.call_args.args[0]
        assert config.debug is True

    def test_debug_defaults_false(self):
        """Without ``--debug`` the context records ``debug=False``."""
        outcome, mock = _run_and_capture_config(_FETCH_ARGS)
        assert outcome.exit_code == _EXIT_OK
        config = mock.call_args.args[0]
        assert config.debug is False

    def test_debug_envvar(self):
        """``SAFARI_DEBUG`` env var toggles the debug flag."""
        outcome, mock = _run_and_capture_config(_FETCH_ARGS, env={"SAFARI_DEBUG": "1"})
        assert outcome.exit_code == _EXIT_OK
        config = mock.call_args.args[0]
        assert config.debug is True


class TestAppRegistration:
    """Sanity checks on app wiring."""

    def test_subcommands_registered(self):
        """Both the ``auth`` group and ``fetch`` command are registered."""
        outcome = runner.invoke(app, ["--help"])
        assert "auth" in outcome.output
        assert "fetch" in outcome.output
