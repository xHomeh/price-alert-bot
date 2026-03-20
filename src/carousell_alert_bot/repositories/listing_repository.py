from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from carousell_alert_bot.contracts import (
    ComparisonSnapshot,
    LLMEvaluationResult,
    ReferencePriceSnapshot,
    ScrapedListing,
)
from carousell_alert_bot.db.models import Alert, Listing, ListingEvaluation, ListingImage, Watch
from carousell_alert_bot.utils import normalize_query, utc_now


class ListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_external_id(self, external_id: str) -> Listing | None:
        result = await self.session.execute(
            select(Listing)
            .options(selectinload(Listing.images))
            .where(Listing.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def upsert_from_scraped(self, scraped: ScrapedListing) -> Listing:
        image_records = [
            ListingImage(url=str(image_url), position=index)
            for index, image_url in enumerate(scraped.image_urls)
        ]
        listing = await self.get_by_external_id(scraped.external_id)
        if listing is None:
            listing = Listing(
                external_id=scraped.external_id,
                source="carousell_sg",
                url=str(scraped.url),
                title=scraped.title,
                normalized_title=normalize_query(scraped.title),
                description=scraped.description,
                price_cents=scraped.price_cents,
                currency=scraped.currency,
                seller_name=scraped.seller_name,
                seller_location=scraped.seller_location,
                listed_at=scraped.listed_at,
                scraped_at=utc_now(),
                summary_hash=scraped.summary_hash,
                raw_payload=scraped.raw_payload,
                images=image_records,
            )
            self.session.add(listing)
            await self.session.flush()
        else:
            listing.url = str(scraped.url)
            listing.title = scraped.title
            listing.normalized_title = normalize_query(scraped.title)
            listing.description = scraped.description
            listing.price_cents = scraped.price_cents
            listing.currency = scraped.currency
            listing.seller_name = scraped.seller_name
            listing.seller_location = scraped.seller_location
            listing.listed_at = scraped.listed_at
            listing.scraped_at = utc_now()
            listing.summary_hash = scraped.summary_hash
            listing.raw_payload = scraped.raw_payload

            await self.session.execute(
                delete(ListingImage).where(ListingImage.listing_id == listing.id)
            )
            listing.images = image_records

        await self.session.flush()
        return listing

    async def get_evaluation(self, watch_id: str, listing_id: str) -> ListingEvaluation | None:
        result = await self.session.execute(
            select(ListingEvaluation).where(
                ListingEvaluation.watch_id == watch_id,
                ListingEvaluation.listing_id == listing_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_evaluation(
        self,
        *,
        watch: Watch,
        listing: Listing,
        evaluation: LLMEvaluationResult,
        comparison_snapshot: ComparisonSnapshot,
        reference_snapshot: ReferencePriceSnapshot,
        model_name: str,
    ) -> ListingEvaluation:
        record = await self.get_evaluation(watch.id, listing.id)
        payload = evaluation.model_dump()
        if record is None:
            record = ListingEvaluation(
                watch_id=watch.id,
                listing_id=listing.id,
                normalized_brand=evaluation.normalized_brand,
                normalized_model=evaluation.normalized_model,
                condition_grade=evaluation.condition_grade,
                condition_notes=evaluation.condition_notes,
                estimated_fair_price_min_cents=evaluation.estimated_fair_price_min_cents,
                estimated_fair_price_max_cents=evaluation.estimated_fair_price_max_cents,
                deal_score=evaluation.deal_score,
                should_alert=evaluation.should_alert,
                alert_reason=evaluation.alert_reason,
                confidence=evaluation.confidence,
                comp_snapshot=comparison_snapshot.model_dump(),
                reference_price_snapshot=reference_snapshot.model_dump(),
                llm_output=payload,
                model_name=model_name,
            )
            self.session.add(record)
        else:
            record.normalized_brand = evaluation.normalized_brand
            record.normalized_model = evaluation.normalized_model
            record.condition_grade = evaluation.condition_grade
            record.condition_notes = evaluation.condition_notes
            record.estimated_fair_price_min_cents = evaluation.estimated_fair_price_min_cents
            record.estimated_fair_price_max_cents = evaluation.estimated_fair_price_max_cents
            record.deal_score = evaluation.deal_score
            record.should_alert = evaluation.should_alert
            record.alert_reason = evaluation.alert_reason
            record.confidence = evaluation.confidence
            record.comp_snapshot = comparison_snapshot.model_dump()
            record.reference_price_snapshot = reference_snapshot.model_dump()
            record.llm_output = payload
            record.model_name = model_name

        await self.session.flush()
        return record

    async def get_existing_alert(
        self,
        *,
        user_id: str,
        watch_id: str,
        listing_id: str,
    ) -> Alert | None:
        result = await self.session.execute(
            select(Alert).where(
                Alert.user_id == user_id,
                Alert.watch_id == watch_id,
                Alert.listing_id == listing_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_alert(
        self,
        *,
        user_id: str,
        watch_id: str,
        listing_id: str,
        evaluation_id: str | None,
        telegram_chat_id: int,
        telegram_message_id: int | None,
        status: str,
        error_message: str | None = None,
    ) -> Alert:
        alert = Alert(
            user_id=user_id,
            watch_id=watch_id,
            listing_id=listing_id,
            evaluation_id=evaluation_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            status=status,
            error_message=error_message,
            sent_at=utc_now(),
        )
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def prices_for_watch(
        self,
        *,
        watch_id: str,
        exclude_listing_id: str | None = None,
    ) -> list[int]:
        stmt = (
            select(Listing.price_cents)
            .join(ListingEvaluation, ListingEvaluation.listing_id == Listing.id)
            .where(ListingEvaluation.watch_id == watch_id)
        )
        if exclude_listing_id:
            stmt = stmt.where(Listing.id != exclude_listing_id)
        result = await self.session.execute(stmt)
        return [price for price in result.scalars().all() if price is not None]

    async def prices_for_normalized_query(
        self,
        *,
        normalized_query: str,
        exclude_listing_id: str | None = None,
    ) -> list[int]:
        stmt = (
            select(Listing.price_cents)
            .join(ListingEvaluation, ListingEvaluation.listing_id == Listing.id)
            .join(Watch, Watch.id == ListingEvaluation.watch_id)
            .where(Watch.normalized_query == normalized_query)
        )
        if exclude_listing_id:
            stmt = stmt.where(Listing.id != exclude_listing_id)
        result = await self.session.execute(stmt)
        return [price for price in result.scalars().all() if price is not None]

    @staticmethod
    def listing_to_scraped(listing: Listing) -> ScrapedListing:
        return ScrapedListing(
            external_id=listing.external_id,
            url=listing.url,
            title=listing.title,
            description=listing.description,
            price_cents=listing.price_cents,
            currency=listing.currency,
            seller_name=listing.seller_name,
            seller_location=listing.seller_location,
            listed_at=listing.listed_at,
            image_urls=[image.url for image in listing.images],
            summary_hash=listing.summary_hash,
            raw_payload=listing.raw_payload,
        )

    async def load_many_by_external_ids(self, external_ids: Sequence[str]) -> list[Listing]:
        if not external_ids:
            return []
        result = await self.session.execute(
            select(Listing)
            .options(selectinload(Listing.images))
            .where(Listing.external_id.in_(list(external_ids)))
        )
        return list(result.scalars().all())
