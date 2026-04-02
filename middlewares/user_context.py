"""User context middleware for injecting current user."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    ChosenInlineResult,
    InlineQuery,
    Message,
    TelegramObject,
)
from sqlalchemy.ext.asyncio import AsyncSession

from services.user_service import UserService


class UserContextMiddleware(BaseMiddleware):
    """Middleware to inject current user into handler context."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process handler with user context injection.

        Extracts user information from Telegram events, registers or
        retrieves the user from database, and injects db_user into
        handler context data.

        Args:
            handler: The next handler in the middleware chain.
            event: The Telegram event being processed.
            data: Context data passed through middleware chain.

        Returns:
            Result from the handler.
        """
        session: AsyncSession = data.get("session")
        if not session:
            return await handler(event, data)

        # Extract user info from event
        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user
        elif isinstance(event, InlineQuery) and event.from_user:
            user = event.from_user
        elif isinstance(event, ChosenInlineResult) and event.from_user:
            user = event.from_user

        if user:
            # Register or get user from database
            user_service = UserService(session)
            db_user = await user_service.register_user(
                telegram_id=user.id,
                username=user.username,
                full_name=user.full_name or user.username or "Unknown",
                language="zh",  # Default language
            )
            data["db_user"] = db_user
            data["user_id"] = user.id

        return await handler(event, data)
