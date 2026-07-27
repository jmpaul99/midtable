# Midtable

Platform for running multi-pool football draft leagues: create a league from a competition template, invite managers (email or shareable join link), draft clubs, sync fixtures, and score standings with upsets, bonuses, and phase-based payouts.

## Stack

| Layer | Tech |
| --- | --- |
| API | FastAPI, SQLAlchemy 2, Pydantic Settings |
| App | Next.js 16, React 19, Tailwind CSS 4 |
| Auth / DB | Supabase Auth + Postgres |
| Fixtures | [football-data.org](https://www.football-data.org/) API |

Python **3.14+**, Node **26.5.0+**.

## What’s in the box

- **Competition templates** — reusable rules (draft style, roster slots, pools, result points, upset rules, leaderboard phases/tiebreakers, buy-in, payouts, bonus types)
- **Leagues** — invite- or join-link membership, commissioner settings, readiness checks, team bootstrap from the provider
- **Draft** — linear/snake order, preassigns, picks, undo last pick, roster tweaks (draft reset only when `APP_ENV=development`)
- **Sync & scoring** — pull fixtures/results, recompute standings, match events, sync status
- **Analytics** — standings, points-per-game, matchweeks, upsets, form, splits, highlights
- **Admin** — manual bonuses, bonus types, ranking lists
- **Cron** — `POST /internal/sync-and-score` (secured with `CRON_SECRET`) for active/drafting leagues

Interactive API docs: `http://localhost:8000/docs`

## Repo layout

```
backend/          FastAPI app (`app/`), tests, seed script, Dockerfile
frontend/         Next.js app (+ Dockerfile for Cloud Run)
supabase/         Postgres migrations (`migrations/001`–`011`)
compose.yaml      API + frontend containers (local; override adds API --reload)
.env.example      Shared backend + frontend env template
```

## Prerequisites

- Python 3.14+ (or Docker for the API)
- Node 26.5.0+
- [Docker](https://docs.docker.com/get-docker/) (optional; for running the API in a container)
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
| `DATABASE_URL` | Postgres URL (`postgresql+psycopg://…`); hosted Supabase should use `?sslmode=require` (also enforced for remote hosts in code) |
| `SUPABASE_URL` | Auth issuer base; JWKS at `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` |
| `SUPABASE_JWT_AUDIENCE` | Usually `authenticated` |
| `FOOTBALL_DATA_API_TOKEN` | Provider token |
| `CRON_SECRET` | Protects `/internal/*` (required non-default in production) |
| `INTERNAL_API_SECRET` | Shared by API + Next.js BFF for `/auth/email-status` (required non-default in production) |
| `TURNSTILE_SECRET` | Cloudflare Turnstile secret key (required in production) |
| `TURNSTILE_HOSTNAMES` | Frontend hostnames allowed by siteverify (no scheme; comma/space/semicolon separated) |
| `CORS_ORIGINS` | Comma-separated origins (e.g. `http://localhost:3000`) |
| `AUTH_BYPASS_EMAIL` | Dev-only: skip JWT and act as this email (forbidden in production) |
| `PUBLIC_APP_URL` | Frontend origin for invite accept + join links (required in production) |
| `MAILJET_API_KEY_PUBLIC` / `MAILJET_API_KEY_PRIVATE` | Mailjet Send API credentials (required in production) |
| `MAILJET_FROM_EMAIL` / `MAILJET_FROM_NAME` | Verified sender for invite emails (inline HTML; no template ID) |
| `API_URL` | Server-side API base for the Next.js BFF (Compose: service DNS; Cloud Run: public API origin) |
| `NEXT_PUBLIC_API_URL` | Backend base URL (browser) |
| `NEXT_PUBLIC_SUPABASE_URL` | Same project URL the browser uses |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Publishable key |
| `NEXT_PUBLIC_TURNSTILE_SITEKEY` | Cloudflare Turnstile sitekey (public) |

### 2. Database

Apply migrations from `supabase/migrations/`:

```bash
# From backend/ (uses DATABASE_URL from ../.env or the environment)
cd backend && pip install -e . && python -m app.scripts.run_migrations
```

Or `supabase db push` against a linked/local project, or run the SQL files in order via the Supabase SQL editor. Production deploys run the same migration script automatically before Cloud Run update.

Local Supabase defaults match `.env.example` (`54321` API, `54322` DB).

### 3. Backend

**Option A — Docker Compose (API + frontend, hot reload)**

Compose builds `midtable-api` and `midtable-frontend`, loads root `.env`, and merges `compose.override.yaml`:

- API: bind-mount + `uvicorn --reload`
- Frontend: `frontend/Dockerfile.dev` + bind-mounts + `next dev` (polling enabled for Docker Desktop)

Production still deploys frontend via Cloud Run, not Compose. For a production-like frontend image locally, run without the override: `docker compose -f compose.yaml up --build`.

When the API runs in Docker and Supabase stays on the host, point backend URLs at `host.docker.internal` in `.env` (see comments in `.env.example`). Keep frontend `NEXT_PUBLIC_*` on `127.0.0.1` / `localhost` in `frontend/.env.local` — Compose hot-reload loads that file (same as `npm run dev`). Root `.env` `NEXT_PUBLIC_*` are only used when building the production frontend image (`compose.yaml` without override / Cloud Run).

```bash
docker compose up --build
```

- API: `http://localhost:8000`
- App: `http://localhost:3000`

API only:

```bash
docker compose up --build midtable-api
```

Optional seed inside the container:

```bash
docker compose exec midtable-api python -m app.scripts.seed_pl_template
```

Backend `pyproject.toml` or frontend `package-lock.json` changes need `docker compose up --build` again (frontend `node_modules` live in a named volume).

**Option B — local venv**

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

### 4. Frontend (local Node, without Docker)

```bash
cd frontend
npm install
npm run dev
```

App: `http://localhost:3000`

### Production deploy (Cloud Run)

Frontend and API both deploy to **Google Cloud Run** via GitHub Actions (same GCP project and Artifact Registry Docker repo `midtable` in `us-central1`).

Workflows: [`.github/workflows/deploy-backend.yml`](.github/workflows/deploy-backend.yml), [`.github/workflows/deploy-frontend.yml`](.github/workflows/deploy-frontend.yml), [`.github/workflows/sync.yml`](.github/workflows/sync.yml).

#### What to set in GitHub

Settings → Secrets and variables → Actions.

| Name | Type | Value |
| --- | --- | --- |
| `GCP_PROJECT_ID` | Variable | GCP project id |
| `GCP_SA_KEY` | Secret | Deploy service-account JSON |
| `DATABASE_URL` | Secret | Hosted Supabase Postgres URL with `?sslmode=require` (also used to apply migrations on backend deploy) |
| `SUPABASE_URL` | Secret | Hosted Supabase project URL (`https://….supabase.co`) |
| `FOOTBALL_DATA_API_TOKEN` | Secret | football-data.org API token |
| `CRON_SECRET` | Secret | Long random string |
| `INTERNAL_API_SECRET` | Secret | Long random string (same value on API + frontend Cloud Run) |
| `TURNSTILE_SECRET` | Secret | Cloudflare Turnstile secret key |
| `TURNSTILE_HOSTNAMES` | Secret | Frontend hostnames for siteverify (no scheme), e.g. `mid-table.com,midtable-frontend-….run.app` |
| `NEXT_PUBLIC_TURNSTILE_SITEKEY` | Secret | Cloudflare Turnstile sitekey (public; baked into frontend image) |
| `PUBLIC_APP_URL` | Secret | Frontend origin (e.g. `https://….run.app` or `https://mid-table.com`) |
| `MAILJET_API_KEY_PUBLIC` | Secret | Mailjet public key |
| `MAILJET_API_KEY_PRIVATE` | Secret | Mailjet private key |
| `MAILJET_FROM_EMAIL` | Secret | Verified sender email |
| `API_URL` | Secret | API origin (e.g. `https://….run.app`, no path) |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Secret | Supabase publishable key |

**1 variable + 15 secrets.** Shared mappings (do not create these as separate GitHub secrets):

- `API_URL` → frontend build `NEXT_PUBLIC_API_URL` + frontend runtime `API_URL` (BFF) + cron base URL
- `PUBLIC_APP_URL` → backend `PUBLIC_APP_URL` + `CORS_ORIGINS` + frontend `NEXT_PUBLIC_SITE_URL`
- `SUPABASE_URL` → backend + frontend `NEXT_PUBLIC_SUPABASE_URL`
- `CRON_SECRET` → backend + cron
- `INTERNAL_API_SECRET` → backend + frontend runtime (BFF → `/auth/email-status`)

Use **hosted** Supabase URLs — not `127.0.0.1` or `host.docker.internal`. Backend workflow sets `APP_ENV=production` and `MAILJET_FROM_NAME=Midtable`.

Backend deploy runs `python -m app.scripts.run_migrations` with `DATABASE_URL` after CI and **before** building/pushing the API image. Pending files under `supabase/migrations/*.sql` are applied; if the DB already has the schema but no tracking rows, existing files are recorded without re-running.

#### Before first deploy

1. Enable Cloud Run + Artifact Registry; create Artifact Registry Docker repo `midtable` in `us-central1`.
2. Deploy SA JSON → secret `GCP_SA_KEY`; set variable `GCP_PROJECT_ID`.
3. Set secrets that do not need Cloud Run URLs yet (`DATABASE_URL`, `SUPABASE_URL`, Mailjet, `FOOTBALL_DATA_API_TOKEN`, `CRON_SECRET`, `INTERNAL_API_SECRET`, Turnstile keys/hostnames, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`). Schema migrations are applied by the backend deploy workflow.
4. Temporary `PUBLIC_APP_URL` (e.g. `https://example.com`) → deploy **backend** → copy API origin → set `API_URL`.
5. Deploy **frontend** → copy frontend origin → set `PUBLIC_APP_URL` to that origin → update `TURNSTILE_HOSTNAMES` to match → redeploy backend and frontend.
6. Supabase Auth redirects: `{frontend-origin}`, `{frontend-origin}/auth/callback`.
7. Confirm cron secrets (`API_URL` + `CRON_SECRET`); run Sync and score via `workflow_dispatch`.

Local smoke tests:

```bash
docker build -t midtable-api ./backend
docker run --rm -p 8000:8000 --env-file .env midtable-api

docker build -f frontend/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 \
  --build-arg NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 \
  --build-arg NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=test-publishable-key \
  --build-arg NEXT_PUBLIC_SITE_URL=http://localhost:3000 \
  --build-arg NEXT_PUBLIC_TURNSTILE_SITEKEY=1x00000000000000000000AA \
  -t midtable-frontend .
docker run --rm -p 3000:3000 \
  -e API_URL=http://host.docker.internal:8000 \
  -e INTERNAL_API_SECRET=dev-internal-secret \
  midtable-frontend
```

## Auth model

- Users sign in via Supabase (password, signup, or magic link).
- API requests send the Supabase JWT; the backend verifies it via JWKS.
- Accounts are open: any authenticated user can create a profile.
- League access is gated by a **personal email invite** or a commissioner **join link**.

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

GitHub Actions (`.github/workflows/ci.yml`) runs backend pytest, a frontend typecheck + production build, and Docker image builds for the API and frontend on push/PR. Production deploys: `.github/workflows/deploy-backend.yml` and `.github/workflows/deploy-frontend.yml` (Cloud Run).
