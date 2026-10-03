"""
Flask blueprints: HTML pages + JSON API for the dashboard.

Two independent pipelines are exposed:
    Lead Generation  (/leadgen)   — scrape/parse/score/categorize/sheets
    Outreach         (/outreach)  — qualified leads -> queue -> email/IG

Both share the existing SQLite database through one LeadGenSystem. No secrets
are ever rendered (see /api/health — booleans only).
"""

import logging

from flask import Blueprint, current_app, jsonify, redirect, render_template, request

logger = logging.getLogger(__name__)

pages = Blueprint('pages', __name__)
api = Blueprint('api', __name__)


def _system():
    return current_app.extensions['system']


def _db():
    return _system().db


def _leadgen():
    return current_app.extensions['leadgen_runner']


def _outreach():
    return current_app.extensions['outreach_runner']


def _sched(name):
    return current_app.extensions[f'scheduler_{name}']


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------

@pages.route('/')
def index():
    return render_template('index.html')


@pages.route('/leadgen')
def leadgen():
    return render_template('leadgen.html')


@pages.route('/outreach')
def outreach():
    return render_template('outreach.html')


@pages.route('/leads')
def leads():
    return render_template('leads.html')


@pages.route('/pipeline')
def pipeline_old():
    return redirect('/leadgen', code=301)


# ----------------------------------------------------------------------
# API — Overview / health
# ----------------------------------------------------------------------

@api.route('/api/overview')
def overview():
    db = _db()
    lg, og = _leadgen(), _outreach()
    recent = db.get_run_history(limit=10)
    last_leadgen = next((r for r in recent if r.get('run_type', '').startswith('leadgen')), None)
    last_outreach = next((r for r in recent if r.get('run_type', '').startswith('outreach')), None)
    s_lg, s_og = _sched('leadgen').status(), _sched('outreach').status()
    try:
        health = _system().validate_setup()
    except Exception as e:
        health = [f"validate_setup failed: {e}"]

    return jsonify({
        'total_leads': db.count_total_leads(),
        'categories': db.count_leads_by_category(),
        'qualified': db.count_qualified_leads(),
        'contacted': db.count_contacted_leads(),
        'replies': db.count_replies(),
        # Contact availability (phone/email/instagram are first-class channels)
        'total_contactable': db.count_contactable_leads(),
        'leads_with_phone': db.count_leads_with_phone(),
        'leads_with_email': db.count_leads_with_email(),
        'leads_with_instagram': db.count_leads_with_instagram(),
        'leads_with_no_contact': db.count_leads_without_contact(),
        'leadgen': {
            'running': lg.running,
            'last_run': last_leadgen,
            'next_scheduled_run': s_lg.get('next_run_at'),
            'scheduler_enabled': s_lg.get('enabled', False),
        },
        'outreach': {
            'running': og.running,
            'mode': og.get_mode(),
            'channels': og.get_channels(),
            'stats': db.get_outreach_stats(),
            'last_run': last_outreach,
            'next_scheduled_run': s_og.get('next_run_at'),
            'scheduler_enabled': s_og.get('enabled', False),
        },
        'health_issues': health,
        'health_ok': not health,
    })


@api.route('/api/health')
def health():
    """Sanitized health — booleans/counts only, never secret values."""
    sys = _system()
    issues = []
    try:
        issues = sys.validate_setup()
    except Exception as e:
        issues = [f"validate_setup failed: {e}"]
    try:
        db_ok = sys.db.get_run_history(limit=1) is not None
    except Exception:
        db_ok = False

    return jsonify({
        'healthy': not issues and db_ok,
        'db_ok': db_ok,
        'config_ok': not issues,
        'issue_count': len(issues),
        'issues': issues,  # labels only, no credential values
    })


# ----------------------------------------------------------------------
# API — Lead Generation pipeline
# ----------------------------------------------------------------------

@api.route('/api/leadgen/status')
def leadgen_status():
    return jsonify(_leadgen().state.snapshot())


@api.route('/api/leadgen/run', methods=['POST'])
def leadgen_run():
    result = _leadgen().start(run_type='manual')
    return jsonify(result), 200 if result.get('ok') else 409


@api.route('/api/leadgen/stop', methods=['POST'])
def leadgen_stop():
    result = _leadgen().stop()
    return jsonify(result), 200 if result.get('ok') else 409


@api.route('/api/leadgen/history')
def leadgen_history():
    limit = request.args.get('limit', default=20, type=int)
    runs = _db().get_run_history(limit=min(limit, 100))
    return jsonify({'runs': [r for r in runs if r.get('run_type', '').startswith('leadgen')]})


# ----------------------------------------------------------------------
# API — Outreach pipeline
# ----------------------------------------------------------------------

@api.route('/api/outreach/status')
def outreach_status():
    snap = _outreach().snapshot()
    snap['stats'] = _db().get_outreach_stats()
    return jsonify(snap)


@api.route('/api/outreach/run', methods=['POST'])
def outreach_run():
    result = _outreach().start(run_type='manual')
    return jsonify(result), 200 if result.get('ok') else 409


