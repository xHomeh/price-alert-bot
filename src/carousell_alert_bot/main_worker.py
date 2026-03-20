from __future__ import annotations

import asyncio
import contextlib
import logging

from carousell_alert_bot.config import Settings
from carousell_alert_bot.db.session import create_session_factory
from carousell_alert_bot.providers.carousell import PlaywrightCarousellScraper
from carousell_alert_bot.providers.llm import OpenAILLMProvider
from carousell_alert_bot.providers.notifier import TelegramNotifier
from carousell_alert_bot.providers.reference_price import SerpApiReferencePriceProvider
from carousell_alert_bot.worker.runner import WatchWorker


async def async_main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    session_factory = create_session_factory(settings)
    scraper = PlaywrightCarousellScraper(
        headless=settings.playwright_headless,
        storage_state_path=settings.playwright_storage_state_path,
    )
    reference_provider = SerpApiReferencePriceProvider(api_key=settings.serpapi_api_key)
    llm_provider = OpenAILLMProvider(
        api_key=settings.openai_api_key,
        model_name=settings.openai_model,
    )
    notifier = TelegramNotifier(bot_token=settings.telegram_bot_token)

    worker = WatchWorker(
        settings=settings,
        session_factory=session_factory,
        scraper=scraper,
        reference_price_provider=reference_provider,
        llm_provider=llm_provider,
        notifier=notifier,
    )
    try:
        await worker.run_forever()
    finally:
        await worker.shutdown()
        await scraper.close()
        with contextlib.suppress(Exception):
            await notifier.close()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
