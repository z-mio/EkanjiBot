"""Base model utilities."""

from datetime import datetime

from sqlalchemy import func
from sqlmodel import Field


# Use Field directly instead of Annotated types
def CreatedAtField():
    """Factory for created_at field."""
    return Field(default_factory=datetime.utcnow, nullable=False)


def UpdatedAtField():
    """Factory for updated_at field."""
    return Field(default_factory=datetime.utcnow, nullable=False, sa_column_kwargs={"onupdate": func.now()})
