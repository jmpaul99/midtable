-- Persist football-data.org competition.type on team pools for MW vs round labeling.
ALTER TABLE team_pools
  ADD COLUMN IF NOT EXISTS competition_type TEXT;

ALTER TABLE team_pools
  DROP CONSTRAINT IF EXISTS team_pools_competition_type_check;

ALTER TABLE team_pools
  ADD CONSTRAINT team_pools_competition_type_check
  CHECK (
    competition_type IS NULL
    OR competition_type IN ('LEAGUE', 'LEAGUE_CUP', 'CUP', 'PLAYOFFS')
  );

COMMENT ON COLUMN team_pools.competition_type IS
  'football-data.org competition.type — LEAGUE uses matchweek labels; others use round';

-- Backfill known free-plan codes so UI is correct before the next provider sync.
UPDATE team_pools
SET competition_type = 'LEAGUE'
WHERE competition_type IS NULL
  AND UPPER(competition_code) IN (
    'PL', 'BL1', 'DED', 'BSA', 'PD', 'FL1', 'ELC', 'PPL', 'SA'
  );

UPDATE team_pools
SET competition_type = 'CUP'
WHERE competition_type IS NULL
  AND UPPER(competition_code) IN ('CL', 'WC', 'EC');
