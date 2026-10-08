"""PostgreSQL repositories for the production persistence foundation.

The module has no import-time PostgreSQL dependency. A connection factory is
injected, keeping tests database-free and keeping credentials outside source.
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional
from uuid import uuid4
from datetime import datetime, timezone

from core.domain import (
    EnrichmentResult,
    ICP,
    Lead,
    LeadDNA,
    OnboardingProfile,
    QualificationResult,
    User,
    WebsiteProfile,
    Workspace,
)
from .mappers import (
    enrichment_from_row,
    icp_from_row,
    lead_dna_from_row,
    lead_from_row,
    onboarding_from_row,
    qualification_from_row,
    user_from_row,
    website_from_row,
    workspace_from_row,
)

ConnectionFactory = Callable[[], Any]


class PostgresStore:
    def __init__(self, connection_factory: ConnectionFactory):
        self._connection_factory = connection_factory

    def _execute(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> None:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
            connection.commit()
            return None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _fetch_one(
        self,
        sql: str,
        params: tuple[Any, ...],
    ) -> Optional[Mapping[str, Any]]:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                if row is None:
                    return None
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, row))
        finally:
            connection.close()


def _json_value(value: Any) -> str:
    return json.dumps(value)


class PostgresUserRepository(PostgresStore):
    def save(self, user: User) -> None:
        self._execute(
            """INSERT INTO users (id, email, display_name, created_at)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 email = EXCLUDED.email,
                 display_name = EXCLUDED.display_name""",
            (user.id, user.email, user.display_name, user.created_at),
        )

    def get(self, user_id: str) -> User | None:
        row = self._fetch_one(
            "SELECT * FROM users WHERE id = %s", (user_id,))
        return user_from_row(row) if row else None

    def get_by_auth_subject(self, provider: str, subject: str) -> User | None:
        row = self._fetch_one(
            """SELECT u.* FROM users u
               WHERE u.auth_provider = %s AND u.auth_subject = %s""",
            (provider, subject),
        )
        return user_from_row(row) if row else None

    def bind_identity(self, user_id: str, provider: str, subject: str) -> None:
        self._execute(
            """UPDATE users SET auth_provider = %s, auth_subject = %s
               WHERE id = %s""",
            (provider, subject, user_id),
        )

    def provision(self, provider: str, subject: str, email: str,
                  display_name: str | None = None) -> User:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO users
                         (id, email, display_name, created_at,
                          auth_provider, auth_subject)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (auth_provider, auth_subject)
                       WHERE auth_provider IS NOT NULL
                         AND auth_subject IS NOT NULL
                       DO UPDATE SET auth_subject = EXCLUDED.auth_subject
                       RETURNING id, email, display_name, created_at""",
                    (str(uuid4()), email, display_name,
                     datetime.now(timezone.utc), provider, subject),
                )
                row = cursor.fetchone()
                columns = [column[0] for column in cursor.description]
            connection.commit()
            return user_from_row(dict(zip(columns, row)))
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class PostgresWorkspaceRepository(PostgresStore):
    def save(self, workspace: Workspace) -> None:
        self._execute(
            """INSERT INTO workspaces
                 (id, owner_user_id, name, created_at)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name""",
            (workspace.id, workspace.owner_user_id,
             workspace.name, workspace.created_at),
        )

    def get(self, workspace_id: str) -> Workspace | None:
        row = self._fetch_one(
            "SELECT * FROM workspaces WHERE id = %s", (workspace_id,))
        return workspace_from_row(row) if row else None

    def get_default_for_user(self, user_id: str) -> str | None:
        row = self._fetch_one(
            """SELECT id FROM workspaces
               WHERE owner_user_id = %s
               ORDER BY created_at ASC LIMIT 1""",
            (user_id,),
        )
        return str(row['id']) if row else None

    def get_or_create_default(self, user_id: str) -> Workspace:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO workspaces
                         (id, owner_user_id, name, created_at)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (owner_user_id, name)
                       DO UPDATE SET name = EXCLUDED.name
                       RETURNING id, owner_user_id, name, created_at""",
                    (str(uuid4()), user_id, 'Default Workspace',
                     datetime.now(timezone.utc)),
                )
                row = cursor.fetchone()
                columns = [column[0] for column in cursor.description]
            connection.commit()
            return workspace_from_row(dict(zip(columns, row)))
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class PostgresOnboardingProfileRepository(PostgresStore):
    def save(self, profile: OnboardingProfile) -> None:
        self._execute(
            """INSERT INTO onboarding_profiles
                 (id, user_id, workspace_id, company_name, website_url,
                  has_website, target_niche, target_service, icp_description,
                  icp_document_reference, completed, ready_for_processing,
                  completed_at, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 company_name = EXCLUDED.company_name,
                 website_url = EXCLUDED.website_url,
                 has_website = EXCLUDED.has_website,
                 target_niche = EXCLUDED.target_niche,
                 target_service = EXCLUDED.target_service,
                 icp_description = EXCLUDED.icp_description,
                 icp_document_reference = EXCLUDED.icp_document_reference,
                 completed = EXCLUDED.completed,
                 ready_for_processing = EXCLUDED.ready_for_processing,
                 completed_at = EXCLUDED.completed_at,
                 updated_at = EXCLUDED.updated_at""",
            (profile.id, profile.user_id, _required_workspace(profile),
             profile.company_name, profile.website_url,
             profile.has_website, profile.target_niche, profile.target_service,
             profile.icp_description, profile.icp_document_reference,
             profile.completed, profile.ready_for_processing,
             profile.completed_at,
             profile.created_at, profile.updated_at),
        )

    def get_for_user(self, user_id: str) -> OnboardingProfile | None:
        row = self._fetch_one(
            "SELECT * FROM onboarding_profiles WHERE user_id = %s",
            (user_id,))
        return onboarding_from_row(row) if row else None


class PostgresWebsiteProfileRepository(PostgresStore):
    def save(self, profile: WebsiteProfile) -> None:
        self._execute(
            """INSERT INTO website_profiles
                 (id, user_id, workspace_id, url, title, description, analyzed_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 url = EXCLUDED.url, title = EXCLUDED.title,
                 description = EXCLUDED.description,
                 analyzed_at = EXCLUDED.analyzed_at""",
            (profile.id, profile.user_id, _required_workspace(profile),
             profile.url, profile.title, profile.description,
             profile.analyzed_at),
        )

    def get(self, profile_id: str) -> WebsiteProfile | None:
        row = self._fetch_one(
            "SELECT * FROM website_profiles WHERE id = %s", (profile_id,))
        return website_from_row(row) if row else None


class PostgresICPRepository(PostgresStore):
    def save(self, icp: ICP) -> None:
        self._execute(
            """INSERT INTO icps
                 (id, user_id, workspace_id, name, industries, locations,
                  company_sizes, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 name = EXCLUDED.name, industries = EXCLUDED.industries,
                 locations = EXCLUDED.locations,
                 company_sizes = EXCLUDED.company_sizes""",
            (icp.id, icp.user_id, _required_workspace(icp), icp.name,
             _json_value(icp.industries), _json_value(icp.locations),
             _json_value(icp.company_sizes), icp.created_at),
        )

    def get(self, icp_id: str) -> ICP | None:
        row = self._fetch_one("SELECT * FROM icps WHERE id = %s", (icp_id,))
        return icp_from_row(row) if row else None


class PostgresLeadDNARepository(PostgresStore):
    def save(self, dna: LeadDNA) -> None:
        self._execute(
            """INSERT INTO lead_dna
                 (id, user_id, workspace_id, icp_id, attributes, created_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 icp_id = EXCLUDED.icp_id, attributes = EXCLUDED.attributes""",
            (dna.id, dna.user_id, _required_workspace(dna), dna.icp_id,
             _json_value(dna.attributes), dna.created_at),
        )

    def get(self, dna_id: str) -> LeadDNA | None:
        row = self._fetch_one(
            "SELECT * FROM lead_dna WHERE id = %s", (dna_id,))
        return lead_dna_from_row(row) if row else None


class PostgresLeadRepository(PostgresStore):
    def save(self, lead: Lead) -> None:
        self._execute(
            """INSERT INTO leads
                 (id, workspace_id, name, company_name, website_url, source,
                  discovered_at, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                 name = EXCLUDED.name, company_name = EXCLUDED.company_name,
                 website_url = EXCLUDED.website_url,
                 source = EXCLUDED.source, metadata = EXCLUDED.metadata""",
            (lead.id, _required_workspace(lead), lead.name,
             lead.company_name, lead.website_url, lead.source,
             lead.discovered_at, _json_value(lead.metadata)),
        )

    def get(self, lead_id: str) -> Lead | None:
        row = self._fetch_one("SELECT * FROM leads WHERE id = %s", (lead_id,))
        return lead_from_row(row) if row else None


class PostgresQualificationResultRepository(PostgresStore):
    def save(self, result: QualificationResult) -> None:
        self._execute(
            """INSERT INTO qualification_results
                 (lead_id, workspace_id, qualified, score, reasons, evaluated_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (lead_id) DO UPDATE SET
                 qualified = EXCLUDED.qualified, score = EXCLUDED.score,
                 reasons = EXCLUDED.reasons, evaluated_at = EXCLUDED.evaluated_at""",
            (result.lead_id, _required_workspace(result), result.qualified,
             result.score, _json_value(result.reasons), result.evaluated_at),
        )

    def get_for_lead(self, lead_id: str) -> QualificationResult | None:
        row = self._fetch_one(
            "SELECT * FROM qualification_results WHERE lead_id = %s",
            (lead_id,))
        return qualification_from_row(row) if row else None


class PostgresEnrichmentResultRepository(PostgresStore):
    def save(self, result: EnrichmentResult) -> None:
        self._execute(
            """INSERT INTO enrichment_results
                 (lead_id, workspace_id, email, phone, social_profiles,
                  sources, enriched_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (lead_id) DO UPDATE SET
                 email = EXCLUDED.email, phone = EXCLUDED.phone,
                 social_profiles = EXCLUDED.social_profiles,
                 sources = EXCLUDED.sources, enriched_at = EXCLUDED.enriched_at""",
            (result.lead_id, _required_workspace(result), result.email,
             result.phone, _json_value(result.social_profiles),
             _json_value(result.sources), result.enriched_at),
        )

    def get_for_lead(self, lead_id: str) -> EnrichmentResult | None:
        row = self._fetch_one(
            "SELECT * FROM enrichment_results WHERE lead_id = %s",
            (lead_id,))
        return enrichment_from_row(row) if row else None


def _required_workspace(resource: Any) -> str:
    workspace_id = getattr(resource, 'workspace_id', None)
    if not workspace_id:
        raise ValueError('workspace_id is required for production persistence')
    return workspace_id


@dataclass(frozen=True)
class PostgresRepositories:
    users: PostgresUserRepository
    workspaces: PostgresWorkspaceRepository
    onboarding_profiles: PostgresOnboardingProfileRepository
    website_profiles: PostgresWebsiteProfileRepository
    icps: PostgresICPRepository
    lead_dna: PostgresLeadDNARepository
    leads: PostgresLeadRepository
    qualification_results: PostgresQualificationResultRepository
    enrichment_results: PostgresEnrichmentResultRepository


def build_postgres_repositories(
    connection_factory: ConnectionFactory | None = None,
) -> PostgresRepositories:
    """Build repositories from an injected factory or POSTGRES_DATABASE_URL."""
    if connection_factory is None:
        dsn = os.environ.get('POSTGRES_DATABASE_URL', '')
        if not dsn:
            raise ValueError('POSTGRES_DATABASE_URL is not configured')
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                'psycopg is required to connect to PostgreSQL') from exc
        connection_factory = lambda: psycopg.connect(dsn)
    return PostgresRepositories(
        users=PostgresUserRepository(connection_factory),
        workspaces=PostgresWorkspaceRepository(connection_factory),
        onboarding_profiles=PostgresOnboardingProfileRepository(connection_factory),
        website_profiles=PostgresWebsiteProfileRepository(connection_factory),
        icps=PostgresICPRepository(connection_factory),
        lead_dna=PostgresLeadDNARepository(connection_factory),
        leads=PostgresLeadRepository(connection_factory),
        qualification_results=PostgresQualificationResultRepository(connection_factory),
        enrichment_results=PostgresEnrichmentResultRepository(connection_factory),
    )
