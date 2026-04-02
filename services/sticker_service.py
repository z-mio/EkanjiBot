"""Sticker management service.

This module provides sticker pack management and text-to-emoji conversion
for Telegram Custom Emoji stickers. Uses a global serial task queue for
sticker creation to ensure correctness and simplify caching.

Architecture:
- Global serial queue: Only one sticker creation at a time
- Task-based: Each character creation is a task
- Automatic caching: Database stores character → emoji mapping
- User packs: Each user has their own sticker packs
"""

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile, InputSticker, MessageEntity
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import bs
from db.repositories.character_glyph_repo import CharacterGlyphRepository
from db.repositories.sticker_set_repo import StickerSetRepository
from services.image_service import ImageRenderer
from utils.emoji_utils import is_unicode_emoji


@dataclass
class StickerCreationTask:
    """Task for creating a single sticker.

    Attributes:
        character: Character to convert.
        font_id: Font database ID.
        font_path: Path to font file.
        image_bytes: Rendered WebP image.
        bot_username: Bot username for pack naming.
        result_event: Event to signal completion.
        result: Will hold custom_emoji_id after completion.
        error: Will hold exception if failed.
    """

    character: str
    font_id: int
    font_path: Path
    image_bytes: bytes
    bot_username: str
    result_event: asyncio.Event = None
    result: str | None = None
    error: Exception | None = None

    def __post_init__(self):
        self.result_event = asyncio.Event()


