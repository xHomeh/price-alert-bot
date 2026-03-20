from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text

from alembic import context
from carousell_alert_bot.db import models  # noqa: F401
from carousell_alert_bot.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

raw_database_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
sync_database_url = raw_database_url.replace("+asyncpg", "+psycopg")
config.set_main_option("sqlalchemy.url", sync_database_url)
target_metadata = Base.metadata
MIGRATION_LOCK_ID = 202603210001


def run_migrations_offline() -> None:
    context.configure(
        url=sync_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            if connection.dialect.name == "postgresql":
                # Keep startup-safe when multiple containers run Alembic together.
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": MIGRATION_LOCK_ID},
                )
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
