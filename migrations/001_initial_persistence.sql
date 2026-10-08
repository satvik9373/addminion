-- PostgreSQL foundation for the multi-tenant Addminion data layer.
-- SQLite remains the legacy runtime store; this migration is not applied by
-- the current application.

CREATE TABLE users (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE workspaces (
    id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (owner_user_id, name)
);

CREATE TABLE onboarding_profiles (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    company_name TEXT,
    website_url TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (workspace_id, user_id)
);

CREATE TABLE website_profiles (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    url TEXT NOT NULL,
    title TEXT,
    description TEXT,
    analyzed_at TIMESTAMPTZ
);

CREATE TABLE icps (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    name TEXT,
    industries JSONB NOT NULL DEFAULT '[]'::jsonb,
    locations JSONB NOT NULL DEFAULT '[]'::jsonb,
    company_sizes JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE lead_dna (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    icp_id UUID REFERENCES icps(id),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE leads (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL,
    company_name TEXT,
    website_url TEXT,
    source TEXT,
    discovered_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE qualification_results (
    lead_id UUID PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    qualified BOOLEAN NOT NULL,
    score DOUBLE PRECISION,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    evaluated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE enrichment_results (
    lead_id UUID PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    email TEXT,
    phone TEXT,
    social_profiles JSONB NOT NULL DEFAULT '{}'::jsonb,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    enriched_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_workspaces_owner_user_id ON workspaces(owner_user_id);
CREATE INDEX idx_onboarding_profiles_workspace_id ON onboarding_profiles(workspace_id);
CREATE INDEX idx_website_profiles_workspace_id ON website_profiles(workspace_id);
CREATE INDEX idx_icps_workspace_id ON icps(workspace_id);
CREATE INDEX idx_lead_dna_workspace_id ON lead_dna(workspace_id);
CREATE INDEX idx_leads_workspace_id ON leads(workspace_id);
CREATE INDEX idx_qualification_results_workspace_id ON qualification_results(workspace_id);
CREATE INDEX idx_enrichment_results_workspace_id ON enrichment_results(workspace_id);
