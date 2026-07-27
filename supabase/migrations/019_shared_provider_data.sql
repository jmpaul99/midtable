-- Share fixtures (matches), standings snapshots, and ranking freezes across leagues.
-- Scoring events remain per-league; sync status is keyed by competition.

-- ---------------------------------------------------------------------------
-- matches: league/pool scope -> provider + competition + season
-- ---------------------------------------------------------------------------
ALTER TABLE matches
  ADD COLUMN IF NOT EXISTS competition_code TEXT,
  ADD COLUMN IF NOT EXISTS season_year INT;

UPDATE matches m
SET
  competition_code = tp.competition_code,
  season_year = tp.season_year
FROM team_pools tp
WHERE m.pool_id = tp.id
  AND (m.competition_code IS NULL OR m.season_year IS NULL);

ALTER TABLE matches
  DROP CONSTRAINT IF EXISTS matches_league_provider_external_key;

ALTER TABLE scoring_events
  DROP CONSTRAINT IF EXISTS scoring_events_match_team_type_key;

ALTER TABLE scoring_events
  ADD CONSTRAINT scoring_events_league_match_team_type_key
  UNIQUE (league_id, match_id, team_id, event_type);

CREATE TEMP TABLE match_dedupe_map ON COMMIT DROP AS
SELECT m.id AS dupe_id, c.canonical_id
FROM matches m
JOIN (
  SELECT
    provider,
    competition_code,
    season_year,
    external_id,
    MIN(id) AS canonical_id
  FROM matches
  WHERE competition_code IS NOT NULL
    AND season_year IS NOT NULL
  GROUP BY provider, competition_code, season_year, external_id
) c
  ON m.provider = c.provider
 AND m.competition_code = c.competition_code
 AND m.season_year = c.season_year
 AND m.external_id = c.external_id
WHERE m.id <> c.canonical_id;

UPDATE scoring_events se
SET match_id = d.canonical_id
FROM match_dedupe_map d
WHERE se.match_id = d.dupe_id;

UPDATE manual_bonuses mb
SET match_id = d.canonical_id
FROM match_dedupe_map d
WHERE mb.match_id = d.dupe_id;

DELETE FROM matches m
USING match_dedupe_map d
WHERE m.id = d.dupe_id;

DELETE FROM matches
WHERE competition_code IS NULL
   OR season_year IS NULL;

ALTER TABLE matches
  ALTER COLUMN competition_code SET NOT NULL,
  ALTER COLUMN season_year SET NOT NULL;

DROP INDEX IF EXISTS matches_pool_kickoff_idx;
DROP INDEX IF EXISTS matches_league_status_idx;

ALTER TABLE matches
  DROP COLUMN league_id,
  DROP COLUMN pool_id;

ALTER TABLE matches
  ADD CONSTRAINT matches_provider_competition_season_external_key
  UNIQUE (provider, competition_code, season_year, external_id);

CREATE INDEX matches_competition_kickoff_idx
  ON matches (provider, competition_code, season_year, kickoff_at);

CREATE INDEX matches_competition_status_idx
  ON matches (provider, competition_code, season_year, status);

-- ---------------------------------------------------------------------------
-- standings_snapshots: pool scope -> provider + competition + season
-- ---------------------------------------------------------------------------
ALTER TABLE standings_snapshots
  ADD COLUMN IF NOT EXISTS provider TEXT,
  ADD COLUMN IF NOT EXISTS competition_code TEXT,
  ADD COLUMN IF NOT EXISTS season_year INT;

UPDATE standings_snapshots ss
SET
  provider = tp.provider,
  competition_code = tp.competition_code,
  season_year = tp.season_year
FROM team_pools tp
WHERE ss.pool_id = tp.id
  AND (
    ss.provider IS NULL
    OR ss.competition_code IS NULL
    OR ss.season_year IS NULL
  );

CREATE TEMP TABLE standings_dedupe_map ON COMMIT DROP AS
SELECT ss.id AS dupe_id, c.canonical_id
FROM standings_snapshots ss
JOIN (
  SELECT
    provider,
    competition_code,
    season_year,
    kickoff_at,
    MIN(id) AS canonical_id
  FROM standings_snapshots
  WHERE provider IS NOT NULL
    AND competition_code IS NOT NULL
    AND season_year IS NOT NULL
  GROUP BY provider, competition_code, season_year, kickoff_at
) c
  ON ss.provider = c.provider
 AND ss.competition_code = c.competition_code
 AND ss.season_year = c.season_year
 AND ss.kickoff_at = c.kickoff_at
WHERE ss.id <> c.canonical_id;

DELETE FROM standings_snapshots ss
USING standings_dedupe_map d
WHERE ss.id = d.dupe_id;

