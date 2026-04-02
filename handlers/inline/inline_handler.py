"""Inline query handler for text to emoji conversion with auto-edit mode."""

import random

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

from db.models.font import Font
from db.models.user import User
from db.repositories.font_repo import FontRepository
from services.image_service import FontService
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
    Supports "rf" prefix for random font mode.
    """
    query_text = inline_query.query or ""
    if not query_text.strip():
        await inline_query.answer([], cache_time=1)
        return

    # Check for random font prefix "rf "
    is_random_font = query_text.startswith("rf ")
    if is_random_font:
        display_text = query_text[3:]  # Strip "rf " prefix for display
    else:
        display_text = query_text

    if not display_text.strip():
        await inline_query.answer([], cache_time=1)
        return

    # Create placeholder message
    placeholder_text = display_text[:100] if display_text else "..."
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
            [InlineKeyboardButton(text="生 成 中...", callback_data="processing", style=ButtonStyle.PRIMARY)]
        ]
    )

    # Set title based on mode
    if is_random_font:
        title_normal = "🎲 随机字体"
        title_zwsp = "🎲 随机字体(带前缀)"
    else:
        title_normal = "普通发送"
        title_zwsp = "带隐形前缀发送"

    # Create inline query results
    result_normal = InlineQueryResultArticle(
        id=result_id,
        title=title_normal,
        description=display_text[:100] if len(display_text) > 100 else display_text,
        input_message_content=InputTextMessageContent(
            message_text=placeholder_text,
            parse_mode="HTML",
        ),
        reply_markup=keyboard,
    )

    result_zwsp = InlineQueryResultArticle(
        id=zwsp_result_id,
        title=title_zwsp,
        description=display_text[:100] if len(display_text) > 100 else display_text,
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


async def process_with_random_fonts(
    sticker_service: StickerService,
    user_id: int,
    text: str,
    fonts: list[Font],
    bot_username: str,
) -> tuple[str, list]:
    """Process text with random font per character for inline mode."""
    if not fonts or len(fonts) < 2:
        # Fall back to single font if not enough fonts
        font = fonts[0] if fonts else None
        if not font:
            return text, []

        font_path = font.get_absolute_path()
        if not font_path.exists():
            return text, []

        return await sticker_service.process_text_with_layout(
            user_id=user_id,
            text=text,
            font_id=font.id,
            font_path=font_path,
            bot_username=bot_username,
        )

    # Process each character with random font
    results = []

    for char in text:
        if char.isspace():
            results.append((char, None))
            continue

        font = random.choice(fonts)
        font_path = font.get_absolute_path()

        if not font_path.exists():
            results.append((char, None))
            continue

        try:
            result_text, result_entities = await sticker_service.process_text_with_layout(
                user_id=user_id,
                text=char,
                font_id=font.id,
                font_path=font_path,
                bot_username=bot_username,
            )

            if result_entities:
                results.append((result_text, result_entities[0]))
            else:
                results.append((char, None))
        except Exception:
            results.append((char, None))

    # Combine results
    final_text = ""
    final_entities = []
    current_offset = 0

    for text_part, entity in results:
        final_text += text_part

        if entity:
            from aiogram.types import MessageEntity

            adjusted_entity = MessageEntity(
                type=entity.type,
                offset=current_offset,
                length=entity.length,
                custom_emoji_id=entity.custom_emoji_id,
            )
            final_entities.append(adjusted_entity)

        current_offset += len(text_part.encode("utf-16-le")) // 2

    return final_text, final_entities


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
            text="<b>Cache expired</b>",
            parse_mode="HTML",
        )
        return

    query_text, is_random_font = cached_data

    # Check if this is zero-width non-joiner prefix version
    is_zwsp_prefix = "zwsp_" in result_id
    text_to_process = query_text[1:] if is_zwsp_prefix and query_text.startswith("\u200c") else query_text

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
                text="<b>No fonts available</b>",
                parse_mode="HTML",
            )
            return

        sticker_service = StickerService(session, bot)

        if is_random_font:
            # Random font mode
            result_text, result_entities = await process_with_random_fonts(
                sticker_service=sticker_service,
                user_id=chosen_result.from_user.id,
                text=text_to_process,
                fonts=fonts,
                bot_username=bot_username,
            )
        else:
            # Normal mode - use user's preferred font or default
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
                    text="<b>Font file not found</b>",
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
            text="<b>Failed to generate emojis</b>",
            parse_mode="HTML",
        )
