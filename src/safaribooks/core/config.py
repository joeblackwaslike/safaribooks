"""Application configuration using pydantic-settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

_DEFAULT_KEEPALIVE_INTERVAL = 300
_CONFIG_TOML = Path.home() / ".config" / "safaribooks" / "config.toml"


class AppConfig(BaseSettings):
    """Runtime configuration for safaribooks.

    Values are loaded from (highest priority first) constructor arguments,
    environment variables prefixed with ``SAFARI_``, a ``.env`` file, and a
    ``~/.config/safaribooks/config.toml`` file when present.
    """

    model_config = SettingsConfigDict(
        env_prefix="SAFARI_",
        env_file=".env",
        extra="ignore",
        toml_file=_CONFIG_TOML,
    )

    cookies_file: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "safaribooks" / "cookies.json",
    )
    output_dir: Path = Field(default=Path("Books"))
    library_dir: Path = Field(
        default_factory=lambda: Path.home() / ".safaribooks",
    )
    preserve_log: bool = False
    image_max_size: int = Field(
        default=0,
        description="Max image dimension in pixels, 0=no resize",
    )
    image_quality: int = Field(
        default=0,
        description="JPEG quality 1-95, 0=keep original",
    )
    ssl_skip: bool = False
    debug: bool = False
    rate_limit: float = Field(
        default=1.0,
        description="Max requests per second (0=unlimited).",
    )
    rate_burst: int = Field(
        default=2,
        description="Token bucket burst capacity.",
    )
    auto_refresh_browser: str | None = Field(
        default=None,
        description="Browser to auto-extract cookies from on session expiry (chrome/firefox/edge/chromium). None=disabled.",
    )
    keepalive_interval: int = Field(
        default=_DEFAULT_KEEPALIVE_INTERVAL,
        description="Seconds between session keepalive pings during downloads (0=disabled).",
    )
    markdown: bool = Field(
        default=False,
        description="Also write an LLM-oriented Markdown file beside the EPUB.",
    )
    markdown_only: bool = Field(
        default=False,
        description="Write only the Markdown file; build the EPUB to a temp dir and discard it.",
    )
    markdown_extensions: list[str] = Field(
        default_factory=list,
        description="Ordered Markdown transformation extension names (pipeline order).",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Add a TOML config-file source below env/.env but above secrets."""
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )
