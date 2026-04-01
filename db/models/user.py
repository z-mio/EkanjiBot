"""User model for language preferences and tracking."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from db.models.base import CreatedAtField, UpdatedAtField

if TYPE_CHECKING:
    from db.models.sticker_set import StickerSet


class User(SQLModel, table=True):
    """User table with language preferences."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    telegram_id: int = Field(index=True, unique=True, description="Telegram User ID")
    username: str | None = Field(default=None, max_length=32)
    full_name: str = Field(max_length=128)
    language: str = Field(default="zh", max_length=2, description="Language code (e.g., zh, en, ru)")
    is_admin: bool = Field(default=False)
    is_active: bool = Field(default=True)
    created_at: datetime = CreatedAtField()
    updated_at: datetime = UpdatedAtField()

    # Relationships
    sticker_sets: list["StickerSet"] = Relationship(back_populates="user")
