"""Character glyph repository for managing character to emoji mappings."""

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.character_glyph import CharacterGlyph
from db.repositories.base import BaseRepository


class CharacterGlyphRepository(BaseRepository[CharacterGlyph]):
    """Repository for CharacterGlyph model."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, CharacterGlyph)

    async def get_by_character_and_font(self, character: str, font_id: int) -> CharacterGlyph | None:
        """Get glyph for specific character and font."""
        result = await self.session.execute(
            select(CharacterGlyph).where(and_(CharacterGlyph.character == character, CharacterGlyph.font_id == font_id))
        )
        return result.scalar_one_or_none()

    async def get_by_custom_emoji_id(self, emoji_id: str) -> CharacterGlyph | None:
        """Get glyph by custom emoji ID."""
        result = await self.session.execute(select(CharacterGlyph).where(CharacterGlyph.custom_emoji_id == emoji_id))
        return result.scalar_one_or_none()

    async def get_glyphs_for_font(self, font_id: int, skip: int = 0, limit: int = 100) -> list[CharacterGlyph]:
        """Get all glyphs for a font."""
        result = await self.session.execute(
            select(CharacterGlyph).where(CharacterGlyph.font_id == font_id).offset(skip).limit(limit)
        )
        return list(result.scalars().all())
