# Midtable

Invite-only platform for running multi-pool football draft leagues: create a league from a competition template, invite managers, draft clubs, sync fixtures, and score standings with upsets, bonuses, and phase-based payouts.

## Stack

| Layer | Tech |
| --- | --- |
| API | FastAPI, SQLAlchemy 2, Pydantic Settings |
| App | Next.js 15, React 19, Tailwind CSS 4 |
| Auth / DB | Supabase Auth + Postgres |
| Fixtures | [football-data.org](https://www.football-data.org/) API |

Python **3.12+**, Node **20+**.

## What’s in the box

- **Competition templates** — reusable rules (draft style, roster slots, pools, result points, upset rules, leaderboard phases/tiebreaks, buy-in, payouts, bonus types)
- **Leagues** — invite-only membership, commissioner settings, readiness checks, team bootstrap from the provider
- **Draft** — linear/snake order, preassigns, picks, undo last pick, roster tweaks (draft reset only when `APP_ENV=development`)
- **Sync & scoring** — pull fixtures/results, recompute standings, match events, sync status
- **Analytics** — standings, points-per-game, matchweeks, upsets, form, splits, highlights
- **Admin** — manual bonuses, bonus types, ranking lists
- **Cron** — `POST /internal/sync-and-score` (secured with `CRON_SECRET`) for active/drafting leagues

Interactive API docs: `http://localhost:8000/docs`

## Repo layout

```
backend/          FastAPI app (`app/`), tests, seed script
frontend/         Next.js app
supabase/         Postgres migrations (`migrations/001`–`008`)
.env.example      Shared backend + frontend env template
```

## Prerequisites

- Python 3.12+
- Node 20+
- [Supabase CLI](https://supabase.com/docs/guides/cli) (local) **or** a hosted Supabase project
- A football-data.org API token (for bootstrap/sync)

## Setup

### 1. Environment

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env.local
```

Fill in values. Root `.env` is loaded by the backend; frontend reads `frontend/.env.local`.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres URL (`postgresql+psycopg://…`) |
| `SUPABASE_URL` | Auth issuer base; JWKS at `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` |
| `SUPABASE_SECRET_KEY` | Server key (legacy alias: `SUPABASE_SERVICE_ROLE_KEY`) |
| `SUPABASE_JWT_AUDIENCE` | Usually `authenticated` |
| `FOOTBALL_DATA_API_TOKEN` | Provider token |
| `CRON_SECRET` | Protects `/internal/*` (required non-default in production) |
| `CORS_ORIGINS` | Comma-separated origins (e.g. `http://localhost:3000`) |
| `AUTH_BYPASS_EMAIL` | Dev-only: skip JWT and act as this invited email (forbidden in production) |
| `NEXT_PUBLIC_API_URL` | Backend base URL |
| `NEXT_PUBLIC_SUPABASE_URL` | Same project URL the browser uses |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Publishable key (legacy: `NEXT_PUBLIC_SUPABASE_ANON_KEY`) |

### 2. Database

Apply migrations from `supabase/migrations/` (e.g. `supabase db push` against your linked/local project, or run the SQL in order via the Supabase SQL editor).

Local Supabase defaults match `.env.example` (`54321` API, `54322` DB).

### 3. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Optional Premier League template seed:

```bash
cd backend
python -m app.scripts.seed_pl_template
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: `http://localhost:3000`

## Auth model

- Users sign in via Supabase (password, signup, or magic link).
- API requests send the Supabase JWT; the backend verifies it via JWKS.
- League access is **invite-only**: a profile is created/used only when the email has a pending or accepted invite (unless using `AUTH_BYPASS_EMAIL` in development).

## Typical local flow

1. Start Supabase / point env at your project and apply migrations.
2. Run API + frontend.
3. Seed the PL template (optional).
4. Sign up / sign in in the UI.
5. Create a league from a template, invite managers, bootstrap teams, open the draft.
6. Sync fixtures when the season is live; standings and stats update from scored results.

Cron-style scoring for all drafting/active leagues:

```bash
curl -X POST http://localhost:8000/internal/sync-and-score \
  -H "X-Cron-Secret: $CRON_SECRET"
```

## Tests & CI

```bash
cd backend
pytest -q

cd frontend
npx tsc --noEmit
npm run build
```

GitHub Actions (`.github/workflows/ci.yml`) runs backend pytest and a frontend typecheck + production build on push/PR.
