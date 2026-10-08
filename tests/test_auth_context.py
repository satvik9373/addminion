import pytest
from flask import Flask, g, jsonify

from adapters import InMemoryUserRepository, InMemoryWorkspaceRepository
from adapters.flask_auth import require_authentication
from application.auth import (
    AuthContext,
    AuthenticatedIdentity,
    AuthenticationError,
    SupabaseAuthAdapter,
    UserResolver,
    WorkspaceResolver,
)
from core.domain import User, Workspace


def _repositories():
    users = InMemoryUserRepository()
    workspaces = InMemoryWorkspaceRepository()
    user = User(id='user-1', email='owner@example.com')
    workspace = Workspace(
        id='workspace-1', owner_user_id=user.id, name='Default')
    users.save(user)
    users.bind_identity(user.id, 'supabase', 'subject-1')
    workspaces.save(workspace)
    return users, workspaces, user, workspace


def test_supabase_adapter_maps_verified_claims_without_passwords():
    adapter = SupabaseAuthAdapter(
        lambda token: {'sub': token, 'email': 'owner@example.com'})

    identity = adapter.authenticate('subject-1')

    assert identity == AuthenticatedIdentity(
        provider='supabase', subject='subject-1',
        email='owner@example.com')


def test_missing_identity_is_rejected():
    users, _, _, _ = _repositories()

    with pytest.raises(AuthenticationError):
        UserResolver(users).resolve(
            AuthenticatedIdentity(provider='supabase', subject='unknown'))


def test_user_resolves_to_owned_default_workspace():
    users, workspaces, user, workspace = _repositories()
    identity = AuthenticatedIdentity(provider='supabase', subject='subject-1')
    auth = AuthContext(identity=identity, user=User(
        id=user.id, email=user.email, created_at=user.created_at))

    resolved = WorkspaceResolver(workspaces).resolve(auth)

    assert resolved.user_id == user.id
    assert resolved.workspace_id == workspace.id


def test_cross_workspace_access_is_rejected():
    users, workspaces, user, _ = _repositories()
    other = User(id='user-2', email='other@example.com')
    users.save(other)
    workspaces.save(Workspace(
        id='workspace-2', owner_user_id=other.id, name='Other'))
    auth = AuthContext(
        identity=AuthenticatedIdentity(
            provider='supabase', subject='subject-1'),
        user=user,
    )

    with pytest.raises(PermissionError):
        WorkspaceResolver(workspaces).resolve(auth, 'workspace-2')


def test_flask_boundary_fails_closed_and_attaches_context():
    users, _, user, _ = _repositories()
    app = Flask(__name__)
    authenticator = SupabaseAuthAdapter(
        lambda token: {'sub': token, 'email': user.email})
    resolver = UserResolver(users)

    @app.get('/protected')
    @require_authentication(authenticator, resolver)
    def protected():
        return jsonify({'user_id': g.auth_context.user_id})

    client = app.test_client()
    assert client.get('/protected').status_code == 401
    response = client.get(
        '/protected',
        headers={'Authorization': 'Bearer subject-1'},
    )
    assert response.status_code == 200
    assert response.get_json()['user_id'] == user.id
