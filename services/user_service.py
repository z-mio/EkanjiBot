"""User management service."""

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from db.repositories.user_repo import UserRepository


class UserService:
    """Service for user management."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = UserRepository(session)

    async def register_user(self, telegram_id: int, username: str | None, full_name: str, language: str = "zh") -> User:
        """Register new user or update existing."""
        return await self.repo.get_or_create(
            telegram_id=telegram_id, username=username, full_name=full_name, language=language
        )

    async def get_user(self, telegram_id: int) -> User | None:
        """Get user by Telegram ID."""
        return await self.repo.get_by_telegram_id(telegram_id)

    async def update_language(self, telegram_id: int, language: str) -> User | None:
        """Update user's preferred language."""
        user = await self.repo.get_by_telegram_id(telegram_id)
        if not user:
            return None

        user.language = language
        await self.session.flush()
        return user
