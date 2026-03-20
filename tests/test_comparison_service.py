from __future__ import annotations

from carousell_alert_bot.db.models import Listing, ListingEvaluation, User, Watch, WatchStatus
from carousell_alert_bot.services.comps import ComparisonService
from carousell_alert_bot.utils import normalize_query, utc_now
from tests.support import create_test_session_factory, run


def test_comparison_snapshot_aggregates_same_watch_and_same_query() -> None:
    async def scenario() -> None:
        session_factory, engine = await create_test_session_factory()
        try:
            async with session_factory() as session:
                user = User(
                    telegram_user_id=111,
                    username="joel",
                    full_name="Joel",
                    is_admin=True,
                    is_allowed=True,
                    onboarding_complete=True,
                )
                watch_a = Watch(
                    user=user,
                    query="Sony XM5",
                    normalized_query=normalize_query("Sony XM5"),
                    max_price_cents=30_000,
                    cadence_minutes=15,
                    alert_style="Only alert for great deals.",
                    region="SG",
                    status=WatchStatus.ACTIVE,
                    next_scan_at=utc_now(),
                )
                watch_b = Watch(
                    user=user,
                    query="Sony XM5",
                    normalized_query=normalize_query("Sony XM5"),
                    max_price_cents=30_000,
                    cadence_minutes=30,
                    alert_style="Any good deal is fine.",
                    region="SG",
                    status=WatchStatus.ACTIVE,
                    next_scan_at=utc_now(),
                )
                listing_one = Listing(
                    external_id="1",
                    url="https://www.carousell.sg/p/1",
                    title="Sony XM5 one",
                    normalized_title=normalize_query("Sony XM5 one"),
                    description="Listing one",
                    price_cents=20_000,
                    currency="SGD",
                    scraped_at=utc_now(),
                    summary_hash="hash-1",
                    raw_payload={},
                )
                listing_two = Listing(
                    external_id="2",
                    url="https://www.carousell.sg/p/2",
                    title="Sony XM5 two",
                    normalized_title=normalize_query("Sony XM5 two"),
                    description="Listing two",
                    price_cents=24_000,
                    currency="SGD",
                    scraped_at=utc_now(),
                    summary_hash="hash-2",
                    raw_payload={},
                )
                listing_three = Listing(
                    external_id="3",
                    url="https://www.carousell.sg/p/3",
                    title="Sony XM5 three",
                    normalized_title=normalize_query("Sony XM5 three"),
                    description="Listing three",
                    price_cents=28_000,
                    currency="SGD",
                    scraped_at=utc_now(),
                    summary_hash="hash-3",
                    raw_payload={},
                )
                session.add_all([user, watch_a, watch_b, listing_one, listing_two, listing_three])
                await session.flush()
                session.add_all(
                    [
                        ListingEvaluation(
                            watch_id=watch_a.id,
                            listing_id=listing_one.id,
                            normalized_brand="Sony",
                            normalized_model="XM5",
                            condition_grade="B",
                            condition_notes="Good",
                            estimated_fair_price_min_cents=22_000,
                            estimated_fair_price_max_cents=26_000,
                            deal_score=80,
                            should_alert=True,
                            alert_reason="Good value",
                            confidence=0.8,
                            comp_snapshot={},
                            reference_price_snapshot={},
                            llm_output={},
                            model_name="gpt-5.2",
                        ),
                        ListingEvaluation(
                            watch_id=watch_a.id,
                            listing_id=listing_two.id,
                            normalized_brand="Sony",
                            normalized_model="XM5",
                            condition_grade="B",
                            condition_notes="Good",
                            estimated_fair_price_min_cents=22_000,
                            estimated_fair_price_max_cents=26_000,
                            deal_score=75,
                            should_alert=False,
                            alert_reason="Average",
                            confidence=0.8,
                            comp_snapshot={},
                            reference_price_snapshot={},
                            llm_output={},
                            model_name="gpt-5.2",
                        ),
                        ListingEvaluation(
                            watch_id=watch_b.id,
                            listing_id=listing_three.id,
                            normalized_brand="Sony",
                            normalized_model="XM5",
                            condition_grade="A",
                            condition_notes="Great",
                            estimated_fair_price_min_cents=24_000,
                            estimated_fair_price_max_cents=29_000,
                            deal_score=78,
                            should_alert=False,
                            alert_reason="Decent",
                            confidence=0.8,
                            comp_snapshot={},
                            reference_price_snapshot={},
                            llm_output={},
                            model_name="gpt-5.2",
                        ),
                    ]
                )
                await session.commit()

            async with session_factory() as session:
                snapshot = await ComparisonService(session).build_snapshot(watch=watch_a)
                assert snapshot.same_watch.sample_size == 2
                assert snapshot.same_watch.median_price_cents == 22_000
                assert snapshot.same_query.sample_size == 3
                assert snapshot.same_query.max_price_cents == 28_000
        finally:
            await engine.dispose()

    run(scenario())

