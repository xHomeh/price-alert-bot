# Carousell Price Alert Bot

Python app that scans Carousell Singapore listings, evaluates deals with an LLM, and sends immediate Telegram alerts when a listing matches a user's watch and quality threshold.

## What It Includes

- Multi-user Telegram bot with allowlist access control
- Slash commands and guided button flows for watch management
- Async worker that claims due watches from Postgres with a lease pattern
- Playwright-based Carousell scraper with an extension point for optional authenticated sessions
- Reference-price lookup provider using SerpAPI
- OpenAI-backed single-call evaluation step for deal scoring
- Postgres storage for watches, listings, evaluations, scan runs, and alert deduplication
- Docker Compose stack for `bot`, `worker`, and `postgres`
- Alembic migration and automated tests

## Architecture

### Services

- `bot`: Telegram long-polling process for onboarding and watch management
- `worker`: scheduler and scan pipeline
- `postgres`: persistent database

### Scan flow

1. A user creates a watch in Telegram with a search query, max price, cadence, and natural-language alert style.
2. The worker claims due watches from Postgres.
3. Playwright scrapes Carousell search results and fetches detail pages for new or changed listings.
4. The worker computes comparable prices from historical data in Postgres.
5. The reference-price provider fetches public retail hints from SerpAPI.
6. One OpenAI call evaluates the listing and returns structured JSON.
7. The app stores the listing, evaluation, and alert history, then notifies the user if the deal clears the confidence and alert thresholds.

## Project Layout

```text
src/carousell_alert_bot/
  bot/           Telegram handlers and FSM flows
  db/            SQLAlchemy models and session helpers
  providers/     Playwright, SerpAPI, OpenAI, Telegram notifier
  repositories/  Database access layer
  services/      Watch management and scan orchestration
  worker/        Worker loop
alembic/         Database migration
tests/           Parser, service, and pipeline coverage
```

## Environment

Copy `.env.example` to `.env` and fill in the secrets:

```env
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/carousell_alert_bot
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.2
SERPAPI_API_KEY=...
ALLOWED_TELEGRAM_IDS=123456789
ADMIN_TELEGRAM_IDS=123456789
```

Important notes:

- `ALLOWED_TELEGRAM_IDS` and `ADMIN_TELEGRAM_IDS` are comma-separated Telegram numeric IDs.
- `PLAYWRIGHT_STORAGE_STATE_PATH` is optional. Mount a saved Playwright storage state there if you want to extend scraping with an authenticated session later.
- Prices are stored in integer cents and the app is currently Singapore-only.

## Running Locally

### With `uv`

```bash
uv sync --extra dev
cp .env.example .env
alembic upgrade head
uv run carousell-bot
```

In another shell:

```bash
uv run carousell-worker
```

### With Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

## Telegram Commands

- `/start` - open the dashboard
- `/add` - start the guided create-watch flow
- `/list` - list and manage active watches
- `/pause <id>` - pause a watch
- `/resume <id>` - resume a watch
- `/delete <id>` - delete a watch
- `/cadence <id> <minutes>` - update scan frequency
- `/style <id> <text>` - update the natural-language alert preference
- `/cancel` - cancel the active guided flow

The watch ID shown in Telegram is a short UUID prefix.

## Development Checks

```bash
uv run pytest
uv run ruff check
```

## Current Limits

- The scraper targets public Carousell pages first and relies on page structure staying reasonably stable.
- Reference-price discovery is only as strong as the upstream search results returned by SerpAPI.
- The OpenAI provider expects the model to return strict JSON and validates the result before saving it.
