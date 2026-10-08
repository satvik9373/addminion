"""Composition root for the new application-service layer.

This module is the only place that wires repositories and capability
implementations to services. It does not run a pipeline or perform I/O.
"""

from dataclasses import dataclass
import os

from adapters.in_memory import (
    InMemoryEnrichmentResultRepository,
    InMemoryLeadRepository,
    InMemoryOnboardingProfileRepository,
    InMemoryQualificationResultRepository,
    InMemoryUserRepository,
    InMemoryWorkspaceRepository,
)
from adapters.legacy import (
    LegacyDiscoveryAdapter,
    LegacyEnrichmentAdapter,
    LegacyQualificationAdapter,
)
from application.services import (
    LeadDNAService,
    LeadDiscoveryService,
    LeadEnrichmentService,
    LeadPipelineService,
    LeadQualificationService,
    OnboardingProfileService,
    WebsiteAnalysisService,
    OnboardingService,
)
from application.provisioning import UserProvisioningService
from application.auth import (
    SupabaseAuthAdapter,
    SupabaseJWTVerifier,
    WorkspaceResolver,
)
from core.ports import (
    ContactEnrichmentProvider,
    LeadDiscoveryProvider,
    LeadScoringService,
    WebsiteAnalyzer,
)
from persistence import PostgresRepositories, build_postgres_repositories


@dataclass
class ApplicationServices:
    onboarding_profiles: OnboardingProfileService
    website_analysis: WebsiteAnalysisService
    lead_dna: LeadDNAService
    lead_discovery: LeadDiscoveryService
    lead_qualification: LeadQualificationService
    lead_enrichment: LeadEnrichmentService
    lead_pipeline: LeadPipelineService


@dataclass(frozen=True)
class InMemoryRepositories:
    users: InMemoryUserRepository
    workspaces: InMemoryWorkspaceRepository
    onboarding_profiles: InMemoryOnboardingProfileRepository
    leads: InMemoryLeadRepository
    qualification_results: InMemoryQualificationResultRepository
    enrichment_results: InMemoryEnrichmentResultRepository


def build_in_memory_application(
    discovery_provider: LeadDiscoveryProvider,
    scoring_service: LeadScoringService,
    enrichment_provider: ContactEnrichmentProvider,
    website_analyzer: WebsiteAnalyzer,
) -> tuple[ApplicationServices, InMemoryRepositories]:
    """Wire test/local services without constructing infrastructure."""
    repositories = InMemoryRepositories(
        users=InMemoryUserRepository(),
        workspaces=InMemoryWorkspaceRepository(),
        onboarding_profiles=InMemoryOnboardingProfileRepository(),
        leads=InMemoryLeadRepository(),
        qualification_results=InMemoryQualificationResultRepository(),
        enrichment_results=InMemoryEnrichmentResultRepository(),
    )
    onboarding_profiles = OnboardingProfileService(repositories.onboarding_profiles)
    website_analysis = WebsiteAnalysisService(website_analyzer)
    lead_dna = LeadDNAService()
    lead_discovery = LeadDiscoveryService(discovery_provider, repositories.leads)
    lead_qualification = LeadQualificationService(
        scoring_service, repositories.qualification_results)
    lead_enrichment = LeadEnrichmentService(
        enrichment_provider, repositories.enrichment_results)
    services = ApplicationServices(
        onboarding_profiles=onboarding_profiles,
        website_analysis=website_analysis,
        lead_dna=lead_dna,
        lead_discovery=lead_discovery,
        lead_qualification=lead_qualification,
        lead_enrichment=lead_enrichment,
        lead_pipeline=LeadPipelineService(
            lead_discovery, lead_qualification, lead_enrichment),
    )
    return services, repositories


@dataclass(frozen=True)
class OnboardingDependencies:
    authenticator: object
    provisioning: UserProvisioningService
    workspace_resolver: object
    service: OnboardingService


def build_in_memory_onboarding_dependencies(authenticator: object) -> OnboardingDependencies:
    users = InMemoryUserRepository()
    workspaces = InMemoryWorkspaceRepository()
    profiles = InMemoryOnboardingProfileRepository()
    provisioning = UserProvisioningService(users, workspaces)
    from application.auth import WorkspaceResolver
    return OnboardingDependencies(
        authenticator=authenticator,
        provisioning=provisioning,
        workspace_resolver=WorkspaceResolver(workspaces),
        service=OnboardingService(profiles),
    )


def build_legacy_application(
    discovery_provider: object,
    discovery_method: str,
    scorer: object,
    enricher: object,
    website_analyzer: WebsiteAnalyzer,
) -> tuple[ApplicationServices, InMemoryRepositories]:
    """Wire legacy implementations behind the new application contracts."""
    return build_in_memory_application(
        discovery_provider=LegacyDiscoveryAdapter(
            discovery_provider, discovery_method),
        scoring_service=LegacyQualificationAdapter(scorer),
        enrichment_provider=LegacyEnrichmentAdapter(enricher),
        website_analyzer=website_analyzer,
    )


def build_production_repositories() -> PostgresRepositories:
    """Composition-root entry point for configured PostgreSQL persistence."""
    return build_postgres_repositories()


def build_production_onboarding_dependencies() -> OnboardingDependencies:
    """Wire verified Supabase JWTs to PostgreSQL-backed onboarding."""
    repositories = build_production_repositories()
    verifier = SupabaseJWTVerifier(
        os.environ.get('SUPABASE_PROJECT_URL', ''),
        jwks_url=os.environ.get('SUPABASE_JWKS_URL') or None,
        audience=os.environ.get(
            'SUPABASE_JWT_AUDIENCE', 'authenticated'),
    )
    return OnboardingDependencies(
        authenticator=SupabaseAuthAdapter(verifier),
        provisioning=UserProvisioningService(
            repositories.users, repositories.workspaces),
        workspace_resolver=WorkspaceResolver(repositories.workspaces),
        service=OnboardingService(repositories.onboarding_profiles),
    )
