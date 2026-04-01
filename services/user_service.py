"""User management service.

This module provides user registration, retrieval, and preference
management for Telegram bot users.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from db.repositories.user_repo import UserRepository


class UserService:
    """Service for managing Telegram bot users.

    Handles user registration, profile retrieval, and preference updates.
    All operations are asynchronous and use the repository pattern.
    """

    def __init__(self, session: AsyncSession):
        """Initialize user service.

        Args:
            session: Database session for repository operations.
        """
        self.session = session
        self.repo = UserRepository(session)

    async def register_user(
        self,
        telegram_id: int,
        username: str | None,
        full_name: str,
        language: str = "zh",
    ) -> User:
        """Register new user or update existing user information.

        If a user with the given Telegram ID already exists, their profile
        is updated with the latest information.

        Args:
            telegram_id: User's Telegram ID.
            username: Telegram username without @, or None.
            full_name: User's display name.
            language: Preferred language code (default: 'zh').

        Returns:
            Created or updated User model instance.
        """
        return await self.repo.get_or_create(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            language=language,
        )

    async def get_user(self, telegram_id: int) -> User | None:
        """Get user by Telegram ID.

        Args:
            telegram_id: User's Telegram ID.

        Returns:
            User model instance, or None if not found.
        """
        return await self.repo.get_by_telegram_id(telegram_id)

    async def update_language(self, telegram_id: int, language: str) -> User | None:
        """Update user's preferred language.

        Args:
            telegram_id: User's Telegram ID.
            language: New language code to set.

        Returns:
            Updated User model instance, or None if user not found.
        """
        user = await self.repo.get_by_telegram_id(telegram_id)
        if not user:
            return None

        user.language = language
        await self.session.flush()
        return user
