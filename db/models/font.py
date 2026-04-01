"""Font model for available fonts."""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from core.config import bs
from db.models.base import CreatedAtField

if TYPE_CHECKING:
    from db.models.character_glyph import CharacterGlyph


class Font(SQLModel, table=True):
    """Font table for storing available fonts."""

    __tablename__ = "fonts"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=64, description="Font display name")
    file_path: str = Field(max_length=256, description="Relative path to font file")
    is_active: bool = Field(default=True)
    created_at: datetime = CreatedAtField()

    # Relationships
    glyphs: list["CharacterGlyph"] = Relationship(back_populates="font")

    def get_absolute_path(self) -> Path:
        """Get absolute path to font file."""
        return bs.fonts_dir / self.file_path
