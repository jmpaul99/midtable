-- Default post-draft roster club order for leagues created from a template.
ALTER TABLE competition_templates
  ADD COLUMN IF NOT EXISTS roster_club_order TEXT NOT NULL DEFAULT 'draft'
  CHECK (roster_club_order IN ('draft', 'competition'));
