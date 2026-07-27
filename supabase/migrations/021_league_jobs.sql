-- Durable league sync/recompute jobs (manual + cron). Full history retained for audit.

CREATE TABLE league_jobs (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('sync', 'recompute')),
  source TEXT NOT NULL CHECK (source IN ('commissioner', 'cron')),
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
  created_by_profile_id BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
  error TEXT,
  summary JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  CONSTRAINT league_jobs_public_id_key UNIQUE (public_id)
);

CREATE UNIQUE INDEX league_jobs_one_active_per_league
  ON league_jobs (league_id)
  WHERE status IN ('pending', 'running');

CREATE INDEX league_jobs_league_source_created_at_idx
  ON league_jobs (league_id, source, created_at DESC);
