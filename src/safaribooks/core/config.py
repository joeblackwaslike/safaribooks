"""Application configuration using pydantic-settings."""


from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Runtime configuration for safaribooks.

    Values are loaded from environment variables prefixed with ``SAFARI_``
    and from a ``.env`` file if present.
    """

    model_config = SettingsConfigDict(env_prefix="SAFARI_", env_file=".env", extra="ignore")

    cookies_file: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "safaribooks" / "cookies.json",
    )
    output_dir: Path = Field(default=Path("Books"))
    library_dir: Path = Field(
        default_factory=lambda: Path.home() / ".safaribooks",
    )
    kindle: bool = False
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
