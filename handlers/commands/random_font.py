"""Random font command handler.

This module provides the /rf command for converting text with random fonts
per character using the serial task queue for sticker creation.
"""

import random

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message, MessageEntity
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.font import Font
from db.models.user import User
from services.image_service import FontService
from services.sticker_service import StickerCreationTask, StickerService

router = Router()

# Maximum characters allowed per request
MAX_TEXT_LENGTH = 120


async def process_text_with_random_fonts(
    sticker_service: StickerService,
    user_id: int,
    text: str,
    fonts: list[Font],
    bot_username: str,
) -> tuple[str, list[MessageEntity]]:
    """Process text with random font per character using serial task queue.

    Args:
        sticker_service: StickerService instance.
        user_id: Telegram user ID.
        text: Input text to convert.
        fonts: List of available fonts to randomize from.
        bot_username: Bot username for sticker pack naming.

    Returns:
        Tuple of (result_text, result_entities).
    """
    if not fonts:
        return text, []

    if len(fonts) < 2:
        # Single font - use normal processing
        font = fonts[0]
        font_path = font.get_absolute_path()
        if not font_path.exists():
            return text, []
        return await sticker_service.process_text_with_layout(
            user_id=user_id,
            text=text,
            font_id=font.id,
            font_path=font_path,
            bot_username=bot_username,
        )

    # Step 1: Assign random font to each unique character (including whitespace)
    char_to_font: dict[str, Font] = {}
    unique_chars = set(text)
    for char in unique_chars:
        char_to_font[char] = random.choice(fonts)

    # Step 2: Batch check cache for all character+font combinations (1 query)
    char_font_pairs = [(char, font.id) for char, font in char_to_font.items()]
    cached_results = await sticker_service.glyph_repo.get_by_characters_and_fonts(char_font_pairs)

    # Step 3: Group missing characters by font for batch rendering
    chars_by_font: dict[int, list[str]] = {}
    for char, font in char_to_font.items():
        key = (char, font.id)
        if key not in cached_results:
            if font.id not in chars_by_font:
                chars_by_font[font.id] = []
            chars_by_font[font.id].append(char)

    # Step 4: Render and create stickers for missing characters (serial via queue)
    new_emoji_ids: dict[tuple[str, int], str] = {}

    for font_id, chars in chars_by_font.items():
        font = next(f for f in fonts if f.id == font_id)
        font_path = font.get_absolute_path()

        if not font_path.exists():
            continue

        # Batch render all characters for this font
        images = await sticker_service.renderer.render_batch(chars, font_path)

        # Submit tasks to queue and wait for results (serial processing)
        for char, image in zip(chars, images, strict=False):
            try:
                task = StickerCreationTask(
                    user_id=user_id,
                    character=char,
                    font_id=font_id,
                    font_path=font_path,
                    image_bytes=image,
                    bot_username=bot_username,
                )
                emoji_id = await sticker_service._task_queue.submit(task)
                new_emoji_ids[(char, font_id)] = emoji_id
            except Exception:
                logger.exception(f"Failed to create sticker for '{char}'")
                # Continue with other characters

    # Step 5: Merge cached and new results
    all_emoji_ids: dict[tuple[str, int], str] = {**cached_results, **new_emoji_ids}

    # Step 6: Build final text with entity mapping (including whitespace as emoji)
    final_text = ""
    final_entities: list[MessageEntity] = []
    current_offset = 0

    for char in text:
        font = char_to_font.get(char)
        if not font:
            final_text += char
            current_offset += len(char.encode("utf-16-le")) // 2
            continue

        emoji_id = all_emoji_ids.get((char, font.id))
        if not emoji_id:
            final_text += char
            current_offset += len(char.encode("utf-16-le")) // 2
            continue

        # Use placeholder emoji
        placeholder = "🎨"
        final_text += placeholder
        placeholder_len = len(placeholder.encode("utf-16-le")) // 2

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


@router.message(Command("rf"))
async def cmd_random_font(
    message: Message,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    """Convert text to emojis with random font per character.

    Usage: /rf <text>
    Each character will use a randomly selected font from available fonts.

    Args:
        message: Incoming Telegram message.
        session: Database session for repository operations.
        db_user: User model from middleware context.
        bot: Aiogram Bot instance.
    """
    # Parse text from command
    command_text = message.text or ""
    parts = command_text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "<b>🎲 随机字体模式</b>\n\n"
            "用法: <code>/rf &lt;文字&gt;</code>\n\n"
            "示例: <code>/rf 你好世界</code>\n\n"
            "每个字符将随机使用一种字体",
            parse_mode="HTML",
        )
        return

    text = parts[1]

    # Check text length limit
    if len(text) > MAX_TEXT_LENGTH:
        await message.answer(
            f"<b>文字过长</b>\n\n最多支持 <code>{MAX_TEXT_LENGTH}</code> 个字符\n当前: <code>{len(text)}</code> 个字符",
            parse_mode="HTML",
        )
        return

    # Get bot username
    bot_info = await bot.get_me()
    bot_username = bot_info.username or "bot"

    # Get available fonts
    font_service = FontService(session)
    fonts = await font_service.get_available_fonts()

    if not fonts:
        await message.answer("<b>暂无可用字体</b>\n\n请联系管理员添加字体文件", parse_mode="HTML")
        return

    if len(fonts) < 2:
        await message.answer(
            "<b>随机字体模式需要至少2种字体</b>\n\n请添加更多字体到 assets/fonts/ 目录",
            parse_mode="HTML",
        )
        return

    # Process text with random fonts
    try:
        sticker_service = StickerService(session, bot)

        await message.answer("<i>⏳ 生成随机字体表情中...</i>", parse_mode="HTML")

        result_text, result_entities = await process_text_with_random_fonts(
            sticker_service=sticker_service,
            user_id=message.from_user.id if message.from_user else 0,
            text=text,
            fonts=fonts,
            bot_username=bot_username,
        )

        logger.debug(f"Random font result: {result_text}")
        await message.reply(
            text=result_text,
            entities=result_entities if result_entities else None,
            parse_mode=None,
        )

    except Exception:
        logger.exception("Error in random font mode")
        await message.reply("<b>生成失败</b>\n\n请稍后重试", parse_mode="HTML")
