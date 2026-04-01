"""Font management commands.

This module provides the /fonts command for listing available fonts.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from services.font_sync_service import FontSyncService
from services.image_service import FontService

router = Router()


@router.message(Command("fonts"))
async def cmd_list_fonts(message: Message, session: AsyncSession, db_user: User) -> None:
    """List available fonts.

    Displays all active fonts with the default font marked.

    Args:
        message: Incoming Telegram message.
        session: Database session for repository operations.
        db_user: User model from middleware context.
    """
    font_service = FontService(session)
    fonts = await font_service.get_available_fonts()

    if not fonts:
        await message.answer("<b>No fonts available</b>", parse_mode="HTML")
        return

    # Get default font (first alphabetically)
    sync_service = FontSyncService(session)
    default_font = await sync_service.get_default_font()
    default_font_id = default_font.id if default_font else None

    font_list = []
    for i, font in enumerate(fonts, 1):
        if font.id == default_font_id:
            font_label = "<i>(default)</i>"
        else:
            font_label = ""
        font_list.append(f"{i}. <b>{font.name}</b> {font_label}")

    text = "<b>Available Fonts</b>\n\n" + "\n".join(font_list)
    text += "\n\n<i>Send text to generate emojis with default font</i>"

    await message.answer(text, parse_mode="HTML")
