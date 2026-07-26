-- Default manager count for leagues created from a template.
ALTER TABLE competition_templates
  ADD COLUMN IF NOT EXISTS max_members INTEGER
  CHECK (max_members IS NULL OR (max_members >= 2 AND max_members <= 100));
