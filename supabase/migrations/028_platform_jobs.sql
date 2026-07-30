-- Durable platform-admin sync jobs (manual teams+rankings + cron FIFA). Full history retained.

CREATE TABLE platform_jobs (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  kind TEXT NOT NULL CHECK (kind IN ('teams_and_rankings', 'fifa_rankings')),
  source TEXT NOT NULL CHECK (source IN ('admin', 'cron')),
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
  created_by_profile_id BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
  params JSONB,
  error TEXT,
  summary JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  CONSTRAINT platform_jobs_public_id_key UNIQUE (public_id)
);

CREATE UNIQUE INDEX platform_jobs_one_active
  ON platform_jobs ((true))
  WHERE status IN ('pending', 'running');

CREATE INDEX platform_jobs_source_created_at_idx
  ON platform_jobs (source, created_at DESC);
