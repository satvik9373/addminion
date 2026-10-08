"""Idempotent local account provisioning from verified auth identities."""

from dataclasses import dataclass

from application.auth import AuthenticatedIdentity, AuthenticationError
from core.domain import User, Workspace
from core.ports import UserRepository, WorkspaceRepository


@dataclass(frozen=True)
class ProvisionedAccount:
    user: User
    workspace: Workspace


class UserProvisioningService:
    def __init__(
        self,
        users: UserRepository,
        workspaces: WorkspaceRepository,
    ):
        self.users = users
        self.workspaces = workspaces

    def execute(self, identity: AuthenticatedIdentity) -> ProvisionedAccount:
        existing = self.users.get_by_auth_subject(
            identity.provider, identity.subject)
        if existing is not None:
            return ProvisionedAccount(
                existing,
                self.workspaces.get_or_create_default(existing.id),
            )
        if not identity.email:
            raise AuthenticationError(
                'authenticated identity must provide an email for provisioning')
        try:
            user = self.users.provision(
                identity.provider,
                identity.subject,
                identity.email,
                identity.display_name,
            )
        except ValueError as exc:
            raise AuthenticationError(
                'authenticated identity could not be provisioned') from exc
        workspace = self.workspaces.get_or_create_default(user.id)
        return ProvisionedAccount(user, workspace)
