-- Classify teams as national (men/women) or club for FIFA ranking matching.
ALTER TABLE teams
  ADD COLUMN IF NOT EXISTS team_kind TEXT;

ALTER TABLE teams
  DROP CONSTRAINT IF EXISTS teams_team_kind_check;

ALTER TABLE teams
  ADD CONSTRAINT teams_team_kind_check
  CHECK (
    team_kind IS NULL
    OR team_kind IN ('national_men', 'national_women', 'club')
  );

COMMENT ON COLUMN teams.team_kind IS
  'national_men / national_women / club — used to scope FIFA ranking matches';
