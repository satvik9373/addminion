"""Adapters that translate current implementations to domain contracts."""

from .legacy import (
    LegacyDiscoveryAdapter,
    LegacyEnrichmentAdapter,
    LegacyQualificationAdapter,
    LegacySqliteRepository,
)
from .in_memory import (
    InMemoryEnrichmentResultRepository,
    InMemoryLeadRepository,
    InMemoryOnboardingProfileRepository,
    InMemoryQualificationResultRepository,
    InMemoryUserRepository,
    InMemoryWorkspaceRepository,
)
from .flask_auth import require_authentication

__all__ = [
    'LegacyDiscoveryAdapter',
    'LegacyQualificationAdapter',
    'LegacyEnrichmentAdapter',
    'LegacySqliteRepository',
    'InMemoryUserRepository',
    'InMemoryWorkspaceRepository',
    'InMemoryOnboardingProfileRepository',
    'InMemoryLeadRepository',
    'InMemoryQualificationResultRepository',
    'InMemoryEnrichmentResultRepository',
    'require_authentication',
]
