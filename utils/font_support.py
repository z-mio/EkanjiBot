"""Font character support detection utilities.

This module provides tools to detect whether a font supports a specific character.
Uses fonttools for cmap table inspection (fast) and Pillow for render verification.
"""

from pathlib import Path

from fontTools.ttLib import TTFont
from loguru import logger
from PIL import Image, ImageDraw, ImageFont


def has_glyph_in_cmap(font_path: Path, character: str) -> bool:
    """Check if character exists in font's cmap table.

    This is a fast check that looks up the character in the font's
    character-to-glyph mapping table. However, it doesn't guarantee
    the glyph is actually rendered correctly.

    Args:
        font_path: Path to font file.
        character: Single Unicode character to check.

    Returns:
        True if character is mapped in cmap, False otherwise.
    """
    try:
        font = TTFont(str(font_path))
        cmap = font.getBestCmap()

        # Check if character code exists in cmap
        char_code = ord(character)
        result = char_code in cmap

        font.close()
        return result
    except Exception as e:
        logger.warning(f"Failed to check cmap for {font_path}: {e}")
        return False


def can_render_character(font_path: Path, character: str, font_size: int = 100) -> bool:
    """Check if font can actually render the character with visible output.

    This performs a render test - draws the character and checks if
    the result is non-empty (not just blank/tofu).

    Args:
        font_path: Path to font file.
        character: Single Unicode character to check.
        font_size: Font size to use for rendering test.

    Returns:
        True if character renders with visible pixels, False otherwise.
    """
    try:
        # Create a small test image
        img = Image.new("RGBA", (font_size, font_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Load font
        try:
            font = ImageFont.truetype(str(font_path), font_size)
        except Exception:
            return False

        # Draw character
        draw.text((0, 0), character, font=font, fill=(255, 255, 255, 255))

        # Check if image has any non-transparent pixels
        # Get the alpha channel
        alpha = img.split()[-1]

        # If all pixels are transparent (0), character didn't render
        bbox = alpha.getbbox()
        return bbox is not None

    except Exception as e:
        logger.warning(f"Failed to render test for {font_path}: {e}")
        return False


def supports_character(font_path: Path, character: str, verify_render: bool = False) -> bool:
    """Check if font supports a character.

    Two-stage check:
    1. Fast cmap table lookup
    2. Optional render verification

    Args:
        font_path: Path to font file.
        character: Single Unicode character to check.
        verify_render: If True, also verify actual rendering.

    Returns:
        True if font supports the character.
    """
    # Fast check: cmap table
    if not has_glyph_in_cmap(font_path, character):
        return False

    # Optional: render verification
    if verify_render:
        return can_render_character(font_path, character)

    return True


def get_supported_characters(font_path: Path) -> set[int]:
    """Get all character codes supported by a font.

    Args:
        font_path: Path to font file.

    Returns:
        Set of Unicode code points supported by the font.
    """
    try:
        font = TTFont(str(font_path))
        cmap = font.getBestCmap()
        codes = set(cmap.keys())
        font.close()
        return codes
    except Exception as e:
        logger.warning(f"Failed to get supported characters for {font_path}: {e}")
        return set()


def find_fonts_supporting_character(font_paths: list[Path], character: str) -> list[Path]:
    """Filter fonts that support a specific character.

    Args:
        font_paths: List of font file paths.
        character: Character to check support for.

    Returns:
        List of font paths that support the character.
    """
    return [fp for fp in font_paths if supports_character(fp, character)]
