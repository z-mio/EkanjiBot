"""Start command handler.

This module handles the /start and /lang commands for user onboarding
and language preference settings.
"""

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession, db_user: User, bot: Bot) -> None:
    """Handle /start command.

    Sends welcome message with usage instructions.

    Args:
        message: Incoming Telegram message.
        session: Database session (unused, injected by middleware).
        db_user: User model from middleware context.
        bot: Aiogram Bot instance.
    """
    bot_info = await bot.get_me()
    bot_username = bot_info.username or "bot"

    welcome_text = (
        f"👋 你好，<b>{db_user.full_name}</b>！\n\n"
        "欢迎使用 <b>文字转表情 Bot</b>\n\n"
        "✨ <b>功能介绍</b>\n\n"
        "📝 <b>直接发送文字</b>\n"
        "   自动转换为自定义表情\n\n"
        "🎨 <b>字体相关</b>\n"
        "   /fonts — 查看可用字体列表\n"
        "   /sf &lt;ID&gt; — 设置偏好字体\n\n"
        "🎲 <b>随机字体模式</b>\n"
        "   /rf &lt;文字&gt; — 每个字符随机字体\n"
        "   行内模式输入 rf &lt;文字&gt; 同样有效\n\n"
        "💬 <b>行内模式</b>\n"
        f"   在任意聊天输入 @{bot_username} &lt;文字&gt;\n"
        "   即可使用表情，无需添加好友\n\n"
        "💡 <b>提示</b>\n"
        "   每个字符只需生成一次，永久缓存\n"
        "   最多支持 120 个字符"
    )
    await message.answer(welcome_text, parse_mode="HTML")


@router.message(Command("lang"))
async def cmd_set_language(message: Message, session: AsyncSession) -> None:
    """Handle /lang command for language settings.

    Args:
        message: Incoming Telegram message.
        session: Database session (unused, injected by middleware).
    """
    # TODO: Implement language selection keyboard
    await message.answer(
        "🌐 <b>语言设置</b>\n\n该功能开发中...\n\n当前仅支持 <b>中文</b>",
        parse_mode="HTML",
    )
