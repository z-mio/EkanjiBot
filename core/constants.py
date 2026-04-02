"""Centralized constants for EkanjiBot.

This module defines all magic numbers and configuration constants
used throughout the codebase to ensure consistency and easy maintenance.
"""

# Text processing limits
MAX_TEXT_LENGTH: int = 120  # Maximum characters per request
PLACEHOLDER_DISPLAY_LIMIT: int = 100  # Max chars to show in inline query placeholder

# Sticker configuration
MAX_STICKERS_PER_PACK: int = 120  # Telegram's limit per pack
STICKER_SIZE: tuple[int, int] = (100, 100)  # Pixel dimensions for sticker images
FONT_SIZE: int = 100  # Font size in points for rendering

# Database configuration (SQLite optimizations)
DB_TIMEOUT_SECONDS: float = 60.0
DB_CACHE_SIZE: int = 10000  # ~10MB cache
DB_BUSY_TIMEOUT_MS: int = 60000  # 60 seconds in milliseconds

# Telegram constants
CUSTOM_EMOJI_PLACEHOLDER: str = "🎨"  # Placeholder for custom emoji entities

# Sticker pack templates
STICKER_PACK_TITLE_TEMPLATE: str = "Ekanji #{}"
STICKER_PACK_NAME_TEMPLATE: str = "p{}_by_{}"

# Font configuration
FONT_EXTENSIONS: set[str] = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}

# Rendering configuration
RENDER_THREAD_POOL_SIZE: int = 4
WEBP_QUALITY: int = 85
WEBP_METHOD: int = 4

# Default language
DEFAULT_LANGUAGE: str = "zh"
