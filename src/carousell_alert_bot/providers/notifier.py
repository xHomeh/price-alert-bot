from __future__ import annotations

from carousell_alert_bot.contracts import (
    LLMEvaluationResult,
    NotificationDelivery,
    ReferencePriceSnapshot,
    ScrapedListing,
)
from carousell_alert_bot.utils import format_sgd


class TelegramNotifier:
    def __init__(self, *, bot_token: str) -> None:
        self.bot_token = bot_token
        self._bot = None

    async def _get_bot(self):
        if self._bot is not None:
            return self._bot
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode

        self._bot = Bot(
            token=self.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        return self._bot

    async def send_deal_alert(
        self,
        *,
        telegram_user_id: int,
        watch_query: str,
        watch_max_price_cents: int,
        listing: ScrapedListing,
        evaluation: LLMEvaluationResult,
        reference_snapshot: ReferencePriceSnapshot,
    ) -> NotificationDelivery:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        bot = await self._get_bot()
        reference_hint = (
            format_sgd(reference_snapshot.median_price_cents)
            if reference_snapshot.median_price_cents
            else "N/A"
        )
        text = (
            "<b>Deal alert</b>\n"
            f"<b>Query:</b> {watch_query}\n"
            f"<b>Listing:</b> {listing.title}\n"
            f"<b>Price:</b> {format_sgd(listing.price_cents)}"
            f" (watch max {format_sgd(watch_max_price_cents)})\n"
            f"<b>Condition:</b> {evaluation.condition_grade}\n"
            f"<b>Score:</b> {evaluation.deal_score:.1f} / 100\n"
            f"<b>Reference median:</b> {reference_hint}\n"
            f"<b>Reason:</b> {evaluation.alert_reason}"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Open listing", url=str(listing.url))]
            ]
        )
        message = await bot.send_message(
            chat_id=telegram_user_id,
            text=text,
            reply_markup=keyboard,
            disable_web_page_preview=False,
        )
        return NotificationDelivery(
            status="sent",
            telegram_message_id=message.message_id,
            raw_payload={"chat_id": telegram_user_id},
        )

    async def close(self) -> None:
        if self._bot is None:
            return
        await self._bot.session.close()
        self._bot = None

