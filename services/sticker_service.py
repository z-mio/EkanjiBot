"""Sticker management service."""

import asyncio
import re
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile, InputSticker
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.character_glyph import CharacterGlyph
from db.repositories.character_glyph_repo import CharacterGlyphRepository
from db.repositories.sticker_set_repo import StickerSetRepository
from services.image_service import ImageRenderer


class StickerService:
    """Service for managing stickers and converting text to emojis."""

    MAX_STICKERS_PER_PACK = 120  # Telegram limit for custom emoji stickers per pack
    MAX_CONCURRENT_UPLOADS = 5  # Limit concurrent uploads to avoid rate limits

    # 匹配所有非空白字符（包括符号、标点、所有语言）
    CONVERTIBLE_PATTERN = re.compile(r"\S")

    # Class-level lock for pack creation to prevent race conditions
    _pack_creation_locks: dict[int, asyncio.Lock] = {}

    def __init__(self, session: AsyncSession, bot: Bot):
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
    ) -> str:
        """
        Process text and return formatted message with custom emojis.
        Preserves original layout (line breaks, spaces, non-convertible chars).
        Skips existing custom emojis in entities.
        """

        def get_utf16_length(s: str) -> int:
            """Get UTF-16 length as Telegram API uses."""
            return len(s.encode("utf-16-le")) // 2

        # Build set of character indices that are already custom emojis (using UTF-16 positions)
        # Also store the custom_emoji_id for each position
        skip_indices = set()
        pos_to_custom_emoji_id: dict[int, str] = {}  # UTF-16 position -> custom_emoji_id
        if entities:
            for entity in entities:
                if entity.type == "custom_emoji" and entity.custom_emoji_id:
                    # Mark all UTF-16 positions in this range as skip
                    for i in range(entity.offset, entity.offset + entity.length):
                        skip_indices.add(i)
                        pos_to_custom_emoji_id[i] = str(entity.custom_emoji_id)

        from loguru import logger

        logger.debug(f"Input text: {repr(text)}")
        logger.debug(f"Input entities: {entities}")
        logger.debug(f"skip_indices (UTF-16 positions): {sorted(skip_indices)}")
        logger.debug(f"pos_to_custom_emoji_id: {pos_to_custom_emoji_id}")

        # Build mapping from UTF-16 position to character
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

        # Extract unique convertible characters (excluding existing custom emojis)
        convertible_chars = []
        seen = set()

        def is_unicode_emoji(char: str) -> bool:
            """Check if character is a Unicode emoji (not custom emoji)."""
            import unicodedata

            if len(char) == 0:
                return False
            # Check if it's an emoji using Unicode categories
            for c in char:
                if unicodedata.category(c) == "So":  # Symbol, other (includes emojis)
                    return True
            # Alternative: check emoji Unicode ranges
            code = ord(char[0])
            # Emoji ranges
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
            # Skip if this position is an existing custom emoji
            if idx in skip_char_indices:
                continue
            # Skip whitespace
            if char.isspace():
                continue
            # Skip Unicode emojis (they should not be converted to custom emojis)
            if is_unicode_emoji(char):
                logger.debug(f"Skipping Unicode emoji: {repr(char)}")
                continue
            # Add to list if not seen
            if char not in seen:
                convertible_chars.append(char)
                seen.add(char)

        if not convertible_chars:
            # No convertible characters, return original with existing entities preserved
            return text, []

        # Check cache concurrently
        cache_tasks = [self._check_cache(char, font_id) for char in convertible_chars]
        cache_results = await asyncio.gather(*cache_tasks)

        # Build emoji mapping: char -> emoji_id
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
            # Keep existing custom emojis as-is (check by character index)
            if idx in skip_char_indices:
                # 找到这个字符对应的任意一个 UTF-16 位置来获取 custom_emoji_id
                char_utf16_len = get_utf16_length(char)
                # 重建这个字符的 UTF-16 位置范围
                char_start_pos = sum(get_utf16_length(text[i]) for i in range(idx))
                # 获取 custom_emoji_id（从任意一个位置）
                custom_emoji_id = None
                for pos in range(char_start_pos, char_start_pos + char_utf16_len):
                    if pos in pos_to_custom_emoji_id:
                        custom_emoji_id = pos_to_custom_emoji_id[pos]
                        break

                result_text.append(char)
                char_len = get_utf16_length(char)
                if custom_emoji_id:
                    from aiogram.types import MessageEntity

                    result_entities.append(
                        MessageEntity(
                            type="custom_emoji",
                            offset=current_offset,
                            length=char_len,
                            custom_emoji_id=custom_emoji_id,
                        )
                    )
                    logger.debug(f"Keeping original custom emoji at idx {idx}: {repr(char)}, id={custom_emoji_id}")
                else:
                    logger.debug(f"Keeping character at idx {idx}: {repr(char)} (no custom_emoji_id found)")
                current_offset += char_len
            elif char in char_to_emoji_id:
                # Use "🎨" as placeholder for custom emoji (shorter UTF-16)
                placeholder = "🎨"
                result_text.append(placeholder)
                placeholder_length = get_utf16_length(placeholder)
                # Create entity for this position
                from aiogram.types import MessageEntity

                result_entities.append(
                    MessageEntity(
                        type="custom_emoji",
                        offset=current_offset,
                        length=placeholder_length,
                        custom_emoji_id=str(char_to_emoji_id[char]),  # Convert to string
                    )
                )
                logger.debug(f"Adding new emoji for '{char}' at offset {current_offset}, id={char_to_emoji_id[char]}")
                current_offset += placeholder_length
            else:
                # Keep original: spaces, newlines, punctuation, etc.
                result_text.append(char)
                current_offset += get_utf16_length(char)

        logger.debug(f"Result entities count: {len(result_entities)}")
        return "".join(result_text), result_entities

    async def _check_cache(self, character: str, font_id: int) -> str | None:
        """Check if character exists in cache. Returns emoji_id or None."""
        cached = await self.glyph_repo.get_by_character_and_font(character, font_id)
        return cached.custom_emoji_id if cached else None

    async def _create_sticker(
        self, user_id: int, character: str, font_id: int, image_bytes: bytes, bot_username: str
    ) -> str:
        """Create a sticker for a character and return its custom emoji ID."""
        # Get available pack or prepare to create new one
        pack, is_new_pack = await self._get_or_create_pack(user_id, bot_username)

        # Prepare sticker input
        input_sticker = InputSticker(
            sticker=BufferedInputFile(image_bytes, filename=f"{ord(character):04x}.webp"),
            emoji_list=["✏️"],
            format="static",
        )

        if is_new_pack:
            # Create new sticker set with this first sticker
            # Telegram requires at least 1 sticker when creating a set
            await self.bot.create_new_sticker_set(
                user_id=user_id,
                name=pack.pack_name,
                title=f"Custom Emoji Pack #{pack.pack_index}",
                stickers=[input_sticker],  # Must include at least 1 sticker
                sticker_type="custom_emoji",
                needs_repainting=True,
            )
            # Update pack count (now has 1 sticker)
            pack.sticker_count = 1
            await self.session.flush()
        else:
            # Add to existing sticker set
            success = await self.bot.add_sticker_to_set(user_id=user_id, name=pack.pack_name, sticker=input_sticker)
            if not success:
                raise Exception(f"Failed to add sticker for character: {character}")
            # Update pack count
            await self.pack_repo.increment_sticker_count(pack.id)

        # Get the newly added sticker's emoji ID
        sticker_set = await self.bot.get_sticker_set(name=pack.pack_name)
        new_sticker = sticker_set.stickers[-1]  # Last added sticker

        # Save to glyph database
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
        """Get available pack or create new one. Returns (pack, is_new_pack)."""
        # Acquire lock for this user to prevent concurrent pack creation
        if user_id not in StickerService._pack_creation_locks:
            StickerService._pack_creation_locks[user_id] = asyncio.Lock()
        lock = StickerService._pack_creation_locks[user_id]

        async with lock:
            # Double-check after acquiring lock (another task might have created a pack)
            pack = await self.pack_repo.get_available_pack(user_id)
            if pack:
                return pack, False

            return await self._do_create_pack(user_id, bot_username)

    async def _do_create_pack(self, user_id: int, bot_username: str) -> tuple:
        """Internal method to create a new pack. Must be called with lock held."""
        from db.models.sticker_set import StickerSet

        # Need to create new pack - find next available index
        # First check what packs already exist for this user (including full ones)
        existing_packs = await self.pack_repo.get_user_packs(user_id)
        existing_indices = {p.pack_index for p in existing_packs}

        # Find the first available index
        pack_index = 1
        while pack_index in existing_indices:
            pack_index += 1

        pack_name = f"u{user_id}_p{pack_index}_by_{bot_username}"

        # Double-check pack_name doesn't exist in database (safety)
        existing_pack = await self.pack_repo.get_by_pack_name(pack_name)
        if existing_pack:
            # If found, use it (shouldn't happen normally)
            return existing_pack, False

        # Check if sticker pack already exists in Telegram (database was reset but Telegram packs remain)
        # In this case, delete the old pack and skip to next index since character mappings are lost
        tg_pack_checked = False
        try:
            tg_sticker_set = await self.bot.get_sticker_set(name=pack_name)
            if tg_sticker_set:
                logger.warning(f"Found existing Telegram sticker pack: {pack_name} - deleting it (database was reset)")
                try:
                    # Try to delete the sticker set
                    await self.bot.delete_sticker_set(name=pack_name)
                    logger.info(f"Deleted existing Telegram sticker pack: {pack_name}")
                    # Skip this index - let first character create fresh pack at next index
                    pack_index += 1
                    pack_name = f"u{user_id}_p{pack_index}_by_{bot_username}"
                    tg_pack_checked = True
                except Exception as e:
                    logger.error(f"Failed to delete sticker pack {pack_name}: {e}")
                    # Check if it's because pack doesn't exist anymore
                    if "STICKERSET_INVALID" in str(e) or "STICKERPACK_NOT_FOUND" in str(e):
                        # Pack already gone, we can use this index
                        tg_pack_checked = True
                    else:
                        # Pack exists but can't be deleted, try next index
                        pack_index += 1
                        pack_name = f"u{user_id}_p{pack_index}_by_{bot_username}"
                        tg_pack_checked = True
        except Exception:
            # Pack doesn't exist in Telegram, proceed to create new at current index
            pass

        # If we had to skip an index, verify the new index is also free
        while tg_pack_checked:
            try:
                tg_sticker_set = await self.bot.get_sticker_set(name=pack_name)
                if not tg_sticker_set:
                    # This pack name is free
                    tg_pack_checked = False
                else:
                    # Try to delete this one too
                    logger.warning(f"Found another existing pack at new index: {pack_name} - deleting")
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
                # Error checking, assume pack doesn't exist
                tg_pack_checked = False

        # Create pack record in database (but not in Telegram yet)
        pack = StickerSet(
            user_id=user_id,
            pack_name=pack_name,
            pack_index=pack_index,
            max_stickers=self.MAX_STICKERS_PER_PACK,
            sticker_count=0,
        )
        pack = await self.pack_repo.create(pack)

        return pack, True
