"""Tests for the standalone ``safari markdown`` CLI command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import click
from typer.testing import CliRunner

from safaribooks.cli import app
from tests.core.markdown._epub import ChapterSpec, build_epub

runner = CliRunner()


def _config_stub(extensions: list[str] | None = None) -> MagicMock:
    """Return an AppConfig stub with controlled markdown_extensions."""
    config = MagicMock()
    config.markdown_extensions = extensions or []
    return config


def _build(tmp_path: Path) -> Path:
    specs = [ChapterSpec("One", "<p>hello</p>"), ChapterSpec("Two", "<p>world</p>")]
    return build_epub(tmp_path / "book.epub", "A Book", specs)


def _invoke_markdown(*args: str, env: dict[str, str] | None = None):
    """Invoke the ``safari markdown`` command with *args*."""
    return runner.invoke(app, ["markdown", *args], env=env)


def test_markdown_help_registered() -> None:
    # CI renders this with ANSI color codes on (this shell's Console detects
    # no color support, so it doesn't); Typer's option highlighter then styles
    # a flag's leading "-" in a separate span from the rest of the name, so a
    # plain substring check only breaks when color is on. Strip ANSI codes
    # (see the identical fix in tests/cli/test_fetch.py) instead of guessing
    # at console width, which has no effect here either.
    invoke_result = _invoke_markdown("--help")
    assert invoke_result.exit_code == 0
    output = click.unstyle(invoke_result.output)
    assert "--output" in output
    assert "--force" in output


@patch("safaribooks.cli.markdown.AppConfig")
def test_markdown_converts_existing_epub(config_cls: MagicMock, tmp_path: Path) -> None:
    config_cls.return_value = _config_stub()
    epub = _build(tmp_path)
    out_dir = tmp_path / "out"
    invoke_result = _invoke_markdown(str(epub), "-o", str(out_dir))
    assert invoke_result.exit_code == 0, invoke_result.output
    md = out_dir / "book.md"
    assert md.is_file()
    text = md.read_text("utf-8")
    assert text.startswith("---\n")
    assert "## One" in text


@patch("safaribooks.cli.markdown.AppConfig")
def test_markdown_refuses_overwrite(config_cls: MagicMock, tmp_path: Path) -> None:
    config_cls.return_value = _config_stub()
    epub = _build(tmp_path)
    _invoke_markdown(str(epub))
    invoke_result = _invoke_markdown(str(epub))
    assert invoke_result.exit_code == 1
    assert "force" in invoke_result.output.lower()
