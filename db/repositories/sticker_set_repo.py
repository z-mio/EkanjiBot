"""Sticker set repository with quota management."""

import asyncio

from loguru import logger
from sqlalchemy import and_, func, select, update
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
        max_retries: int = 10,
        base_delay: float = 0.5,
    ) -> StickerSet | None:
        """Increment sticker count with retry on database lock.

        Uses atomic UPDATE statement instead of SELECT+UPDATE pattern
        to minimize lock contention with SQLite.

        Args:
            pack_id: Sticker set ID to update.
            max_retries: Maximum number of retry attempts (default 10).
            base_delay: Base delay between retries in seconds (default 0.5s, exponential backoff).

        Returns:
            Updated StickerSet or None if not found.
        """
        from sqlite3 import OperationalError

        for attempt in range(max_retries):
            try:
                # Use atomic UPDATE with RETURNING to get the updated row
                result = await self.session.execute(
                    update(StickerSet)
                    .where(StickerSet.id == pack_id)
                    .values(sticker_count=StickerSet.sticker_count + 1)
                    .returning(StickerSet)
                )
                pack = result.scalar_one_or_none()

                if not pack:
                    return None

                # Check if pack is now full
                if pack.sticker_count >= pack.max_stickers and not pack.is_full:
                    pack.is_full = True
                    await self.session.flush()

                return pack

            except OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    # Exponential backoff: 0.5s, 1s, 2s, 4s, 8s...
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        f"Database locked during increment_sticker_count (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                    # Rollback to clear any pending transaction state
                    await self.session.rollback()
                    continue
                raise

        return None

    async def increment_sticker_count(self, pack_id: int) -> StickerSet | None:
        """Increment sticker count and check if pack is full.

        Uses retry logic for SQLite concurrency safety.
        """
        return await self.increment_sticker_count_with_retry(pack_id)
