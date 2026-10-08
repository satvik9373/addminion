"""Explicit translations for the current dictionary-based implementations."""

from typing import Any, Mapping

from core.domain import EnrichmentResult, Lead, QualificationResult


def lead_from_mapping(raw: Mapping[str, Any], workspace_id: str | None = None) -> Lead:
    name = str(raw.get('name') or raw.get('full_name') or raw.get('title') or 'Unnamed lead')
    return Lead(
        id=str(raw.get('id') or raw.get('profile_url') or name),
        workspace_id=workspace_id,
        name=name,
        company_name=raw.get('company_name') or raw.get('brokerage'),
        website_url=raw.get('website') or raw.get('website_url') or raw.get('profile_url'),
        source=raw.get('source'),
        metadata=dict(raw),
    )


def qualification_result_from_mapping(
    lead_id: str,
    raw: Mapping[str, Any],
    workspace_id: str | None = None,
) -> QualificationResult:
    score = raw.get('score')
    if score is None:
        score = raw.get('total_score')
    return QualificationResult(
        lead_id=lead_id,
        workspace_id=workspace_id,
        qualified=bool(raw.get('qualified', False)),
        score=float(score) if score is not None else None,
        reasons=tuple(raw.get('triggers') or raw.get('reasons') or ()),
    )


def enrichment_result_from_mapping(
    lead_id: str,
    raw: Mapping[str, Any],
    workspace_id: str | None = None,
) -> EnrichmentResult:
    social_profiles = {
        key: str(raw[key])
        for key in ('instagram', 'linkedin')
        if raw.get(key)
    }
    return EnrichmentResult(
        lead_id=lead_id,
        workspace_id=workspace_id,
        email=raw.get('email'),
        phone=raw.get('phone'),
        social_profiles=social_profiles,
        sources=tuple(raw.get('sources') or ()),
    )
