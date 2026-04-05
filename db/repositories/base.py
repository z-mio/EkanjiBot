"""Base repository with common CRUD operations."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository[ModelType]:
    """Base repository providing generic CRUD operations."""

    def __init__(self, session: AsyncSession, model: type[ModelType]):
        self.session = session
        self.model = model

    async def get_by_id(self, id: int) -> ModelType | None:
        """Get single record by ID.

        Args:
            id: Primary key of the record.

        Returns:
            Model instance if found, None otherwise.
        """
        result = await self.session.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[ModelType]:
        """Get multiple records with pagination.

        Args:
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            Sequence of model instances.
        """
        result = await self.session.execute(select(self.model).offset(skip).limit(limit))
        return result.scalars().all()

    async def create(self, obj: ModelType) -> ModelType:
        """Create a new record.

        Args:
            obj: Model instance to create.

        Returns:
            Created model instance with ID populated.
        """
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, id: int, **kwargs: Any) -> ModelType | None:
        """Update a record by ID.

        Args:
            id: Primary key of the record to update.
            **kwargs: Field values to update.

        Returns:
            Updated model instance if found, None otherwise.
        """
        await self.session.execute(update(self.model).where(self.model.id == id).values(**kwargs))
        await self.session.flush()
        return await self.get_by_id(id)

    async def delete(self, id: int) -> bool:
        """Delete a record by ID.

        Args:
            id: Primary key of the record to delete.

        Returns:
            True if record was deleted, False if not found.
        """
        result = await self.session.execute(delete(self.model).where(self.model.id == id))
        await self.session.flush()
        return result.rowcount > 0
