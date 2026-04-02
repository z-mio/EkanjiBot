"""Image rendering service using Pillow.

This module provides asynchronous image rendering capabilities for converting
text characters into WebP format sticker images suitable for Telegram
Custom Emoji stickers.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.font import Font
from db.repositories.font_repo import FontRepository
from utils.font_support import supports_character


class FontNotSupportedError(Exception):
    """Raised when a font cannot render a character."""

    def __init__(self, font_path: Path, character: str):
        self.font_path = font_path
        self.character = character
        super().__init__(f"Font {font_path.name} does not support character '{character}'")


class ImageRenderer:
    """Optimized image renderer for text to sticker conversion.

    Renders individual characters as 100x100 WebP images suitable for
    Telegram Custom Emoji stickers. Uses ThreadPoolExecutor for
    non-blocking CPU-intensive rendering operations.

    Attributes:
        STICKER_SIZE: Target sticker dimensions (100x100 pixels).
        FONT_SIZE: Font size in points for rendering.
        MAX_WORKERS: Maximum threads in rendering pool.
    """

    STICKER_SIZE = (100, 100)
    FONT_SIZE = 100
    MAX_WORKERS = 4

    def __init__(self):
        """Initialize renderer with thread pool and font cache."""
        self._executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS)
        self._font_cache: dict[int, ImageFont.FreeTypeFont] = {}

    def _get_font(self, font_path: Path) -> ImageFont.FreeTypeFont:
        """Load and cache font from path.

        Args:
            font_path: Absolute path to TrueType font file.

        Returns:
            Loaded Pillow font object.
        """
        cache_key = hash(str(font_path))
        if cache_key not in self._font_cache:
            self._font_cache[cache_key] = ImageFont.truetype(str(font_path), self.FONT_SIZE)
        return self._font_cache[cache_key]

    def supports_character(self, font_path: Path, character: str) -> bool:
        """Check if font supports a character.

        Args:
            font_path: Path to font file.
            character: Character to check.

        Returns:
            True if font supports the character.
        """
        return supports_character(font_path, character, verify_render=False)

    def _render_sync(self, character: str, font: ImageFont.FreeTypeFont) -> bytes:
        """Synchronous character rendering executed in thread pool.

        Args:
            character: Single character to render.
            font: Loaded Pillow font object.

        Returns:
            WebP image data as bytes.
        """
        # Create transparent image
        img = Image.new("RGBA", self.STICKER_SIZE, (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)

        # Draw centered text with middle-middle alignment
        draw.text(
            (self.STICKER_SIZE[0] // 2, self.STICKER_SIZE[1] // 2),
            character,
            font=font,
            fill=(255, 255, 255, 255),  # White for repainting support
            anchor="mm",
        )

        # Save to WebP with optimized settings
        buffer = BytesIO()
        img.save(buffer, format="WEBP", quality=85, method=4)
        return buffer.getvalue()

    async def render_character(self, character: str, font_path: Path, check_support: bool = True) -> bytes:
        """Render single character to WebP image asynchronously.

        Args:
            character: Single character to render.
            font_path: Path to TrueType font file.
            check_support: If True, verify font supports the character first.

        Returns:
            WebP image data as bytes.

        Raises:
            FontNotSupportedError: If font doesn't support the character.
        """
        # Check character support before rendering
        if check_support and not self.supports_character(font_path, character):
            raise FontNotSupportedError(font_path, character)

        font = self._get_font(font_path)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._render_sync, character, font)

    async def render_batch(self, characters: list[str], font_path: Path, check_support: bool = True) -> list[bytes]:
        """Render multiple characters concurrently.

        Args:
            characters: List of characters to render.
            font_path: Path to TrueType font file.
            check_support: If True, verify font supports each character first.

        Returns:
            List of WebP image data in same order as input characters.

        Raises:
            FontNotSupportedError: If check_support=True and font doesn't support a character.
        """
        tasks = [self.render_character(char, font_path, check_support=check_support) for char in characters]
        return await asyncio.gather(*tasks)


class FontService:
    """Font management service.

    Provides high-level operations for font discovery and retrieval
    from the database.
    """

    def __init__(self, session: AsyncSession):
        """Initialize font service.

        Args:
            session: Database session for repository operations.
        """
        self.session = session
        self.repo = FontRepository(session)
        self.renderer = ImageRenderer()

    async def get_available_fonts(self) -> list[Font]:
        """Get all active fonts available for use.

        Returns:
            List of active Font model instances.
        """
        return await self.repo.get_active_fonts()

    async def get_font_path(self, font_id: int) -> Path | None:
        """Get absolute file path for a font by ID.

        Args:
            font_id: Database ID of the font.

        Returns:
            Absolute path to font file, or None if not found.
        """
        fonts = await self.repo.get_active_fonts()
        for font in fonts:
            if font.id == font_id:
                return font.get_absolute_path()
        return None

    async def find_fonts_for_character(self, character: str) -> list[Font]:
        """Find fonts that support a specific character.

        Args:
            character: Character to check support for.

        Returns:
            List of fonts that can render the character.
        """
        fonts = await self.repo.get_active_fonts()
        supported = []

        for font in fonts:
            font_path = font.get_absolute_path()
            if self.renderer.supports_character(font_path, character):
                supported.append(font)

        return supported

    async def get_best_font_for_character(self, character: str, preferred_font_id: int | None = None) -> Font | None:
        """Get the best font for rendering a character.

        Priority:
        1. Preferred font if it supports the character
        2. First available font that supports the character

        Args:
            character: Character to render.
            preferred_font_id: User's preferred font ID.

        Returns:
            Font that supports the character, or None if no font supports it.
        """
        # Try preferred font first
        if preferred_font_id:
            preferred_font = await self.repo.get_by_id(preferred_font_id)
            if preferred_font and preferred_font.is_active:
                font_path = preferred_font.get_absolute_path()
                if self.renderer.supports_character(font_path, character):
                    return preferred_font

        # Fall back to any supporting font
        supported_fonts = await self.find_fonts_for_character(character)
        return supported_fonts[0] if supported_fonts else None
