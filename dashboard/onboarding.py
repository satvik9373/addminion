"""Optional composition hook for protected onboarding API routes."""

from adapters.flask_onboarding import create_onboarding_blueprint


def register_onboarding_api(app, dependencies) -> None:
    """Register onboarding routes from explicitly injected dependencies."""
    blueprint = create_onboarding_blueprint(
        dependencies.authenticator,
        dependencies.provisioning,
        dependencies.workspace_resolver,
        dependencies.service,
    )
    app.register_blueprint(blueprint)
