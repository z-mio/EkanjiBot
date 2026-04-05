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
    if not fonts:
        return text, []

    if len(fonts) < 2:
        font = fonts[0]
        font_path = font.get_absolute_path()
        if not font_path.exists():
            return text, []
        from services.sticker_service import StickerService

        sticker_service = StickerService(session, None)
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

    chars_to_process = []
    seen = set()

    for char in text:
        if char == "\n":
            continue
        if char not in seen:
            chars_to_process.append(char)
            seen.add(char)

    if not chars_to_process:
        return text, []

    all_char_font_pairs = []
    for char in chars_to_process:
        for font in fonts:
            all_char_font_pairs.append((char, font.id))
    unique_pairs = list(set(all_char_font_pairs))
    cached_results = await glyph_repo.get_by_characters_and_fonts(unique_pairs)

    position_to_font: dict[int, Font] = {}
    position_to_emoji_id: dict[int, str] = {}

    for idx, char in enumerate(text):
        if char == "\n":
            continue

        # Check if any font has this character cached
        cached_fonts = []
        for font in fonts:
            emoji_id = cached_results.get((char, font.id))
            if emoji_id:
                cached_fonts.append((font, emoji_id))

        if cached_fonts:
            # Cache hit - use cached font (random selection among cached fonts)
            font, emoji_id = random.choice(cached_fonts)
            position_to_font[idx] = font
            position_to_emoji_id[idx] = emoji_id
            continue

        # Cache miss - check font support and assign font
        supporting_fonts = [f for f in fonts if renderer.supports_character(f.get_absolute_path(), char)]

        if supporting_fonts:
            position_to_font[idx] = random.choice(supporting_fonts)
        else:
            # No font supports this character - will be preserved as-is
            logger.debug(f"No font supports character: {repr(char)} at position {idx}")

    chars_by_font: dict[int, set[str]] = {}
    for idx, font in position_to_font.items():
        if idx in position_to_emoji_id:
            continue  # Already cached
        char = text[idx]
        if font.id not in chars_by_font:
            chars_by_font[font.id] = set()
        chars_by_font[font.id].add(char)

    chars_by_font_lists: dict[int, list[str]] = {font_id: list(chars) for font_id, chars in chars_by_font.items()}

    new_emoji_ids: dict[tuple[str, int], str] = {}

    for font_id, chars in chars_by_font_lists.items():
        font = next(f for f in fonts if f.id == font_id)
        font_path = font.get_absolute_path()

        if not font_path.exists():
            continue

        images = await renderer.render_batch(chars, font_path, check_support=False)

        tasks = []
        for char, image in zip(chars, images, strict=False):
            task = StickerCreationTask(
                character=char,
                font_id=font_id,
                font_path=font_path,
                image_bytes=image,
                bot_username=bot_username,
            )
            await task_queue.put(task)
            tasks.append(task)

        for task in tasks:
            await task.result_event.wait()
            if task.error:
                logger.exception(f"Failed to create sticker for '{task.character}'")
                continue
            new_emoji_ids[(task.character, font_id)] = task.result

    all_emoji_ids = {**cached_results, **new_emoji_ids}

    final_text = ""
    final_entities: list[MessageEntity] = []
    current_offset = 0

    for idx, char in enumerate(text):
        font = position_to_font.get(idx)
        if not font:
            final_text += char
            current_offset += _get_utf16_length(char)
            continue

        emoji_id = position_to_emoji_id.get(idx) or all_emoji_ids.get((char, font.id))
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
