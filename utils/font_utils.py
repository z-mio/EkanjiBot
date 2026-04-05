"""Font resolution utilities for EkanjiBot."""

from db.models.font import Font
from db.models.user import User
from db.repositories.font_repo import FontRepository


async def get_user_font(
    db_user: User,
    fonts: list[Font],
    font_repo: FontRepository,
) -> tuple[Font, bool]:
    """Get font for user based on preference and availability.

    Priority: user's preferred font if set and available, otherwise first available font.

    Returns:
        Tuple of (font_to_use, is_preferred) where is_preferred indicates
        if using user's preferred font.
    """
    if db_user.preferred_font_id:
        for font in fonts:
            if font.id == db_user.preferred_font_id:
                return font, True

        preferred_font = await font_repo.get_by_id(db_user.preferred_font_id)
        if preferred_font and preferred_font.is_active:
            return preferred_font, True

    return fonts[0], False
