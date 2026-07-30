-- Secure Supabase Realtime (Postgres Changes) for draft live sync.
-- Clients may SELECT draft_state / draft_picks only for leagues they belong to.
-- API writes use the DB owner role and are unaffected by RLS.

CREATE OR REPLACE FUNCTION public.is_league_member(p_league_id bigint)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM league_members lm
    JOIN profiles p ON p.id = lm.profile_id
    WHERE lm.league_id = p_league_id
      AND p.auth_user_id = auth.uid()
  );
$$;

REVOKE ALL ON FUNCTION public.is_league_member(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.is_league_member(bigint) TO authenticated;

ALTER TABLE draft_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE draft_picks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS draft_state_select_member ON draft_state;
CREATE POLICY draft_state_select_member ON draft_state
  FOR SELECT
  TO authenticated
  USING (public.is_league_member(league_id));

DROP POLICY IF EXISTS draft_picks_select_member ON draft_picks;
CREATE POLICY draft_picks_select_member ON draft_picks
  FOR SELECT
  TO authenticated
  USING (public.is_league_member(league_id));

GRANT SELECT ON draft_state TO authenticated;
GRANT SELECT ON draft_picks TO authenticated;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    IF NOT EXISTS (
      SELECT 1
      FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime'
        AND schemaname = 'public'
        AND tablename = 'draft_state'
    ) THEN
      ALTER PUBLICATION supabase_realtime ADD TABLE draft_state;
    END IF;
    IF NOT EXISTS (
      SELECT 1
      FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime'
        AND schemaname = 'public'
        AND tablename = 'draft_picks'
    ) THEN
      ALTER PUBLICATION supabase_realtime ADD TABLE draft_picks;
    END IF;
  END IF;
END $$;
