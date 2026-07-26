-- Track which profile created a competition template (nullable for legacy/seeded rows)

ALTER TABLE competition_templates
  ADD COLUMN IF NOT EXISTS created_by_profile_id BIGINT REFERENCES profiles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS competition_templates_created_by_profile_id_idx
  ON competition_templates (created_by_profile_id);
