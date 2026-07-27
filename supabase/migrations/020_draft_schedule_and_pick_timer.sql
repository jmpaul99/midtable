-- Draft schedule and per-pick timer (league settings only; not templates).

ALTER TABLE leagues
  ADD COLUMN IF NOT EXISTS draft_scheduled_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS pick_timer_seconds INTEGER;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'leagues_pick_timer_seconds_positive'
  ) THEN
    ALTER TABLE leagues
      ADD CONSTRAINT leagues_pick_timer_seconds_positive
      CHECK (pick_timer_seconds IS NULL OR pick_timer_seconds > 0);
  END IF;
END $$;

ALTER TABLE draft_state
  ADD COLUMN IF NOT EXISTS pick_deadline_at TIMESTAMPTZ;
