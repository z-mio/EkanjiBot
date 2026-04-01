"""Main text to emoji handler.

This module handles converting user text messages into custom emoji stickers
using the configured fonts and caching system.
"""

from aiogram import Bot, F, Router
from aiogram.types import Message
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from services.image_service import FontService
from services.sticker_service import StickerService

router = Router()


@router.message(F.text)
async def handle_text_to_emoji(
    message: Message,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    """Convert user text to custom emoji stickers.

    Main workflow:
        1. Get text and available font
        2. Check cache for existing character glyphs
        3. Render and upload new characters as needed
        4. Return formatted message with custom emojis

    Args:
        message: Incoming Telegram message.
        session: Database session for repository operations.
        db_user: User model from middleware context.
        bot: Aiogram Bot instance.
    """
    text = message.text or ""
    if not text:
        return

    # Get bot username for sticker pack naming
    bot_info = await bot.get_me()
    bot_username = bot_info.username or "bot"

    # Get default font
    font_service = FontService(session)
    fonts = await font_service.get_available_fonts()

    if not fonts:
        await message.answer("<b>No fonts available</b>", parse_mode="HTML")
        return

    # Use first available font as default
    font = fonts[0]
    font_path = font.get_absolute_path()

    if not font_path.exists():
        await message.answer("<b>Font file not found</b>", parse_mode="HTML")
        return

    # Process text to emojis
    try:
        sticker_service = StickerService(session, bot)

        result_text, result_entities = await sticker_service.process_text_with_layout(
            user_id=message.from_user.id if message.from_user else 0,
            text=text,
            font_id=font.id,
            font_path=font_path,
            bot_username=bot_username,
            entities=message.entities,
        )

        logger.debug(f"Sending text: {result_text}")
        logger.debug(f"Sending entities: {result_entities}")
        await message.reply(
            text=result_text,
            entities=result_entities if result_entities else None,
            parse_mode=None,  # Must be None when using entities
        )

    except Exception:
        logger.exception("Error processing text to emoji")
        await message.reply("<b>Failed to generate emojis</b>", parse_mode="HTML")
