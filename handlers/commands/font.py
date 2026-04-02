"""Font management commands.

This module provides the /fonts and /sf commands for font management.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from db.repositories.font_repo import FontRepository
from db.repositories.user_repo import UserRepository
from services.font_sync_service import FontSyncService
from services.image_service import FontService

router = Router()


@router.message(Command("fonts"))
async def cmd_list_fonts(message: Message, session: AsyncSession, db_user: User) -> None:
    """List available fonts.

    Displays all active fonts with the default font and user's preferred font marked.

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

    # Get user's preferred font
    user_preferred_id = db_user.preferred_font_id

    font_list = []
    for i, font in enumerate(fonts, 1):
        labels = []
        if font.id == default_font_id:
            labels.append("<i>(default)</i>")
        if font.id == user_preferred_id:
            labels.append("<i>(your choice)</i>")

        font_label = " ".join(labels)
        font_list.append(f"{i}. <b>{font.name}</b> {font_label}")

    text = "<b>Available Fonts</b>\n\n" + "\n".join(font_list)
    text += "\n\n<i>Use /sf &lt;font_id&gt; to set your preferred font</i>"
    text += "\n<i>Send text to generate emojis</i>"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("sf"))
async def cmd_set_font(message: Message, session: AsyncSession, db_user: User) -> None:
    """Set user's preferred font.

    Usage: /sf <font_id>
    Use /fonts to see available fonts and their IDs.

    Args:
        message: Incoming Telegram message.
        session: Database session for repository operations.
        db_user: User model from middleware context.
    """
    # Parse font_id from command arguments
    command_parts = message.text.split() if message.text else []

    if len(command_parts) < 2:
        await message.answer(
            "<b>Set your preferred font</b>\n\n"
            "Usage: <code>/sf &lt;font_id&gt;</code>\n\n"
            "Example: <code>/sf 1</code>\n\n"
            "Use /fonts to see available fonts and their IDs.",
            parse_mode="HTML",
        )
        return

    try:
        font_id = int(command_parts[1])
    except ValueError:
        await message.answer(
            "<b>Error:</b> Font ID must be a number.\n\nExample: <code>/sf 1</code>",
            parse_mode="HTML",
        )
        return

    # Verify font exists and is active
    font_repo = FontRepository(session)
    font = await font_repo.get_by_id(font_id)

    if not font:
        await message.answer(
            f"<b>Error:</b> Font with ID {font_id} not found.\n\nUse /fonts to see available fonts.",
            parse_mode="HTML",
        )
        return

    if not font.is_active:
        await message.answer(
            f"<b>Error:</b> Font <code>{font.name}</code> is currently unavailable.\n\n"
            "Use /fonts to see available fonts.",
            parse_mode="HTML",
        )
        return

    # Update user's preferred font
    user_repo = UserRepository(session)
    updated_user = await user_repo.update_preferred_font(db_user.id, font_id)

    if updated_user:
        logger.info(f"User {db_user.telegram_id} set preferred font to {font_id} ({font.name})")
        await message.answer(
            f"<b>Font set successfully!</b>\n\n"
            f"Your preferred font is now: <code>{font.name}</code>\n\n"
            f"Send any text to use this font.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "<b>Error:</b> Failed to update font preference. Please try again.",
            parse_mode="HTML",
        )
