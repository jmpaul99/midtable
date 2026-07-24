-- Placeholder display names for existing profiles (previously auto-filled from email).
-- Users can set a real name from the profile page; signup now requires one.
UPDATE profiles
SET display_name = 'Display Name',
    updated_at = now()
WHERE display_name IS DISTINCT FROM 'Display Name';
