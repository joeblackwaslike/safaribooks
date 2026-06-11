"""Tests for safaribooks.core.config."""


from pathlib import Path

from safaribooks.core.config import AppConfig


class TestAppConfigDefaults:
    def test_default_output_dir(self):
        config = AppConfig()
        assert config.output_dir == Path("Books")

    def test_default_kindle_false(self):
        config = AppConfig()
        assert config.kindle is False

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

    def test_default_library_dir(self):
        config = AppConfig()
        assert config.library_dir == Path.home() / ".safaribooks"

    def test_default_cookies_file_path(self):
        config = AppConfig()
        expected = Path.home() / ".config" / "safaribooks" / "cookies.json"
        assert config.cookies_file == expected

    def test_default_rate_limit(self):
        config = AppConfig()
        assert config.rate_limit == 1.0

    def test_default_rate_burst(self):
        config = AppConfig()
        assert config.rate_burst == 2


class TestAppConfigFromEnv:
    def test_output_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_OUTPUT_DIR", "/tmp/mybooks")
        config = AppConfig()
        assert config.output_dir == Path("/tmp/mybooks")

    def test_kindle_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_KINDLE", "true")
        config = AppConfig()
        assert config.kindle is True

    def test_image_max_size_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_IMAGE_MAX_SIZE", "800")
        config = AppConfig()
        assert config.image_max_size == 800

    def test_image_quality_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_IMAGE_QUALITY", "75")
        config = AppConfig()
        assert config.image_quality == 75

    def test_debug_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_DEBUG", "1")
        config = AppConfig()
        assert config.debug is True

    def test_cookies_file_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_COOKIES_FILE", "/tmp/cookies.json")
        config = AppConfig()
        assert config.cookies_file == Path("/tmp/cookies.json")

    def test_rate_limit_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_RATE_LIMIT", "5.0")
        config = AppConfig()
        assert config.rate_limit == 5.0

    def test_rate_burst_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_RATE_BURST", "10")
        config = AppConfig()
        assert config.rate_burst == 10

    def test_library_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("SAFARI_LIBRARY_DIR", "/tmp/mylib")
        config = AppConfig()
        assert config.library_dir == Path("/tmp/mylib")

    def test_rate_limit_zero_disables(self, monkeypatch):
        monkeypatch.setenv("SAFARI_RATE_LIMIT", "0")
        config = AppConfig()
        assert config.rate_limit == 0.0
