"""Image rendering service using Pillow."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.font import Font
from db.repositories.font_repo import FontRepository


class ImageRenderer:
    """Optimized image renderer for text to sticker conversion."""

    # Telegram custom emoji requires 100x100 for static stickers
    STICKER_SIZE = (100, 100)
    FONT_SIZE = 100
    MAX_WORKERS = 4

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS)
        self._font_cache: dict[int, ImageFont.FreeTypeFont] = {}

    def _get_font(self, font_path: Path) -> ImageFont.FreeTypeFont:
        """Load and cache font from path."""
        cache_key = hash(str(font_path))
        if cache_key not in self._font_cache:
            self._font_cache[cache_key] = ImageFont.truetype(str(font_path), self.FONT_SIZE)
        return self._font_cache[cache_key]

    def _render_sync(self, character: str, font: ImageFont.FreeTypeFont) -> bytes:
        """Synchronous character rendering (executed in thread pool)."""
        # Create transparent image
        img = Image.new("RGBA", self.STICKER_SIZE, (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)

        # Draw centered text
        draw.text(
            (self.STICKER_SIZE[0] // 2, self.STICKER_SIZE[1] // 2),
            character,
            font=font,
            fill=(255, 255, 255, 255),  # White, supports repainting
            anchor="mm",  # Middle-middle alignment
        )

        # Save to WebP with optimized settings
        buffer = BytesIO()
        img.save(buffer, format="WEBP", quality=85, method=4)
        return buffer.getvalue()

    async def render_character(self, character: str, font_path: Path) -> bytes:
        """Async render single character to WebP image."""
        font = self._get_font(font_path)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._render_sync, character, font)

    async def render_batch(self, characters: list[str], font_path: Path) -> list[bytes]:
        """Batch render multiple characters concurrently."""
        tasks = [self.render_character(char, font_path) for char in characters]
        return await asyncio.gather(*tasks)


class FontService:
    """Font management service."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = FontRepository(session)
        self.renderer = ImageRenderer()

    async def get_available_fonts(self) -> list[Font]:
        """Get all available fonts."""
        return await self.repo.get_active_fonts()

    async def get_font_path(self, font_id: int) -> Path | None:
        """Get font file path if exists."""
        fonts = await self.repo.get_active_fonts()
        for font in fonts:
            if font.id == font_id:
                return font.get_absolute_path()
        return None
