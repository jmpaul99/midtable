-- Rename preassign_mode values: none->off, supported->required; add preassign_count.

ALTER TABLE competition_templates
  DROP CONSTRAINT IF EXISTS competition_templates_preassign_mode_check;

ALTER TABLE leagues
  DROP CONSTRAINT IF EXISTS leagues_preassign_mode_check;

UPDATE competition_templates
SET preassign_mode = CASE preassign_mode
  WHEN 'none' THEN 'off'
  WHEN 'supported' THEN 'required'
  ELSE preassign_mode
END;

UPDATE leagues
SET preassign_mode = CASE preassign_mode
  WHEN 'none' THEN 'off'
  WHEN 'supported' THEN 'required'
  ELSE preassign_mode
END;

ALTER TABLE competition_templates
  ALTER COLUMN preassign_mode SET DEFAULT 'off';

ALTER TABLE leagues
  ALTER COLUMN preassign_mode SET DEFAULT 'off';

ALTER TABLE competition_templates
  ADD CONSTRAINT competition_templates_preassign_mode_check
  CHECK (preassign_mode IN ('off', 'optional', 'required'));

ALTER TABLE leagues
  ADD CONSTRAINT leagues_preassign_mode_check
  CHECK (preassign_mode IN ('off', 'optional', 'required'));

ALTER TABLE competition_templates
  ADD COLUMN IF NOT EXISTS preassign_count INTEGER NOT NULL DEFAULT 1
  CHECK (preassign_count >= 0);

ALTER TABLE leagues
  ADD COLUMN IF NOT EXISTS preassign_count INTEGER NOT NULL DEFAULT 1
  CHECK (preassign_count >= 0);
