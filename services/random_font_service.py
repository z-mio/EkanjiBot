"""Random font service for multi-font text conversion.

This module provides functionality for converting text to emojis with
random font assignment per character position. Each character at a
different position can use a different font, creating visual variety.
"""

import random

from aiogram.types import MessageEntity
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import CUSTOM_EMOJI_PLACEHOLDER
from db.models.font import Font
from db.repositories.character_glyph_repo import CharacterGlyphRepository
from services.image_service import ImageRenderer
from services.sticker_service import StickerCreationTask, StickerTaskQueue


async def process_text_with_random_fonts(
    session: AsyncSession,
    user_id: int,
    text: str,
    fonts: list[Font],
    bot_username: str,
) -> tuple[str, list[MessageEntity]]:
    """Process text with random font per character using serial task queue.

    Each character position gets a randomly assigned font from the available
    fonts that support that character. This creates visual variety where the
    same character at different positions can have different fonts.

    Args:
        session: Database session for repository operations.
        user_id: Telegram user ID (for logging purposes).
        text: Input text to convert.
        fonts: List of available fonts to randomize from.
        bot_username: Bot username for sticker pack naming.

    Returns:
        Tuple of (result_text, result_entities) where result_text uses
        placeholder characters and result_entities maps them to custom emojis.

    Note:
        Uses global StickerTaskQueue for serial sticker creation.
        All fonts should be active and have valid paths.
    """
    if not fonts:
        return text, []

    if len(fonts) < 2:
        # Single font - use normal processing
        font = fonts[0]
        font_path = font.get_absolute_path()
        if not font_path.exists():
            return text, []
        # Import here to avoid circular dependency
        from services.sticker_service import StickerService

        sticker_service = StickerService(session, None)  # type: ignore
        return await sticker_service.process_text_with_layout(
            user_id=user_id,
            text=text,
            font_id=font.id,
            font_path=font_path,
            bot_username=bot_username,
        )

    glyph_repo = CharacterGlyphRepository(session)
    renderer = ImageRenderer()
    task_queue = StickerTaskQueue.get_instance()

    # Step 1: Assign random font to each position (not unique character)
    # This ensures same character at different positions can have different fonts
    position_to_font: dict[int, Font] = {}

    for idx, char in enumerate(text):
        # Skip newlines - keep original line break format
        if char == "\n":
            continue
        # Filter fonts that support this character
        supporting_fonts = [f for f in fonts if renderer.supports_character(f.get_absolute_path(), char)]

        if supporting_fonts:
            position_to_font[idx] = random.choice(supporting_fonts)
        else:
            # No font supports this character - will be preserved as-is
            logger.debug(f"No font supports character: {repr(char)} at position {idx}")

    # Step 2: Batch check cache for all character+font combinations
    char_font_pairs = [(text[idx], font.id) for idx, font in position_to_font.items()]
    # Deduplicate pairs for cache query
    unique_pairs = list(set(char_font_pairs))
    cached_results = await glyph_repo.get_by_characters_and_fonts(unique_pairs)

    # Step 3: Group missing characters by font for batch rendering
    chars_by_font: dict[int, set[str]] = {}
    for idx, font in position_to_font.items():
        char = text[idx]
        key = (char, font.id)
        if key not in cached_results:
            if font.id not in chars_by_font:
                chars_by_font[font.id] = set()
            chars_by_font[font.id].add(char)

    # Convert sets to lists for rendering
    chars_by_font_lists: dict[int, list[str]] = {font_id: list(chars) for font_id, chars in chars_by_font.items()}

    # Step 4: Render and create stickers for missing characters (serial via queue)
    new_emoji_ids: dict[tuple[str, int], str] = {}

    for font_id, chars in chars_by_font_lists.items():
        font = next(f for f in fonts if f.id == font_id)
        font_path = font.get_absolute_path()

        if not font_path.exists():
            continue

        # Batch render all characters for this font (support already checked above)
        images = await renderer.render_batch(chars, font_path, check_support=False)

        # Submit tasks to queue and wait for results (serial processing)
        for char, image in zip(chars, images, strict=False):
            try:
                task = StickerCreationTask(
                    character=char,
                    font_id=font_id,
                    font_path=font_path,
                    image_bytes=image,
                    bot_username=bot_username,
                )
                emoji_id = await task_queue.submit(task)
                new_emoji_ids[(char, font_id)] = emoji_id
            except Exception:
                logger.exception(f"Failed to create sticker for '{char}'")
                # Continue with other characters

    # Step 5: Merge cached and new results
    all_emoji_ids = {**cached_results, **new_emoji_ids}

    # Step 6: Build final text with entity mapping (each position gets its own font)
    final_text = ""
    final_entities: list[MessageEntity] = []
    current_offset = 0

    for idx, char in enumerate(text):
        font = position_to_font.get(idx)
        if not font:
            final_text += char
            current_offset += _get_utf16_length(char)
            continue

        emoji_id = all_emoji_ids.get((char, font.id))
        if not emoji_id:
            final_text += char
            current_offset += _get_utf16_length(char)
            continue

        # Use placeholder emoji
        final_text += CUSTOM_EMOJI_PLACEHOLDER
        placeholder_len = _get_utf16_length(CUSTOM_EMOJI_PLACEHOLDER)

        final_entities.append(
            MessageEntity(
                type="custom_emoji",
                offset=current_offset,
                length=placeholder_len,
                custom_emoji_id=emoji_id,
            )
        )
        current_offset += placeholder_len

    return final_text, final_entities


def _get_utf16_length(s: str) -> int:
    """Calculate UTF-16 code unit length as Telegram API uses.

    Args:
        s: String to measure.

    Returns:
        Number of UTF-16 code units.
    """
    return len(s.encode("utf-16-le")) // 2
