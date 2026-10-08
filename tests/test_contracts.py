from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from adapters import (
    InMemoryEnrichmentResultRepository,
    InMemoryLeadRepository,
    InMemoryOnboardingProfileRepository,
    InMemoryQualificationResultRepository,
    InMemoryUserRepository,
)
from application.auth import WorkspaceContext
from adapters.legacy import (
    LegacyDiscoveryAdapter,
    LegacyEnrichmentAdapter,
    LegacyQualificationAdapter,
)
from application.use_cases import (
    AnalyzeWebsite,
    BuildLeadDNA,
    BuildOnboardingProfile,
    DiscoverLeads,
    EnrichLead,
    QualifyLead,
    RunLeadPipeline,
)
from application.composition import (
    build_in_memory_application,
    build_legacy_application,
)
from application.services import (
    LeadDNAService,
    LeadDiscoveryService,
    LeadEnrichmentService,
    LeadPipelineService,
    LeadQualificationService,
    OnboardingProfileService,
    WebsiteAnalysisService,
)
from core.domain import (
    EnrichmentResult,
    ICP,
    Lead,
    LeadDNA,
    OnboardingProfile,
    QualificationResult,
    User,
    WebsiteProfile,
)


def test_domain_models_have_stable_ids_and_timestamps():
    user = User(email='owner@example.com')
    profile = OnboardingProfile(user_id=user.id)
    website = WebsiteProfile(user_id=user.id, url='https://example.com')
    icp = ICP(user_id=user.id)
    dna = LeadDNA(user_id=user.id, icp_id=icp.id)
    lead = Lead(name='Example Lead')
    qualification = QualificationResult(lead_id=lead.id, qualified=True, score=80)
    enrichment = EnrichmentResult(lead_id=lead.id, email='lead@example.com')

    for model in (user, profile, website, icp, dna, lead,
                  qualification, enrichment):
        assert model.id if hasattr(model, 'id') else model.lead_id
        timestamp = next(
            (getattr(model, name, None) for name in (
                'created_at', 'updated_at', 'evaluated_at', 'enriched_at'
            ) if getattr(model, name, None) is not None),
            None,
        )
        if timestamp is not None:
            assert isinstance(timestamp, datetime)
            assert timestamp.tzinfo == timezone.utc


def test_domain_required_fields_and_immutability():
    with pytest.raises(ValueError):
        User(email='')
    with pytest.raises(ValueError):
        WebsiteProfile(user_id='user-1', url='')
    with pytest.raises(ValueError):
        Lead(name='')

    with pytest.raises(FrozenInstanceError):
        User(email='owner@example.com').email = 'changed@example.com'


def test_use_case_contracts_are_importable_without_infrastructure():
    contracts = (
        BuildOnboardingProfile,
        AnalyzeWebsite,
        BuildLeadDNA,
        DiscoverLeads,
        QualifyLead,
        EnrichLead,
        RunLeadPipeline,
    )
    assert all(callable(contract) for contract in contracts)


def test_legacy_adapters_translate_existing_shapes():
    class Provider:
        def scrape(self):
            return [{'id': 'lead-1', 'name': 'A Lead', 'source': 'test'}]

    class Scorer:
        def score_lead(self, lead):
            return {'score': 42, 'qualified': True, 'triggers': ['signal']}

    class Enricher:
        def enrich_lead(self, lead):
            return {
                'email': 'lead@example.com',
                'instagram': '@lead',
                'sources': ['test-provider'],
            }

    lead_dna = LeadDNA(user_id='user-1')
    lead = LegacyDiscoveryAdapter(Provider(), 'scrape').discover(lead_dna)[0]
    result = LegacyQualificationAdapter(Scorer()).score_lead(lead)
    enriched = LegacyEnrichmentAdapter(Enricher()).enrich(lead)

    assert lead.name == 'A Lead'
    assert result.qualified is True
    assert result.score == 42
    assert enriched.email == 'lead@example.com'
    assert enriched.social_profiles['instagram'] == '@lead'


