-- Store football-data.org score.duration for ET / PK fantasy scoring.
ALTER TABLE matches
  ADD COLUMN IF NOT EXISTS duration TEXT NOT NULL DEFAULT 'REGULAR';
