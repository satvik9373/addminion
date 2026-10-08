-- Provider identity mapping for external authentication (for example,
-- Supabase Auth). Passwords and provider credentials are not stored here.

ALTER TABLE users ADD COLUMN auth_provider TEXT;
ALTER TABLE users ADD COLUMN auth_subject TEXT;

CREATE UNIQUE INDEX idx_users_auth_identity
    ON users(auth_provider, auth_subject)
    WHERE auth_provider IS NOT NULL AND auth_subject IS NOT NULL;
