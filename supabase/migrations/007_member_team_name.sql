-- Per-league fantasy team name for each member (distinct from profiles.display_name).
ALTER TABLE league_members
  ADD COLUMN team_name TEXT NULL;

ALTER TABLE league_members
  ADD CONSTRAINT league_members_team_name_len
  CHECK (team_name IS NULL OR char_length(btrim(team_name)) BETWEEN 1 AND 80);
