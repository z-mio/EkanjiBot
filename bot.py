"""Main entry point for the Telegram Bot."""

import asyncio
from pathlib import Path

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


def get_system_font_path() -> Path | None:
    """Find a suitable system font for default rendering."""
    # Windows system fonts
    windows_fonts = [
        Path(r"C:\Windows\Fonts\STXINGKA.TTF"),  # 华文行楷
        Path(r"C:\Windows\Fonts\STKAITI.TTF"),  # 华文楷体
        Path(r"C:\Windows\Fonts\simhei.ttf"),  # 黑体
        Path(r"C:\Windows\Fonts\simsun.ttc"),  # 宋体
        Path(r"C:\Windows\Fonts\msyh.ttc"),  # 微软雅黑
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),  # 微软雅黑 Bold
    ]

    # Linux fonts
    linux_fonts = [
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]

    for font_path in windows_fonts + linux_fonts:
        if font_path.exists():
            return font_path

    return None


async def init_system_fonts(session) -> None:
    """Initialize fonts using FontSyncService.

    Syncs fonts from assets/fonts/ with database:
    - Adds new fonts
    - Reactivates previously deleted fonts
    - Deactivates missing fonts
    - Falls back to copying system font if directory is empty
    """
    from services.font_sync_service import FontSyncService

    sync_service = FontSyncService(session)

    # Perform sync
    result = await sync_service.sync_fonts()

    # Handle empty directory fallback
    if result.total_active == 0:
        logger.warning("No fonts available after sync, copying system font...")

        fonts_dir = bs.fonts_dir
        system_font_path = get_system_font_path()

        if system_font_path:
            import shutil

            font_filename = system_font_path.name
            target_path = fonts_dir / font_filename

            if not target_path.exists():
                shutil.copy2(system_font_path, target_path)
                logger.info(f"Copied system font to {target_path}")

            # Re-run sync to register the copied font
            result = await sync_service.sync_fonts()
        else:
            logger.error("No system font available for fallback!")
            return

    # Log default font
    default_font = await sync_service.get_default_font()
    if default_font:
        logger.info(f"Default font: {default_font.name} ({default_font.file_path})")
    else:
        logger.warning("No default font could be determined!")


async def on_startup() -> None:
    """Startup initialization."""
    logger.info("Initializing database...")
    await init_db()

    # Initialize system fonts
    from core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await init_system_fonts(session)
        await session.commit()

    logger.info("Bot started successfully!")


async def on_shutdown() -> None:
    """Shutdown cleanup."""
    logger.info("Shutting down...")
    await close_db()


def main() -> None:
    """Main entry point."""
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
        # 先删除 webhook 并丢弃所有待处理的更新
        await bot.delete_webhook(drop_pending_updates=True)
        # skip_updates=True 再次确保跳过积压消息
        await dp.start_polling(bot, skip_updates=True)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
