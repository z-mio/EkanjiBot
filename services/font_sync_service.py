"""Font synchronization service for managing fonts."""

import os
from pathlib import Path
from typing import NamedTuple

from loguru import logger
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import bs
from core.constants import FONT_EXTENSIONS
from db.models.font import Font
from db.repositories.font_repo import FontRepository


class SyncResult(NamedTuple):
    """Result of font synchronization operation."""

    added: int
    updated: int
    deactivated: int
    reactivated: int
    total_active: int


class FontSyncService:
    """Service for synchronizing fonts with database.

    This service handles automatic discovery and registration of fonts
    from the assets/fonts/ directory. It implements an incremental merge
    strategy to keep the database in sync with the filesystem.
    """

    def __init__(self, session: AsyncSession, fonts_dir: Path | None = None):
        """Initialize sync service.

        Args:
            session: Database session
            fonts_dir: Directory to scan (defaults to assets/fonts/)
        """
        self.session = session
        self.repo = FontRepository(session)
        self.fonts_dir = fonts_dir or bs.fonts_dir
        self.fonts_dir.mkdir(parents=True, exist_ok=True)

    def _get_font_display_name(self, file_path: Path) -> str:
        """Extract display name from font file.

        Uses filename without extension.
        """
        return file_path.stem

    def _scan_font_files(self) -> set[str]:
        """Scan fonts directory for font files.

        Returns:
            Set of filenames (e.g., {"font.ttf", "font.otf"})
        """
        fonts = set()

        try:
            with os.scandir(self.fonts_dir) as entries:
                for entry in entries:
                    if entry.is_file():
                        ext = Path(entry.name).suffix.lower()
                        if ext in FONT_EXTENSIONS:
                            fonts.add(entry.name)
        except OSError as e:
            logger.error(f"Error scanning fonts directory: {e}")
            raise

        logger.debug(f"Scanned {len(fonts)} font files in {self.fonts_dir}")
        return fonts

    async def sync_fonts(self) -> SyncResult:
        """Synchronize fonts with database.

        Implements incremental merge strategy:
        - Add new fonts (on disk, not in DB)
        - Reactivate fonts (on disk and in DB but inactive)
        - Deactivate missing fonts (in DB but not on disk)

        Returns:
            SyncResult with counts of operations performed
        """
        logger.info("Starting font synchronization...")

        # 1. Scan filesystem
        disk_fonts = self._scan_font_files()

        if not disk_fonts:
            logger.warning(f"No fonts found in {self.fonts_dir}")
            return SyncResult(added=0, updated=0, deactivated=0, reactivated=0, total_active=0)

        # 2. Get current DB state
        db_fonts = await self.repo.get_all_fonts()
        db_fonts_by_path = {f.file_path: f for f in db_fonts}

        # 3. Classify fonts
        disk_paths = disk_fonts
        db_paths = set(db_fonts_by_path.keys())

        # New fonts: on disk but not in DB
        new_paths = disk_paths - db_paths

        # Existing fonts: on disk and in DB
        existing_paths = disk_paths & db_paths

        # Missing fonts: in DB but not on disk
        missing_paths = db_paths - disk_paths

        logger.info(
            f"Font sync classification: "
            f"new={len(new_paths)}, existing={len(existing_paths)}, missing={len(missing_paths)}"
        )

        # 4. Add new fonts (bulk insert)
        added_count = 0
        if new_paths:
            new_fonts_data = [
                {
                    "name": self._get_font_display_name(Path(p)),
                    "file_path": p,
                    "is_active": True,
                }
                for p in new_paths
            ]

            await self.session.execute(insert(Font), new_fonts_data)
            added_count = len(new_paths)
            logger.info(f"Added {added_count} new fonts: {sorted(new_paths)}")

        # 5. Update names for existing fonts if they don't match filename
        updated_count = 0
        for path in existing_paths:
            font = db_fonts_by_path[path]
            expected_name = self._get_font_display_name(Path(path))
            if font.name != expected_name:
                await self.repo.update_font_name(font.id, expected_name)
                updated_count += 1
                logger.info(f"Updated font name: '{font.name}' -> '{expected_name}' ({path})")

        # 6. Reactivate fonts that are inactive but now exist
        # Find fonts in existing_paths that are currently inactive
        inactive_existing = {p for p in existing_paths if not db_fonts_by_path[p].is_active}

        reactivated_count = 0
        if inactive_existing:
            reactivated_count = await self.repo.activate_fonts_in(inactive_existing)
            logger.info(f"Reactivated {reactivated_count} fonts: {sorted(inactive_existing)}")

        # 7. Deactivate fonts no longer on disk
        deactivated_count = await self.repo.deactivate_fonts_not_in(disk_paths)
        if deactivated_count:
            logger.info(f"Deactivated {deactivated_count} missing fonts")

        # 8. Get total active count
        active_fonts = await self.repo.get_active_fonts()
        total_active = len(active_fonts)

        logger.info(
            f"Font sync complete: added={added_count}, updated={updated_count}, "
            f"deactivated={deactivated_count}, reactivated={reactivated_count}, "
            f"total_active={total_active}"
        )

        return SyncResult(
            added=added_count,
            updated=updated_count,
            deactivated=deactivated_count,
            reactivated=reactivated_count,
            total_active=total_active,
        )

    async def get_default_font(self) -> Font | None:
        """Get default font.

        Returns first active font alphabetically by name.

        Returns:
            Font instance or None if no fonts available
        """
        active_fonts = await self.repo.get_active_fonts()

        if not active_fonts:
            return None

        # List is already sorted by name, return first
        return active_fonts[0]
