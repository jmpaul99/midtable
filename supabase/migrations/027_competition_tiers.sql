-- Editable domestic competition tiers for draft autopick ordering.
-- NULL domestic_tier = cups / internationals (no domestic ladder).

CREATE TABLE IF NOT EXISTS competition_tiers (
  competition_code TEXT PRIMARY KEY,
  domestic_tier INTEGER,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT competition_tiers_domestic_tier_check
    CHECK (domestic_tier IS NULL OR domestic_tier >= 1)
);

COMMENT ON TABLE competition_tiers IS
  'Platform-admin curated domestic ladder tiers (1 = top flight). Shared across leagues.';

COMMENT ON COLUMN competition_tiers.domestic_tier IS
  '1 = top flight, 2 = second tier, etc. NULL = cups/internationals (sort after numbered tiers).';

INSERT INTO competition_tiers (competition_code, domestic_tier) VALUES
  ('WC', NULL),
  ('CL', NULL),
  ('BL1', 1),
  ('DED', 1),
  ('BSA', 1),
  ('PD', 1),
  ('FL1', 1),
  ('ELC', 2),
  ('PPL', 1),
  ('EC', NULL),
  ('SA', 1),
  ('PL', 1)
ON CONFLICT (competition_code) DO NOTHING;
