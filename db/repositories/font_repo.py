"""Font repository with font-specific operations."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.font import Font
from db.repositories.base import BaseRepository


class FontRepository(BaseRepository[Font]):
    """Repository for Font model."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Font)

    async def get_active_fonts(self) -> list[Font]:
        """Get all active fonts."""
        result = await self.session.execute(select(Font).where(Font.is_active.is_(True)))
        return list(result.scalars().all())

    async def get_all_fonts(self) -> list[Font]:
        """Get all fonts including inactive ones."""
        result = await self.session.execute(select(Font))
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Font | None:
        """Get font by name."""
        result = await self.session.execute(select(Font).where(Font.name == name, Font.is_active.is_(True)))
        return result.scalar_one_or_none()

    async def get_font_by_path(self, file_path: str) -> Font | None:
        """Get font by file_path (exact match)."""
        result = await self.session.execute(select(Font).where(Font.file_path == file_path))
        return result.scalar_one_or_none()

    async def deactivate_fonts_not_in(self, file_paths: set[str]) -> int:
        """Soft delete fonts not in given file_paths set. Returns count deactivated."""
        result = await self.session.execute(
            update(Font)
            .where(
                Font.is_active.is_(True),
                Font.file_path.notin_(file_paths),
            )
            .values(is_active=False)
        )
        return result.rowcount

    async def activate_fonts_in(self, file_paths: set[str]) -> int:
        """Reactivate fonts that are inactive but exist in file_paths. Returns count activated."""
        result = await self.session.execute(
            update(Font)
            .where(
                Font.is_active.is_(False),
                Font.file_path.in_(file_paths),
            )
            .values(is_active=True)
        )
        return result.rowcount

    async def update_font_name(self, font_id: int, new_name: str) -> None:
        """Update font display name."""
        await self.session.execute(update(Font).where(Font.id == font_id).values(name=new_name))
