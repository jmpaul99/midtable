-- Bridge hardening for DBs that already applied 001_initial_schema.sql

ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_provider_external_key;
ALTER TABLE matches DROP CONSTRAINT IF EXISTS matches_league_provider_external_key;
ALTER TABLE matches
  ADD CONSTRAINT matches_league_provider_external_key
  UNIQUE (league_id, provider, external_id);

ALTER TABLE invites ADD COLUMN IF NOT EXISTS token TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS invites_token_key ON invites (token);

CREATE INDEX IF NOT EXISTS league_members_profile_id_idx ON league_members (profile_id);
CREATE INDEX IF NOT EXISTS league_members_league_id_idx ON league_members (league_id);
CREATE UNIQUE INDEX IF NOT EXISTS league_members_league_draft_slot_uidx
  ON league_members (league_id, draft_slot)
  WHERE draft_slot IS NOT NULL;
CREATE INDEX IF NOT EXISTS roster_entries_member_id_idx ON roster_entries (member_id);
CREATE INDEX IF NOT EXISTS invites_email_idx ON invites (email);
CREATE INDEX IF NOT EXISTS invites_token_idx ON invites (token);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'profiles_set_updated_at') THEN
    CREATE TRIGGER profiles_set_updated_at
      BEFORE UPDATE ON profiles FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'competition_templates_set_updated_at') THEN
    CREATE TRIGGER competition_templates_set_updated_at
      BEFORE UPDATE ON competition_templates FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'leagues_set_updated_at') THEN
    CREATE TRIGGER leagues_set_updated_at
      BEFORE UPDATE ON leagues FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'invites_set_updated_at') THEN
    CREATE TRIGGER invites_set_updated_at
      BEFORE UPDATE ON invites FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'league_members_set_updated_at') THEN
    CREATE TRIGGER league_members_set_updated_at
      BEFORE UPDATE ON league_members FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'team_pools_set_updated_at') THEN
    CREATE TRIGGER team_pools_set_updated_at
      BEFORE UPDATE ON team_pools FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'teams_set_updated_at') THEN
    CREATE TRIGGER teams_set_updated_at
      BEFORE UPDATE ON teams FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'draft_state_set_updated_at') THEN
    CREATE TRIGGER draft_state_set_updated_at
      BEFORE UPDATE ON draft_state FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'matches_set_updated_at') THEN
    CREATE TRIGGER matches_set_updated_at
      BEFORE UPDATE ON matches FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'ranking_lists_set_updated_at') THEN
    CREATE TRIGGER ranking_lists_set_updated_at
      BEFORE UPDATE ON ranking_lists FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'sync_status_set_updated_at') THEN
    CREATE TRIGGER sync_status_set_updated_at
      BEFORE UPDATE ON sync_status FOR EACH ROW EXECUTE FUNCTION set_updated_at();
  END IF;
END $$;
