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
        """Get glyph for specific character and font.

        Returns the first match if multiple exist (handles potential duplicates
        from race conditions before unique constraint was added).
        """
        result = await self.session.execute(
            select(CharacterGlyph)
            .where(and_(CharacterGlyph.character == character, CharacterGlyph.font_id == font_id))
            .order_by(CharacterGlyph.id.asc())  # Get oldest/first one
            .limit(1)
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

    async def create_or_get(
        self,
        character: str,
        font_id: int,
        custom_emoji_id: str,
        file_id: str,
        emoji_list: str = "✏️",
    ) -> CharacterGlyph:
        """Create new glyph or return existing if duplicate exists.

        Handles race conditions where multiple concurrent requests try to
        create the same character+font combination.

        Args:
            character: Single Unicode character.
            font_id: Font ID.
            custom_emoji_id: Telegram custom emoji ID.
            file_id: Telegram file ID.
            emoji_list: Associated emoji list.

        Returns:
            Created or existing CharacterGlyph.
        """
        # First check if already exists (handles duplicate race condition)
        existing = await self.get_by_character_and_font(character, font_id)
        if existing:
            return existing

        # Create new glyph
        glyph = CharacterGlyph(
            character=character,
            font_id=font_id,
            custom_emoji_id=custom_emoji_id,
            file_id=file_id,
            emoji_list=emoji_list,
        )
        return await self.create(glyph)
