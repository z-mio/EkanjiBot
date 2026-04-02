"""Handlers package setup."""

from aiogram import Dispatcher

from handlers.commands import font_router, random_font_router, start_router
from handlers.inline import inline_router
from handlers.messages import text_router
from middlewares.database import DatabaseMiddleware
from middlewares.user_context import UserContextMiddleware


def setup_handlers(dp: Dispatcher) -> None:
    """Register all handlers and middlewares."""
    # Register middlewares globally
    dp.message.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())
    dp.inline_query.middleware(DatabaseMiddleware())
    dp.chosen_inline_result.middleware(DatabaseMiddleware())

    dp.message.middleware(UserContextMiddleware())
    dp.callback_query.middleware(UserContextMiddleware())
    dp.inline_query.middleware(UserContextMiddleware())
    dp.chosen_inline_result.middleware(UserContextMiddleware())

    # Register routers
    dp.include_router(start_router)
    dp.include_router(font_router)
    dp.include_router(random_font_router)
    dp.include_router(text_router)
    dp.include_router(inline_router)