@api.route('/api/outreach/stop', methods=['POST'])
def outreach_stop():
    result = _outreach().stop()
    return jsonify(result), 200 if result.get('ok') else 409


@api.route('/api/outreach/history')
def outreach_history():
    limit = request.args.get('limit', default=20, type=int)
    runs = _db().get_run_history(limit=min(limit, 100))
    return jsonify({'runs': [r for r in runs if r.get('run_type', '').startswith('outreach')]})


@api.route('/api/outreach/mode', methods=['GET', 'POST'])
def outreach_mode():
    if request.method == 'GET':
        return jsonify({'mode': _outreach().get_mode()})
    body = request.get_json(silent=True) or {}
    return jsonify(_outreach().set_mode(body.get('mode')))


@api.route('/api/outreach/channels', methods=['POST'])
def outreach_channels():
    body = request.get_json(silent=True) or {}
    return jsonify(_outreach().set_channels(body))


@api.route('/api/outreach/phone/complete', methods=['POST'])
def outreach_phone_complete():
    """Manually mark a phone call task as completed (idempotent)."""
    body = request.get_json(silent=True) or {}
    lead_id = body.get('lead_id')
    result = _outreach().mark_phone_called(lead_id)
    return jsonify(result), 200 if result.get('ok') else 400


@api.route('/api/outreach/phone/skip', methods=['POST'])
def outreach_phone_skip():
    """Manually skip a phone call task (kept retryable)."""
    body = request.get_json(silent=True) or {}
    lead_id = body.get('lead_id')
    result = _outreach().skip_phone_task(lead_id)
    return jsonify(result), 200 if result.get('ok') else 400


# ----------------------------------------------------------------------
# API — Schedulers (two independent, one per pipeline)
# ----------------------------------------------------------------------

@api.route('/api/scheduler/leadgen/status')
def scheduler_leadgen_status():
    return jsonify(_sched('leadgen').status())


@api.route('/api/scheduler/leadgen/enable', methods=['POST'])
def scheduler_leadgen_enable():
    return jsonify(_sched('leadgen').enable())


@api.route('/api/scheduler/leadgen/disable', methods=['POST'])
def scheduler_leadgen_disable():
    return jsonify(_sched('leadgen').disable())


@api.route('/api/scheduler/leadgen/config', methods=['POST'])
def scheduler_leadgen_config():
    return _scheduler_config('leadgen')


@api.route('/api/scheduler/outreach/status')
def scheduler_outreach_status():
    return jsonify(_sched('outreach').status())


@api.route('/api/scheduler/outreach/enable', methods=['POST'])
def scheduler_outreach_enable():
    return jsonify(_sched('outreach').enable())


@api.route('/api/scheduler/outreach/disable', methods=['POST'])
def scheduler_outreach_disable():
    return jsonify(_sched('outreach').disable())


@api.route('/api/scheduler/outreach/config', methods=['POST'])
def scheduler_outreach_config():
    return _scheduler_config('outreach')


def _scheduler_config(name):
    body = request.get_json(silent=True) or {}
    if 'frequency_hours' in body:
        return jsonify(_sched(name).set_frequency(body['frequency_hours']))
    return jsonify({'ok': False, 'error': 'frequency_hours required'}), 400


# ----------------------------------------------------------------------
# API — Leads
# ----------------------------------------------------------------------

@api.route('/api/leads')
def leads_list():
    q = request.args.get('q', type=str) or None
    source = request.args.get('source', type=str) or None
    category = request.args.get('category', type=str) or None
    status = request.args.get('status', type=str) or None
    min_score = request.args.get('min_score', type=int)
    max_score = request.args.get('max_score', type=int)
    contactable = request.args.get('contactable') == '1'
    no_contact = request.args.get('no_contact') == '1'
    has_phone = request.args.get('has_phone') == '1'
    has_email = request.args.get('has_email') == '1'
    has_instagram = request.args.get('has_instagram') == '1'
    limit = min(request.args.get('limit', default=100, type=int), 500)
    offset = request.args.get('offset', default=0, type=int)

    leads = _db().get_leads(query=q, source=source, category=category, status=status,
                            min_score=min_score, max_score=max_score,
                            contactable=contactable, no_contact=no_contact,
                            has_phone=has_phone, has_email=has_email,
                            has_instagram=has_instagram,
                            limit=limit, offset=offset)
    return jsonify({
        'leads': leads,
        'count': len(leads),
        'sources': _db().get_distinct_sources(),
    })


@api.route('/api/leads/<path:lead_id>')
def lead_detail(lead_id):
    # Lead IDs are full URLs (e.g. https://www.realtor.com/realestateagents/123).
    # The default Flask string converter cannot match slashes, so we use
    # <path:lead_id>. The JS client URL-encodes the ID; Werkzeug keeps %2F
    # encoded in the matched variable, so decode here. unquote is idempotent
    # for already-decoded values.
    import urllib.parse
    lead_id = urllib.parse.unquote(lead_id)
    lead = _db().get_lead_by_id(lead_id)
    if not lead:
        return jsonify({'error': 'Lead not found'}), 404
    lead['outreach_history'] = _db().get_outreach_history(lead_id)
    return jsonify(lead)
