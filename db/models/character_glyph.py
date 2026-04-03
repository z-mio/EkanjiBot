"""Character glyph model for storing character to emoji mappings."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from core.constants import CUSTOM_EMOJI_PLACEHOLDER
from db.models.base import CreatedAtField

if TYPE_CHECKING:
    from db.models.font import Font


class CharacterGlyph(SQLModel, table=True):
    """Character glyph table storing character to custom emoji mappings.

    This is permanent storage (not cache) - each character is rendered once
    per font and reused via the custom emoji ID. Characters are uniquely
    identified by the combination of character + font.

    Attributes:
        id: Database primary key.
        character: Single Unicode character.
        custom_emoji_id: Telegram custom emoji ID for this character.
        file_id: Telegram file ID for the sticker.
        emoji_list: Associated emoji list (default "✏️").
        font_id: Foreign key to fonts table.
        created_at: Timestamp when record was created.
    """

    __tablename__ = "character_glyphs"

    # Unique constraint: one glyph per character per font
    __table_args__ = (
        {"sqlite_autoincrement": True},  # Auto-increment primary key
    )

    id: int | None = Field(default=None, primary_key=True)
    character: str = Field(max_length=1, description="Single Unicode character")
    custom_emoji_id: str = Field(max_length=64, description="Telegram custom emoji ID")
    file_id: str = Field(max_length=255, description="Telegram file ID")
    emoji_list: str = Field(default=CUSTOM_EMOJI_PLACEHOLDER, max_length=20, description="Associated emoji list")
    created_at: datetime = CreatedAtField()

    # Foreign key
    font_id: int = Field(foreign_key="fonts.id", index=True)

    # Relationships
    font: "Font" = Relationship(back_populates="glyphs")
