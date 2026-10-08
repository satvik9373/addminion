"""Business-facing domain models for the future Addminion flow.

These models deliberately do not mirror the current SQLite rows or scraper
payloads. They are stable contracts for application services and contain no
framework or external-provider dependencies.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence
from uuid import uuid4


def _timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


def _require_id(value: str, field_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f'{field_name} must not be empty')
    return value


@dataclass(frozen=True)
class User:
    id: str = field(default_factory=_new_id)
    email: str = ''
    created_at: datetime = field(default_factory=_timestamp)
    display_name: Optional[str] = None

    def __post_init__(self) -> None:
        _require_id(self.id, 'id')
        if not self.email or '@' not in self.email:
            raise ValueError('email must be a valid non-empty email address')


@dataclass(frozen=True)
class Workspace:
    id: str = field(default_factory=_new_id)
    owner_user_id: str = ''
    name: str = ''
    created_at: datetime = field(default_factory=_timestamp)

    def __post_init__(self) -> None:
        _require_id(self.id, 'id')
        _require_id(self.owner_user_id, 'owner_user_id')
        if not self.name or not self.name.strip():
            raise ValueError('name must not be empty')


@dataclass(frozen=True)
class OnboardingProfile:
    id: str = field(default_factory=_new_id)
    user_id: str = ''
    workspace_id: Optional[str] = None
    has_website: bool = False
    company_name: Optional[str] = None
    website_url: Optional[str] = None
    target_niche: Optional[str] = None
    target_service: Optional[str] = None
    icp_description: Optional[str] = None
    icp_document_reference: Optional[str] = None
    completed: bool = False
    ready_for_processing: bool = False
    completed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=_timestamp)
    updated_at: datetime = field(default_factory=_timestamp)

    def __post_init__(self) -> None:
        _require_id(self.id, 'id')
        _require_id(self.user_id, 'user_id')
        if self.has_website and not self.website_url:
            raise ValueError('website_url is required when has_website is true')
        if self.website_url and not self.has_website:
            raise ValueError('has_website must be true when website_url is provided')


@dataclass(frozen=True)
class WebsiteProfile:
    id: str = field(default_factory=_new_id)
    user_id: str = ''
    workspace_id: Optional[str] = None
    url: str = ''
    title: Optional[str] = None
    description: Optional[str] = None
    analyzed_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        _require_id(self.id, 'id')
        _require_id(self.user_id, 'user_id')
        _require_id(self.url, 'url')


@dataclass(frozen=True)
class ICP:
    id: str = field(default_factory=_new_id)
    user_id: str = ''
    workspace_id: Optional[str] = None
    name: Optional[str] = None
    industries: Sequence[str] = field(default_factory=tuple)
    locations: Sequence[str] = field(default_factory=tuple)
    company_sizes: Sequence[str] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=_timestamp)

    def __post_init__(self) -> None:
        _require_id(self.id, 'id')
        _require_id(self.user_id, 'user_id')


@dataclass(frozen=True)
class LeadDNA:
    id: str = field(default_factory=_new_id)
    user_id: str = ''
    workspace_id: Optional[str] = None
    icp_id: Optional[str] = None
    attributes: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_timestamp)

    def __post_init__(self) -> None:
        _require_id(self.id, 'id')
        _require_id(self.user_id, 'user_id')


@dataclass(frozen=True)
class Lead:
    id: str = field(default_factory=_new_id)
    workspace_id: Optional[str] = None
    name: str = ''
    company_name: Optional[str] = None
    website_url: Optional[str] = None
    source: Optional[str] = None
    discovered_at: datetime = field(default_factory=_timestamp)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_id(self.id, 'id')
        _require_id(self.name, 'name')


@dataclass(frozen=True)
class QualificationResult:
    lead_id: str = ''
    workspace_id: Optional[str] = None
    qualified: bool = False
    score: Optional[float] = None
    reasons: Sequence[str] = field(default_factory=tuple)
    evaluated_at: datetime = field(default_factory=_timestamp)

    def __post_init__(self) -> None:
        _require_id(self.lead_id, 'lead_id')


@dataclass(frozen=True)
class EnrichmentResult:
    lead_id: str = ''
    workspace_id: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    social_profiles: Mapping[str, str] = field(default_factory=dict)
    sources: Sequence[str] = field(default_factory=tuple)
    enriched_at: datetime = field(default_factory=_timestamp)

    def __post_init__(self) -> None:
        _require_id(self.lead_id, 'lead_id')
