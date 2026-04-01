"""Start command handler."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession, db_user: User):
    """Handle /start command."""
    welcome_text = (
        f"你好，{db_user.full_name}！\n\n"
        "欢迎使用文字转表情 Bot！\n\n"
        "发送任意文字，我会将其转换为自定义表情。\n"
        "使用 /fonts 查看可用字体\n"
        "使用 /lang 设置语言"
    )
    await message.answer(welcome_text)


@router.message(Command("lang"))
async def cmd_set_language(message: Message, session: AsyncSession):
    """Handle /lang command for language settings."""
    # TODO: Implement language selection keyboard
    await message.answer("语言设置功能即将上线\n当前仅支持中文(zh)")
