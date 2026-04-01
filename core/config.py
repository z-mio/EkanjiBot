from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
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

    # Path settings
    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def data_dir(self) -> Path:
        path = self.base_dir / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def assets_dir(self) -> Path:
        path = self.base_dir / "assets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def fonts_dir(self) -> Path:
        path = self.assets_dir / "fonts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @field_validator("bot_proxy", mode="before")
    @classmethod
    def proxy_config(cls, v: str | None = None) -> str | None:
        url = urlparse(v) if v else None
        if not url:
            return None
        return url.geturl()

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure using async driver for SQLite"""
        if v.startswith("sqlite://") and not v.startswith("sqlite+aiosqlite://"):
            return v.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return v

    @property
    def bot_session_name(self) -> str:
        return f"bot_{self.bot_token.split(':')[0]}"


bs = BotSettings()  # type: ignore
