"""Main text to emoji handler.

This module handles converting user text messages into custom emoji stickers
using the configured fonts and caching system.
"""

from aiogram import Bot, F, Router
from aiogram.types import Message
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.font import Font
from db.models.user import User
from db.repositories.font_repo import FontRepository
from services.image_service import FontService
from services.sticker_service import StickerService

router = Router()

# Maximum characters allowed per message
MAX_TEXT_LENGTH = 120


async def get_user_font(
    db_user: User,
    fonts: list[Font],
    font_repo: FontRepository,
) -> tuple[Font, bool]:
    """Get the font to use for user.

    Priority:
    1. User's preferred font if set and available
    2. First available font (alphabetical default)

    Args:
        db_user: User model.
        fonts: List of available fonts.
        font_repo: Font repository for lookup.

    Returns:
        Tuple of (font_to_use, is_preferred) where is_preferred indicates
        if using user's preferred font.
    """
    # Check if user has preferred font
    if db_user.preferred_font_id:
        # Try to find preferred font in available fonts
        for font in fonts:
            if font.id == db_user.preferred_font_id:
                return font, True

        # Preferred font not in active list, try to get it from DB
        preferred_font = await font_repo.get_by_id(db_user.preferred_font_id)
        if preferred_font and preferred_font.is_active:
            return preferred_font, True

    # Fall back to first font (alphabetical default)
    return fonts[0], False


@router.message(F.text)
async def handle_text_to_emoji(
    message: Message,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    """Convert user text to custom emoji stickers.

    Main workflow:
        1. Check text length limit
        2. Get text and user's preferred font (or default)
        3. Check cache for existing character glyphs
        4. Render and upload new characters as needed
        5. Return formatted message with custom emojis

    Args:
        message: Incoming Telegram message.
        session: Database session for repository operations.
        db_user: User model from middleware context.
        bot: Aiogram Bot instance.
    """
    text = message.text or ""
    if not text:
        return

    # Check text length limit
    if len(text) > MAX_TEXT_LENGTH:
        await message.reply(
            f"<b>文字过长</b>\n\n最多支持 <code>{MAX_TEXT_LENGTH}</code> 个字符\n当前: <code>{len(text)}</code> 个字符",
            parse_mode="HTML",
        )
        return

    # Get bot username for sticker pack naming
    bot_info = await bot.get_me()
    bot_username = bot_info.username or "bot"

    # Get available fonts
    font_service = FontService(session)
    fonts = await font_service.get_available_fonts()

    if not fonts:
        await message.answer("<b>暂无可用字体</b>\n\n请联系管理员添加字体文件", parse_mode="HTML")
        return

    # Get user's preferred font or default
    font_repo = FontRepository(session)
    font, is_preferred = await get_user_font(db_user, fonts, font_repo)
    font_path = font.get_absolute_path()

    if not font_path.exists():
        await message.answer("<b>字体文件不存在</b>\n\n请联系管理员修复", parse_mode="HTML")
        return

    # Show processing hint
    status_msg = await message.reply("<i>⏳ 生成中...</i>", parse_mode="HTML")

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

        # Delete status message and send result
        await status_msg.delete()
        await message.reply(
            text=result_text,
            entities=result_entities if result_entities else None,
            parse_mode=None,  # Must be None when using entities
        )

    except Exception:
        logger.exception("Error processing text to emoji")
        await status_msg.edit_text("<b>生成失败</b>\n\n请稍后重试", parse_mode="HTML")
