"""
Web Dashboard for LeadGen — Flask app factory.

Layered on top of the existing LeadGenSystem; never modifies it.

Architecture:
    LeadGenerationRunner  (scrape -> parse -> score -> categorize -> sheets)
    OutreachRunner        (qualified leads -> queue -> email/IG, dry-run/live)
    Two independent schedulers, one per runner, both default OFF.

Binds to 127.0.0.1 by default (local-only).
"""

import logging
import os
import secrets

from flask import Flask

logger = logging.getLogger(__name__)

DEFAULT_PORT = int(os.environ.get('DASHBOARD_PORT', '5001'))


def create_app(config_path: str = None, *, onboarding_dependencies=None) -> Flask:
    """Build the Flask app with two runners + two schedulers wired up."""
    from application.legacy_pipeline import LeadGenSystem
    from .leadgen_runner import LeadGenerationRunner
    from .outreach_runner import OutreachRunner
    from .scheduler import SchedulerManager

    app = Flask(__name__)
    app.secret_key = secrets.token_hex(16)  # local session signing, not auth

    # One shared LeadGenSystem; both runners read/write the same DB but are
    # never connected to each other.
    system = LeadGenSystem()
    if getattr(system.db, 'connection', None) is None:
        system.db.connect()
    system.db.create_tables()

    leadgen_runner = LeadGenerationRunner(system)
    outreach_runner = OutreachRunner(system, config_path='data/outreach_config.json')

    # Two completely independent schedulers (separate config files).
    scheduler_leadgen = SchedulerManager(
        leadgen_runner, config_path=config_path or 'data/scheduler_leadgen.json')
    scheduler_outreach = SchedulerManager(
        outreach_runner, config_path='data/scheduler_outreach.json')
    scheduler_leadgen.resume_after_restart()
    scheduler_outreach.resume_after_restart()

    app.extensions['system'] = system
    app.extensions['leadgen_runner'] = leadgen_runner
    app.extensions['outreach_runner'] = outreach_runner
    app.extensions['scheduler_leadgen'] = scheduler_leadgen
    app.extensions['scheduler_outreach'] = scheduler_outreach

    from .routes import pages, api
    app.register_blueprint(pages)
    app.register_blueprint(api)
    if onboarding_dependencies is not None:
        from .onboarding import register_onboarding_api
        register_onboarding_api(app, onboarding_dependencies)

    return app


def create_production_app(config_path: str = None) -> Flask:
    """Create the dashboard with production PostgreSQL/auth onboarding wiring."""
    from application.composition import build_production_onboarding_dependencies
    return create_app(
        config_path,
        onboarding_dependencies=build_production_onboarding_dependencies(),
    )


def main():
    """CLI entry: python -m dashboard"""
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app = create_app()
    host = os.environ.get('DASHBOARD_HOST', '127.0.0.1')
    print(f"\n  LeadGen Dashboard  ->  http://{host}:{DEFAULT_PORT}\n")
    print("    Lead Generation + Outreach pipelines (schedulers default OFF)\n")
    # Reloader off: it would spawn a second process and duplicate the schedulers.
    app.run(host=host, port=DEFAULT_PORT, threaded=True, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
