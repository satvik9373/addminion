"""Application orchestration for profile and lead-DNA preparation."""

from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from core.domain import ICP, LeadDNA, OnboardingProfile, User, WebsiteProfile
from core.ports import (
    OnboardingProfileRepository,
    OnboardingProfileBuilder,
    WebsiteAnalyzer,
)


class OnboardingProfileService:
    def __init__(self, repository: OnboardingProfileRepository):
        self.repository = repository

    def execute(
        self,
        user: User,
        *,
        company_name: Optional[str] = None,
        website_url: Optional[str] = None,
    ) -> OnboardingProfile:
        existing = self.repository.get_for_user(user.id)
        now = datetime.now(timezone.utc)
        profile = (
            replace(
                existing,
                has_website=(
                    bool(website_url)
                    if website_url is not None else existing.has_website
                ),
                company_name=company_name if company_name is not None else existing.company_name,
                website_url=website_url if website_url is not None else existing.website_url,
                updated_at=now,
            )
            if existing
            else OnboardingProfile(
                user_id=user.id,
                has_website=bool(website_url),
                company_name=company_name,
                website_url=website_url,
                created_at=now,
                updated_at=now,
            )
        )
        self.repository.save(profile)
        return profile


class WebsiteAnalysisService:
    def __init__(self, analyzer: WebsiteAnalyzer):
        self.analyzer = analyzer

    def execute(self, profile: OnboardingProfile) -> WebsiteProfile:
        return self.analyzer.execute(profile)


class LeadDNAService:
    def __init__(self):
        pass

    def execute(
        self,
        profile: OnboardingProfile,
        website: Optional[WebsiteProfile] = None,
        icp: Optional[ICP] = None,
    ) -> LeadDNA:
        attributes = {
            'company_name': profile.company_name,
            'website_url': profile.website_url,
        }
        if website:
            attributes.update({
                'website_title': website.title,
                'website_description': website.description,
            })
        if icp:
            attributes['industries'] = tuple(icp.industries)
            attributes['locations'] = tuple(icp.locations)
            attributes['company_sizes'] = tuple(icp.company_sizes)
        return LeadDNA(
            user_id=profile.user_id,
            workspace_id=profile.workspace_id,
            icp_id=icp.id if icp else None,
            attributes=attributes,
        )
