-- Do not invent max_members=4 when unset; empty config means no soft cap.
ALTER TABLE leagues
  ALTER COLUMN config SET DEFAULT '{}'::jsonb;
