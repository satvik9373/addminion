"""Protected Flask endpoints for the first Addminion onboarding flow."""

import logging

from flask import Blueprint, g, jsonify, request

from adapters.flask_auth import require_provisioned_context
from application.auth import Authenticator, WorkspaceResolver
from application.provisioning import UserProvisioningService
from application.services import OnboardingService

logger = logging.getLogger(__name__)


def create_onboarding_blueprint(
    authenticator: Authenticator,
    provisioning: UserProvisioningService,
    workspace_resolver: WorkspaceResolver,
    service: OnboardingService,
) -> Blueprint:
    blueprint = Blueprint('onboarding', __name__)
    guard = require_provisioned_context(
        authenticator, provisioning, workspace_resolver)

    @blueprint.get('/api/onboarding')
    @guard
    def get_onboarding():
        try:
            profile = service.get_current(g.workspace_context)
        except Exception:
            logger.exception('Onboarding profile lookup failed')
            return jsonify({'error': 'onboarding could not be loaded'}), 500
        return jsonify(_serialize(profile) if profile else {
            'exists': False,
            'completed': False,
            'ready_for_processing': False,
        })

    @blueprint.post('/api/onboarding')
    @guard
    def save_onboarding():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({'error': 'a JSON object is required'}), 400
        try:
            profile = service.save(
                g.workspace_context,
                has_website=_boolean(body, 'has_website'),
                website_url=_text(body, 'website_url'),
                target_niche=_text(body, 'target_niche'),
                target_service=_text(body, 'target_service'),
                icp_description=_text(body, 'icp_description'),
                icp_document_reference=_text(
                    body, 'icp_document_reference'),
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        except Exception:
            logger.exception('Onboarding profile save failed')
            return jsonify({'error': 'onboarding could not be saved'}), 500
        return jsonify(_serialize(profile)), 200

    @blueprint.post('/api/onboarding/ready')
    @guard
    def mark_onboarding_ready():
        try:
            profile = service.mark_ready(g.workspace_context)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        except Exception:
            logger.exception('Onboarding completion failed')
            return jsonify({'error': 'onboarding could not be completed'}), 500
        return jsonify(_serialize(profile)), 200

    return blueprint


def _text(body: dict, name: str) -> str | None:
    value = body.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'{name} must be a string')
    value = value.strip()
    return value or None


def _boolean(body: dict, name: str) -> bool:
    value = body.get(name)
    if not isinstance(value, bool):
        raise ValueError(f'{name} must be a boolean')
    return value


def _serialize(profile) -> dict:
    return {
        'id': profile.id,
        'user_id': profile.user_id,
        'workspace_id': profile.workspace_id,
        'has_website': profile.has_website,
        'company_name': profile.company_name,
        'website_url': profile.website_url,
        'target_niche': profile.target_niche,
        'target_service': profile.target_service,
        'icp_description': profile.icp_description,
        'icp_document_reference': profile.icp_document_reference,
        'completed': profile.completed,
        'ready_for_processing': profile.ready_for_processing,
        'completed_at': (
            profile.completed_at.isoformat()
            if profile.completed_at else None
        ),
    }
