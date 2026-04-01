"""Font management commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from services.image_service import FontService

router = Router()


@router.message(Command("fonts"))
async def cmd_list_fonts(message: Message, session: AsyncSession, db_user: User):
    """List available fonts."""
    font_service = FontService(session)
    fonts = await font_service.get_available_fonts()

    if not fonts:
        await message.answer("<b>▎暂无可用字体</b>", parse_mode="HTML")
        return

    # Get the default font (first font alphabetically)
    from services.font_sync_service import FontSyncService

    sync_service = FontSyncService(session)
    default_font = await sync_service.get_default_font()
    default_font_id = default_font.id if default_font else None

    font_list = []
    for i, font in enumerate(fonts, 1):
        # Mark default font specially
        if font.id == default_font_id:
            font_label = "<i>(默认)</i>"
        else:
            font_label = ""
        font_list.append(f"{i}. <b>{font.name}</b> {font_label}")

    text = "<b>▎可用字体</b>\n\n" + "\n".join(font_list)
    text += "\n\n<i>发送文字即可使用默认字体生成表情</i>"

    await message.answer(text, parse_mode="HTML")
