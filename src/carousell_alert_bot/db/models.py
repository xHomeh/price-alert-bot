from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from carousell_alert_bot.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WatchStatus(enum.StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class ScanRunStatus(enum.StrEnum):
    STARTED = "started"
    SUCCESS = "success"
    FAILED = "failed"


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    watches: Mapped[list[Watch]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[list[Alert]] = relationship(back_populates="user")


class Watch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "watches"
    __table_args__ = (Index("ix_watches_due", "status", "next_scan_at", "leased_until"),)

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    query: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_query: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    max_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    cadence_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_style: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str] = mapped_column(String(8), default="SG", nullable=False)
    status: Mapped[WatchStatus] = mapped_column(
        Enum(WatchStatus, name="watch_status", values_callable=enum_values),
        default=WatchStatus.ACTIVE,
        nullable=False,
    )
    next_scan_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scan_error: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="watches")
    scan_runs: Mapped[list[ScanRun]] = relationship(
        back_populates="watch",
        cascade="all, delete-orphan",
    )
    evaluations: Mapped[list[ListingEvaluation]] = relationship(back_populates="watch")
    alerts: Mapped[list[Alert]] = relationship(back_populates="watch")


class ScanRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scan_runs"

    watch_id: Mapped[str] = mapped_column(
        ForeignKey("watches.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[ScanRunStatus] = mapped_column(
        Enum(ScanRunStatus, name="scan_run_status", values_callable=enum_values),
        default=ScanRunStatus.STARTED,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    listings_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listings_evaluated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alerts_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    watch: Mapped[Watch] = relationship(back_populates="scan_runs")


class Listing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "listings"

    external_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="carousell_sg", nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="SGD", nullable=False)
    seller_name: Mapped[str | None] = mapped_column(String(255))
    seller_location: Mapped[str | None] = mapped_column(String(255))
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    images: Mapped[list[ListingImage]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        order_by="ListingImage.position",
    )
    evaluations: Mapped[list[ListingEvaluation]] = relationship(back_populates="listing")
    alerts: Mapped[list[Alert]] = relationship(back_populates="listing")


class ListingImage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "listing_images"
    __table_args__ = (
        UniqueConstraint("listing_id", "position", name="uq_listing_images_position"),
    )

    listing_id: Mapped[str] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_path: Mapped[str | None] = mapped_column(Text)

    listing: Mapped[Listing] = relationship(back_populates="images")


class ListingEvaluation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "listing_evaluations"
    __table_args__ = (
        UniqueConstraint("watch_id", "listing_id", name="uq_evaluation_watch_listing"),
    )

    watch_id: Mapped[str] = mapped_column(
        ForeignKey("watches.id", ondelete="CASCADE"),
        nullable=False,
    )
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    normalized_brand: Mapped[str | None] = mapped_column(String(255))
    normalized_model: Mapped[str | None] = mapped_column(String(255))
    condition_grade: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_notes: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_fair_price_min_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_fair_price_max_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    deal_score: Mapped[float] = mapped_column(Float, nullable=False)
    should_alert: Mapped[bool] = mapped_column(Boolean, nullable=False)
    alert_reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    comp_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reference_price_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    llm_output: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)

    watch: Mapped[Watch] = relationship(back_populates="evaluations")
    listing: Mapped[Listing] = relationship(back_populates="evaluations")
    alerts: Mapped[list[Alert]] = relationship(back_populates="evaluation")


class Alert(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("user_id", "watch_id", "listing_id", name="uq_alert_dedup"),
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    watch_id: Mapped[str] = mapped_column(
        ForeignKey("watches.id", ondelete="CASCADE"),
        nullable=False,
    )
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("listing_evaluations.id", ondelete="SET NULL")
    )
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32), default="sent", nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="alerts")
    watch: Mapped[Watch] = relationship(back_populates="alerts")
    listing: Mapped[Listing] = relationship(back_populates="alerts")
    evaluation: Mapped[ListingEvaluation] = relationship(back_populates="alerts")
