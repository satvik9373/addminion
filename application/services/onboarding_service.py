"""Application service for authenticated user onboarding."""

from dataclasses import replace
from datetime import datetime, timezone
from typing import Optional

from application.auth import WorkspaceContext, require_workspace
from core.domain import OnboardingProfile
from core.ports import OnboardingProfileRepository


class OnboardingService:
    def __init__(self, repository: OnboardingProfileRepository):
        self.repository = repository

    def get_current(self, context: WorkspaceContext) -> OnboardingProfile | None:
        require_workspace(context)
        profile = self.repository.get_for_user(context.user_id)
        if profile and profile.workspace_id != context.workspace_id:
            raise PermissionError('onboarding belongs to another workspace')
        return profile

    def save(
        self,
        context: WorkspaceContext,
        *,
        has_website: bool,
        website_url: Optional[str] = None,
        target_niche: Optional[str] = None,
        target_service: Optional[str] = None,
        icp_description: Optional[str] = None,
        icp_document_reference: Optional[str] = None,
    ) -> OnboardingProfile:
        require_workspace(context)
        if has_website and not website_url:
            raise ValueError('website_url is required when has_website is true')
        if not has_website and website_url:
            raise ValueError('website_url is only valid for website onboarding')
        if not has_website and not target_niche and not target_service and not icp_description and not icp_document_reference:
            raise ValueError('provide niche, service, or ICP information')

        existing = self.get_current(context)
        now = datetime.now(timezone.utc)
        values = dict(
            has_website=has_website,
            website_url=website_url,
            target_niche=target_niche,
            target_service=target_service,
            icp_description=icp_description,
            icp_document_reference=icp_document_reference,
            completed=False,
            ready_for_processing=False,
            completed_at=None,
            updated_at=now,
        )
        profile = (
            replace(existing, **values)
            if existing else OnboardingProfile(
                user_id=context.user_id,
                workspace_id=context.workspace_id,
                created_at=now,
                **values,
            )
        )
        self.repository.save(profile)
        return profile

    def mark_ready(self, context: WorkspaceContext) -> OnboardingProfile:
        require_workspace(context)
        profile = self.get_current(context)
        if profile is None:
            raise ValueError('onboarding profile does not exist')
        if not self._is_complete(profile):
            raise ValueError('onboarding information is incomplete')
        now = datetime.now(timezone.utc)
        updated = replace(
            profile,
            completed=True,
            ready_for_processing=True,
            completed_at=now,
            updated_at=now,
        )
        self.repository.save(updated)
        return updated

    @staticmethod
    def _is_complete(profile: OnboardingProfile) -> bool:
        if profile.has_website:
            return bool(profile.website_url)
        return bool(
            profile.target_niche
            or profile.target_service
            or profile.icp_description
            or profile.icp_document_reference
        )
