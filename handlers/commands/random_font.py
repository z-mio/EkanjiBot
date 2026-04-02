"""Random font command handler.

This module provides the /rf command for converting text with random fonts
per character using the serial task queue for sticker creation.
"""

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import MAX_TEXT_LENGTH
from core.messages import ErrorMessages, HelpMessages, InfoMessages
from db.models.user import User
from services.image_service import FontService
from services.random_font_service import process_text_with_random_fonts

router = Router()


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
            HelpMessages.RANDOM_FONT,
            parse_mode="HTML",
        )
        return

    text = parts[1]

    # Check text length limit
    if len(text) > MAX_TEXT_LENGTH:
        await message.answer(
            ErrorMessages.text_too_long(len(text)),
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
        await message.answer(ErrorMessages.NO_FONTS_AVAILABLE, parse_mode="HTML")
        return

    if len(fonts) < 2:
        await message.answer(
            InfoMessages.NEED_MORE_FONTS,
            parse_mode="HTML",
        )
        return

    # Process text with random fonts
    try:
        await message.answer(InfoMessages.PROCESSING_RANDOM, parse_mode="HTML")

        result_text, result_entities = await process_text_with_random_fonts(
            session=session,
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
        await message.reply(ErrorMessages.GENERATION_FAILED, parse_mode="HTML")