DELETE FROM standings_snapshots
WHERE provider IS NULL
   OR competition_code IS NULL
   OR season_year IS NULL;

ALTER TABLE standings_snapshots
  ALTER COLUMN provider SET NOT NULL,
  ALTER COLUMN provider SET DEFAULT 'football-data.org',
  ALTER COLUMN competition_code SET NOT NULL,
  ALTER COLUMN season_year SET NOT NULL;

ALTER TABLE standings_snapshots
  DROP CONSTRAINT IF EXISTS standings_snapshots_pool_kickoff_key;

ALTER TABLE standings_snapshots
  DROP COLUMN pool_id;

ALTER TABLE standings_snapshots
  ADD CONSTRAINT standings_snapshots_competition_kickoff_key
  UNIQUE (provider, competition_code, season_year, kickoff_at);

CREATE INDEX standings_snapshots_competition_kickoff_idx
  ON standings_snapshots (provider, competition_code, season_year, kickoff_at);

-- ---------------------------------------------------------------------------
-- sync_status: league scope -> provider + competition + season
-- ---------------------------------------------------------------------------
DELETE FROM sync_status;

ALTER TABLE sync_status
  DROP CONSTRAINT IF EXISTS sync_status_league_provider_key;

ALTER TABLE sync_status
  DROP COLUMN league_id;

ALTER TABLE sync_status
  ADD COLUMN competition_code TEXT NOT NULL,
  ADD COLUMN season_year INT NOT NULL;

ALTER TABLE sync_status
  ADD CONSTRAINT sync_status_provider_competition_season_key
  UNIQUE (provider, competition_code, season_year);

-- ---------------------------------------------------------------------------
-- ranking freezes (shared catalog snapshots)
-- ---------------------------------------------------------------------------
CREATE TABLE ranking_freezes (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  catalog_id BIGINT NOT NULL REFERENCES ranking_catalogs(id) ON DELETE CASCADE,
  as_of DATE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ranking_freezes_public_id_key UNIQUE (public_id),
  CONSTRAINT ranking_freezes_catalog_as_of_key UNIQUE (catalog_id, as_of)
);

CREATE TABLE ranking_freeze_entries (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  freeze_id BIGINT NOT NULL REFERENCES ranking_freezes(id) ON DELETE CASCADE,
  team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  rank INT NOT NULL,
  CONSTRAINT ranking_freeze_entries_public_id_key UNIQUE (public_id),
  CONSTRAINT ranking_freeze_entries_freeze_team_key UNIQUE (freeze_id, team_id)
);

CREATE INDEX ranking_freeze_entries_freeze_id_idx
  ON ranking_freeze_entries (freeze_id);

ALTER TABLE ranking_lists
  ADD COLUMN freeze_id BIGINT REFERENCES ranking_freezes(id) ON DELETE SET NULL;

-- Locked league lists tied to a catalog: materialize shared freeze + link list.
INSERT INTO ranking_freezes (catalog_id, as_of)
SELECT DISTINCT
  rc.id,
  COALESCE(rl.as_of, CURRENT_DATE)
FROM ranking_lists rl
JOIN ranking_catalogs rc ON rc.key = rl.key
WHERE rl.locked = TRUE
  AND EXISTS (
    SELECT 1
    FROM team_rankings tr
    WHERE tr.ranking_list_id = rl.id
  )
ON CONFLICT (catalog_id, as_of) DO NOTHING;

INSERT INTO ranking_freeze_entries (freeze_id, team_id, rank)
SELECT rf.id, tr.team_id, tr.rank
FROM ranking_lists rl
JOIN ranking_catalogs rc ON rc.key = rl.key
JOIN ranking_freezes rf
  ON rf.catalog_id = rc.id
 AND rf.as_of = COALESCE(rl.as_of, CURRENT_DATE)
JOIN team_rankings tr ON tr.ranking_list_id = rl.id
WHERE rl.locked = TRUE
ON CONFLICT (freeze_id, team_id) DO NOTHING;

UPDATE ranking_lists rl
SET freeze_id = rf.id
FROM ranking_catalogs rc
JOIN ranking_freezes rf
  ON rf.catalog_id = rc.id
WHERE rc.key = rl.key
  AND rf.as_of = COALESCE(rl.as_of, CURRENT_DATE)
  AND rl.locked = TRUE
  AND EXISTS (
    SELECT 1
    FROM team_rankings tr
    WHERE tr.ranking_list_id = rl.id
  );

-- Unlocked non-manual / catalog-backed lists: drop stale per-league rows.
DELETE FROM team_rankings tr
USING ranking_lists rl
LEFT JOIN ranking_catalogs rc ON rc.key = rl.key
WHERE tr.ranking_list_id = rl.id
  AND rl.locked = FALSE
  AND (rl.source <> 'manual' OR rc.id IS NOT NULL);
