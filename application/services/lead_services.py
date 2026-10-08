"""Application orchestration for discovery, qualification, and enrichment."""

from typing import Sequence

from application.auth import WorkspaceContext, require_workspace
from core.domain import EnrichmentResult, Lead, LeadDNA, QualificationResult
from core.ports import (
    ContactEnrichmentProvider,
    EnrichmentResultRepository,
    LeadDiscoveryProvider,
    LeadRepositoryPort,
    LeadScoringService,
    QualificationResultRepository,
)


class LeadDiscoveryService:
    def __init__(
        self,
        provider: LeadDiscoveryProvider,
        repository: LeadRepositoryPort | None = None,
    ):
        self.provider = provider
        self.repository = repository

    def execute(self, context: WorkspaceContext, lead_dna: LeadDNA) -> Sequence[Lead]:
        require_workspace(context)
        if lead_dna.user_id != context.user_id:
            raise PermissionError('lead DNA belongs to another user')
        leads = tuple(self.provider.discover(lead_dna))
        if self.repository:
            for lead in leads:
                self.repository.save(lead)
        return leads


class LeadQualificationService:
    def __init__(
        self,
        scorer: LeadScoringService,
        repository: QualificationResultRepository | None = None,
    ):
        self.scorer = scorer
        self.repository = repository

    def execute(self, context: WorkspaceContext, lead: Lead) -> QualificationResult:
        require_workspace(context)
        if lead.workspace_id != context.workspace_id:
            raise PermissionError('lead belongs to another workspace')
        result = self.scorer.score_lead(lead)
        if self.repository:
            self.repository.save(result)
        return result


class LeadEnrichmentService:
    def __init__(
        self,
        provider: ContactEnrichmentProvider,
        repository: EnrichmentResultRepository | None = None,
    ):
        self.provider = provider
        self.repository = repository

    def execute(self, context: WorkspaceContext, lead: Lead) -> EnrichmentResult:
        require_workspace(context)
        if lead.workspace_id != context.workspace_id:
            raise PermissionError('lead belongs to another workspace')
        result = self.provider.enrich(lead)
        if self.repository:
            self.repository.save(result)
        return result


class LeadPipelineService:
    def __init__(
        self,
        discovery: LeadDiscoveryService,
        qualification: LeadQualificationService,
        enrichment: LeadEnrichmentService,
    ):
        self.discovery = discovery
        self.qualification = qualification
        self.enrichment = enrichment

    def execute(self, context: WorkspaceContext, lead_dna: LeadDNA) -> Sequence[Lead]:
        require_workspace(context)
        leads = self.discovery.execute(context, lead_dna)
        for lead in leads:
            self.qualification.execute(context, lead)
            self.enrichment.execute(context, lead)
        return leads
