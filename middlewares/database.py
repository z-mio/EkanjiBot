"""Database session middleware for dependency injection."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from core.database import AsyncSessionLocal


class DatabaseMiddleware(BaseMiddleware):
    """Middleware to provide database session to handlers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process handler with database session injection.

        Creates a new database session, injects it into handler data,
        and handles automatic commit/rollback based on handler result.

        Args:
            handler: The next handler in the middleware chain.
            event: The Telegram event being processed.
            data: Context data passed through middleware chain.

        Returns:
            Result from the handler.
        """
        async with AsyncSessionLocal() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
