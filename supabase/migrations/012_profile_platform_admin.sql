-- Platform admin flag on profiles (replaces JWT app_metadata.role checks)

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS is_platform_admin BOOLEAN NOT NULL DEFAULT FALSE;
