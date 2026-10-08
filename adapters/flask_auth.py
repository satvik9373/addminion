"""Thin Flask adapter for the framework-independent auth boundary."""

from functools import wraps
import logging
from typing import Callable

from flask import g, request

from application.auth import (
    AuthContext,
    AuthenticationError,
    Authenticator,
    UserResolver,
    WorkspaceResolver,
)
from application.provisioning import UserProvisioningService

logger = logging.getLogger(__name__)


def require_authentication(
    authenticator: Authenticator,
    user_resolver: UserResolver,
) -> Callable:
    """Attach AuthContext to ``flask.g`` and fail closed with 401."""
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            header = request.headers.get('Authorization', '')
            token = header[7:].strip() if header.startswith('Bearer ') else None
            identity = authenticator.authenticate(token)
            if identity is None:
                return {'error': 'authentication required'}, 401
            try:
                g.auth_context = AuthContext(
                    identity=identity,
                    user=user_resolver.resolve(identity),
                )
            except AuthenticationError:
                return {'error': 'authentication required'}, 401
            return view(*args, **kwargs)
        return wrapped
    return decorator


def require_provisioned_context(
    authenticator: Authenticator,
    provisioning: UserProvisioningService,
    workspaces: WorkspaceResolver,
) -> Callable:
    """Authenticate, provision the local account, and attach tenant context."""
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            header = request.headers.get('Authorization', '')
            token = header[7:].strip() if header.startswith('Bearer ') else None
            identity = authenticator.authenticate(token)
            if identity is None:
                return {'error': 'authentication required'}, 401
            try:
                account = provisioning.execute(identity)
                auth_context = AuthContext(identity, account.user)
                workspace_id = request.headers.get('X-Workspace-ID')
                g.auth_context = auth_context
                g.workspace_context = workspaces.resolve(
                    auth_context, workspace_id)
            except AuthenticationError:
                return {'error': 'authentication required'}, 401
            except PermissionError:
                return {'error': 'workspace access is not allowed'}, 403
            except ValueError as exc:
                return {'error': 'invalid authentication context'}, 401
            except Exception:
                logger.exception('Protected request setup failed')
                return {'error': 'request could not be authenticated'}, 500
            return view(*args, **kwargs)
        return wrapped
    return decorator
