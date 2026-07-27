-- Manual bonuses belong to a league, not a user. Drop authorship FK.
ALTER TABLE manual_bonuses
  DROP COLUMN IF EXISTS created_by_profile_id;
