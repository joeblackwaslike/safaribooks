"""Tests for the standalone ``safari markdown`` CLI command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_markdown_help_registered() -> None:
    result = runner.invoke(app, ["markdown", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "--output" in result.output
    assert "--force" in result.output


@patch("safaribooks.cli.markdown.AppConfig")
def test_markdown_converts_existing_epub(config_cls: MagicMock, tmp_path: Path) -> None:
    config_cls.return_value = _config_stub()
    epub = _build(tmp_path)
    out_dir = tmp_path / "out"
    result = runner.invoke(app, ["markdown", str(epub), "-o", str(out_dir)])
    assert result.exit_code == 0, result.output
    md = out_dir / "book.md"
    assert md.is_file()
    text = md.read_text("utf-8")
    assert text.startswith("---\n")
    assert "## One" in text


@patch("safaribooks.cli.markdown.AppConfig")
def test_markdown_refuses_overwrite(config_cls: MagicMock, tmp_path: Path) -> None:
    config_cls.return_value = _config_stub()
    epub = _build(tmp_path)
    runner.invoke(app, ["markdown", str(epub)])
    result = runner.invoke(app, ["markdown", str(epub)])
    assert result.exit_code == 1
    assert "force" in result.output.lower()
