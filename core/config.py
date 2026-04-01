"""Bot configuration management using Pydantic Settings.

This module provides centralized configuration management for the EkanjiBot
Telegram bot, including environment variables, path management, and validation.
"""

from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    """Bot configuration settings loaded from environment variables.

    All settings are loaded from .env file or environment variables.
    Provides centralized access to bot configuration including:
    - Telegram Bot API credentials
    - Database connection settings
    - File system paths
    - Proxy configuration

    Attributes:
        bot_token: Telegram Bot API token from @BotFather
        bot_proxy: Optional proxy URL for API requests
        debug: Enable debug logging mode
        database_url: SQLAlchemy async database connection URL
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str
    bot_proxy: str | None = Field(default=None)
    debug: bool = Field(default=False)

    # Database settings
    database_url: str = Field(default="sqlite+aiosqlite:///./data/bot.db")

    @property
    def base_dir(self) -> Path:
        """Get project root directory.

        Returns:
            Absolute path to project root directory.
        """
        return Path(__file__).resolve().parent.parent

    @property
    def data_dir(self) -> Path:
        """Get data directory, creating if needed.

        Returns:
            Absolute path to data directory.
        """
        path = self.base_dir / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def assets_dir(self) -> Path:
        """Get assets directory, creating if needed.

        Returns:
            Absolute path to assets directory.
        """
        path = self.base_dir / "assets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def fonts_dir(self) -> Path:
        """Get fonts directory, creating if needed.

        Returns:
            Absolute path to fonts directory.
        """
        path = self.assets_dir / "fonts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @field_validator("bot_proxy", mode="before")
    @classmethod
    def validate_proxy(cls, v: str | None) -> str | None:
        """Validate and normalize proxy URL.

        Args:
            v: Raw proxy URL from environment.

        Returns:
            Normalized proxy URL or None if empty.
        """
        url = urlparse(v) if v else None
        if not url:
            return None
        return url.geturl()

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure SQLite URL uses async driver.

        Automatically converts 'sqlite://' to 'sqlite+aiosqlite://'.

        Args:
            v: Database URL from environment.

        Returns:
            Database URL with async driver.
        """
        if v.startswith("sqlite://") and not v.startswith("sqlite+aiosqlite://"):
            return v.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return v

    @property
    def bot_session_name(self) -> str:
        """Generate unique session name from bot token.

        Returns:
            Session name based on bot token prefix.
        """
        return f"bot_{self.bot_token.split(':')[0]}"


bs = BotSettings()
