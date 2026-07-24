-- Football Draft League — initial schema
-- Every entity: bigint id PK + uuid public_id (unique indexed)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Core identity
-- ---------------------------------------------------------------------------
CREATE TABLE profiles (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  auth_user_id UUID UNIQUE,
  email TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT profiles_public_id_key UNIQUE (public_id)
);

CREATE TABLE competition_templates (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  key TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  draft_style TEXT NOT NULL DEFAULT 'linear' CHECK (draft_style IN ('linear', 'snake')),
  preassign_mode TEXT NOT NULL DEFAULT 'none' CHECK (preassign_mode IN ('none', 'supported', 'optional')),
  result_points JSONB NOT NULL DEFAULT '{"win": 3, "draw": 1}'::jsonb,
  upset_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
  leaderboard_phases JSONB NOT NULL DEFAULT '[]'::jsonb,
  leaderboard_tiebreaks JSONB NOT NULL DEFAULT '[{"metric":"total_points","direction":"desc"}]'::jsonb,
  buy_in NUMERIC(10,2) NOT NULL DEFAULT 0,
  payouts JSONB NOT NULL DEFAULT '[]'::jsonb,
  roster_slots JSONB NOT NULL DEFAULT '[]'::jsonb,
  pool_definitions JSONB NOT NULL DEFAULT '[]'::jsonb,
  bonus_types JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT competition_templates_public_id_key UNIQUE (public_id)
);

CREATE TABLE leagues (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  template_id BIGINT REFERENCES competition_templates(id),
  name TEXT NOT NULL,
  season_label TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pre_draft'
    CHECK (status IN ('pre_draft', 'drafting', 'active', 'complete')),
  draft_style TEXT NOT NULL DEFAULT 'linear' CHECK (draft_style IN ('linear', 'snake')),
  preassign_mode TEXT NOT NULL DEFAULT 'none' CHECK (preassign_mode IN ('none', 'supported', 'optional')),
  result_points JSONB NOT NULL DEFAULT '{"win": 3, "draw": 1}'::jsonb,
  upset_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
  leaderboard_phases JSONB NOT NULL DEFAULT '[]'::jsonb,
  leaderboard_tiebreaks JSONB NOT NULL DEFAULT '[{"metric":"total_points","direction":"desc"}]'::jsonb,
  buy_in NUMERIC(10,2) NOT NULL DEFAULT 0,
  payouts JSONB NOT NULL DEFAULT '[]'::jsonb,
  scheduled_start_date DATE,
  scheduled_end_date DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT leagues_public_id_key UNIQUE (public_id)
);

CREATE TABLE invites (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  is_commissioner BOOLEAN NOT NULL DEFAULT FALSE,
  draft_slot INT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'accepted', 'revoked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT invites_public_id_key UNIQUE (public_id),
  CONSTRAINT invites_league_email_key UNIQUE (league_id, email)
);

CREATE TABLE league_members (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  is_commissioner BOOLEAN NOT NULL DEFAULT FALSE,
  draft_slot INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT league_members_public_id_key UNIQUE (public_id),
  CONSTRAINT league_members_league_profile_key UNIQUE (league_id, profile_id)
);

CREATE TABLE team_pools (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  label TEXT NOT NULL,
  scores_match_results BOOLEAN NOT NULL DEFAULT TRUE,
  slot_count INT NOT NULL DEFAULT 0,
  tie_break_order JSONB NOT NULL DEFAULT '["points","gd","gf","name"]'::jsonb,
  provider TEXT NOT NULL DEFAULT 'football-data.org',
  competition_code TEXT,
  season_year INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT team_pools_public_id_key UNIQUE (public_id),
  CONSTRAINT team_pools_league_key UNIQUE (league_id, key)
);

CREATE TABLE teams (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  provider TEXT NOT NULL DEFAULT 'football-data.org',
  external_id TEXT NOT NULL,
  name TEXT NOT NULL,
  short_name TEXT,
  tla TEXT,
  crest_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT teams_public_id_key UNIQUE (public_id),
  CONSTRAINT teams_provider_external_key UNIQUE (provider, external_id)
);

CREATE TABLE pool_teams (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  pool_id BIGINT NOT NULL REFERENCES team_pools(id) ON DELETE CASCADE,
  team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT pool_teams_public_id_key UNIQUE (public_id),
  CONSTRAINT pool_teams_pool_team_key UNIQUE (pool_id, team_id)
);

CREATE TABLE roster_entries (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  member_id BIGINT NOT NULL REFERENCES league_members(id) ON DELETE CASCADE,
  team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  pool_id BIGINT NOT NULL REFERENCES team_pools(id) ON DELETE CASCADE,
  source TEXT NOT NULL CHECK (source IN ('preassigned', 'draft')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT roster_entries_public_id_key UNIQUE (public_id),
  CONSTRAINT roster_entries_league_team_key UNIQUE (league_id, team_id)
);

CREATE TABLE draft_state (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL UNIQUE REFERENCES leagues(id) ON DELETE CASCADE,
  current_pick_number INT NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'open', 'complete')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT draft_state_public_id_key UNIQUE (public_id)
);

