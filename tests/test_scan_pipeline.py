from __future__ import annotations

from carousell_alert_bot.contracts import (
    ComparisonSnapshot,
    ListingSummary,
    LLMEvaluationResult,
    NotificationDelivery,
    ReferencePriceSnapshot,
    ScrapedListing,
)
from carousell_alert_bot.db.models import Alert, ListingEvaluation
from carousell_alert_bot.repositories.listing_repository import ListingRepository
from carousell_alert_bot.services.scan_service import WatchScanService
from carousell_alert_bot.services.watch_service import TelegramIdentity, WatchService
from tests.support import create_test_session_factory, make_settings, run


class FakeScraper:
    def __init__(self, *, price_cents: int = 18_000) -> None:
        self.price_cents = price_cents
        self.search_calls = 0
        self.detail_calls = 0

    async def search(self, query: str, *, region: str, limit: int) -> list[ListingSummary]:
        self.search_calls += 1
        return [
            ListingSummary(
                external_id="listing-1",
                url="https://www.carousell.sg/p/sony-wh-1000xm5-123456789",
                title="Sony WH-1000XM5 Headphones",
                price_cents=self.price_cents,
                seller_location="Bedok",
                image_url="https://images.example.com/sony-wh1000xm5-1.jpg",
                summary_hash=f"hash-{self.price_cents}",
                raw_payload={"query": query},
            )
        ]

    async def fetch_detail(self, summary: ListingSummary) -> ScrapedListing:
        self.detail_calls += 1
        return ScrapedListing(
            external_id=summary.external_id,
            url=str(summary.url),
            title=summary.title,
            description="Used lightly for two months.",
            price_cents=summary.price_cents,
            seller_name="Joel Seller",
            seller_location=summary.seller_location,
            image_urls=["https://images.example.com/sony-wh1000xm5-1.jpg"],
            summary_hash=summary.summary_hash,
            raw_payload=summary.raw_payload,
        )

    async def close(self) -> None:
        return None


class FakeReferenceProvider:
    def __init__(self, *, status: str = "ok") -> None:
        self.status = status
        self.calls = 0

    async def lookup(self, query: str) -> ReferencePriceSnapshot:
        self.calls += 1
        if self.status == "error":
            return ReferencePriceSnapshot.from_quotes(
                source="serpapi",
                status="error",
                query=query,
                quotes=[],
                error="upstream failed",
            )
        return ReferencePriceSnapshot.from_quotes(
            source="serpapi",
            status="ok",
            query=query,
            quotes=[],
        )


class FakeLLMProvider:
    def __init__(self, result: LLMEvaluationResult) -> None:
        self.result = result
        self.calls = 0

    async def evaluate_candidate(
        self,
        *,
        listing: ScrapedListing,
        user_alert_style: str,
        max_price_cents: int,
        comparison_snapshot: ComparisonSnapshot,
        reference_snapshot: ReferencePriceSnapshot,
    ) -> LLMEvaluationResult:
        self.calls += 1
        return self.result


class FakeNotifier:
    def __init__(self) -> None:
        self.calls: list[int] = []

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
        self.calls.append(telegram_user_id)
        return NotificationDelivery(status="sent", telegram_message_id=42)

    async def close(self) -> None:
        return None


def _positive_evaluation() -> LLMEvaluationResult:
    return LLMEvaluationResult(
        normalized_brand="Sony",
        normalized_model="WH-1000XM5",
        condition_grade="B",
        condition_notes="Minor wear only.",
        estimated_fair_price_min_cents=24_000,
        estimated_fair_price_max_cents=31_000,
        deal_score=92.0,
        should_alert=True,
        alert_reason="Listing is well below expected resale value.",
        confidence=0.91,
    )


def _low_confidence_evaluation() -> LLMEvaluationResult:
    return LLMEvaluationResult(
        normalized_brand="Sony",
        normalized_model="WH-1000XM5",
        condition_grade="B",
        condition_notes="Minor wear only.",
        estimated_fair_price_min_cents=24_000,
        estimated_fair_price_max_cents=31_000,
        deal_score=70.0,
        should_alert=True,
        alert_reason="Might be okay but evidence is weak.",
        confidence=0.4,
    )


