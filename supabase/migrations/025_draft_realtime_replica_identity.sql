-- Realtime + RLS: non-PK columns (league_id) are used in SELECT policies.
-- FULL replica identity ensures UPDATE/DELETE change payloads include those
-- columns so subscribers can authorize and receive undo (DELETE) events.
-- With RLS enabled, DELETE old payloads still expose only primary keys to clients.

ALTER TABLE draft_state REPLICA IDENTITY FULL;
ALTER TABLE draft_picks REPLICA IDENTITY FULL;
