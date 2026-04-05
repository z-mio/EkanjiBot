"""Telegram API uses UTF-16 code units for entity offsets."""


def get_utf16_length(s: str) -> int:
    """Telegram Bot API requires UTF-16 code unit length for entity offsets."""
    return len(s.encode("utf-16-le")) // 2
