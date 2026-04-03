"""Font management commands.

This module provides the /sf command for font selection.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from db.repositories.user_repo import UserRepository
from services.image_service import FontService

router = Router()


@router.message(Command("sf"))
async def cmd_set_font(message: Message, session: AsyncSession, db_user: User) -> None:
    """Set or list user's preferred font.

    Usage:
    - /sf           - List available fonts
    - /sf <index>   - Set preferred font by display index

    Args:
        message: Incoming Telegram message.
        session: Database session for repository operations.
        db_user: User model from middleware context.
    """
    command_parts = message.text.split() if message.text else []
    font_service = FontService(session)
    fonts = await font_service.get_available_fonts()

    if not fonts:
        await message.answer("<b>暂无可用字体</b>\n\n请联系管理员添加字体文件", parse_mode="HTML")
        return

    # No argument: show font list
    if len(command_parts) < 2:
        user_preferred_id = db_user.preferred_font_id

        font_list = []
        for i, font in enumerate(fonts, 1):
            if font.id == user_preferred_id:
                font_list.append(f"{i}. <b>{font.name}</b> <i>(已选)</i>")
            else:
                font_list.append(f"{i}. <b>{font.name}</b>")

        text = "<b>可用字体列表</b>\n\n" + "\n".join(font_list)
        text += "\n\n<i>使用 /sf &lt;序号&gt; 设置偏好字体</i>"

        await message.answer(text, parse_mode="HTML")
        return

    # Has argument: set font
    try:
        display_index = int(command_parts[1])
    except ValueError:
        await message.answer(
            "<b>错误:</b> 序号必须是数字\n\n示例: <code>/sf 1</code>",
            parse_mode="HTML",
        )
        return

    # Validate index
    if display_index < 1 or display_index > len(fonts):
        await message.answer(
            f"<b>错误:</b> 序号 {display_index} 无效\n\n有效范围: 1-{len(fonts)}",
            parse_mode="HTML",
        )
        return

    # Map display index to font
    font = fonts[display_index - 1]
    font_id = font.id

    # Update user's preferred font
    user_repo = UserRepository(session)
    updated_user = await user_repo.update_preferred_font(db_user.id, font_id)

    if updated_user:
        logger.info(f"User {db_user.telegram_id} set preferred font to {font_id} ({font.name})")
        await message.answer(
            f"<b>设置成功！</b>\n\n偏好字体: <code>{font.name}</code>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "<b>错误:</b> 设置失败，请重试",
            parse_mode="HTML",
        )
