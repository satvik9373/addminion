"""Application use-case contracts for the future Addminion product flow.

These contracts intentionally do not implement product behavior yet. They
define stable application-facing inputs and outputs for future adapters.
"""

from typing import Protocol, Sequence

from application.auth import WorkspaceContext
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


class BuildOnboardingProfile(Protocol):
    def execute(self, user: User) -> OnboardingProfile:
        ...


class AnalyzeWebsite(Protocol):
    def execute(self, profile: OnboardingProfile) -> WebsiteProfile:
        ...


class BuildLeadDNA(Protocol):
    def execute(self, profile: WebsiteProfile, icp: ICP) -> LeadDNA:
        ...


class DiscoverLeads(Protocol):
    def execute(self, context: WorkspaceContext, lead_dna: LeadDNA) -> Sequence[Lead]:
        ...


class QualifyLead(Protocol):
    def execute(self, context: WorkspaceContext, lead: Lead) -> QualificationResult:
        ...


class EnrichLead(Protocol):
    def execute(self, context: WorkspaceContext, lead: Lead) -> EnrichmentResult:
        ...


class RunLeadPipeline(Protocol):
    def execute(self, context: WorkspaceContext, lead_dna: LeadDNA) -> Sequence[Lead]:
        ...


__all__ = [
    'BuildOnboardingProfile',
    'AnalyzeWebsite',
    'BuildLeadDNA',
    'DiscoverLeads',
    'QualifyLead',
    'EnrichLead',
    'RunLeadPipeline',
]
