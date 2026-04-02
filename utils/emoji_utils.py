"""Emoji utility functions for EkanjiBot.

This module provides utilities for detecting and handling Unicode emojis
in text processing.
"""

import unicodedata


def is_unicode_emoji(char: str) -> bool:
    """Check if a character is a Unicode emoji.

    Uses Unicode category checks and known emoji code ranges to determine
    if a character should be skipped during text-to-emoji conversion.

    Args:
        char: Single character to check.

    Returns:
        True if the character is a Unicode emoji, False otherwise.
    """
    if len(char) == 0:
        return False

    # Check Unicode category for Symbol, Other (So)
    for c in char:
        if unicodedata.category(c) == "So":
            return True

    # Check known emoji Unicode ranges
    code = ord(char[0])
    if (
        (0x1F600 <= code <= 0x1F64F)  # Emoticons
        or (0x1F300 <= code <= 0x1F5FF)  # Misc symbols
        or (0x1F680 <= code <= 0x1F6FF)  # Transport
        or (0x1F1E0 <= code <= 0x1F1FF)  # Flags
        or (0x2600 <= code <= 0x26FF)  # Misc
        or (0x2700 <= code <= 0x27BF)  # Dingbats
    ):
        return True

    return False
