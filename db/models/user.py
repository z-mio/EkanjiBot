"""User model for language preferences and tracking."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from db.models.base import CreatedAtField, UpdatedAtField

if TYPE_CHECKING:
    from db.models.font import Font
    from db.models.sticker_set import StickerSet


class User(SQLModel, table=True):
    """User table storing Telegram user information and preferences.

    Tracks user metadata from Telegram and application-specific settings
    like language preference, font preference, and admin status.

    Attributes:
        id: Database primary key.
        telegram_id: Telegram User ID (unique).
        username: Telegram username without @, or None.
        full_name: User's display name.
        language: Preferred language code (default "zh" for Chinese).
        preferred_font_id: User's preferred font ID, or None to use default.
        is_admin: Whether user has admin privileges.
        is_active: Whether user account is active.
        created_at: Timestamp when record was created.
        updated_at: Timestamp when record was last updated.
    """

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    telegram_id: int = Field(index=True, unique=True, description="Telegram User ID")
    username: str | None = Field(default=None, max_length=32)
    full_name: str = Field(max_length=128)
    language: str = Field(default="zh", max_length=2, description="Language code (e.g., zh, en)")
    preferred_font_id: int | None = Field(default=None, foreign_key="fonts.id", description="Preferred font ID")
    is_admin: bool = Field(default=False)
    is_active: bool = Field(default=True)
    created_at: datetime = CreatedAtField()
    updated_at: datetime = UpdatedAtField()

    # Relationships
    created_packs: list["StickerSet"] = Relationship(back_populates="creator")
    preferred_font: "Font" = Relationship()
