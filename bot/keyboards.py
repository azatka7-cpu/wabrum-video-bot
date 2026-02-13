"""Inline keyboards for the Telegram bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def video_approval_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown under a newly generated video."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{task_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{task_id}"),
        ],
        [
            InlineKeyboardButton("🔄 Перегенерировать", callback_data=f"regenerate_{task_id}"),
            InlineKeyboardButton("ℹ️ Подробнее", callback_data=f"details_{task_id}"),
        ],
    ])


def approved_video_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown after a video is approved."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📤 Опубликовать сейчас", callback_data=f"publish_{task_id}"
            )
        ]
    ])
