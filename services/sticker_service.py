"""Sticker management service.

This module provides sticker pack management and text-to-emoji conversion
for Telegram Custom Emoji stickers. Uses a global concurrent task queue for
sticker creation to maximize throughput while maintaining correctness.

Architecture:
- Global concurrent queue: 5 workers process tasks in parallel
- Task-based: Each character creation is a task
- Automatic caching: Database stores character → emoji mapping
- User packs: Each user has their own sticker packs
"""

import asyncio
import re
from pathlib import Path

from aiogram import Bot
from aiogram.types import MessageEntity
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.character_glyph_repo import CharacterGlyphRepository
from db.repositories.sticker_set_repo import StickerSetRepository
from services.image_service import ImageRenderer
from utils.emoji_utils import is_unicode_emoji

# Global lock for pack creation - ensures only one pack is created at a time
_pack_lock = asyncio.Lock()

# Global lock for sticker addition - ensures stickers are added serially to avoid race conditions
_sticker_add_lock = asyncio.Lock()


class StickerService:
    """Service for managing stickers and converting text to emojis.

    Uses the global StickerTaskQueue for all sticker creation operations.
    The service itself is stateless - it just coordinates rendering,
    caching, and task submission.
    """

    MAX_STICKERS_PER_PACK = 120
    CONVERTIBLE_PATTERN = re.compile(r"\S")

    def __init__(self, session: AsyncSession, bot: Bot):
        """Initialize sticker service.

        Args:
            session: Database session for repository operations.
            bot: Aiogram Bot instance for Telegram API calls.
        """
        self.session = session
        self.bot = bot
        self.glyph_repo = CharacterGlyphRepository(session)
        self.pack_repo = StickerSetRepository(session)
        self.renderer = ImageRenderer()

    async def process_text_with_layout(
        self,
        user_id: int,
        text: str,
        font_id: int,
        font_path: Path,
        bot_username: str,
        entities: list | None = None,
    ) -> tuple[str, list[MessageEntity]]:
        """Process text and convert to custom emoji stickers.

        Preserves original layout including line breaks, spaces, and
        non-convertible characters. Skips existing custom emojis in entities.

        Workflow:
            1. Parse existing custom emoji entities
            2. Extract unique convertible characters
            3. Check cache for existing glyphs
            4. Create tasks for missing characters (serial queue)
            5. Build result with proper UTF-16 entity offsets

        Args:
            user_id: Telegram user ID.
            text: Input text to convert.
            font_id: Database ID of font to use.
            font_path: Path to TrueType font file.
            bot_username: Bot username for sticker pack naming.
            entities: Optional existing message entities.

        Returns:
            Tuple of (result_text, result_entities) where result_text uses
            placeholder characters and result_entities maps them to custom emojis.
        """

        def get_utf16_length(s: str) -> int:
            """Calculate UTF-16 code unit length as Telegram API uses."""
            return len(s.encode("utf-16-le")) // 2

        # Build set of UTF-16 positions that are already custom emojis
        skip_indices = set()
        pos_to_custom_emoji_id: dict[int, str] = {}
        if entities:
            for entity in entities:
                if entity.type == "custom_emoji" and entity.custom_emoji_id:
                    for i in range(entity.offset, entity.offset + entity.length):
                        skip_indices.add(i)
                        pos_to_custom_emoji_id[i] = str(entity.custom_emoji_id)

        logger.debug(f"Input text: {repr(text)}")
        logger.debug(f"Input entities: {entities}")
        logger.debug(f"skip_indices (UTF-16 positions): {sorted(skip_indices)}")
        logger.debug(f"pos_to_custom_emoji_id: {pos_to_custom_emoji_id}")

        # Build mapping from UTF-16 position to character index
        utf16_pos_to_char_idx = {}
        current_pos = 0
        for char_idx, char in enumerate(text):
            char_utf16_len = get_utf16_length(char)
            for pos in range(current_pos, current_pos + char_utf16_len):
                utf16_pos_to_char_idx[pos] = char_idx
            current_pos += char_utf16_len

        # Find which character indices to skip
        skip_char_indices = set()
        for skip_pos in skip_indices:
            if skip_pos in utf16_pos_to_char_idx:
                skip_char_indices.add(utf16_pos_to_char_idx[skip_pos])

        logger.debug(f"utf16_pos_to_char_idx: {utf16_pos_to_char_idx}")
        logger.debug(f"skip_char_indices: {sorted(skip_char_indices)}")
        logger.debug(f"Total chars: {len(text)}, text: {repr(text)}")

        # Step 1: Extract unique characters to process (skip newlines, Unicode emoji, existing custom emoji)
        chars_to_process = []
        seen = set()

        for idx, char in enumerate(text):
            if idx in skip_char_indices:
                continue
            # Skip newlines - keep original line break format
            if char == "\n":
                continue
            # Skip Unicode emoji
            if is_unicode_emoji(char):
                logger.debug(f"Skipping Unicode emoji: {repr(char)}")
                continue
            if char not in seen:
                chars_to_process.append(char)
                seen.add(char)

        if not chars_to_process:
            return text, []

        # Step 2: Batch check cache FIRST (cache first, then check font support)
        char_font_pairs = [(char, font_id) for char in chars_to_process]
        cache_map = await self.glyph_repo.get_by_characters_and_fonts(char_font_pairs)

        # Step 3: For cache misses, check font support and create if supported
        char_to_emoji_id: dict[str, str] = {}

        # Handle cache hits - direct use, no font check needed
        for char in chars_to_process:
            emoji_id = cache_map.get((char, font_id))
            if emoji_id:
                char_to_emoji_id[char] = emoji_id

        # Handle cache misses - check font support before creating
        chars_to_create = []
        for char in chars_to_process:
            if (char, font_id) in cache_map:
                continue  # Already cached, skip
            # Check font support only for cache misses
            if not self.renderer.supports_character(font_path, char):
                logger.debug(f"Skipping unsupported character: {repr(char)} (font: {font_path.name})")
                continue
            chars_to_create.append(char)

        if chars_to_create:
            images = await self.renderer.render_batch(chars_to_create, font_path, check_support=False)

            for char, image in zip(chars_to_create, images, strict=False):
                try:
                    emoji_id = await self._create_sticker(
                        character=char,
                        font_id=font_id,
                        font_path=font_path,
                        image_bytes=image,
                        bot_username=bot_username,
                    )
                    char_to_emoji_id[char] = emoji_id
                except Exception as e:
                    logger.error(f"Failed to create sticker for '{char}': {e}")
                    continue

        # Build result text and entities
        result_text = []
        result_entities = []
        current_offset = 0

        for idx, char in enumerate(text):
            if idx in skip_char_indices:
                # Preserve existing custom emoji
                char_utf16_len = get_utf16_length(char)
                char_start_pos = sum(get_utf16_length(text[i]) for i in range(idx))

                custom_emoji_id = None
                for pos in range(char_start_pos, char_start_pos + char_utf16_len):
                    if pos in pos_to_custom_emoji_id:
                        custom_emoji_id = pos_to_custom_emoji_id[pos]
                        break

                result_text.append(char)
                if custom_emoji_id:
                    result_entities.append(
                        MessageEntity(
                            type="custom_emoji",
                            offset=current_offset,
                            length=char_utf16_len,
                            custom_emoji_id=custom_emoji_id,
                        )
                    )
                    logger.debug(f"Preserved existing custom emoji at {idx}: {repr(char)}")
                current_offset += char_utf16_len
            elif char in char_to_emoji_id:
                # Insert custom emoji placeholder
                placeholder = "🎨"
                result_text.append(placeholder)
                placeholder_length = get_utf16_length(placeholder)
                result_entities.append(
                    MessageEntity(
                        type="custom_emoji",
                        offset=current_offset,
                        length=placeholder_length,
                        custom_emoji_id=str(char_to_emoji_id[char]),
                    )
                )
                logger.debug(f"Added new emoji for '{char}' at offset {current_offset}")
                current_offset += placeholder_length
            else:
                # Keep original character
                result_text.append(char)
                current_offset += get_utf16_length(char)

        logger.debug(f"Result entities count: {len(result_entities)}")
        return "".join(result_text), result_entities

    async def _create_sticker(
        self,
        character: str,
        font_id: int,
        font_path: Path,
        image_bytes: bytes,
        bot_username: str,
    ) -> str:
        """Create a sticker for a character.

        Args:
            character: Character to convert.
            font_id: Font database ID.
            font_path: Path to font file.
            image_bytes: Rendered WebP image.
            bot_username: Bot username for pack naming.

        Returns:
            Custom emoji ID from Telegram.
        """
        from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
        from aiogram.types import BufferedInputFile, InputSticker

        from core.config import bs
        from core.constants import CUSTOM_EMOJI_PLACEHOLDER

        glyph_repo = CharacterGlyphRepository(self.session)
        pack_repo = StickerSetRepository(self.session)

        existing = await glyph_repo.get_by_character_and_font(character, font_id)
        if existing:
            logger.debug(f"Cache hit for '{character}' (font={font_id})")
            return existing.custom_emoji_id

        pack, is_new_pack = await self._get_or_create_pack(bot_username, pack_repo, self.session)

        input_sticker = InputSticker(
            sticker=BufferedInputFile(image_bytes, filename=f"{ord(character):04x}.webp"),
            emoji_list=[CUSTOM_EMOJI_PLACEHOLDER],
            format="static",
        )

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if is_new_pack:
                    await self.bot.create_new_sticker_set(
                        user_id=bs.user_id,
                        name=pack.pack_name,
                        title=f"Ekanji #{pack.pack_index}",
                        stickers=[input_sticker],
                        sticker_type="custom_emoji",
                        needs_repainting=True,
                    )
                    pack.sticker_count = 1
                    await self.session.flush()

                    # For new packs, get the sticker
                    sticker_set = await self.bot.get_sticker_set(name=pack.pack_name)
                    if not sticker_set.stickers:
                        raise Exception(f"Newly created pack {pack.pack_name} has no stickers")
                    new_sticker = sticker_set.stickers[0]
                else:
                    # Record existing stickers before adding
                    sticker_set_before = await self.bot.get_sticker_set(name=pack.pack_name)
                    existing_file_unique_ids = {s.file_unique_id for s in sticker_set_before.stickers}

                    success = await self.bot.add_sticker_to_set(
                        user_id=bs.user_id, name=pack.pack_name, sticker=input_sticker
                    )
                    if not success:
                        raise Exception(f"Failed to add sticker for character: {character}")

                    # Find the newly added sticker by comparing file_unique_ids
                    sticker_set_after = await self.bot.get_sticker_set(name=pack.pack_name)
                    new_sticker = None
                    for s in sticker_set_after.stickers:
                        if s.file_unique_id not in existing_file_unique_ids:
                            new_sticker = s
                            break

                    if not new_sticker:
                        raise Exception(f"Could not find newly added sticker for character: {character}")

                    await pack_repo.increment_sticker_count(pack.id)

                # Save to cache and commit
                await glyph_repo.create_or_get(
                    character=character,
                    font_id=font_id,
                    custom_emoji_id=new_sticker.custom_emoji_id,
                    file_id=new_sticker.file_id,
                    emoji_list=CUSTOM_EMOJI_PLACEHOLDER,
                )
                await self.session.commit()

                logger.info(f"Created sticker for '{character}' -> {new_sticker.custom_emoji_id}")
                return new_sticker.custom_emoji_id

            except TelegramNetworkError as e:
                if attempt < max_retries - 1:
                    wait = 2**attempt
                    logger.warning(f"Network error, retrying in {wait}s ({attempt + 1}/{max_retries}): {e}")
                    await asyncio.sleep(wait)
                    continue
                raise
            except TelegramBadRequest as e:
                error_str = str(e)
                if "STICKERSET_INVALID" in error_str or "STICKERSET_NOT_FOUND" in error_str:
                    async with _pack_lock:
                        async with self._session_factory() as fresh_session:
                            fresh_pack = await StickerSetRepository(fresh_session).get_by_pack_name(pack.pack_name)
                            if fresh_pack and fresh_pack.is_active:
                                fresh_pack.is_active = False
                                await fresh_session.commit()
                                logger.warning(f"Sticker set {pack.pack_name} marked invalid")
                    # Re-check cache before retrying
                    existing = await glyph_repo.get_by_character_and_font(character, font_id)
                    if existing:
                        logger.debug(f"Cache hit after retry for '{character}' (font={font_id})")
                        return existing.custom_emoji_id
                    pack, is_new_pack = await self._get_or_create_pack(bot_username, pack_repo, self.session)
                    continue
                elif "Too Many Requests" in error_str and attempt < max_retries - 1:
                    retry_after = getattr(e, "retry_after", 1) or 1
                    logger.warning(f"Rate limited, waiting {retry_after}s before retry {attempt + 1}/{max_retries}")
                    await asyncio.sleep(retry_after)
                    continue
                raise

    async def _get_or_create_pack(self, bot_username: str, pack_repo, session):
        """Get an available pack or create a new one.

        Args:
            bot_username: Bot username for pack naming.
            pack_repo: StickerSetRepository instance.
            session: Database session.

        Returns:
            Tuple of (pack, is_new_pack) where pack is StickerSet and is_new_pack is bool.
        """
        from core.config import bs
        from db.models.sticker_set import StickerSet

        async with _pack_lock:
            pack = await pack_repo.get_available_pack()
            if pack:
                return pack, False

            pack_index = await pack_repo.get_next_pack_index()
            pack_name = f"p{pack_index}_by_{bot_username}"
            pack_name = await self._handle_orphaned_packs(bot_username, pack_name, pack_index)

            pack = StickerSet(
                created_by=bs.user_id,
                pack_name=pack_name,
                pack_index=pack_index,
                max_stickers=120,
                sticker_count=0,
            )
            pack = await pack_repo.create(pack)
            await session.commit()

            return pack, True

    async def _handle_orphaned_packs(self, bot_username: str, pack_name: str, pack_index: int) -> str:
        """Handle orphaned Telegram packs from database resets.

        Args:
            bot_username: Bot username.
            pack_name: Initial pack name to check.
            pack_index: Initial pack index.

        Returns:
            Available pack name.
        """
        max_attempts = 10
        for _ in range(max_attempts):
            try:
                tg_sticker_set = await self.bot.get_sticker_set(name=pack_name)
                if tg_sticker_set:
                    logger.warning(f"Found orphaned pack: {pack_name} - deleting")
                    try:
                        await self.bot.delete_sticker_set(name=pack_name)
                        logger.info(f"Deleted orphaned pack: {pack_name}")
                    except Exception as e:
                        if "STICKERSET_INVALID" not in str(e) and "STICKERPACK_NOT_FOUND" not in str(e):
                            logger.error(f"Failed to delete pack {pack_name}: {e}")

                    pack_index += 1
                    pack_name = f"p{pack_index}_by_{bot_username}"
            except Exception:
                # Pack doesn't exist, name is available
                break

        return pack_name
