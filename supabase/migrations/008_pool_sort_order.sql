-- Add display order for roster/pool listing (Premier League before Championship, etc.)
ALTER TABLE team_pools
  ADD COLUMN IF NOT EXISTS sort_order INT NOT NULL DEFAULT 0;

-- Prefer creation order within each league as a baseline.
WITH ranked AS (
  SELECT
    id,
    ROW_NUMBER() OVER (PARTITION BY league_id ORDER BY created_at ASC, id ASC) AS rn
  FROM team_pools
)
UPDATE team_pools tp
SET sort_order = ranked.rn
FROM ranked
WHERE tp.id = ranked.id;

-- Known English pyramid keys: Premier League first, Championship second.
UPDATE team_pools
SET sort_order = 1
WHERE lower(key) IN ('premier_league', 'pl', 'premier')
   OR upper(coalesce(competition_code, '')) = 'PL';

UPDATE team_pools
SET sort_order = 2
WHERE lower(key) IN ('championship', 'elc', 'efl_championship')
   OR upper(coalesce(competition_code, '')) IN ('ELC', 'CHA');
