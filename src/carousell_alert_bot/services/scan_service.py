from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from carousell_alert_bot.config import Settings
from carousell_alert_bot.contracts import ScrapedListing
from carousell_alert_bot.db.models import ScanRun, ScanRunStatus, Watch
from carousell_alert_bot.providers.interfaces import (
    LLMProvider,
    Notifier,
    ReferencePriceProvider,
    ScraperProvider,
)
from carousell_alert_bot.repositories.listing_repository import ListingRepository
from carousell_alert_bot.repositories.watch_repository import WatchRepository
from carousell_alert_bot.services.comps import ComparisonService
from carousell_alert_bot.utils import next_scan_at, utc_now


class WatchScanService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        scraper: ScraperProvider,
        reference_price_provider: ReferencePriceProvider,
        llm_provider: LLMProvider,
        notifier: Notifier,
    ) -> None:
        self.session = session
        self.settings = settings
        self.scraper = scraper
        self.reference_price_provider = reference_price_provider
        self.llm_provider = llm_provider
        self.notifier = notifier
        self.watch_repo = WatchRepository(session)
        self.listing_repo = ListingRepository(session)
        self.comparison_service = ComparisonService(session)

    async def process_watch(self, watch_id: str) -> ScanRun:
        watch = await self.watch_repo.get_by_id(watch_id)
        if watch is None:
            raise ValueError(f"Watch {watch_id} was not found.")

        now = utc_now()
        scan_run = ScanRun(
            watch_id=watch.id,
            status=ScanRunStatus.STARTED,
            started_at=now,
            metadata_json={"query": watch.query},
        )
        self.session.add(scan_run)
        await self.session.flush()

        listings_seen = 0
        listings_evaluated = 0
        alerts_sent = 0

        try:
            summaries = await self.scraper.search(
                watch.query,
                region=watch.region,
                limit=self.settings.listing_scan_limit,
            )
            listings_seen = len(summaries)
            for summary in summaries:
                listing = await self.listing_repo.get_by_external_id(summary.external_id)
                needs_refresh = listing is None or listing.summary_hash != summary.summary_hash
                if needs_refresh:
                    scraped_listing = await self.scraper.fetch_detail(summary)
                    listing = await self.listing_repo.upsert_from_scraped(scraped_listing)
                elif listing is not None:
                    scraped_listing = self.listing_repo.listing_to_scraped(listing)
                else:
                    continue

                evaluated, sent_alert = await self._evaluate_and_notify(
                    watch=watch,
                    listing=listing,
                    scraped_listing=scraped_listing,
                    skip_if_existing=not needs_refresh,
                )
                listings_evaluated += int(evaluated)
                alerts_sent += sent_alert

            scan_run.status = ScanRunStatus.SUCCESS
            scan_run.error_message = None
        except Exception as exc:
            scan_run.status = ScanRunStatus.FAILED
            scan_run.error_message = str(exc)
            watch.last_scan_error = str(exc)
            raise
        finally:
            finished_at = utc_now()
            watch.last_scanned_at = finished_at
            watch.leased_until = None
            watch.next_scan_at = next_scan_at(watch.cadence_minutes, from_time=finished_at)
            scan_run.finished_at = finished_at
            scan_run.listings_seen = listings_seen
            scan_run.listings_evaluated = listings_evaluated
            scan_run.alerts_sent = alerts_sent
            if scan_run.status == ScanRunStatus.SUCCESS:
                watch.last_scan_error = None
            await self.session.commit()

        return scan_run

    async def _evaluate_and_notify(
        self,
        *,
        watch: Watch,
        listing,
        scraped_listing: ScrapedListing,
        skip_if_existing: bool,
    ) -> tuple[bool, int]:
        if listing.price_cents > watch.max_price_cents:
            return False, 0

        existing_evaluation = await self.listing_repo.get_evaluation(watch.id, listing.id)
        if existing_evaluation is not None and skip_if_existing:
            return False, 0

        comparison_snapshot = await self.comparison_service.build_snapshot(
            watch=watch,
            exclude_listing_id=listing.id,
        )
        reference_snapshot = await self.reference_price_provider.lookup(scraped_listing.title)
        evaluation = await self.llm_provider.evaluate_candidate(
            listing=scraped_listing,
            user_alert_style=watch.alert_style,
            max_price_cents=watch.max_price_cents,
            comparison_snapshot=comparison_snapshot,
            reference_snapshot=reference_snapshot,
        )
        evaluation_record = await self.listing_repo.upsert_evaluation(
            watch=watch,
            listing=listing,
            evaluation=evaluation,
            comparison_snapshot=comparison_snapshot,
            reference_snapshot=reference_snapshot,
            model_name=self.settings.openai_model,
        )

        if not (
            evaluation.should_alert
            and evaluation.confidence >= self.settings.min_confidence_to_alert
        ):
            return True, 0

        existing_alert = await self.listing_repo.get_existing_alert(
            user_id=watch.user_id,
            watch_id=watch.id,
            listing_id=listing.id,
        )
        if existing_alert is not None:
            return True, 0

        try:
            delivery = await self.notifier.send_deal_alert(
                telegram_user_id=watch.user.telegram_user_id,
                watch_query=watch.query,
                watch_max_price_cents=watch.max_price_cents,
                listing=scraped_listing,
                evaluation=evaluation,
                reference_snapshot=reference_snapshot,
            )
            await self.listing_repo.create_alert(
                user_id=watch.user_id,
                watch_id=watch.id,
                listing_id=listing.id,
                evaluation_id=evaluation_record.id,
                telegram_chat_id=watch.user.telegram_user_id,
                telegram_message_id=delivery.telegram_message_id,
                status=delivery.status,
            )
            return True, 1
        except Exception as exc:
            await self.listing_repo.create_alert(
                user_id=watch.user_id,
                watch_id=watch.id,
                listing_id=listing.id,
                evaluation_id=evaluation_record.id,
                telegram_chat_id=watch.user.telegram_user_id,
                telegram_message_id=None,
                status="failed",
                error_message=str(exc),
            )
            return True, 0
