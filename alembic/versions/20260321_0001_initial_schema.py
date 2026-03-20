"""Initial schema for the Carousell price alert bot."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260321_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    watch_status = postgresql.ENUM(
        "active",
        "paused",
        "deleted",
        name="watch_status",
        create_type=False,
    )
    scan_run_status = postgresql.ENUM(
        "started",
        "success",
        "failed",
        name="scan_run_status",
        create_type=False,
    )
    watch_status.create(op.get_bind(), checkfirst=True)
    scan_run_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_allowed", sa.Boolean(), nullable=False),
        sa.Column("onboarding_complete", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )

    op.create_table(
        "watches",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("query", sa.String(length=255), nullable=False),
        sa.Column("normalized_query", sa.String(length=255), nullable=False),
        sa.Column("max_price_cents", sa.Integer(), nullable=False),
        sa.Column("cadence_minutes", sa.Integer(), nullable=False),
        sa.Column("alert_style", sa.Text(), nullable=False),
        sa.Column("region", sa.String(length=8), nullable=False),
        sa.Column("status", watch_status, nullable=False),
        sa.Column("next_scan_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scan_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_watches_normalized_query", "watches", ["normalized_query"], unique=False)
    op.create_index(
        "ix_watches_due",
        "watches",
        ["status", "next_scan_at", "leased_until"],
        unique=False,
    )

    op.create_table(
        "scan_runs",
        sa.Column("watch_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("status", scan_run_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("listings_seen", sa.Integer(), nullable=False),
        sa.Column("listings_evaluated", sa.Integer(), nullable=False),
        sa.Column("alerts_sent", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["watch_id"], ["watches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "listings",
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("normalized_title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("seller_name", sa.String(length=255), nullable=True),
        sa.Column("seller_location", sa.String(length=255), nullable=True),
        sa.Column("listed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )

    op.create_table(
        "listing_images",
        sa.Column("listing_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("cached_path", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_id", "position", name="uq_listing_images_position"),
    )

    op.create_table(
        "listing_evaluations",
        sa.Column("watch_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("listing_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("normalized_brand", sa.String(length=255), nullable=True),
        sa.Column("normalized_model", sa.String(length=255), nullable=True),
        sa.Column("condition_grade", sa.String(length=64), nullable=False),
        sa.Column("condition_notes", sa.Text(), nullable=False),
        sa.Column("estimated_fair_price_min_cents", sa.Integer(), nullable=False),
        sa.Column("estimated_fair_price_max_cents", sa.Integer(), nullable=False),
        sa.Column("deal_score", sa.Float(), nullable=False),
        sa.Column("should_alert", sa.Boolean(), nullable=False),
        sa.Column("alert_reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("comp_snapshot", sa.JSON(), nullable=False),
        sa.Column("reference_price_snapshot", sa.JSON(), nullable=False),
        sa.Column("llm_output", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["watch_id"], ["watches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("watch_id", "listing_id", name="uq_evaluation_watch_listing"),
    )

    op.create_table(
        "alerts",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("watch_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("listing_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("evaluation_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_id"], ["listing_evaluations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["watch_id"], ["watches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "watch_id", "listing_id", name="uq_alert_dedup"),
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("listing_evaluations")
    op.drop_table("listing_images")
    op.drop_table("listings")
    op.drop_table("scan_runs")
    op.drop_index("ix_watches_due", table_name="watches")
    op.drop_index("ix_watches_normalized_query", table_name="watches")
    op.drop_table("watches")
    op.drop_table("users")

    postgresql.ENUM(
        "started",
        "success",
        "failed",
        name="scan_run_status",
        create_type=False,
    ).drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(
        "active",
        "paused",
        "deleted",
        name="watch_status",
        create_type=False,
    ).drop(op.get_bind(), checkfirst=True)
