"""Base model utilities."""

from datetime import UTC, datetime

from sqlalchemy import func
from sqlmodel import Field


def CreatedAtField():
    """Factory for created_at field with UTC timezone."""
    return Field(default_factory=lambda: datetime.now(UTC), nullable=False)


def UpdatedAtField():
    """Factory for updated_at field with UTC timezone."""
    return Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
        sa_column_kwargs={"onupdate": func.now()},
    )
