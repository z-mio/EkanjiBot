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
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import MAX_TEXT_LENGTH, PLACEHOLDER_DISPLAY_LIMIT
from core.messages import ErrorMessages, InlineMessages
from db.models.user import User
from db.repositories.font_repo import FontRepository
from services.image_service import FontService
from services.random_font_service import process_text_with_random_fonts
from services.sticker_service import StickerService

router = Router()

# Temporary cache to store query text and flags by result_id
_query_cache: dict[str, tuple[str, bool]] = {}  # (text, is_random_font)


@router.inline_query()
async def handle_inline_query(
    inline_query: InlineQuery,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
):
    """Handle inline query - return placeholder message.

    The actual conversion happens automatically via ChosenInlineResult.
    Supports "rf" prefix for random font mode:
    - @bot rf测试 (no space)
    - @bot rf 测试 (with space)
    """
    query_text = inline_query.query or ""
    if not query_text.strip():
        await inline_query.answer([], cache_time=1)
        return

    # Check for random font prefix "rf" (with or without space)
    is_random_font = query_text.lower().startswith("rf")
    if is_random_font:
        # Strip "rf" prefix, handle both "rf测试" and "rf 测试"
        remaining = query_text[2:]
        if remaining.startswith(" "):
            remaining = remaining[1:]  # Strip space if present
        display_text = remaining
    else:
        display_text = query_text

    if not display_text.strip():
        await inline_query.answer([], cache_time=1)
        return

    # Create placeholder message
    placeholder_text = display_text[:PLACEHOLDER_DISPLAY_LIMIT] if display_text else "..."
    zwsp_placeholder_text = f"\u200c{placeholder_text}"  # U+200C zero-width non-joiner prefix

    # Create result ids
    base_hash = hash(display_text) & 0x7FFFFFFF
    prefix = "rf_" if is_random_font else "emoji_"

    # Normal version
    result_id = f"{prefix}{inline_query.from_user.id}_{base_hash}"
    _query_cache[result_id] = (display_text, is_random_font)

    # Zero-width non-joiner prefix version
    zwsp_result_id = f"{prefix}zwsp_{inline_query.from_user.id}_{base_hash}"
    _query_cache[zwsp_result_id] = (f"\u200c{display_text}", is_random_font)

    # Create inline keyboard
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=InlineMessages.BUTTON_GENERATING, callback_data="processing", style=ButtonStyle.PRIMARY
                )
            ]
        ]
    )

    # Set title based on mode
    if is_random_font:
        title_normal = InlineMessages.TITLE_RANDOM
        title_zwsp = InlineMessages.TITLE_RANDOM_ZWSP
    else:
        title_normal = InlineMessages.TITLE_NORMAL
        title_zwsp = InlineMessages.TITLE_ZWSP

    # Create inline query results
    result_normal = InlineQueryResultArticle(
        id=result_id,
        title=title_normal,
        description=display_text[:PLACEHOLDER_DISPLAY_LIMIT]
        if len(display_text) > PLACEHOLDER_DISPLAY_LIMIT
        else display_text,
        input_message_content=InputTextMessageContent(
            message_text=placeholder_text,
            parse_mode="HTML",
        ),
        reply_markup=keyboard,
    )

    result_zwsp = InlineQueryResultArticle(
        id=zwsp_result_id,
        title=title_zwsp,
        description=display_text[:PLACEHOLDER_DISPLAY_LIMIT]
        if len(display_text) > PLACEHOLDER_DISPLAY_LIMIT
        else display_text,
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
    """Handle when user selects inline result.

    Automatically edit the message to show custom emojis.
    Supports random font mode if "rf" prefix was used.
    """
    result_id = chosen_result.result_id
    inline_message_id = chosen_result.inline_message_id

    if not inline_message_id:
        return

    # Get query data from cache
    cached_data = _query_cache.pop(result_id, None)
    if not cached_data:
        await bot.edit_message_text(
            inline_message_id=inline_message_id,
            text=ErrorMessages.CACHE_EXPIRED,
            parse_mode="HTML",
        )
        return

    query_text, is_random_font = cached_data

    # Check if this is zero-width non-joiner prefix version
    is_zwsp_prefix = "zwsp_" in result_id
    text_to_process = query_text[1:] if is_zwsp_prefix and query_text.startswith("\u200c") else query_text

    # Check text length limit
    if len(text_to_process) > MAX_TEXT_LENGTH:
        await bot.edit_message_text(
            inline_message_id=inline_message_id,
            text=ErrorMessages.text_too_long(len(text_to_process)),
            parse_mode="HTML",
        )
        return

    try:
        # Get bot username
        bot_info = await bot.get_me()
        bot_username = bot_info.username or "bot"

        # Get available fonts
        font_service = FontService(session)
        fonts = await font_service.get_available_fonts()

        if not fonts:
            await bot.edit_message_text(
                inline_message_id=inline_message_id,
                text=ErrorMessages.NO_FONTS_AVAILABLE,
                parse_mode="HTML",
            )
            return

        if is_random_font:
            # Random font mode
            result_text, result_entities = await process_text_with_random_fonts(
                session=session,
                user_id=chosen_result.from_user.id,
                text=text_to_process,
                fonts=fonts,
                bot_username=bot_username,
            )
        else:
            # Normal mode - use user's preferred font or default
            sticker_service = StickerService(session, bot)
            font_repo = FontRepository(session)

            font = None
            if db_user.preferred_font_id:
                # Try to find preferred font
                for f in fonts:
                    if f.id == db_user.preferred_font_id:
                        font = f
                        break

                if not font:
                    # Try to get from DB
                    preferred = await font_repo.get_by_id(db_user.preferred_font_id)
                    if preferred and preferred.is_active:
                        font = preferred

            if not font:
                # Fall back to first font
                font = fonts[0]

            font_path = font.get_absolute_path()

            if not font_path.exists():
                await bot.edit_message_text(
                    inline_message_id=inline_message_id,
                    text=ErrorMessages.FONT_FILE_NOT_FOUND,
                    parse_mode="HTML",
                )
                return

            result_text, result_entities = await sticker_service.process_text_with_layout(
                user_id=chosen_result.from_user.id,
                text=text_to_process,
                font_id=font.id,
                font_path=font_path,
                bot_username=bot_username,
            )

        # Add zero-width non-joiner prefix back if needed
        if is_zwsp_prefix:
            result_text = "\u200c" + result_text
            if result_entities:
                for entity in result_entities:
                    entity.offset += 1

        # Edit the message to show final result
        await bot.edit_message_text(
            inline_message_id=inline_message_id,
            text=result_text,
            entities=result_entities if result_entities else None,
            parse_mode=None,
        )

    except Exception:
        logger.exception("Error processing inline result")
        await bot.edit_message_text(
            inline_message_id=inline_message_id,
            text=ErrorMessages.GENERATION_FAILED,
            parse_mode="HTML",
        )
