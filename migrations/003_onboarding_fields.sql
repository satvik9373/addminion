-- Addminion onboarding inputs. Raw ICP references are retained for a later
-- processing phase; this migration does not parse or crawl anything.

ALTER TABLE onboarding_profiles
    ADD COLUMN has_website BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE onboarding_profiles
    ADD COLUMN target_niche TEXT;
ALTER TABLE onboarding_profiles
    ADD COLUMN target_service TEXT;
ALTER TABLE onboarding_profiles
    ADD COLUMN icp_description TEXT;
ALTER TABLE onboarding_profiles
    ADD COLUMN icp_document_reference TEXT;
ALTER TABLE onboarding_profiles
    ADD COLUMN completed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE onboarding_profiles
    ADD COLUMN ready_for_processing BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE onboarding_profiles
    ADD COLUMN completed_at TIMESTAMPTZ;
