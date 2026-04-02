"""Sticker set repository with quota management."""

import asyncio

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

    async def increment_sticker_count_with_retry(
        self,
        pack_id: int,
        max_retries: int = 3,
        base_delay: float = 0.1,
    ) -> StickerSet | None:
        """Increment sticker count with retry on database lock.

        SQLite can have concurrency issues with concurrent writes.
        This method retries the update if a lock conflict occurs.

        Args:
            pack_id: Sticker set ID to update.
            max_retries: Maximum number of retry attempts.
            base_delay: Base delay between retries (exponential backoff).

        Returns:
            Updated StickerSet or None if not found.
        """
        from sqlite3 import OperationalError

        for attempt in range(max_retries):
            try:
                # Use SELECT FOR UPDATE equivalent (SQLite doesn't support it directly)
                # But we can use a fresh query to get current state
                result = await self.session.execute(select(StickerSet).where(StickerSet.id == pack_id))
                pack = result.scalar_one_or_none()

                if not pack:
                    return None

                # Increment and check full status
                pack.sticker_count += 1
                if pack.sticker_count >= pack.max_stickers:
                    pack.is_full = True

                # Try to flush immediately to catch lock errors early
                await self.session.flush()
                return pack

            except OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    # Exponential backoff
                    delay = base_delay * (2**attempt)
                    await asyncio.sleep(delay)
                    # Refresh session to clear any pending state
                    await self.session.rollback()
                    continue
                raise

        return None

    async def increment_sticker_count(self, pack_id: int) -> StickerSet | None:
        """Increment sticker count and check if pack is full.

        Uses retry logic for SQLite concurrency safety.
        """
        return await self.increment_sticker_count_with_retry(pack_id)
