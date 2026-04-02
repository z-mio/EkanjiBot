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
    MessageEntity,
)
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.font import Font
from db.models.user import User
from db.repositories.font_repo import FontRepository
from services.image_service import FontService
from services.sticker_service import StickerCreationTask, StickerService

router = Router()

# Maximum characters allowed per request
MAX_TEXT_LENGTH = 120

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
) -> tuple[str, list[MessageEntity]]:
    """Process text with random font per character using serial task queue.

    Args:
        sticker_service: StickerService instance.
        user_id: Telegram user ID.
        text: Input text to convert.
        fonts: List of available fonts to randomize from.
        bot_username: Bot username for sticker pack naming.

    Returns:
        Tuple of (result_text, result_entities).
    """
    if not fonts:
        return text, []

    if len(fonts) < 2:
        # Single font - use normal processing
        font = fonts[0]
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

    # Step 1: Assign random font to each position (not unique character)
    # This ensures same character at different positions can have different fonts
    position_to_font: dict[int, Font] = {}

    for idx, char in enumerate(text):
        # Filter fonts that support this character
        supporting_fonts = [
            f for f in fonts if sticker_service.renderer.supports_character(f.get_absolute_path(), char)
        ]

        if supporting_fonts:
            position_to_font[idx] = random.choice(supporting_fonts)
        else:
            # No font supports this character - will be preserved as-is
            logger.debug(f"No font supports character: {repr(char)} at position {idx}")

    # Step 2: Batch check cache for all character+font combinations
    char_font_pairs = [(text[idx], font.id) for idx, font in position_to_font.items()]
    # Deduplicate pairs for cache query
    unique_pairs = list(set(char_font_pairs))
    cached_results = await sticker_service.glyph_repo.get_by_characters_and_fonts(unique_pairs)

    # Step 3: Group missing characters by font for batch rendering
    chars_by_font: dict[int, set[str]] = {}
    for idx, font in position_to_font.items():
        char = text[idx]
        key = (char, font.id)
        if key not in cached_results:
            if font.id not in chars_by_font:
                chars_by_font[font.id] = set()
            chars_by_font[font.id].add(char)

    # Convert sets to lists for rendering
    chars_by_font_lists: dict[int, list[str]] = {font_id: list(chars) for font_id, chars in chars_by_font.items()}

    # Step 4: Render and create stickers for missing characters (serial via queue)
    new_emoji_ids: dict[tuple[str, int], str] = {}

    for font_id, chars in chars_by_font_lists.items():
        font = next(f for f in fonts if f.id == font_id)
        font_path = font.get_absolute_path()

        if not font_path.exists():
            continue

        # Batch render all characters for this font (support already checked above)
        images = await sticker_service.renderer.render_batch(chars, font_path, check_support=False)

        # Submit tasks to queue and wait for results (serial processing)
        for char, image in zip(chars, images, strict=False):
            try:
                task = StickerCreationTask(
                    character=char,
                    font_id=font_id,
                    font_path=font_path,
                    image_bytes=image,
                    bot_username=bot_username,
                )
                emoji_id = await sticker_service._task_queue.submit(task)
                new_emoji_ids[(char, font_id)] = emoji_id
            except Exception:
                logger.exception(f"Failed to create sticker for '{char}'")
                # Continue with other characters

    # Step 5: Merge cached and new results
    all_emoji_ids = {**cached_results, **new_emoji_ids}

    # Step 6: Build final text with entity mapping (each position gets its own font)
    final_text = ""
    final_entities: list[MessageEntity] = []
    current_offset = 0

    for idx, char in enumerate(text):
        font = position_to_font.get(idx)
        if not font:
            final_text += char
            current_offset += len(char.encode("utf-16-le")) // 2
            continue

        emoji_id = all_emoji_ids.get((char, font.id))
        if not emoji_id:
            final_text += char
            current_offset += len(char.encode("utf-16-le")) // 2
            continue

        # Use placeholder emoji
        placeholder = "🎨"
        final_text += placeholder
        placeholder_len = len(placeholder.encode("utf-16-le")) // 2

        final_entities.append(
            MessageEntity(
                type="custom_emoji",
                offset=current_offset,
                length=placeholder_len,
                custom_emoji_id=emoji_id,
            )
        )
        current_offset += placeholder_len

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
            text="<b>缓存已过期</b>\n\n请重新发送",
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
            text=f"<b>文字过长</b>\n\n最多支持 {MAX_TEXT_LENGTH} 个字符\n当前: {len(text_to_process)} 个字符",
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
                text="<b>暂无可用字体</b>\n\n请联系管理员添加字体文件",
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
                    text="<b>字体文件不存在</b>\n\n请联系管理员修复",
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
            text="<b>生成失败</b>\n\n请稍后重试",
            parse_mode="HTML",
        )
