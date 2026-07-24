-- Soft league config (max_members etc.) + draft pick idempotency

ALTER TABLE leagues
  ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{"max_members": 4}'::jsonb;

CREATE TABLE IF NOT EXISTS draft_idempotency_keys (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  league_id BIGINT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  member_id BIGINT NOT NULL REFERENCES league_members(id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  pick_id BIGINT REFERENCES draft_picks(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT draft_idempotency_keys_public_id_key UNIQUE (public_id),
  CONSTRAINT draft_idempotency_keys_league_member_key UNIQUE (league_id, member_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS draft_idempotency_keys_league_id_idx
  ON draft_idempotency_keys (league_id);
