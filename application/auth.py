"""Framework-independent authentication and tenant-context boundaries."""

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

from core.domain import User
from core.ports import UserRepository, WorkspaceRepository


class AuthenticationError(PermissionError):
    """Raised when a request has no valid authenticated identity."""


class AuthorizationError(PermissionError):
    """Raised when an identity cannot access the requested tenant."""


@dataclass(frozen=True)
class AuthenticatedIdentity:
    provider: str
    subject: str
    email: str | None = None
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.subject.strip():
            raise ValueError('provider and subject are required')


@dataclass(frozen=True)
class AuthContext:
    identity: AuthenticatedIdentity
    user: User

    @property
    def authenticated(self) -> bool:
        return True

    @property
    def user_id(self) -> str:
        return self.user.id


@dataclass(frozen=True)
class WorkspaceContext:
    user_id: str
    workspace_id: str
    authenticated: bool = True

    def require_authenticated(self) -> None:
        if not self.authenticated:
            raise AuthenticationError('authentication is required')


class Authenticator(Protocol):
    def authenticate(self, token: str | None) -> AuthenticatedIdentity | None:
        ...


class SupabaseAuthAdapter:
    """Maps verified Supabase claims without storing passwords.

    Token verification is injected so the application remains independent of
    a Supabase SDK and tests never need network access or credentials.
    """

    def __init__(self, verify_token):
        self._verify_token = verify_token

    def authenticate(self, token: str | None) -> AuthenticatedIdentity | None:
        if not token:
            return None
        try:
            claims = self._verify_token(token)
        except Exception:
            return None
        if not claims:
            return None
        subject = claims.get('sub')
        if not subject:
            return None
        return AuthenticatedIdentity(
            provider='supabase',
            subject=str(subject),
            email=claims.get('email'),
            display_name=claims.get('user_metadata', {}).get('name')
            if isinstance(claims.get('user_metadata'), dict) else None,
        )


class SupabaseJWTVerifier:
    """Verify Supabase JWTs against the project's configured JWKS endpoint."""

    def __init__(
        self,
        project_url: str,
        *,
        jwks_url: str | None = None,
        audience: str = 'authenticated',
        key_client=None,
    ):
        if not project_url.startswith('https://'):
            raise ValueError('Supabase project URL is required')
        try:
            import jwt
            from jwt import PyJWKClient
        except ImportError as exc:
            raise RuntimeError(
                'PyJWT with cryptography support is required') from exc
        self._jwt = jwt
        resolved_jwks_url = jwks_url or urljoin(
                project_url.rstrip('/') + '/',
                'auth/v1/.well-known/jwks.json',
            )
        if not resolved_jwks_url.startswith('https://'):
            raise ValueError('Supabase JWKS URL must use HTTPS')
        self._keys = key_client or PyJWKClient(resolved_jwks_url)
        self._issuer = urljoin(project_url.rstrip('/') + '/', 'auth/v1')
        self._audience = audience

    def __call__(self, token: str) -> dict:
        signing_key = self._keys.get_signing_key_from_jwt(token)
        return self._jwt.decode(
            token,
            signing_key.key,
            algorithms=['RS256', 'ES256'],
            audience=self._audience,
            issuer=self._issuer,
            options={'require': ['exp', 'sub', 'iat']},
        )


class UserResolver:
    def __init__(self, repository: UserRepository):
        self._repository = repository

    def resolve(self, identity: AuthenticatedIdentity) -> User:
        user = self._repository.get_by_auth_subject(
            identity.provider, identity.subject)
        if user is None:
            raise AuthenticationError('authenticated identity is not registered')
        return user


class WorkspaceResolver:
    def __init__(self, repository: WorkspaceRepository):
        self._repository = repository

    def resolve(self, context: AuthContext, workspace_id: str | None = None) -> WorkspaceContext:
        requested_id = workspace_id or self._repository.get_default_for_user(
            context.user_id)
        if not requested_id:
            raise AuthorizationError('no workspace is available for this user')
        workspace = self._repository.get(requested_id)
        if workspace is None or workspace.owner_user_id != context.user_id:
            raise AuthorizationError('workspace access is not allowed')
        return WorkspaceContext(
            user_id=context.user_id,
            workspace_id=workspace.id,
        )


def require_workspace(context: WorkspaceContext) -> WorkspaceContext:
    context.require_authenticated()
    if not context.workspace_id:
        raise AuthorizationError('workspace context is required')
    return context
