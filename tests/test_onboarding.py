from flask import Flask
import pytest

from adapters import InMemoryOnboardingProfileRepository
from adapters.flask_onboarding import create_onboarding_blueprint
from adapters.in_memory import InMemoryUserRepository, InMemoryWorkspaceRepository
from application.auth import (
    AuthenticatedIdentity,
    SupabaseAuthAdapter,
    WorkspaceResolver,
)
from application.provisioning import UserProvisioningService
from application.services import OnboardingService


def _services():
    users = InMemoryUserRepository()
    workspaces = InMemoryWorkspaceRepository()
    profiles = InMemoryOnboardingProfileRepository()
    provisioning = UserProvisioningService(users, workspaces)
    service = OnboardingService(profiles)
    authenticator = SupabaseAuthAdapter(
        lambda token: {'sub': token, 'email': 'owner@example.com'})
    resolver = WorkspaceResolver(workspaces)
    return users, workspaces, profiles, provisioning, service, authenticator, resolver


def test_first_provisioning_creates_user_and_default_workspace():
    _, _, _, provisioning, _, _, _ = _services()
    identity = AuthenticatedIdentity('supabase', 'subject-1', 'owner@example.com')

    account = provisioning.execute(identity)

    assert account.user.email == 'owner@example.com'
    assert account.workspace.owner_user_id == account.user.id


def test_provisioning_is_idempotent():
    users, workspaces, _, provisioning, _, _, _ = _services()
    identity = AuthenticatedIdentity('supabase', 'subject-1', 'owner@example.com')

    first = provisioning.execute(identity)
    second = provisioning.execute(identity)

    assert second == first
    assert len(users._items) == 1
    assert len(workspaces._items) == 1


def test_onboarding_website_and_no_website_paths():
    _, _, _, provisioning, service, _, resolver = _services()
    account = provisioning.execute(
        AuthenticatedIdentity('supabase', 'subject-1', 'owner@example.com'))
    context = resolver.resolve(
        type('Auth', (), {'user_id': account.user.id})())

    website = service.save(
        context, has_website=True, website_url='https://example.com')
    assert website.website_url == 'https://example.com'
    assert service.mark_ready(context).completed

    no_website = service.save(
        context, has_website=False, target_niche='SaaS',
        target_service='Outbound sales',
        icp_description='B2B founders')
    assert no_website.completed is False
    assert service.mark_ready(context).ready_for_processing


def test_onboarding_rejects_invalid_input_and_wrong_workspace():
    _, _, _, provisioning, service, _, resolver = _services()
    account = provisioning.execute(
        AuthenticatedIdentity('supabase', 'subject-1', 'owner@example.com'))
    context = resolver.resolve(
        type('Auth', (), {'user_id': account.user.id})())

    with pytest.raises(ValueError):
        service.save(context, has_website=True)
    with pytest.raises(ValueError):
        service.save(context, has_website=False)

    service.save(
        context, has_website=False, target_niche='SaaS')
    with pytest.raises(PermissionError):
        service.get_current(type(
            'Context', (), {
                'user_id': account.user.id,
                'workspace_id': 'other-workspace',
                'authenticated': True,
                'require_authenticated': lambda self: None,
            })())


def test_protected_onboarding_api_requires_auth_and_persists_profile():
    _, _, _, provisioning, service, authenticator, resolver = _services()
    app = Flask(__name__)
    blueprint = create_onboarding_blueprint(
        authenticator, provisioning, resolver, service)
    app.register_blueprint(blueprint)
    client = app.test_client()

    assert client.get('/api/onboarding').status_code == 401
    response = client.post(
        '/api/onboarding',
        headers={'Authorization': 'Bearer subject-1'},
        json={
            'has_website': False,
            'target_niche': 'B2B SaaS',
            'target_service': 'Lead generation',
        },
    )
    assert response.status_code == 200
    assert response.get_json()['workspace_id']

    ready = client.post(
        '/api/onboarding/ready',
        headers={'Authorization': 'Bearer subject-1'},
    )
    assert ready.status_code == 200
    assert ready.get_json()['ready_for_processing'] is True


def test_protected_onboarding_rejects_another_workspace():
    users, workspaces, _, provisioning, service, authenticator, resolver = _services()
    account = provisioning.execute(
        AuthenticatedIdentity('supabase', 'subject-1', 'owner@example.com'))
    other = provisioning.execute(
        AuthenticatedIdentity('supabase', 'subject-2', 'other@example.com'))
    app = Flask(__name__)
    app.register_blueprint(create_onboarding_blueprint(
        authenticator, provisioning, resolver, service))

    response = app.test_client().get(
        '/api/onboarding',
        headers={
            'Authorization': 'Bearer subject-1',
            'X-Workspace-ID': other.workspace.id,
        },
    )

    assert response.status_code == 403