class StickerTaskQueue:
    """Global serial task queue for sticker creation.

    Ensures only one sticker is created at a time, preventing race conditions
    and simplifying the caching logic. Tasks are processed FIFO.

    The queue worker runs in the background and processes tasks one by one.
    Each task's result is communicated back via asyncio.Event.
    """

    _instance: "StickerTaskQueue | None" = None

    def __init__(self):
        self._queue: asyncio.Queue[StickerCreationTask] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._bot: Bot | None = None
        self._session_factory = None
        self._started = False

    @classmethod
    def get_instance(cls) -> "StickerTaskQueue":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self, bot: Bot, session_factory):
        """Start the background worker.

        Args:
            bot: Aiogram Bot instance.
            session_factory: AsyncSession factory for database operations.
        """
        if self._started:
            return

        self._bot = bot
        self._session_factory = session_factory
        self._worker_task = asyncio.create_task(self._worker())
        self._started = True
        logger.info("StickerTaskQueue started")

    async def stop(self):
        """Stop the background worker."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        self._started = False
        logger.info("StickerTaskQueue stopped")

    async def submit(self, task: StickerCreationTask) -> str:
        """Submit a task and wait for result.

        Args:
            task: Sticker creation task.

        Returns:
            Custom emoji ID from Telegram.

        Raises:
            Exception: If task failed.
        """
        await self._queue.put(task)
        await task.result_event.wait()

        if task.error:
            raise task.error

        return task.result

    async def _worker(self):
        """Background worker that processes tasks serially."""
        while True:
            try:
                task = await self._queue.get()
                logger.debug(f"Processing sticker task: '{task.character}' (font={task.font_id})")

                try:
                    async with self._session_factory() as session:
                        emoji_id = await self._process_task(task, session)
                        task.result = emoji_id
                except Exception as e:
                    logger.exception(f"Task failed for '{task.character}'")
                    task.error = e
                finally:
                    task.result_event.set()

            except asyncio.CancelledError:
                logger.info("Worker cancelled")
                break
            except Exception:
                logger.exception("Worker error")
                # Continue processing other tasks

    async def _process_task(self, task: StickerCreationTask, session: AsyncSession) -> str:
        """Process a single sticker creation task.

        Args:
            task: Sticker creation task.
            session: Database session.

        Returns:
            Custom emoji ID.
        """
        from aiogram.exceptions import TelegramBadRequest

        glyph_repo = CharacterGlyphRepository(session)
        pack_repo = StickerSetRepository(session)

        # Check cache first (may have been created while waiting in queue)
        existing = await glyph_repo.get_by_character_and_font(task.character, task.font_id)
        if existing:
            logger.debug(f"Cache hit for '{task.character}' (font={task.font_id})")
            return existing.custom_emoji_id

        # Get or create pack (uses bs.user_id from config)
        pack, is_new_pack = await self._get_or_create_pack(task.bot_username, pack_repo, session)

        # Upload to Telegram (uses bs.user_id from config)
        input_sticker = InputSticker(
            sticker=BufferedInputFile(task.image_bytes, filename=f"{ord(task.character):04x}.webp"),
            emoji_list=["✏️"],
            format="static",
        )

        if is_new_pack:
            await self._bot.create_new_sticker_set(
                user_id=bs.user_id,
                name=pack.pack_name,
                title=f"Ekanji #{pack.pack_index}",
                stickers=[input_sticker],
                sticker_type="custom_emoji",
                needs_repainting=True,
            )
            pack.sticker_count = 1
            await session.flush()
        else:
            try:
                success = await self._bot.add_sticker_to_set(
                    user_id=bs.user_id, name=pack.pack_name, sticker=input_sticker
                )
                if not success:
                    raise Exception(f"Failed to add sticker for character: {task.character}")

                # Increment count on success
                await pack_repo.increment_sticker_count(pack.id)
            except TelegramBadRequest as e:
                # Handle invalid sticker set - mark as inactive and create new pack
                if "STICKERSET_INVALID" in str(e) or "STICKERSET_NOT_FOUND" in str(e):
                    logger.warning(f"Sticker set {pack.pack_name} is invalid, creating new pack")
                    pack.is_active = False
                    await session.flush()

                    # Create new pack
                    pack, _ = await self._get_or_create_pack(task.bot_username, pack_repo, session)

                    # Create new sticker set
                    await self._bot.create_new_sticker_set(
                        user_id=bs.user_id,
                        name=pack.pack_name,
                        title=f"Ekanji #{pack.pack_index}",
                        stickers=[input_sticker],
                        sticker_type="custom_emoji",
                        needs_repainting=True,
                    )
                    pack.sticker_count = 1
                    await session.flush()
                else:
                    raise

        # Get the newly added sticker
        sticker_set = await self._bot.get_sticker_set(name=pack.pack_name)
        new_sticker = sticker_set.stickers[-1]

        # Save to cache
        await glyph_repo.create_or_get(
            character=task.character,
            font_id=task.font_id,
            custom_emoji_id=new_sticker.custom_emoji_id,
            file_id=new_sticker.file_id,
            emoji_list="✏️",
        )

        await session.commit()

        logger.info(f"Created sticker for '{task.character}' -> {new_sticker.custom_emoji_id}")
        return new_sticker.custom_emoji_id

    async def _get_or_create_pack(self, bot_username: str, pack_repo, session):
        """Get available global pack or create new one.

        Uses bs.user_id from config for sticker pack ownership.

        Args:
            bot_username: Bot username.
            pack_repo: StickerSetRepository.
            session: Database session.

        Returns:
            Tuple of (StickerSet, is_new_pack).
        """
        from db.models.sticker_set import StickerSet

        # Get any available global pack
        pack = await pack_repo.get_available_pack()
        if pack:
            return pack, False

        # Create new pack with user_id from config
        pack_index = await pack_repo.get_next_pack_index()
        pack_name = f"p{pack_index}_by_{bot_username}"

        # Handle orphaned Telegram packs
        pack_name = await self._handle_orphaned_packs(bot_username, pack_name, pack_index)

        # Create in database
        pack = StickerSet(
            created_by=bs.user_id,
            pack_name=pack_name,
            pack_index=pack_index,
            max_stickers=120,
            sticker_count=0,
        )
        pack = await pack_repo.create(pack)
        await session.flush()

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
                tg_sticker_set = await self._bot.get_sticker_set(name=pack_name)
                if tg_sticker_set:
                    logger.warning(f"Found orphaned pack: {pack_name} - deleting")
                    try:
                        await self._bot.delete_sticker_set(name=pack_name)
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
        self._task_queue = StickerTaskQueue.get_instance()

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

        # Create missing characters via serial task queue
        if chars_to_create:
            # Render all missing characters (support already checked above)
            images = await self.renderer.render_batch(chars_to_create, font_path, check_support=False)

            # Create tasks and wait for results (serial processing)
            for char, image in zip(chars_to_create, images, strict=False):
                task = StickerCreationTask(
                    character=char,
                    font_id=font_id,
                    font_path=font_path,
                    image_bytes=image,
                    bot_username=bot_username,
                )

                # Submit to queue and wait
                emoji_id = await self._task_queue.submit(task)
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
