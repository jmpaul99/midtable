-- Invite email delivery history + per-league open join links

CREATE TABLE invite_email_deliveries (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  public_id UUID NOT NULL DEFAULT gen_random_uuid(),
  invite_id BIGINT NOT NULL REFERENCES invites(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'skipped')),
  trigger TEXT NOT NULL CHECK (trigger IN ('create', 'resend')),
  error TEXT,
  provider TEXT NOT NULL DEFAULT 'mailjet',
  provider_message_id TEXT,
  http_attempts INT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT invite_email_deliveries_public_id_key UNIQUE (public_id)
);

CREATE INDEX invite_email_deliveries_invite_id_created_at_idx
  ON invite_email_deliveries (invite_id, created_at DESC);

ALTER TABLE leagues
  ADD COLUMN IF NOT EXISTS join_token TEXT,
  ADD COLUMN IF NOT EXISTS join_link_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS leagues_join_token_key
  ON leagues (join_token)
  WHERE join_token IS NOT NULL;
