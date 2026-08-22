"""Tests for Markdown-related AppConfig fields and the TOML config source."""

from pathlib import Path

import pytest
from pydantic_settings import SettingsConfigDict

from safaribooks.core.config import AppConfig


def _config_class(toml_path: Path) -> type[AppConfig]:
    """Return an AppConfig subclass that reads *toml_path* as its TOML source."""

    class _ScopedConfig(AppConfig):  # noqa: WPS431 -- needs a closure over toml_path
        model_config = SettingsConfigDict(
            env_prefix="SAFARI_",
            env_file=None,
            extra="ignore",
            toml_file=toml_path,
        )

    return _ScopedConfig


def test_defaults_are_empty() -> None:
    config = AppConfig(_env_file=None)  # type: ignore[call-arg]
    assert config.markdown is False
    assert config.markdown_only is False
    assert config.markdown_extensions == []


def test_toml_loads_extension_list(tmp_path: Path) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text(
        'markdown_extensions = ["fix-headings", "remove-footnotes"]\n',
        encoding="utf-8",
    )
    config = _config_class(toml)()
    assert config.markdown_extensions == ["fix-headings", "remove-footnotes"]


def test_missing_toml_is_fine(tmp_path: Path) -> None:
    config = _config_class(tmp_path / "absent.toml")()
    assert config.markdown_extensions == []


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml = tmp_path / "config.toml"
    toml.write_text("markdown = false\n", encoding="utf-8")
    monkeypatch.setenv("SAFARI_MARKDOWN", "true")
    config = _config_class(toml)()
    assert config.markdown is True
