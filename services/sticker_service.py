"""Sticker management service.

This module provides sticker pack management and text-to-emoji conversion
for Telegram Custom Emoji stickers. Handles sticker creation, caching,
pack management with race condition handling, and UTF-16 entity positioning.
"""

import asyncio
import re
import unicodedata
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile, InputSticker, MessageEntity
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.character_glyph import CharacterGlyph
from db.repositories.character_glyph_repo import CharacterGlyphRepository
from db.repositories.sticker_set_repo import StickerSetRepository
from services.image_service import ImageRenderer


class StickerService:
    """Service for managing stickers and converting text to emojis.

    Handles the complete workflow of converting text characters into
    Telegram Custom Emoji stickers, including:
    - Character rendering via ImageRenderer
    - Sticker pack management (auto-creation when full)
    - Race condition handling with per-user locks
    - UTF-16 entity positioning for Telegram API compliance
    - Character-to-emoji caching in database

    Attributes:
        MAX_STICKERS_PER_PACK: Telegram limit (120 stickers per pack).
        MAX_CONCURRENT_UPLOADS: Upload concurrency limit to avoid rate limits.
        CONVERTIBLE_PATTERN: Regex matching non-whitespace characters.
    """

    MAX_STICKERS_PER_PACK = 120
    MAX_CONCURRENT_UPLOADS = 5
    CONVERTIBLE_PATTERN = re.compile(r"\S")

    # Class-level lock dictionary to prevent concurrent pack creation per user
    _pack_creation_locks: dict[int, asyncio.Lock] = {}

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
        self._upload_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_UPLOADS)

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
            4. Render and upload missing characters
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

        # Extract unique convertible characters
        convertible_chars = []
        seen = set()

        def is_unicode_emoji(char: str) -> bool:
            """Check if character is a Unicode emoji.

            Args:
                char: Single character to check.

            Returns:
                True if character is a Unicode emoji.
            """
            if len(char) == 0:
                return False
            # Check Unicode category
            for c in char:
                if unicodedata.category(c) == "So":
                    return True
            # Check emoji Unicode ranges
            code = ord(char[0])
            if (
                (0x1F600 <= code <= 0x1F64F)  # Emoticons
                or (0x1F300 <= code <= 0x1F5FF)  # Misc symbols
                or (0x1F680 <= code <= 0x1F6FF)  # Transport
                or (0x1F1E0 <= code <= 0x1F1FF)  # Flags
                or (0x2600 <= code <= 0x26FF)  # Misc
                or (0x2700 <= code <= 0x27BF)  # Dingbats
            ):
                return True
            return False

        for idx, char in enumerate(text):
            if idx in skip_char_indices:
                continue
            if char.isspace():
                continue
            if is_unicode_emoji(char):
                logger.debug(f"Skipping Unicode emoji: {repr(char)}")
                continue
            if char not in seen:
                convertible_chars.append(char)
                seen.add(char)

        if not convertible_chars:
            return text, []

        # Check cache concurrently
        cache_tasks = [self._check_cache(char, font_id) for char in convertible_chars]
        cache_results = await asyncio.gather(*cache_tasks)

        # Build emoji mapping
        char_to_emoji_id: dict[str, str] = {}
        chars_to_create: list[str] = []

        for char, emoji_id in zip(convertible_chars, cache_results, strict=False):
            if emoji_id:
                char_to_emoji_id[char] = emoji_id
            else:
                chars_to_create.append(char)

        # Create missing characters
        if chars_to_create:
            images = await self.renderer.render_batch(chars_to_create, font_path)

            semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_UPLOADS)

            async def upload_with_limit(char: str, image: bytes) -> tuple[str, str]:
                async with semaphore:
                    emoji_id = await self._create_sticker(
                        user_id=user_id,
                        character=char,
                        font_id=font_id,
                        image_bytes=image,
                        bot_username=bot_username,
                    )
                    return char, emoji_id

            upload_tasks = [
                upload_with_limit(char, image) for char, image in zip(chars_to_create, images, strict=False)
            ]
            upload_results = await asyncio.gather(*upload_tasks)

            for char, emoji_id in upload_results:
                char_to_emoji_id[char] = emoji_id

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

    async def _check_cache(self, character: str, font_id: int) -> str | None:
        """Check if character exists in glyph cache.

        Args:
            character: Character to look up.
            font_id: Font ID for lookup.

        Returns:
            Custom emoji ID if found, None otherwise.
        """
        cached = await self.glyph_repo.get_by_character_and_font(character, font_id)
        return cached.custom_emoji_id if cached else None

    async def _create_sticker(
        self,
        user_id: int,
        character: str,
        font_id: int,
        image_bytes: bytes,
        bot_username: str,
    ) -> str:
        """Create sticker for character and return custom emoji ID.

        Args:
            user_id: Telegram user ID.
            character: Character being converted.
            font_id: Font ID for glyph storage.
            image_bytes: WebP image data.
            bot_username: Bot username for pack naming.

        Returns:
            Custom emoji ID from Telegram.

        Raises:
            Exception: If sticker creation fails.
        """
        pack, is_new_pack = await self._get_or_create_pack(user_id, bot_username)

        input_sticker = InputSticker(
            sticker=BufferedInputFile(image_bytes, filename=f"{ord(character):04x}.webp"),
            emoji_list=["✏️"],
            format="static",
        )

        if is_new_pack:
            await self.bot.create_new_sticker_set(
                user_id=user_id,
                name=pack.pack_name,
                title=f"Custom Emoji Pack #{pack.pack_index}",
                stickers=[input_sticker],
                sticker_type="custom_emoji",
                needs_repainting=True,
            )
            pack.sticker_count = 1
            await self.session.flush()
        else:
            success = await self.bot.add_sticker_to_set(user_id=user_id, name=pack.pack_name, sticker=input_sticker)
            if not success:
                raise Exception(f"Failed to add sticker for character: {character}")
            await self.pack_repo.increment_sticker_count(pack.id)

        sticker_set = await self.bot.get_sticker_set(name=pack.pack_name)
        new_sticker = sticker_set.stickers[-1]

        glyph_entry = CharacterGlyph(
            character=character,
            font_id=font_id,
            custom_emoji_id=new_sticker.custom_emoji_id,
            file_id=new_sticker.file_id,
            emoji_list="✏️",
        )
        await self.glyph_repo.create(glyph_entry)

        return new_sticker.custom_emoji_id

    async def _get_or_create_pack(self, user_id: int, bot_username: str) -> tuple:
        """Get available pack or create new one.

        Uses per-user locking to prevent race conditions during pack creation.

        Args:
            user_id: Telegram user ID.
            bot_username: Bot username for pack naming.

        Returns:
            Tuple of (StickerSet, is_new_pack) where is_new_pack indicates
            if a new pack was created.
        """
        if user_id not in StickerService._pack_creation_locks:
            StickerService._pack_creation_locks[user_id] = asyncio.Lock()
        lock = StickerService._pack_creation_locks[user_id]

        async with lock:
            pack = await self.pack_repo.get_available_pack(user_id)
            if pack:
                return pack, False
            return await self._do_create_pack(user_id, bot_username)

    async def _do_create_pack(self, user_id: int, bot_username: str) -> tuple:
        """Create new sticker pack database record.

        Must be called with user's pack creation lock held.
        Handles orphaned Telegram packs from database resets.

        Args:
            user_id: Telegram user ID.
            bot_username: Bot username for pack naming.

        Returns:
            Tuple of (StickerSet, is_new_pack=True).
        """
        from db.models.sticker_set import StickerSet

        existing_packs = await self.pack_repo.get_user_packs(user_id)
        existing_indices = {p.pack_index for p in existing_packs}

        pack_index = 1
        while pack_index in existing_indices:
            pack_index += 1

        pack_name = f"u{user_id}_p{pack_index}_by_{bot_username}"

        # Safety check: ensure pack_name doesn't exist in database
        existing_pack = await self.pack_repo.get_by_pack_name(pack_name)
        if existing_pack:
            return existing_pack, False

        # Handle orphaned Telegram packs from database reset
        tg_pack_checked = False
        try:
            tg_sticker_set = await self.bot.get_sticker_set(name=pack_name)
            if tg_sticker_set:
                logger.warning(f"Found orphaned pack: {pack_name} - deleting")
                try:
                    await self.bot.delete_sticker_set(name=pack_name)
                    logger.info(f"Deleted orphaned pack: {pack_name}")
                    pack_index += 1
                    pack_name = f"u{user_id}_p{pack_index}_by_{bot_username}"
                    tg_pack_checked = True
                except Exception as e:
                    logger.error(f"Failed to delete pack {pack_name}: {e}")
                    if "STICKERSET_INVALID" in str(e) or "STICKERPACK_NOT_FOUND" in str(e):
                        tg_pack_checked = True
                    else:
                        pack_index += 1
                        pack_name = f"u{user_id}_p{pack_index}_by_{bot_username}"
                        tg_pack_checked = True
        except Exception:
            pass

        # Verify new index is available
        while tg_pack_checked:
            try:
                tg_sticker_set = await self.bot.get_sticker_set(name=pack_name)
                if not tg_sticker_set:
                    tg_pack_checked = False
                else:
                    logger.warning(f"Found another orphaned pack: {pack_name} - deleting")
                    try:
                        await self.bot.delete_sticker_set(name=pack_name)
                        pack_index += 1
                        pack_name = f"u{user_id}_p{pack_index}_by_{bot_username}"
                    except Exception as e2:
                        if "STICKERSET_INVALID" in str(e2) or "STICKERPACK_NOT_FOUND" in str(e2):
                            tg_pack_checked = False
                        else:
                            pack_index += 1
                            pack_name = f"u{user_id}_p{pack_index}_by_{bot_username}"
            except Exception:
                tg_pack_checked = False

        pack = StickerSet(
            user_id=user_id,
            pack_name=pack_name,
            pack_index=pack_index,
            max_stickers=self.MAX_STICKERS_PER_PACK,
            sticker_count=0,
        )
        pack = await self.pack_repo.create(pack)

        return pack, True