CREATE TABLE draft_picks (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  pick_number INT NOT NULL,
  round_number INT NOT NULL,
  member_id BIGINT NOT NULL REFERENCES league_members(id) ON DELETE CASCADE,
  team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  pool_id BIGINT NOT NULL REFERENCES team_pools(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT draft_picks_public_id_key UNIQUE (public_id),
  CONSTRAINT draft_picks_league_pick_key UNIQUE (league_id, pick_number)
);

CREATE TABLE matches (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  pool_id BIGINT NOT NULL REFERENCES team_pools(id) ON DELETE CASCADE,
  provider TEXT NOT NULL DEFAULT 'football-data.org',
  external_id TEXT NOT NULL,
  home_team_id BIGINT NOT NULL REFERENCES teams(id),
  away_team_id BIGINT NOT NULL REFERENCES teams(id),
  kickoff_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'SCHEDULED',
  home_goals INT,
  away_goals INT,
  scheduled_matchweek INT,
  stage TEXT,
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT matches_public_id_key UNIQUE (public_id),
  CONSTRAINT matches_provider_external_key UNIQUE (provider, external_id)
);

CREATE INDEX matches_pool_kickoff_idx ON matches (pool_id, kickoff_at);
CREATE INDEX matches_league_status_idx ON matches (league_id, status);

CREATE TABLE standings_snapshots (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  pool_id BIGINT NOT NULL REFERENCES team_pools(id) ON DELETE CASCADE,
  kickoff_at TIMESTAMPTZ NOT NULL,
  stale BOOLEAN NOT NULL DEFAULT FALSE,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT standings_snapshots_public_id_key UNIQUE (public_id),
  CONSTRAINT standings_snapshots_pool_kickoff_key UNIQUE (pool_id, kickoff_at)
);

CREATE TABLE standings_snapshot_rows (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  snapshot_id BIGINT NOT NULL REFERENCES standings_snapshots(id) ON DELETE CASCADE,
  team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  rank INT NOT NULL,
  played INT NOT NULL DEFAULT 0,
  points INT NOT NULL DEFAULT 0,
  goals_for INT NOT NULL DEFAULT 0,
  goals_against INT NOT NULL DEFAULT 0,
  goal_difference INT NOT NULL DEFAULT 0,
  CONSTRAINT standings_snapshot_rows_public_id_key UNIQUE (public_id),
  CONSTRAINT standings_snapshot_rows_snapshot_team_key UNIQUE (snapshot_id, team_id)
);

CREATE TABLE ranking_lists (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  label TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'manual',
  as_of DATE,
  locked BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ranking_lists_public_id_key UNIQUE (public_id),
  CONSTRAINT ranking_lists_league_key UNIQUE (league_id, key)
);

CREATE TABLE team_rankings (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  ranking_list_id BIGINT NOT NULL REFERENCES ranking_lists(id) ON DELETE CASCADE,
  team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  rank INT NOT NULL,
  CONSTRAINT team_rankings_public_id_key UNIQUE (public_id),
  CONSTRAINT team_rankings_list_team_key UNIQUE (ranking_list_id, team_id)
);

CREATE TABLE bonus_types (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  label TEXT NOT NULL,
  default_points NUMERIC(10,2) NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  include_in_phases JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT bonus_types_public_id_key UNIQUE (public_id),
  CONSTRAINT bonus_types_league_key UNIQUE (league_id, key)
);

CREATE TABLE manual_bonuses (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  bonus_type_id BIGINT NOT NULL REFERENCES bonus_types(id) ON DELETE CASCADE,
  points NUMERIC(10,2) NOT NULL,
  notes TEXT,
  created_by_profile_id BIGINT REFERENCES profiles(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT manual_bonuses_public_id_key UNIQUE (public_id)
);

CREATE TABLE scoring_events (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  team_id BIGINT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  match_id BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  scheduled_matchweek INT,
  stage TEXT,
  event_type TEXT NOT NULL,
  points NUMERIC(10,2) NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT scoring_events_public_id_key UNIQUE (public_id),
  CONSTRAINT scoring_events_match_team_type_key UNIQUE (match_id, team_id, event_type)
);

CREATE INDEX scoring_events_league_team_idx ON scoring_events (league_id, team_id);
CREATE INDEX scoring_events_league_mw_idx ON scoring_events (league_id, scheduled_matchweek);

CREATE TABLE sync_status (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  provider TEXT NOT NULL DEFAULT 'football-data.org',
  last_sync_at TIMESTAMPTZ,
  in_progress BOOLEAN NOT NULL DEFAULT FALSE,
  in_progress_since TIMESTAMPTZ,
  requests_available_minute INT,
  last_error TEXT,
  last_summary JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT sync_status_public_id_key UNIQUE (public_id),
  CONSTRAINT sync_status_league_provider_key UNIQUE (league_id, provider)
);

-- Analytics views (membership resolved via roster_entries)
CREATE OR REPLACE VIEW v_team_match_points AS
SELECT
  se.league_id,
  se.team_id,
  se.match_id,
  se.scheduled_matchweek,
  se.stage,
  SUM(se.points) AS points,
  jsonb_object_agg(se.event_type, se.points) AS by_event_type
FROM scoring_events se
GROUP BY se.league_id, se.team_id, se.match_id, se.scheduled_matchweek, se.stage;

CREATE OR REPLACE VIEW v_member_matchweek_points AS
SELECT
  re.league_id,
  re.member_id,
  se.scheduled_matchweek,
  SUM(se.points) AS points
FROM scoring_events se
JOIN roster_entries re
  ON re.league_id = se.league_id AND re.team_id = se.team_id
WHERE se.scheduled_matchweek IS NOT NULL
GROUP BY re.league_id, re.member_id, se.scheduled_matchweek;

CREATE OR REPLACE VIEW v_team_season_summary AS
SELECT
  se.league_id,
  se.team_id,
  re.member_id,
  SUM(se.points) AS auto_points,
  COUNT(DISTINCT se.match_id) AS matches_with_events
FROM scoring_events se
LEFT JOIN roster_entries re
  ON re.league_id = se.league_id AND re.team_id = se.team_id
GROUP BY se.league_id, se.team_id, re.member_id;
