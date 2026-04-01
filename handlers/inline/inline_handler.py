"""Inline query handler for text to emoji conversion with auto-edit mode."""

from aiogram import Bot, Router
from aiogram.enums import ButtonStyle
from aiogram.types import (
    ChosenInlineResult,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from services.image_service import FontService
from services.sticker_service import StickerService

router = Router()

# Temporary cache to store query text by result_id
_query_cache: dict[str, str] = {}


@router.inline_query()
async def handle_inline_query(
    inline_query: InlineQuery,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
):
    """
    Handle inline query - return placeholder message.
    The actual conversion happens automatically via ChosenInlineResult.
    """
    query_text = inline_query.query or ""
    if not query_text.strip():
        await inline_query.answer([], cache_time=1)
        return

    # Create placeholder message with unified style - only show user input
    placeholder_text = query_text[:100] if query_text else "..."
    zwsp_placeholder_text = f"\u200c{placeholder_text}"  # U+200C zero-width non-joiner prefix

    # Store query in cache and create result id (normal version)
    result_id = f"emoji_{inline_query.from_user.id}_{hash(query_text) & 0x7FFFFFFF}"
    _query_cache[result_id] = query_text

    # Store zero-width non-joiner prefix version in cache
    zwsp_result_id = f"emoji_zwsp_{inline_query.from_user.id}_{hash(query_text) & 0x7FFFFFFF}"
    _query_cache[zwsp_result_id] = f"\u200c{query_text}"

    # Create inline keyboard (required to get inline_message_id in ChosenInlineResult)
    # This button will be removed when we edit the message
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="生 成 中...", callback_data="processing", style=ButtonStyle.PRIMARY)]
        ]
    )

    # Create inline query results
    # 1. Normal version
    result_normal = InlineQueryResultArticle(
        id=result_id,
        title="普通发送",
        description=query_text[:100] if len(query_text) > 100 else query_text,
        input_message_content=InputTextMessageContent(
            message_text=placeholder_text,
            parse_mode="HTML",
        ),
        reply_markup=keyboard,
    )

    # 2. Zero-width non-joiner prefix version (invisible prefix)
    result_zwsp = InlineQueryResultArticle(
        id=zwsp_result_id,
        title="带隐形前缀发送",
        description=query_text[:100] if len(query_text) > 100 else query_text,
        input_message_content=InputTextMessageContent(
            message_text=zwsp_placeholder_text,
            parse_mode="HTML",
        ),
        reply_markup=keyboard,
    )

    # Answer inline query
    await inline_query.answer(
        results=[result_zwsp, result_normal],
        cache_time=0,
        is_personal=True,
    )


@router.chosen_inline_result()
async def handle_chosen_inline_result(
    chosen_result: ChosenInlineResult,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
):
    """
    Handle when user selects inline result.
    Automatically edit the message to show custom emojis.
    """
    result_id = chosen_result.result_id
    inline_message_id = chosen_result.inline_message_id

    if not inline_message_id:
        return

    # Get query text from cache
    query_text = _query_cache.pop(result_id, None)
    if not query_text:
        await bot.edit_message_text(
            inline_message_id=inline_message_id,
            text="<b>▎缓存已过期</b>",
            parse_mode="HTML",
        )
        return

    # Check if this is zero-width non-joiner prefix version
    is_zwsp_prefix = result_id.startswith("emoji_zwsp_")
    # Remove the zero-width non-joiner for processing (it will be added back after)
    text_to_process = query_text[1:] if is_zwsp_prefix and query_text.startswith("\u200c") else query_text

    try:
        # Get bot username
        bot_info = await bot.get_me()
        bot_username = bot_info.username or "bot"

        # Get font
        font_service = FontService(session)
        fonts = await font_service.get_available_fonts()

        if not fonts:
            await bot.edit_message_text(
                inline_message_id=inline_message_id,
                text="<b>▎暂无可用字体</b>",
                parse_mode="HTML",
            )
            return

        font = fonts[0]
        font_path = font.get_absolute_path()

        if not font_path.exists():
            await bot.edit_message_text(
                inline_message_id=inline_message_id,
                text="<b>▎字体文件不存在</b>",
                parse_mode="HTML",
            )
            return

        # Generate emoji text
        sticker_service = StickerService(session, bot)
        result_text, result_entities = await sticker_service.process_text_with_layout(
            user_id=chosen_result.from_user.id,
            text=text_to_process,
            font_id=font.id,
            font_path=font_path,
            bot_username=bot_username,
        )

        # Add zero-width non-joiner prefix back if needed (invisible, not an emoji)
        if is_zwsp_prefix:
            result_text = "\u200c" + result_text
            # Adjust entity offsets by 1 UTF-16 code unit (the ZWNJ takes 1)
            if result_entities:
                for entity in result_entities:
                    entity.offset += 1

        # Edit the message to show final result with entities
        await bot.edit_message_text(
            inline_message_id=inline_message_id,
            text=result_text,
            entities=result_entities if result_entities else None,
            parse_mode=None,  # Must be None when using entities
        )

    except Exception:
        # On error, edit to error message
        await bot.edit_message_text(
            inline_message_id=inline_message_id,
            text="<b>▎生成失败</b>",
            parse_mode="HTML",
        )
