"""User repository with user-specific operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User model."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Get user by Telegram ID."""
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_or_create(self, telegram_id: int, username: str | None, full_name: str, language: str = "zh") -> User:
        """Get existing user or create new one."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            # Update user info if changed
            if user.username != username or user.full_name != full_name:
                user.username = username
                user.full_name = full_name
                await self.session.flush()
            return user

        # Create new user
        new_user = User(telegram_id=telegram_id, username=username, full_name=full_name, language=language)
        return await self.create(new_user)
