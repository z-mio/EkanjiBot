"""TTL (Time-To-Live) cache implementation for temporary data storage.

This module provides a cache with automatic expiration to prevent memory leaks
from unbounded dictionary growth.
"""

import time
from dataclasses import dataclass, field
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class _CacheEntry(Generic[V]):
    """Internal cache entry with expiration timestamp."""

    value: V
    expires_at: float


class TTLCache(Generic[K, V]):
    """Thread-unsafe cache with time-based expiration.

    Items expire after `ttl_seconds` and are lazily removed on access.
    Periodic cleanup can be triggered via `cleanup()`.

    Example:
        >>> cache: TTLCache[str, tuple[str, bool]] = TTLCache(ttl_seconds=300)
        >>> cache["key"] = ("value", True)
        >>> cache["key"]
        ('value', True)
        >>> # After 300 seconds, cache["key"] raises KeyError
    """

    def __init__(self, ttl_seconds: float = 300.0, max_size: int = 10000):
        """Initialize TTL cache.

        Args:
            ttl_seconds: Time-to-live in seconds for each entry.
            max_size: Maximum number of entries before forced cleanup.
        """
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._data: dict[K, _CacheEntry[V]] = {}

    def __getitem__(self, key: K) -> V:
        """Get item by key, raising KeyError if missing or expired."""
        entry = self._data[key]
        if entry.expires_at < time.monotonic():
            del self._data[key]
            raise KeyError(key)
        return entry.value

    def __setitem__(self, key: K, value: V) -> None:
        """Set item with automatic TTL expiration."""
        # Periodic size check
        if len(self._data) >= self._max_size:
            self.cleanup()

        self._data[key] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + self._ttl,
        )

    def __delitem__(self, key: K) -> None:
        """Delete item by key."""
        del self._data[key]

    def __contains__(self, key: K) -> bool:
        """Check if key exists and is not expired."""
        try:
            self[key]
            return True
        except KeyError:
            return False

    def get(self, key: K, default: V | None = None) -> V | None:
        """Get item with default if missing or expired."""
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key: K, *args: V) -> V:
        """Remove and return item, or default if provided.

        Args:
            key: Key to remove.
            *args: Optional default value (at most one).

        Returns:
            Removed value or default.

        Raises:
            KeyError: If key missing and no default provided.
        """
        if key in self._data:
            entry = self._data.pop(key)
            if entry.expires_at >= time.monotonic():
                return entry.value
        if args:
            return args[0]
        raise KeyError(key)

    def cleanup(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries removed.
        """
        now = time.monotonic()
        expired = [k for k, v in self._data.items() if v.expires_at < now]
        for k in expired:
            del self._data[k]
        return len(expired)

    def clear(self) -> None:
        """Remove all entries."""
        self._data.clear()

    def __len__(self) -> int:
        """Return number of entries (including potentially expired)."""
        return len(self._data)

    def __repr__(self) -> str:
        return f"TTLCache(ttl={self._ttl}s, size={len(self._data)})"
