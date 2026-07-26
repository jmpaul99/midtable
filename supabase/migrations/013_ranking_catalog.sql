-- Global ranking catalogs (system FIFA lists + per-user custom lists)

CREATE TABLE ranking_catalogs (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  key TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('system', 'user')),
  owner_profile_id BIGINT REFERENCES profiles(id) ON DELETE CASCADE,
  source TEXT NOT NULL DEFAULT 'manual',
  as_of DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ranking_catalogs_public_id_key UNIQUE (public_id),
  CONSTRAINT ranking_catalogs_owner_kind_check CHECK (
    (kind = 'system' AND owner_profile_id IS NULL)
    OR (kind = 'user' AND owner_profile_id IS NOT NULL)
  )
);

CREATE TABLE ranking_catalog_entries (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  catalog_id BIGINT NOT NULL REFERENCES ranking_catalogs(id) ON DELETE CASCADE,
  rank INT NOT NULL,
  team_name TEXT NOT NULL,
  country_code TEXT,
  confederation TEXT,
  CONSTRAINT ranking_catalog_entries_public_id_key UNIQUE (public_id),
  CONSTRAINT ranking_catalog_entries_catalog_rank_key UNIQUE (catalog_id, rank),
  CONSTRAINT ranking_catalog_entries_catalog_name_key UNIQUE (catalog_id, team_name)
);

CREATE TABLE ranking_catalog_team_overrides (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  catalog_id BIGINT NOT NULL REFERENCES ranking_catalogs(id) ON DELETE CASCADE,
  country_code TEXT,
  team_name TEXT,
  provider TEXT NOT NULL DEFAULT 'football-data.org',
  external_team_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT ranking_catalog_team_overrides_public_id_key UNIQUE (public_id),
  CONSTRAINT ranking_catalog_team_overrides_match_check CHECK (
    country_code IS NOT NULL OR team_name IS NOT NULL
  )
);

CREATE UNIQUE INDEX ranking_catalog_team_overrides_catalog_code_uidx
  ON ranking_catalog_team_overrides (catalog_id, lower(country_code))
  WHERE country_code IS NOT NULL;

CREATE UNIQUE INDEX ranking_catalog_team_overrides_catalog_name_uidx
  ON ranking_catalog_team_overrides (catalog_id, lower(team_name))
  WHERE team_name IS NOT NULL;

CREATE INDEX ranking_catalog_entries_catalog_id_idx
  ON ranking_catalog_entries (catalog_id);

CREATE TRIGGER ranking_catalogs_set_updated_at
  BEFORE UPDATE ON ranking_catalogs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER ranking_catalog_team_overrides_set_updated_at
  BEFORE UPDATE ON ranking_catalog_team_overrides FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO ranking_catalogs (key, label, kind, owner_profile_id, source)
VALUES
  ('fifa_men', 'FIFA Men''s World Ranking', 'system', NULL, 'parse_fifa'),
  ('fifa_women', 'FIFA Women''s World Ranking', 'system', NULL, 'parse_fifa');
