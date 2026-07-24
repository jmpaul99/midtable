-- Hardening: allow commissioner roster edits; index scoring_events by match

ALTER TABLE roster_entries DROP CONSTRAINT IF EXISTS roster_entries_source_check;
ALTER TABLE roster_entries
  ADD CONSTRAINT roster_entries_source_check
  CHECK (source IN ('preassigned', 'draft', 'commissioner'));

CREATE INDEX IF NOT EXISTS scoring_events_match_id_idx ON scoring_events (match_id);