def test_scan_pipeline_alerts_once_and_dedupes() -> None:
    async def scenario() -> None:
        settings = make_settings()
        session_factory, engine = await create_test_session_factory()
        try:
            async with session_factory() as session:
                service = WatchService(session, settings)
                user = await service.ensure_allowed_user(
                    TelegramIdentity(telegram_user_id=111, username="joel", full_name="Joel Tan")
                )
                watch = await service.create_watch(
                    user=user,
                    query="Sony WH-1000XM5",
                    max_price_raw="250",
                    cadence_raw="15",
                    alert_style="Only alert for exceptional deals.",
                )

            scraper = FakeScraper(price_cents=18_000)
            ref_provider = FakeReferenceProvider()
            llm_provider = FakeLLMProvider(_positive_evaluation())
            notifier = FakeNotifier()

            async with session_factory() as session:
                scan_service = WatchScanService(
                    session=session,
                    settings=settings,
                    scraper=scraper,
                    reference_price_provider=ref_provider,
                    llm_provider=llm_provider,
                    notifier=notifier,
                )
                first_run = await scan_service.process_watch(watch.id)
                assert first_run.alerts_sent == 1

            async with session_factory() as session:
                scan_service = WatchScanService(
                    session=session,
                    settings=settings,
                    scraper=scraper,
                    reference_price_provider=ref_provider,
                    llm_provider=llm_provider,
                    notifier=notifier,
                )
                second_run = await scan_service.process_watch(watch.id)
                assert second_run.alerts_sent == 0
                repo = ListingRepository(session)
                listing = await repo.get_by_external_id("listing-1")
                assert listing is not None
                assert await repo.get_existing_alert(
                    user_id=watch.user_id,
                    watch_id=watch.id,
                    listing_id=listing.id,
                ) is not None

            assert len(notifier.calls) == 1
            assert llm_provider.calls == 1
        finally:
            await engine.dispose()

    run(scenario())


def test_listing_above_threshold_skips_llm_and_alert() -> None:
    async def scenario() -> None:
        settings = make_settings()
        session_factory, engine = await create_test_session_factory()
        try:
            async with session_factory() as session:
                service = WatchService(session, settings)
                user = await service.ensure_allowed_user(
                    TelegramIdentity(telegram_user_id=111, username="joel", full_name="Joel Tan")
                )
                watch = await service.create_watch(
                    user=user,
                    query="Sony WH-1000XM5",
                    max_price_raw="200",
                    cadence_raw="15",
                    alert_style="Only alert for exceptional deals.",
                )

            scraper = FakeScraper(price_cents=28_000)
            ref_provider = FakeReferenceProvider()
            llm_provider = FakeLLMProvider(_positive_evaluation())
            notifier = FakeNotifier()

            async with session_factory() as session:
                scan_service = WatchScanService(
                    session=session,
                    settings=settings,
                    scraper=scraper,
                    reference_price_provider=ref_provider,
                    llm_provider=llm_provider,
                    notifier=notifier,
                )
                scan_run = await scan_service.process_watch(watch.id)
                assert scan_run.alerts_sent == 0
                assert llm_provider.calls == 0
                alerts = (await session.execute(Alert.__table__.select())).all()
                assert alerts == []
        finally:
            await engine.dispose()

    run(scenario())


def test_low_confidence_or_reference_failure_does_not_crash_pipeline() -> None:
    async def scenario() -> None:
        settings = make_settings()
        session_factory, engine = await create_test_session_factory()
        try:
            async with session_factory() as session:
                service = WatchService(session, settings)
                user = await service.ensure_allowed_user(
                    TelegramIdentity(telegram_user_id=111, username="joel", full_name="Joel Tan")
                )
                watch = await service.create_watch(
                    user=user,
                    query="Sony WH-1000XM5",
                    max_price_raw="250",
                    cadence_raw="15",
                    alert_style="Slightly good deals are fine.",
                )

            scraper = FakeScraper(price_cents=18_000)
            ref_provider = FakeReferenceProvider(status="error")
            llm_provider = FakeLLMProvider(_low_confidence_evaluation())
            notifier = FakeNotifier()

            async with session_factory() as session:
                scan_service = WatchScanService(
                    session=session,
                    settings=settings,
                    scraper=scraper,
                    reference_price_provider=ref_provider,
                    llm_provider=llm_provider,
                    notifier=notifier,
                )
                scan_run = await scan_service.process_watch(watch.id)
                assert scan_run.status.value == "success"
                assert scan_run.alerts_sent == 0
                evaluations = (await session.execute(ListingEvaluation.__table__.select())).all()
                assert len(evaluations) == 1
                alerts = (await session.execute(Alert.__table__.select())).all()
                assert alerts == []
        finally:
            await engine.dispose()

    run(scenario())
