-- Allow commissioners to cancel hung pending/running league jobs.
-- App writes status='cancelled'; 021 only allowed pending|running|succeeded|failed.

ALTER TABLE league_jobs DROP CONSTRAINT IF EXISTS league_jobs_status_check;

ALTER TABLE league_jobs
  ADD CONSTRAINT league_jobs_status_check
  CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled'));
