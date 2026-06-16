"""Tests for safaribooks.core.config."""

from pathlib import Path

import pytest

from safaribooks.core.config import AppConfig

_RATE_LIMIT_DEFAULT = 1.0
_RATE_LIMIT_CUSTOM = 5.0
_RATE_LIMIT_DISABLED = float(0)
_RATE_BURST_DEFAULT = 2
_RATE_BURST_CUSTOM = 10
_IMAGE_MAX_SIZE = 800
_IMAGE_QUALITY = 75


class TestAppConfigDefaultPaths:
    def test_default_output_dir(self):
        config = AppConfig()
        assert config.output_dir == Path("Books")

    def test_default_library_dir(self):
        config = AppConfig()
        assert config.library_dir == Path.home() / ".safaribooks"

    def test_default_cookies_file_path(self):
        config = AppConfig()
        expected = Path.home() / ".config" / "safaribooks" / "cookies.json"
        assert config.cookies_file == expected


class TestAppConfigDefaultFlags:
    def test_default_image_settings(self):
        config = AppConfig()
        assert config.image_max_size == 0
        assert config.image_quality == 0

    def test_default_ssl_skip_false(self):
        config = AppConfig()
        assert config.ssl_skip is False

    def test_default_debug_false(self):
        config = AppConfig()
        assert config.debug is False

    def test_default_preserve_log_false(self):
        config = AppConfig()
        assert config.preserve_log is False

    def test_default_rate_limit(self):
        config = AppConfig()
        assert config.rate_limit == pytest.approx(_RATE_LIMIT_DEFAULT)

    def test_default_rate_burst(self):
        config = AppConfig()
        assert config.rate_burst == _RATE_BURST_DEFAULT


class TestAppConfigPathsFromEnv:
    def test_output_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_OUTPUT_DIR", "/tmp/mybooks")
        config = AppConfig()
        assert config.output_dir == Path("/tmp/mybooks")

    def test_cookies_file_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_COOKIES_FILE", "/tmp/cookies.json")
        config = AppConfig()
        assert config.cookies_file == Path("/tmp/cookies.json")

    def test_library_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_LIBRARY_DIR", "/tmp/mylib")
        config = AppConfig()
        assert config.library_dir == Path("/tmp/mylib")


class TestAppConfigValuesFromEnv:
    def test_image_max_size_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_IMAGE_MAX_SIZE", "800")
        config = AppConfig()
        assert config.image_max_size == _IMAGE_MAX_SIZE

    def test_image_quality_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_IMAGE_QUALITY", "75")
        config = AppConfig()
        assert config.image_quality == _IMAGE_QUALITY

    def test_debug_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_DEBUG", "1")
        config = AppConfig()
        assert config.debug is True

    def test_rate_limit_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_RATE_LIMIT", "5.0")
        config = AppConfig()
        assert config.rate_limit == pytest.approx(_RATE_LIMIT_CUSTOM)

    def test_rate_burst_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_RATE_BURST", "10")
        config = AppConfig()
        assert config.rate_burst == _RATE_BURST_CUSTOM

    def test_rate_limit_zero_disables(self, monkeypatch):
        monkeypatch.setenv("SAFARI_RATE_LIMIT", "0")
        config = AppConfig()
        assert config.rate_limit == pytest.approx(_RATE_LIMIT_DISABLED)
