"""Sticker set model for quota management."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from db.models.base import CreatedAtField, UpdatedAtField

if TYPE_CHECKING:
    from db.models.user import User


class StickerSet(SQLModel, table=True):
    """Sticker set table for managing pack quotas per user.

    Telegram allows 120 custom emoji stickers per pack, but unlimited
    packs per user. This table tracks pack usage and availability.

    Attributes:
        id: Database primary key.
        pack_name: Telegram sticker set name (e.g., "u12345_p1_by_botname").
        pack_index: Sequential pack number for this user (1, 2, 3...).
        sticker_count: Current number of stickers in pack.
        max_stickers: Maximum stickers allowed (120 per pack).
        pack_type: Sticker set type (default "custom_emoji").
        is_full: Whether pack has reached capacity.
        is_active: Whether pack is active (not deleted).
        user_id: Foreign key to users table.
        created_at: Timestamp when record was created.
        updated_at: Timestamp when record was last updated.
    """

    __tablename__ = "sticker_sets"

    id: int | None = Field(default=None, primary_key=True)
    pack_name: str = Field(max_length=64, unique=True, description="Telegram sticker set name")
    pack_index: int = Field(description="Pack number for this user")
    sticker_count: int = Field(default=0, description="Current number of stickers")
    max_stickers: int = Field(default=120, description="Maximum stickers allowed (120 per pack)")
    pack_type: str = Field(default="custom_emoji", max_length=20)
    is_full: bool = Field(default=False, description="Whether pack is full")
    is_active: bool = Field(default=True)
    created_at: datetime = CreatedAtField()
    updated_at: datetime = UpdatedAtField()

    # Foreign key
    user_id: int = Field(foreign_key="users.id", index=True)

    # Relationships
    user: "User" = Relationship(back_populates="sticker_sets")

    def has_space(self) -> bool:
        """Check if pack has space for more stickers.

        Returns:
            True if pack can accept more stickers, False otherwise.
        """
        return not self.is_full and self.sticker_count < self.max_stickers
