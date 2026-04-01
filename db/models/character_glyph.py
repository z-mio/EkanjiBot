"""Character glyph model for storing character to emoji mappings."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from db.models.base import CreatedAtField

if TYPE_CHECKING:
    from db.models.font import Font


class CharacterGlyph(SQLModel, table=True):
    """Character glyph table - stores character to custom emoji mappings.

    This is permanent storage (not a cache), as each character only needs to be
    rendered once per font and then reused via the custom emoji ID.
    """

    __tablename__ = "character_glyphs"

    id: int | None = Field(default=None, primary_key=True)
    character: str = Field(max_length=1, description="Single character")
    custom_emoji_id: str = Field(max_length=64, description="Telegram custom emoji ID")
    file_id: str = Field(max_length=255, description="Telegram file ID")
    emoji_list: str = Field(default="✏️", max_length=20, description="Associated emoji list")
    created_at: datetime = CreatedAtField()

    # Foreign key
    font_id: int = Field(foreign_key="fonts.id", index=True)

    # Relationships
    font: "Font" = Relationship(back_populates="glyphs")
