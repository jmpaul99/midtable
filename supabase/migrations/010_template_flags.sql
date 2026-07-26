-- Featured / Made by staff flags on competition templates (staff-set only in API)

ALTER TABLE competition_templates
  ADD COLUMN IF NOT EXISTS featured BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS made_by_staff BOOLEAN NOT NULL DEFAULT FALSE;
