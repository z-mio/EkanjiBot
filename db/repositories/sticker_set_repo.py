"""Sticker set repository with quota management."""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.sticker_set import StickerSet
from db.repositories.base import BaseRepository


class StickerSetRepository(BaseRepository[StickerSet]):
    """Repository for StickerSet model with quota management."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, StickerSet)

    async def get_by_pack_name(self, pack_name: str) -> StickerSet | None:
        """Get sticker set by Telegram pack name."""
        result = await self.session.execute(select(StickerSet).where(StickerSet.pack_name == pack_name))
        return result.scalar_one_or_none()

    async def get_user_packs(self, user_id: int) -> list[StickerSet]:
        """Get all sticker packs for a user."""
        result = await self.session.execute(
            select(StickerSet).where(StickerSet.user_id == user_id).order_by(StickerSet.pack_index)
        )
        return list(result.scalars().all())

    async def get_available_pack(self, user_id: int) -> StickerSet | None:
        """Get a non-full sticker pack for user."""
        result = await self.session.execute(
            select(StickerSet)
            .where(
                and_(
                    StickerSet.user_id == user_id,
                    StickerSet.is_full.is_(False),
                    StickerSet.is_active.is_(True),
                    StickerSet.sticker_count < StickerSet.max_stickers,
                )
            )
            .order_by(StickerSet.pack_index)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_next_pack_index(self, user_id: int) -> int:
        """Get next available pack index for user."""
        result = await self.session.execute(
            select(func.max(StickerSet.pack_index)).where(StickerSet.user_id == user_id)
        )
        max_index = result.scalar() or 0
        return max_index + 1

    async def increment_sticker_count(self, pack_id: int) -> StickerSet | None:
        """Increment sticker count and check if pack is full."""
        pack = await self.get_by_id(pack_id)
        if not pack:
            return None

        pack.sticker_count += 1
        if pack.sticker_count >= pack.max_stickers:
            pack.is_full = True

        await self.session.flush()
        return pack
