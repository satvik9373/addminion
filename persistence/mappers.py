"""Explicit PostgreSQL row/domain mappings.

Rows are consumed here and never exposed to the domain layer.
"""

import json
from typing import Any, Mapping

from core.domain import (
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


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value) if isinstance(value, str) else value


def user_from_row(row: Mapping[str, Any]) -> User:
    return User(id=str(row['id']), email=row['email'],
                display_name=row.get('display_name'),
                created_at=row['created_at'])


def workspace_from_row(row: Mapping[str, Any]) -> Workspace:
    return Workspace(id=str(row['id']),
                     owner_user_id=str(row['owner_user_id']),
                     name=row['name'], created_at=row['created_at'])


def onboarding_from_row(row: Mapping[str, Any]) -> OnboardingProfile:
    return OnboardingProfile(
        id=str(row['id']), user_id=str(row['user_id']),
        workspace_id=str(row['workspace_id']),
        has_website=bool(row.get('has_website', False)),
        company_name=row.get('company_name'),
        website_url=row.get('website_url'),
        target_niche=row.get('target_niche'),
        target_service=row.get('target_service'),
        icp_description=row.get('icp_description'),
        icp_document_reference=row.get('icp_document_reference'),
        completed=bool(row.get('completed', False)),
        ready_for_processing=bool(row.get('ready_for_processing', False)),
        completed_at=row.get('completed_at'),
        created_at=row['created_at'], updated_at=row['updated_at'])


def website_from_row(row: Mapping[str, Any]) -> WebsiteProfile:
    return WebsiteProfile(
        id=str(row['id']), user_id=str(row['user_id']),
        workspace_id=str(row['workspace_id']), url=row['url'],
        title=row.get('title'), description=row.get('description'),
        analyzed_at=row.get('analyzed_at'))


def icp_from_row(row: Mapping[str, Any]) -> ICP:
    return ICP(
        id=str(row['id']), user_id=str(row['user_id']),
        workspace_id=str(row['workspace_id']), name=row.get('name'),
        industries=tuple(_json(row.get('industries'), [])),
        locations=tuple(_json(row.get('locations'), [])),
        company_sizes=tuple(_json(row.get('company_sizes'), [])),
        created_at=row['created_at'])


def lead_dna_from_row(row: Mapping[str, Any]) -> LeadDNA:
    return LeadDNA(
        id=str(row['id']), user_id=str(row['user_id']),
        workspace_id=str(row['workspace_id']),
        icp_id=str(row['icp_id']) if row.get('icp_id') else None,
        attributes=_json(row.get('attributes'), {}),
        created_at=row['created_at'])


def lead_from_row(row: Mapping[str, Any]) -> Lead:
    return Lead(
        id=str(row['id']), workspace_id=str(row['workspace_id']),
        name=row['name'], company_name=row.get('company_name'),
        website_url=row.get('website_url'), source=row.get('source'),
        discovered_at=row['discovered_at'],
        metadata=_json(row.get('metadata'), {}))


def qualification_from_row(row: Mapping[str, Any]) -> QualificationResult:
    return QualificationResult(
        lead_id=str(row['lead_id']),
        workspace_id=str(row['workspace_id']),
        qualified=bool(row['qualified']), score=row.get('score'),
        reasons=tuple(_json(row.get('reasons'), [])),
        evaluated_at=row['evaluated_at'])


def enrichment_from_row(row: Mapping[str, Any]) -> EnrichmentResult:
    return EnrichmentResult(
        lead_id=str(row['lead_id']),
        workspace_id=str(row['workspace_id']), email=row.get('email'),
        phone=row.get('phone'),
        social_profiles=_json(row.get('social_profiles'), {}),
        sources=tuple(_json(row.get('sources'), [])),
        enriched_at=row['enriched_at'])
