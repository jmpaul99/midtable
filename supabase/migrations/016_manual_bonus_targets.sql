-- Allow manual bonuses to target a team, a match side (team in match), or a manager.
ALTER TABLE manual_bonuses
  ALTER COLUMN team_id DROP NOT NULL;

ALTER TABLE manual_bonuses
  ADD COLUMN IF NOT EXISTS match_id BIGINT REFERENCES matches(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS member_id BIGINT REFERENCES league_members(id) ON DELETE CASCADE;

ALTER TABLE manual_bonuses
  DROP CONSTRAINT IF EXISTS manual_bonuses_target_check;

ALTER TABLE manual_bonuses
  ADD CONSTRAINT manual_bonuses_target_check CHECK (
    (
      -- Team award
      team_id IS NOT NULL
      AND match_id IS NULL
      AND member_id IS NULL
    )
    OR (
      -- Match award (one team in that match)
      team_id IS NOT NULL
      AND match_id IS NOT NULL
      AND member_id IS NULL
    )
    OR (
      -- Manager award
      member_id IS NOT NULL
      AND team_id IS NULL
      AND match_id IS NULL
    )
  );

CREATE INDEX IF NOT EXISTS manual_bonuses_league_member_idx
  ON manual_bonuses (league_id, member_id);

CREATE INDEX IF NOT EXISTS manual_bonuses_league_match_idx
  ON manual_bonuses (league_id, match_id);
