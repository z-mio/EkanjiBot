"""Database engine and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from core.config import bs

# Create async engine with SQLite optimizations
# Using NullPool to avoid connection reuse issues with SQLite
# Each operation gets a fresh connection, preventing lock inheritance
async_engine = create_async_engine(
    bs.database_url,
    echo=False,  # Disable SQL logging
    future=True,
    connect_args={
        "timeout": 60.0,  # 60 second timeout for lock waits
    },
    poolclass=NullPool,  # No connection pooling - each request gets fresh connection
)


# Enable SQLite WAL mode and other optimizations on connection
@event.listens_for(async_engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Configure SQLite for better concurrency and performance."""
    cursor = dbapi_conn.cursor()
    # WAL mode allows concurrent reads during writes (readers don't block writers)
    cursor.execute("PRAGMA journal_mode=WAL")
    # Synchronous NORMAL is a good balance of durability vs performance
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Increase cache size for better performance (10MB)
    cursor.execute("PRAGMA cache_size=10000")
    # Enable memory-mapped I/O for faster reads
    cursor.execute("PRAGMA mmap_size=30000000000")  # 30GB limit
    # Set busy timeout at SQLite level (in milliseconds)
    cursor.execute("PRAGMA busy_timeout=60000")  # 60 seconds
    cursor.close()


# Async session factory with optimized settings
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initialize database - create all tables."""
    # Ensure data directory exists before creating database
    # This is necessary because SQLite cannot create database file
    # if the parent directory does not exist
    _ = bs.data_dir  # Accessing property creates directory automatically

    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await async_engine.dispose()


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions."""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection compatible session generator."""
    async with get_session_context() as session:
        yield session
