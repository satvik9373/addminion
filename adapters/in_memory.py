"""In-memory repository implementations for application-level testing."""

from typing import Dict

from core.domain import (
    EnrichmentResult,
    Lead,
    OnboardingProfile,
    QualificationResult,
    User,
    Workspace,
)


class InMemoryUserRepository:
    def __init__(self):
        self._items: Dict[str, User] = {}
        self._identities: Dict[tuple[str, str], str] = {}

    def save(self, user: User) -> None:
        self._items[user.id] = user

    def get(self, user_id: str) -> User | None:
        return self._items.get(user_id)

    def get_by_auth_subject(self, provider: str, subject: str) -> User | None:
        user_id = self._identities.get((provider, subject))
        return self.get(user_id) if user_id else None

    def bind_identity(self, user_id: str, provider: str, subject: str) -> None:
        if user_id not in self._items:
            raise ValueError('cannot bind identity to unknown user')
        self._identities[(provider, subject)] = user_id

    def provision(self, provider: str, subject: str, email: str,
                  display_name: str | None = None) -> User:
        existing = self.get_by_auth_subject(provider, subject)
        if existing:
            return existing
        user = User(email=email, display_name=display_name)
        self.save(user)
        self.bind_identity(user.id, provider, subject)
        return user


class InMemoryWorkspaceRepository:
    def __init__(self):
        self._items: Dict[str, Workspace] = {}

    def save(self, workspace: Workspace) -> None:
        self._items[workspace.id] = workspace

    def get(self, workspace_id: str) -> Workspace | None:
        return self._items.get(workspace_id)

    def get_default_for_user(self, user_id: str) -> str | None:
        workspace = next(
            (item for item in self._items.values()
             if item.owner_user_id == user_id),
            None,
        )
        return workspace.id if workspace else None

    def get_or_create_default(self, user_id: str) -> Workspace:
        workspace_id = self.get_default_for_user(user_id)
        if workspace_id:
            workspace = self.get(workspace_id)
            if workspace:
                return workspace
        workspace = Workspace(owner_user_id=user_id, name='Default Workspace')
        self.save(workspace)
        return workspace

class InMemoryOnboardingProfileRepository:
    def __init__(self):
        self._items: Dict[str, OnboardingProfile] = {}

    def save(self, profile: OnboardingProfile) -> None:
        self._items[profile.id] = profile

    def get_for_user(self, user_id: str) -> OnboardingProfile | None:
        return next(
            (profile for profile in self._items.values()
             if profile.user_id == user_id),
            None,
        )


class InMemoryLeadRepository:
    def __init__(self):
        self._items: Dict[str, Lead] = {}

    def save(self, lead: Lead) -> None:
        self._items[lead.id] = lead

    def get(self, lead_id: str) -> Lead | None:
        return self._items.get(lead_id)


class InMemoryQualificationResultRepository:
    def __init__(self):
        self._items: Dict[str, QualificationResult] = {}

    def save(self, result: QualificationResult) -> None:
        self._items[result.lead_id] = result

    def get_for_lead(self, lead_id: str) -> QualificationResult | None:
        return self._items.get(lead_id)


class InMemoryEnrichmentResultRepository:
    def __init__(self):
        self._items: Dict[str, EnrichmentResult] = {}

    def save(self, result: EnrichmentResult) -> None:
        self._items[result.lead_id] = result

    def get_for_lead(self, lead_id: str) -> EnrichmentResult | None:
        return self._items.get(lead_id)
