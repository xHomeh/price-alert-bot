from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from carousell_alert_bot.db.models import Watch, WatchStatus


def dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Add watch", callback_data="watch:add")],
            [InlineKeyboardButton(text="List watches", callback_data="watch:list")],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Cancel", callback_data="flow:cancel")]]
    )


def watch_actions_keyboard(watch: Watch) -> InlineKeyboardMarkup:
    status_button = (
        InlineKeyboardButton(text="Pause", callback_data=f"watch:pause:{watch.id}")
        if watch.status == WatchStatus.ACTIVE
        else InlineKeyboardButton(text="Resume", callback_data=f"watch:resume:{watch.id}")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                status_button,
                InlineKeyboardButton(text="Cadence", callback_data=f"watch:cadence:{watch.id}"),
            ],
            [
                InlineKeyboardButton(text="Style", callback_data=f"watch:style:{watch.id}"),
                InlineKeyboardButton(text="Delete", callback_data=f"watch:delete:{watch.id}"),
            ],
        ]
    )

