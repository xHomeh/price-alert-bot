from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from carousell_alert_bot.config import Settings
from carousell_alert_bot.providers.interfaces import (
    LLMProvider,
    Notifier,
    ReferencePriceProvider,
    ScraperProvider,
)
from carousell_alert_bot.repositories.watch_repository import WatchRepository
from carousell_alert_bot.services.scan_service import WatchScanService
from carousell_alert_bot.utils import utc_now

logger = logging.getLogger(__name__)


class WatchWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: async_sessionmaker,
        scraper: ScraperProvider,
        reference_price_provider: ReferencePriceProvider,
        llm_provider: LLMProvider,
        notifier: Notifier,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.scraper = scraper
        self.reference_price_provider = reference_price_provider
        self.llm_provider = llm_provider
        self.notifier = notifier
        self._shutdown = asyncio.Event()

    async def run_forever(self) -> None:
        while not self._shutdown.is_set():
            try:
                claimed_watch_ids = await self._claim_due_watch_ids()
                for watch_id in claimed_watch_ids:
                    await self._process_watch(watch_id)
            except Exception:
                logger.exception("Worker iteration failed")
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(),
                    timeout=self.settings.scan_loop_seconds,
                )
            except TimeoutError:
                continue

    async def _claim_due_watch_ids(self) -> list[str]:
        async with self.session_factory() as session:
            repo = WatchRepository(session)
            watches = await repo.claim_due_watches(
                limit=self.settings.scan_batch_size,
                lease_seconds=self.settings.watch_lease_seconds,
                now=utc_now(),
            )
            return [watch.id for watch in watches]

    async def _process_watch(self, watch_id: str) -> None:
        async with self.session_factory() as session:
            service = WatchScanService(
                session=session,
                settings=self.settings,
                scraper=self.scraper,
                reference_price_provider=self.reference_price_provider,
                llm_provider=self.llm_provider,
                notifier=self.notifier,
            )
            try:
                scan_run = await service.process_watch(watch_id)
            except Exception:
                logger.exception("Watch scan failed for %s", watch_id)
                return
            logger.info(
                "Processed watch %s with status=%s seen=%s evaluated=%s alerts=%s",
                watch_id,
                scan_run.status.value,
                scan_run.listings_seen,
                scan_run.listings_evaluated,
                scan_run.alerts_sent,
            )

    async def shutdown(self) -> None:
        self._shutdown.set()
