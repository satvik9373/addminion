"""Stable boundaries between the application and replaceable adapters.

These protocols describe the responsibilities of the current implementation
without changing its runtime behavior. Future product flows can depend on
these ports instead of importing a specific provider or storage adapter.
"""

from typing import Any, Mapping, Protocol, Sequence

from .domain import (
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


class LeadDiscoveryProvider(Protocol):
    """A provider that discovers raw lead records."""

    def discover(self, lead_dna: LeadDNA) -> Sequence[Lead]:
        ...


class LeadScoringService(Protocol):
    """A service that calculates qualification data for a lead."""

    def score_lead(self, lead: Lead) -> QualificationResult:
        ...


class ContactEnrichmentProvider(Protocol):
    """A provider that adds or verifies contact information."""

    def enrich(self, lead: Lead) -> EnrichmentResult:
        ...


class LeadRepository(Protocol):
    """Common persistence lifecycle boundary."""

    def connect(self) -> Any:
        ...

    def create_tables(self) -> Any:
        ...


class UserRepository(Protocol):
    def save(self, user: User) -> None:
        ...

    def get(self, user_id: str) -> User | None:
        ...

    def get_by_auth_subject(self, provider: str, subject: str) -> User | None:
        ...

    def bind_identity(self, user_id: str, provider: str, subject: str) -> None:
        ...

    def provision(self, provider: str, subject: str, email: str,
                  display_name: str | None = None) -> User:
        ...

class WorkspaceRepository(Protocol):
    def save(self, workspace: Workspace) -> None:
        ...

    def get(self, workspace_id: str) -> Workspace | None:
        ...

    def get_default_for_user(self, user_id: str) -> str | None:
        ...

    def get_or_create_default(self, user_id: str) -> Workspace:
        ...

class OnboardingProfileRepository(Protocol):
    def save(self, profile: OnboardingProfile) -> None:
        ...

    def get_for_user(self, user_id: str) -> OnboardingProfile | None:
        ...


class WebsiteProfileRepository(Protocol):
    def save(self, profile: WebsiteProfile) -> None:
        ...

    def get(self, profile_id: str) -> WebsiteProfile | None:
        ...


class ICPRepository(Protocol):
    def save(self, icp: ICP) -> None:
        ...

    def get(self, icp_id: str) -> ICP | None:
        ...


class LeadDNARepository(Protocol):
    def save(self, lead_dna: LeadDNA) -> None:
        ...

    def get(self, lead_dna_id: str) -> LeadDNA | None:
        ...


class LeadRepositoryPort(Protocol):
    def save(self, lead: Lead) -> None:
        ...

    def get(self, lead_id: str) -> Lead | None:
        ...


class QualificationResultRepository(Protocol):
    def save(self, result: QualificationResult) -> None:
        ...

    def get_for_lead(self, lead_id: str) -> QualificationResult | None:
        ...


class EnrichmentResultRepository(Protocol):
    def save(self, result: EnrichmentResult) -> None:
        ...

    def get_for_lead(self, lead_id: str) -> EnrichmentResult | None:
        ...


class OnboardingProfileBuilder(Protocol):
    def execute(self, user: User) -> OnboardingProfile:
        ...


class WebsiteAnalyzer(Protocol):
    def execute(self, profile: OnboardingProfile) -> WebsiteProfile:
        ...


class ExternalService(Protocol):
    """Boundary for integrations such as Sheets, email, and social APIs."""

    def authenticate(self) -> bool:
        ...
