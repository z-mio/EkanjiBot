"""Centralized Chinese message templates for EkanjiBot.

This module provides all user-facing messages in Chinese to ensure
consistency and simplify maintenance. Messages are organized by category.
"""

from core.constants import MAX_TEXT_LENGTH


class ErrorMessages:
    """Error message templates."""

    NO_FONTS_AVAILABLE = "<b>暂无可用字体</b>\n\n请联系管理员添加字体文件"

    FONT_FILE_NOT_FOUND = "<b>字体文件不存在</b>\n\n请联系管理员修复"

    GENERATION_FAILED = "<b>生成失败</b>\n\n请稍后重试"

    CACHE_EXPIRED = "<b>缓存已过期</b>\n\n请重新发送"

    @staticmethod
    def text_too_long(current_length: int, max_length: int = MAX_TEXT_LENGTH) -> str:
        """Generate text-too-long error message.

        Args:
            current_length: Current text length in characters.
            max_length: Maximum allowed length.

        Returns:
            Formatted error message with HTML tags.
        """
        return (
            f"<b>文字过长</b>\n\n最多支持 <code>{max_length}</code> 个字符\n当前: <code>{current_length}</code> 个字符"
        )


class InfoMessages:
    """Informational message templates."""

    PROCESSING = "<i>⏳ 生成中...</i>"
    PROCESSING_RANDOM = "<i>⏳ 生成随机字体表情中...</i>"

    NEED_MORE_FONTS = "<b>随机字体模式需要至少2种字体</b>\n\n请添加更多字体到 assets/fonts/ 目录"


class SuccessMessages:
    """Success message templates."""

    @staticmethod
    def font_set(font_name: str) -> str:
        """Generate font-set success message.

        Args:
            font_name: Name of the selected font.

        Returns:
            Formatted success message.
        """
        return f"<b>设置成功！</b>\n\n偏好字体: <code>{font_name}</code>"


class HelpMessages:
    """Help and instruction message templates."""

    FONT_LIST_HEADER = "<b>可用字体列表</b>\n\n"
    FONT_LIST_FOOTER = "\n\n<i>使用 /sf &lt;序号&gt; 设置偏好字体</i>"

    RANDOM_FONT = """<b>🎲 随机字体模式</b>

用法: <code>/rf &lt;文字&gt;</code>

示例: <code>/rf 你好世界</code>

每个字符将随机使用一种字体"""

    @staticmethod
    def font_selected_label() -> str:
        """Generate selected font label.

        Returns:
            Label for selected font.
        """
        return "<i>(已选)</i>"


class InlineMessages:
    """Inline mode message templates."""

    BUTTON_GENERATING = "生 成 中..."

    TITLE_NORMAL = "普通发送"
    TITLE_ZWSP = "带隐形前缀发送"
    TITLE_RANDOM = "🎲 随机字体"
    TITLE_RANDOM_ZWSP = "🎲 随机字体(带前缀)"
