"""Main entry point for the Telegram Bot."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from loguru import logger

from core.config import bs
from core.database import close_db, init_db
from handlers import setup_handlers
from log import setup_logging
from utils.event_loop import setup_optimized_event_loop

setup_logging(debug=bs.debug)


async def init_system_fonts(session) -> None:
    """Initialize fonts using FontSyncService.

    Syncs fonts from assets/fonts/ with database:
    - Adds new fonts
    - Reactivates previously deleted fonts
    - Deactivates missing fonts
    """
    from services.font_sync_service import FontSyncService

    sync_service = FontSyncService(session)

    # Perform sync
    result = await sync_service.sync_fonts()

    if result.total_active == 0:
        logger.error("No fonts available! Please add fonts to assets/fonts/ directory.")
        return

    # Log default font
    default_font = await sync_service.get_default_font()
    if default_font:
        logger.info(f"Default font: {default_font.name} ({default_font.file_path})")
    else:
        logger.warning("No default font could be determined!")


async def on_startup(bot: Bot) -> None:
    """Startup initialization.

    Args:
        bot: Aiogram Bot instance.
    """
    logger.info("Initializing database...")
    await init_db()

    # Initialize system fonts
    from core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await init_system_fonts(session)
        await session.commit()

    # Start sticker task queue
    from services.sticker_service import StickerTaskQueue

    queue = StickerTaskQueue.get_instance()
    queue.start(bot, AsyncSessionLocal)

    logger.info("Bot started successfully!")


async def on_shutdown(bot: Bot) -> None:
    """Shutdown cleanup.

    Args:
        bot: Aiogram Bot instance.
    """
    logger.info("Shutting down...")

    # Stop sticker task queue
    from services.sticker_service import StickerTaskQueue

    queue = StickerTaskQueue.get_instance()
    await queue.stop()

    await close_db()


def main() -> None:
    """Main entry point."""
    # Validate required configuration
    if not bs.user_id:
        logger.error("USER_ID environment variable is required!")
        logger.error("Please set USER_ID in .env file (get your Telegram ID from @userinfobot)")
        raise SystemExit(1)

    logger.info(f"Sticker pack owner user ID: {bs.user_id}")

    setup_optimized_event_loop()

    dp = Dispatcher()

    # Register startup/shutdown handlers
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Setup handlers and middlewares
    setup_handlers(dp)

    async def _run() -> None:
        session = AiohttpSession(proxy=bs.bot_proxy)
        bot = Bot(token=bs.bot_token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, skip_updates=True)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
