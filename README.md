# Football Draft League

Multi-competition friends draft platform (Premier League 2026-27 first).

## Stack

- `frontend/` — Next.js (App Router) + TypeScript
- `backend/` — Python FastAPI
- `supabase/` — Postgres migrations
- Auth via Supabase (magic link, password, social/OAuth)
- Football data via football-data.org (server-side only)

## Local setup

### Prerequisites

- Node.js 20+
- Python 3.12+
- Supabase CLI (optional for local Auth/Postgres) or a hosted Supabase project

### Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env
# Fill in secrets in ../.env
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Database

Apply migrations in `supabase/migrations/` to your Supabase Postgres (SQL editor or `supabase db push`).

Seed the PL competition template:

```bash
cd backend
python -m app.scripts.seed_pl_template
```

### Sync cron (external)

Hit the secured endpoint on a schedule (GitHub Actions is a good fit):

```bash
curl -X POST "$API_URL/internal/sync-and-score" \
  -H "X-Cron-Secret: $CRON_SECRET"
```

Manual commissioner sync: `POST /leagues/{league_id}/sync` with a JWT.

## Project layout

```
football-draft-league/
  frontend/     Next.js UI
  backend/      FastAPI API + scoring + sync
  supabase/     SQL migrations
  .env.example
  README.md
```

## Identity convention

Every table has:

- `id` — bigint primary key (internal)
- `public_id` — UUID unique index (API / frontend only)

## Deploy

Hosting is deferred; wire via GitHub Actions when ready. Nothing in the codebase hardcodes a host.
