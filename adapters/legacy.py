"""Small adapters around the existing lead-generation implementations.

The adapters are intentionally conservative: they translate at the boundary
and leave the legacy provider behavior untouched.
"""

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from core.domain import EnrichmentResult, Lead, LeadDNA, QualificationResult
from core.mappers import (
    enrichment_result_from_mapping,
    lead_from_mapping,
    qualification_result_from_mapping,
)


@dataclass
class LegacyDiscoveryAdapter:
    provider: Any
    method_name: str

    def discover(self, lead_dna: LeadDNA) -> Sequence[Lead]:
        method: Callable[..., Sequence[Mapping[str, Any]]] = getattr(
            self.provider, self.method_name)
        raw_leads = method()
        return [lead_from_mapping(raw, lead_dna.workspace_id) for raw in raw_leads]


@dataclass
class LegacyQualificationAdapter:
    scorer: Any

    def score_lead(self, lead: Lead) -> QualificationResult:
        raw = self.scorer.score_lead(dict(lead.metadata))
        return qualification_result_from_mapping(lead.id, raw, lead.workspace_id)


@dataclass
class LegacyEnrichmentAdapter:
    enricher: Any

    def enrich(self, lead: Lead) -> EnrichmentResult:
        raw = self.enricher.enrich_lead(dict(lead.metadata))
        return enrichment_result_from_mapping(lead.id, raw, lead.workspace_id)


@dataclass
class LegacySqliteRepository:
    """Compatibility boundary; persistence remains dictionary-based for now."""

    database: Any

    def connect(self) -> Any:
        return self.database.connect()

    def create_tables(self) -> Any:
        return self.database.create_tables()

    def save(self, lead: Lead, qualified: Mapping[str, Any] | None = None) -> Any:
        return self.database.save_lead(dict(lead.metadata), dict(qualified or {}))

    def get(self, lead_id: str) -> Lead | None:
        raw = self.database.get_lead_by_id(lead_id)
        return lead_from_mapping(raw) if raw else None