def test_in_memory_repositories_store_and_replace_domain_objects():
    user_repo = InMemoryUserRepository()
    user = User(email='owner@example.com')
    user_repo.save(user)
    assert user_repo.get(user.id) == user

    profile_repo = InMemoryOnboardingProfileRepository()
    profile = OnboardingProfile(user_id=user.id)
    profile_repo.save(profile)
    assert profile_repo.get_for_user(user.id) == profile

    lead_repo = InMemoryLeadRepository()
    lead = Lead(name='Lead')
    lead_repo.save(lead)
    assert lead_repo.get(lead.id) == lead

    qualification_repo = InMemoryQualificationResultRepository()
    qualification = QualificationResult(lead_id=lead.id, score=10)
    qualification_repo.save(qualification)
    assert qualification_repo.get_for_lead(lead.id) == qualification

    enrichment_repo = InMemoryEnrichmentResultRepository()
    enrichment = EnrichmentResult(lead_id=lead.id, email='lead@example.com')
    enrichment_repo.save(enrichment)
    assert enrichment_repo.get_for_lead(lead.id) == enrichment


def test_application_services_orchestrate_injected_capabilities():
    user = User(email='owner@example.com')

    class WebsiteAnalyzer:
        def execute(self, profile):
            return WebsiteProfile(
                user_id=profile.user_id,
                url=profile.website_url or 'https://example.com',
                title='Example',
            )

    class Discovery:
        def discover(self, lead_dna):
            return [Lead(name='Discovered lead', workspace_id='workspace-1')]

    class Scorer:
        def score_lead(self, lead):
            return QualificationResult(
                lead_id=lead.id, workspace_id=lead.workspace_id,
                qualified=True, score=90)

    class Enricher:
        def enrich(self, lead):
            return EnrichmentResult(
                lead_id=lead.id, workspace_id=lead.workspace_id,
                email='lead@example.com')

    profile_repo = InMemoryOnboardingProfileRepository()
    onboarding = OnboardingProfileService(profile_repo)
    profile = onboarding.execute(
        user, company_name='Example Co', website_url='https://example.com')
    assert profile_repo.get_for_user(user.id) == profile

    website = WebsiteAnalysisService(WebsiteAnalyzer()).execute(profile)
    context = WorkspaceContext(user_id=user.id, workspace_id='workspace-1')
    dna = LeadDNAService().execute(profile, website)
    dna = LeadDNA(id=dna.id, user_id=dna.user_id,
                  workspace_id=context.workspace_id,
                  icp_id=dna.icp_id, attributes=dna.attributes,
                  created_at=dna.created_at)
    assert dna.attributes['website_title'] == 'Example'

    discovery = LeadDiscoveryService(Discovery())
    qualification = LeadQualificationService(Scorer())
    enrichment = LeadEnrichmentService(Enricher())
    pipeline = LeadPipelineService(discovery, qualification, enrichment)
    leads = pipeline.execute(context, dna)
    assert len(leads) == 1


def test_composition_root_wires_all_services_and_repositories():
    class WebsiteAnalyzer:
        def execute(self, profile):
            return WebsiteProfile(user_id=profile.user_id, url=profile.website_url or 'https://example.com')

    class Discovery:
        def discover(self, lead_dna):
            return ()

    class Scorer:
        def score_lead(self, lead):
            return QualificationResult(lead_id=lead.id)

    class Enricher:
        def enrich(self, lead):
            return EnrichmentResult(lead_id=lead.id)

    services, repositories = build_in_memory_application(
        Discovery(), Scorer(), Enricher(), WebsiteAnalyzer())
    assert isinstance(services.lead_pipeline, LeadPipelineService)
    assert isinstance(services.lead_dna, LeadDNAService)
    assert isinstance(repositories.leads, InMemoryLeadRepository)


def test_composition_root_can_wire_legacy_adapters():
    class LegacyDiscovery:
        def scrape(self):
            return [{'id': 'legacy-1', 'name': 'Legacy lead'}]

    class LegacyScorer:
        def score_lead(self, lead):
            return {'score': 20, 'qualified': True}

    class LegacyEnricher:
        def enrich_lead(self, lead):
            return {'email': 'legacy@example.com'}

    class WebsiteAnalyzer:
        def execute(self, profile):
            return WebsiteProfile(user_id=profile.user_id, url='https://example.com')

    services, _ = build_legacy_application(
        LegacyDiscovery(), 'scrape', LegacyScorer(), LegacyEnricher(),
        WebsiteAnalyzer())
    leads = services.lead_pipeline.execute(
        WorkspaceContext(user_id='user-1', workspace_id='workspace-1'),
        LeadDNA(user_id='user-1', workspace_id='workspace-1'))
    assert leads[0].name == 'Legacy lead'
