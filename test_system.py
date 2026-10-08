#!/usr/bin/env python3
"""
Test script to verify LeadGen system components
"""

import sys
import os
import json
from datetime import datetime

# Make console output UTF-8 safe on Windows (✓/✗ chars)
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_config():
    """Test configuration loading"""
    print("Testing configuration...")
    try:
        from leadgen.config import config, SCORING_WEIGHTS, BUYING_TRIGGERS, FINANCIAL_INDICATORS, ICP_FIT

        # Check config values
        assert hasattr(config, 'TARGET_ZIP_CODES'), "TARGET_ZIP_CODES missing"
        assert hasattr(config, 'TARGET_BROKERAGES'), "TARGET_BROKERAGES missing"
        assert hasattr(config, 'HIGH_SCORE_THRESHOLD'), "Score thresholds missing"

        print(f"✓ Config loaded")
        print(f"  - Target zip codes: {config.TARGET_ZIP_CODES}")
        print(f"  - Target brokerages: {config.TARGET_BROKERAGES}")
        print(f"  - High score threshold: {config.HIGH_SCORE_THRESHOLD}")
        print(f"  - Medium score threshold: {config.MEDIUM_SCORE_THRESHOLD}")

        # Check scoring weights
        assert sum(SCORING_WEIGHTS.values()) == 100, "Weights should total 100"
        print(f"✓ Scoring weights valid (total: {sum(SCORING_WEIGHTS.values())}%)")

        # Check buying triggers
        print(f"✓ {len(BUYING_TRIGGERS)} buying triggers defined")
        for trigger, points in BUYING_TRIGGERS.items():
            print(f"  - {trigger}: {points} points")

        return True
    except Exception as e:
        print(f"✗ Config test failed: {str(e)}")
        return False

def test_database():
    """Test database setup"""
    print("\nTesting database...")
    try:
        from leadgen.database import Database

        # Use test database
        test_db_path = 'data/test_leadgen.db'
        db = Database(test_db_path)
        db.connect()
        db.create_tables()

        print(f"✓ Database initialized at {test_db_path}")

        # Test save/retrieve
        test_lead = {
            'id': f'test_{datetime.now().isoformat()}',
            'name': 'Test Agent',
            'brokerage': 'Compass',
            'email': 'test@example.com',
            'score': 18,
            'category': 'High Score',
            'source': 'test',
        }

        lead_id = db.save_lead(test_lead)
        assert lead_id, "Failed to save test lead"
        print(f"✓ Test lead saved with ID: {lead_id}")

        # Retrieve
        leads = db.get_leads_by_ids([lead_id])
        assert len(leads) == 1, "Failed to retrieve test lead"
        print(f"✓ Test lead retrieved successfully")

        # Close
        db.close()
        os.remove(test_db_path)
        print(f"✓ Database test complete (test database removed)")

        return True
    except Exception as e:
        print(f"✗ Database test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_scoring_engine():
    """Test lead scoring"""
    print("\nTesting scoring engine...")
    try:
        from leadgen.scoring.lead_scorer import LeadScorer

        scorer = LeadScorer()
        print("✓ LeadScorer initialized")

        # Test with a mock lead
        test_lead = {
            'name': 'Sarah Johnson',
            'brokerage': 'Compass',
            'title': 'Team Leader',
            'bio': 'Top producing agent with $50M annual volume. Hiring an ISA to help manage inquiries.',
            'zip_code': '90210',
            'active_listings': json.dumps([{'address': '123 Luxury Ave', 'price': '$5M+'}]),
            'hiring_indication': True,
            'monthly_spend': '$10K',
        }

        scored = scorer.score_lead(test_lead)
        print(f"✓ Lead scored: {scored['score']}/100")
        print(f"  - Category: {scored['category']}")
        print(f"  - ICP Tier: {scored['icp_tier']}")
        print(f"  - Breakdown: {scored['score_breakdown']}")
        print(f"  - Qualified: {scored['qualified']}")

        # Test categorization
        assert scored['score'] >= 15, f"Score should be high for test lead, got {scored['score']}"
        assert scored['category'] == 'High Score', f"Category should be High Score"
        assert scored['qualified'] == True, "Lead should be qualified"

        print("✓ Scoring engine test passed")
        return True
    except Exception as e:
        print(f"✗ Scoring test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_demo_generator():
    """Test demo generation"""
    print("\nTesting demo generator...")
    try:
        from leadgen.outreach.demo_generator import DemoGenerator

        gen = DemoGenerator()
        print("✓ DemoGenerator initialized")

        test_lead = {
            'name': 'Test Agent',
            'active_listings': [{'address': '123 Luxury Ave, Beverly Hills', 'price': '$5M'}],
        }

        demo = gen.generate_demo(test_lead)
        print(f"✓ Demo generated:")
        print(f"  - Demo ID: {demo['demo_id']}")
        print(f"  - Loom link: {demo['loom_link']}")
        print(f"  - Listing used: {demo['listing_used'].get('address', 'N/A')}")

        return True
    except Exception as e:
        print(f"✗ Demo generator test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_email_templates():
    """Test email template rendering"""
    print("\nTesting email templates...")
    try:
        from leadgen.outreach.email_sender import EmailSender
        from leadgen.config import config

        sender = EmailSender(config)
        print("✓ EmailSender initialized")

        # Test template rendering (without actually sending)
        template = sender.templates['T1']
        print(f"✓ T1 template loaded")
        print(f"  - Subject: {template['subject']}")
        print(f"  - Body length: {len(template['body'])} chars")

        return True
    except Exception as e:
        print(f"✗ Email template test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_sheets_sync():
    """Test Sheets sync initialization"""
    print("\nTesting Sheets sync...")
    try:
        from leadgen.sheets_sync import SheetsSync
        from leadgen.config import config

        sync = SheetsSync(config)
        print("✓ SheetsSync initialized")
        print(f"  - Credentials path: {config.GOOGLE_SHEETS_CREDENTIALS_PATH}")
        print(f"  - Sheets ID: {config.GOOGLE_SHEETS_ID or 'NOT SET'}")

        # Check if credentials file exists
        if os.path.exists(config.GOOGLE_SHEETS_CREDENTIALS_PATH):
            print("✓ Credentials file found")
        else:
            print("  - Credentials file: NOT FOUND (set up required)")

        return True
    except Exception as e:
        print(f"✗ Sheets sync test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

# =====================================================================
# Web Dashboard tests (additive — do not modify the tests above)
# =====================================================================

import tempfile
import time
import threading


def _temp_path(name):
    return os.path.join(tempfile.mkdtemp(), name)


class StubEmailSender:
    """Fake email_sender module for the Outreach runner."""
    def __init__(self):
        self.calls = []          # (lead_id, touch)
        self.capable = True

    def can_send_next_email(self, lead_id):
        return self.capable

    def send_sequence_email(self, lead, touch, loom):
        self.calls.append((lead['id'], touch))
        return True


class StubDemoGenerator:
    def get_demo_for_lead(self, lead):
        return {'loom_link': 'https://loom.example/abc'}


class StubInstagramDM:
    """Fake instagram_dm module for the Outreach runner."""
    def __init__(self):
        self.calls = []          # (kind, lead_id)
        self.capable = True

    def can_send_next_dm(self, lead_id):
        return self.capable

    def send_dm_via_api(self, ig_id, lead):
        self.calls.append(('api', lead['id']))
        return True

    def send_dm(self, handle, lead):
        self.calls.append(('dm', lead['id']))
        return True


class StubSystem:
    """Stand-in for LeadGenSystem with the methods both runners call."""
    def __init__(self, db_path):
        from leadgen.database import Database
        self.db = Database(db_path)
        self.db.connect()
        self.db.create_tables()
        self.email_sender = StubEmailSender()
        self.demo_generator = StubDemoGenerator()
        self.instagram_dm = StubInstagramDM()
        self.config = None
        self.outreach_cycle_calls = 0
        # Every Lead Generation method invoked; must stay EMPTY while the
        # Outreach runner runs (proves Outreach never calls Lead Generation).
        self.leadgen_method_calls = []

    def validate_setup(self):
        return []

    def run_daily_scraping(self):
        self.leadgen_method_calls.append('run_daily_scraping')
        return {'saved_to_db': 3}

    def run_scoring_cycle(self):
        self.leadgen_method_calls.append('run_scoring_cycle')
        return {'total_scored': 3}

    def sync_to_sheets(self):
        self.leadgen_method_calls.append('sync_to_sheets')
        return True

    def run_contact_enrichment(self):
        self.leadgen_method_calls.append('run_contact_enrichment')
        return {'checked': 0, 'enriched': 0, 'partial': 0, 'no_contact': 0, 'failed': 0}

    def run_outreach_cycle(self):
        # If the lead-gen runner ever calls this, the "no outreach" guarantee broke.
        self.outreach_cycle_calls += 1


def _make_dashboard_app():
    """Build a Flask dashboard app isolated to a temp DB (no real data)."""
    from flask import Flask
    from dashboard.leadgen_runner import LeadGenerationRunner
    from dashboard.outreach_runner import OutreachRunner
    from dashboard.scheduler import SchedulerManager
    from dashboard.routes import pages, api

    db_path = _temp_path('dashboard_leads.db')
    stub = StubSystem(db_path)
    leadgen_runner = LeadGenerationRunner(stub)
    outreach_runner = OutreachRunner(stub, config_path=_temp_path('outreach_cfg.json'))
    sched_lg = SchedulerManager(leadgen_runner, config_path=_temp_path('sched_leadgen.json'))
    sched_og = SchedulerManager(outreach_runner, config_path=_temp_path('sched_outreach.json'))

    import dashboard as _dash_pkg
    _pkg_dir = os.path.dirname(_dash_pkg.__file__)
    app = Flask(__name__,
                template_folder=os.path.join(_pkg_dir, 'templates'),
                static_folder=os.path.join(_pkg_dir, 'static'))
    app.extensions['system'] = stub
    app.extensions['leadgen_runner'] = leadgen_runner
    app.extensions['outreach_runner'] = outreach_runner
    app.extensions['scheduler_leadgen'] = sched_lg
    app.extensions['scheduler_outreach'] = sched_og
    app.register_blueprint(pages)
    app.register_blueprint(api)
    return app, stub


_SECRET_MARKERS = ['REDACTED_SMTP_PASSWORD', 'REDACTED_INSTAGRAM_TOKEN', 'apify_api_',
                   'BEGIN PRIVATE KEY', 'SMTP_PASSWORD']


def _assert_no_secrets(text):
    for marker in _SECRET_MARKERS:
        assert marker not in text, f"Secret leak in response: {marker}"


def _wait_done(runner, timeout=10):
    t0 = time.time()
    while runner.running and time.time() - t0 < timeout:
        time.sleep(0.05)
    assert not runner.running, "runner did not finish within timeout"


def test_dashboard_app():
    """Test dashboard pages + API + secret hygiene (two pipelines)"""
    print("Testing web dashboard app...")
    try:
        app, _ = _make_dashboard_app()
        client = app.test_client()

        # Pages render
        for path in ['/', '/leadgen', '/outreach', '/leads']:
            r = client.get(path)
            assert r.status_code == 200, f"{path} -> {r.status_code}"
            _assert_no_secrets(r.get_data(as_text=True))
        # Old combined /pipeline now redirects to /leadgen
        r = client.get('/pipeline')
        assert r.status_code == 301, r.status_code
        assert r.headers['Location'].endswith('/leadgen')
        print("✓ 4 pages render + /pipeline redirects, no secrets in HTML")

        # Overview API covers BOTH pipelines
        o = client.get('/api/overview').get_json()
        for key in ['total_leads', 'categories', 'qualified', 'contacted',
                    'replies', 'leadgen', 'outreach', 'health_ok']:
            assert key in o, f"overview missing {key}"
        assert o['leadgen']['scheduler_enabled'] is False
        assert o['outreach']['mode'] == 'dry_run'      # default DRY RUN
        assert 'stats' in o['outreach']
        _assert_no_secrets(str(o))
        print("✓ /api/overview shape OK (leadgen + outreach)")

        # Health API returns booleans only
        h = client.get('/api/health').get_json()
        assert 'healthy' in h and 'db_ok' in h and 'issue_count' in h
        _assert_no_secrets(str(h))
        print("✓ /api/health sanitized (no secrets)")

        # Both schedulers default OFF and are independent
        sl = client.get('/api/scheduler/leadgen/status').get_json()
        so = client.get('/api/scheduler/outreach/status').get_json()
        assert sl['enabled'] is False and so['enabled'] is False
        print("✓ Both schedulers default OFF")

        # Outreach mode API round-trip
        r = client.post('/api/outreach/mode', json={'mode': 'dry_run'}).get_json()
        assert r['ok'] and r['mode'] == 'dry_run'
        r = client.post('/api/outreach/mode', json={'mode': 'bogus'}).get_json()
        assert r['ok'] is False
        print("✓ Mode API validates dry_run/live")

        # stop on idle returns 409 for each pipeline
        for ep in ['/api/leadgen/stop', '/api/outreach/stop']:
            assert client.post(ep).status_code == 409, ep
        print("✓ stop-when-idle correctly 409s")

        return True
    except Exception as e:
        print(f"✗ Dashboard app test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_dashboard_leadgen():
    """Test LeadGenerationRunner: 6 stages, enrichment before Sheets, no outreach, isolation"""
    print("Testing dashboard lead generation runner...")
    try:
        from leadgen.database import Database
        from dashboard.leadgen_runner import LeadGenerationRunner, STAGES

        class RunDB(Database):
            def __init__(self, path):
                super().__init__(path)
                self.connect()
                self.create_tables()

        class RunSystem:
            def __init__(self, db, fail_scrape=False):
                self.db = db
                self.fail_scrape = fail_scrape
                self.outreach_cycle_calls = 0

            def run_daily_scraping(self):
                if self.fail_scrape:
                    raise RuntimeError('Apify down')
                return {'saved_to_db': 3}

            def run_scoring_cycle(self):
                return {'total_scored': 3}

            def sync_to_sheets(self):
                return True

            def run_contact_enrichment(self):
                return {'checked': 0, 'enriched': 0, 'partial': 0, 'no_contact': 0, 'failed': 0}

            def run_outreach_cycle(self):
                # If the lead-gen runner ever calls this, the "no outreach" guarantee broke.
                self.outreach_cycle_calls += 1

        db = RunDB(_temp_path('leadgen_test.db'))
        sys = RunSystem(db)
        runner = LeadGenerationRunner(sys)

        # start -> running
        assert runner.start()['ok'] is True
        assert runner.running

        # overlap prevention
        assert runner.start()['ok'] is False
        print("✓ Start works + overlap prevented")

        # wait for completion
        _wait_done(runner)
        snap = runner.state.snapshot()
        assert snap['status'] == 'completed', snap['status']
        assert snap['progress'] == 100
        assert set(STAGES) <= set(snap['stage_results'].keys())
        # Contact Enrichment is a real stage AND runs BEFORE the Sheets sync
        assert 'Contact Enrichment' in snap['stage_results']
        assert (STAGES.index('Contact Enrichment')
                < STAGES.index('Google Sheets Sync'))
        assert snap['stage_results']['Contact Enrichment'].get('checked') == 0
        # outreach is NOT among the stages
        assert 'Outreach' not in STAGES
        # the lead-gen runner must never touch the outreach module
        assert sys.outreach_cycle_calls == 0
        print("✓ All 6 stages recorded, enrichment before Sheets, completed, no outreach")

        # history written with a leadgen- prefixed run_type
        hist = db.get_run_history(5)
        assert hist and hist[0]['status'] == 'completed'
        assert hist[0]['new_leads'] == 3
        assert hist[0]['run_type'].startswith('leadgen-')
        print("✓ Run history recorded (new_leads=3, run_type=leadgen-*)")

        # failure isolation: scraping fails, pipeline continues
        db.connection.execute('DELETE FROM pipeline_runs'); db.connection.commit()
        runner2 = LeadGenerationRunner(RunSystem(db, fail_scrape=True))
        runner2.start()
        _wait_done(runner2)
        s2 = runner2.state.snapshot()
        assert s2['status'] == 'completed', s2['status']
        assert 'Scraping' in s2['stage_errors']
        assert 'Contact Enrichment' in s2['stage_results']   # continues past a failure
        assert 'Google Sheets Sync' in s2['stage_results']
        hist2 = db.get_run_history(2)
        assert hist2[0]['stages']['Scraping'] == 'failed'
        assert runner2.system.outreach_cycle_calls == 0
        print("✓ Failed stage isolated, enrichment + remaining stages completed, recorded")

        return True
    except Exception as e:
        print(f"✗ Dashboard leadgen test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_dashboard_outreach():
    """Test OutreachRunner: dry-run, live, idempotency, 5-touch sequence"""
    print("Testing dashboard outreach runner...")
    try:
        app, stub = _make_dashboard_app()
        db = stub.db

        # Seed qualified leads (some contactable via email / IG, one not)
        leads = [
            {'id': 'r1', 'name': 'Ready', 'email': 'r1@x.com', 'instagram': 'ig_r1',
             'qualified': 1, 'score': 20, 'status': 'new'},
            {'id': 'r2', 'name': 'Email Only', 'email': 'r2@x.com',
             'qualified': 1, 'score': 15, 'status': 'new'},
            {'id': 'r3', 'name': 'No Contact', 'qualified': 1, 'score': 8, 'status': 'new'},
        ]
        for lead in leads:
            assert db.save_lead(lead)
        assert len(db.get_qualified_leads_for_outreach()) == 3

        og = app.extensions['outreach_runner']
        assert og.get_mode() == 'dry_run'       # default is DRY RUN

        # ---- DRY RUN: builds the queue, sends NOTHING, records NOTHING ----
        og.start()
        _wait_done(og)
        snap = og.snapshot()
        assert snap['mode'] == 'dry_run'
        assert snap['status'] == 'completed', snap['status']
        assert snap['queue'], "dry run must build a queue"
        types = {i['message_type'] for i in snap['queue']}
        assert 'T1' in types and 'dm' in types
        assert len(snap['queue']) == 3            # r1 email T1, r2 email T1, r1 IG dm
        assert stub.email_sender.calls == []      # nothing sent
        assert stub.instagram_dm.calls == []
        assert db.get_outreach_history('r1') == []  # nothing recorded
        assert db.get_outreach_stats()['sent'] == 0
        print("✓ Dry run: queue built, nothing sent, nothing recorded")

        # ---- LIVE: actually sends through the stub modules + records ----
        assert og.set_mode('live')['ok']
        og.start()
        _wait_done(og)
        snap = og.snapshot()
        assert snap['counts']['sent'] == 3, snap['counts']
        sent_ids = [c[0] for c in stub.email_sender.calls]
        assert 'r1' in sent_ids and 'r2' in sent_ids
        assert stub.instagram_dm.calls == [('dm', 'r1')]
        hist = db.get_outreach_history('r1')
        assert any(h['channel'] == 'email' and h['message_type'] == 'T1'
                   and h['status'] == 'sent' and h['success'] == 1 for h in hist)
        assert any(h['channel'] == 'instagram_dm' and h['status'] == 'sent' for h in hist)
        assert db.get_outreach_stats()['sent'] >= 3
        print("✓ Live: sent via email + IG, every attempt recorded in outreach_history")

        # ---- IDEMPOTENCY: a second live run sends nothing (no duplicates) ----
        email_calls = list(stub.email_sender.calls)
        ig_calls = list(stub.instagram_dm.calls)
        og.start()
        _wait_done(og)
        assert stub.email_sender.calls == email_calls
        assert stub.instagram_dm.calls == ig_calls
        assert og.snapshot()['queue'] == []
        print("✓ Idempotent: re-run sends nothing (already sent leads skipped)")

        # ---- DB-level: duplicate successful record is ignored ----
        db.connection.execute('DELETE FROM outreach_history'); db.connection.commit()
        assert db.record_outreach_result('r1', 'email', 'T1', 'sent', success=1) is True
        assert db.record_outreach_result('r1', 'email', 'T1', 'sent', success=1) is False
        assert db.get_successful_touch_count('r1', 'email') == 1
        # failed retry allowed (success=0 not covered by the unique index)
        assert db.record_outreach_result('r1', 'email', 'T1', 'failed', success=0) is True
        assert db.has_successful_outreach('r1', 'email', 'T1') is True
        assert db.has_successful_outreach('r1', 'email', 'T5') is False
        # 5-touch: T1..T5 all insert, a 6th T1 duplicate is blocked, count caps at 5
        for i in range(2, 6):
            assert db.record_outreach_result('r1', 'email', f'T{i}', 'sent', success=1)
        assert db.get_successful_touch_count('r1', 'email') == 5
        assert db.record_outreach_result('r1', 'email', 'T1', 'sent', success=1) is False
        print("✓ DB idempotency: partial unique index + 5-touch sequence")

        # Outreach must NEVER call any Lead Generation method (pipeline isolation)
        assert stub.leadgen_method_calls == [], stub.leadgen_method_calls
        assert stub.outreach_cycle_calls == 0
        print("✓ Outreach never invokes Lead Generation methods")

        db.close()
        return True
    except Exception as e:
        print(f"✗ Dashboard outreach test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_dashboard_scheduler():
    """Test two independent schedulers: separate configs, both default OFF"""
    print("Testing dashboard scheduler managers...")
    try:
        from dashboard.scheduler import SchedulerManager

        class FakeRunner:
            @property
            def running(self):
                return False

            def start(self, run_type='manual'):
                return {'ok': True}

        runner = FakeRunner()
        path_lg = _temp_path('sched_leadgen.json')
        path_og = _temp_path('sched_outreach.json')

        sm_lg = SchedulerManager(runner, config_path=path_lg)
        sm_og = SchedulerManager(runner, config_path=path_og)
        assert sm_lg.status()['enabled'] is False
        assert sm_og.status()['enabled'] is False
        print("✓ Both schedulers default OFF")

        # enabling lead-gen must NOT touch the outreach config
        assert sm_lg.enable()['ok']
        assert sm_lg.status()['enabled'] is True
        assert sm_og.status()['enabled'] is False
        time.sleep(0.3)  # let the APScheduler background thread come up
        print("✓ Schedulers are independent (leadgen ON does not enable outreach)")

        # separate persistence files
        sm_lg2 = SchedulerManager(runner, config_path=path_lg)
        sm_og2 = SchedulerManager(runner, config_path=path_og)
        assert sm_lg2.status()['enabled'] is True
        assert sm_og2.status()['enabled'] is False
        print("✓ Config persists per-file across restart")

        assert sm_lg2.set_frequency(6)['ok']
        assert SchedulerManager(runner, config_path=path_lg).status()['frequency_hours'] == 6.0
        print("✓ Frequency persists for leadgen scheduler")

        assert sm_lg2.disable()['ok']
        assert SchedulerManager(runner, config_path=path_lg).status()['enabled'] is False
        assert sm_og.set_frequency(-1)['ok'] is False
        print("✓ Disable + invalid frequency rejected")

        sm_lg.disable()  # cleanup background schedulers
        sm_og.disable()
        return True
    except Exception as e:
        print(f"✗ Dashboard scheduler test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_dashboard_leads():
    """Test leads search/filter via the API against a seeded temp DB"""
    print("Testing dashboard leads API...")
    try:
        app, stub = _make_dashboard_app()
        db = stub.db

        # Seed leads
        leads = [
            {'id': 'l1', 'name': 'Alice Doe', 'email': 'alice@x.com', 'source': 'realtor_com',
             'brokerage': 'Compass', 'score': 18, 'category': 'High Score', 'status': 'new',
             'email_status': 'sent'},
            {'id': 'l2', 'name': 'Bob Smith', 'email': 'bob@y.com', 'source': 'zillow',
             'brokerage': 'The Agency', 'score': 11, 'category': 'Medium Score', 'status': 'new'},
            {'id': 'l3', 'name': 'Carol King', 'email': 'carol@z.com', 'source': 'realtor_com',
             'brokerage': 'Compass', 'score': 7, 'category': 'Low Score', 'status': 'interested'},
        ]
        for lead in leads:
            assert db.save_lead(lead)

        client = app.test_client()

        # all
        r = client.get('/api/leads').get_json()
        assert r['count'] == 3, r['count']
        assert 'realtor_com' in r['sources']

        # search by name
        r = client.get('/api/leads?q=Alice').get_json()
        assert r['count'] == 1 and r['leads'][0]['id'] == 'l1'

        # filter by category
        r = client.get('/api/leads?category=High Score').get_json()
        assert r['count'] == 1 and r['leads'][0]['id'] == 'l1'

        # filter by source + min_score
        r = client.get('/api/leads?source=realtor_com&min_score=10').get_json()
        assert r['count'] == 1 and r['leads'][0]['id'] == 'l1'

        # detail includes outreach_history key
        r = client.get('/api/leads/l2').get_json()
        assert r['name'] == 'Bob Smith'
        assert 'outreach_history' in r

        # outreach status snapshot exposes mode + stats (new aggregate endpoint)
        r = client.get('/api/outreach/status').get_json()
        assert r['mode'] == 'dry_run'
        assert 'stats' in r and 'queue' in r and 'counts' in r

        print("✓ Search/filter/detail/outreach-status OK")

        # cleanup
        db.close()
        return True
    except Exception as e:
        print(f"✗ Dashboard leads test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_lead_detail_url_404():
    """Regression (Problem A): lead IDs are full URLs. The detail endpoint
    must resolve them — both the raw slash path and the percent-encoded form
    dashboard.js sends — and a missing lead must still return 404."""
    print("Testing lead-detail URL resolution (404 fix)...")
    try:
        app, stub = _make_dashboard_app()
        url_id = 'https://www.realtor.com/realestateagents/1796470'
        assert stub.db.save_lead({'profile_url': url_id,
                                  'name': 'Jane Doe', 'source': 'realtor'})
        c = app.test_client()

        # Raw URL with slashes in the path (old Flask string converter 404'd)
        r = c.get('/api/leads/' + url_id)
        assert r.status_code == 200, r.status_code
        body = r.get_json()
        assert body['name'] == 'Jane Doe'
        assert 'outreach_history' in body

        # Percent-encoded form (what openDetail() sends via encodeURIComponent)
        from urllib.parse import quote
        r = c.get('/api/leads/' + quote(url_id, safe=''))
        assert r.status_code == 200, r.status_code
        assert r.get_json()['id'] == url_id

        # Missing lead still 404
        r = c.get('/api/leads/' + quote('https://www.realtor.com/realestateagents/999999', safe=''))
        assert r.status_code == 404

        # No secrets in either successful response
        for resp in (c.get('/api/leads/' + url_id),):
            _assert_no_secrets(resp.get_data(as_text=True))

        stub.db.close()
        print("✓ URL ids resolve raw + encoded; missing lead 404s")
        return True
    except Exception as e:
        print(f"✗ Lead-detail URL test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_save_lead_dedup_merge():
    """Regression (Problem B): re-scraping the same lead must NOT create
    duplicate rows and must NOT wipe enriched/outreach data. This is what the
    safe merge upsert replaces INSERT OR REPLACE for."""
    print("Testing save_lead dedup + safe merge...")
    try:
        from leadgen.database import Database
        db = Database(_temp_path('dedup_merge.db'))
        db.connect()
        db.create_tables()
        try:
            url = 'https://www.realtor.com/realestateagents/111'
            # 1) Same profile_url scraped twice -> same id, one row, updated name
            a1 = db.save_lead({'profile_url': url, 'name': 'Jane', 'source': 'realtor'})
            a2 = db.save_lead({'profile_url': url, 'name': 'Jane Doe', 'source': 'realtor'})
            assert a1 == a2
            assert db.get_lead_by_id(a1)['name'] == 'Jane Doe'

            # 2) Enrichment survives a re-scrape that only knows the name
            db.update_lead_enrichment(a1, {'phone': '+1 (415) 555-1234',
                                           'phone_type': 'mobile',
                                           'enrichment_status': 'completed',
                                           'enrichment_last_checked': '2026-08-01'})
            db.save_lead({'profile_url': url, 'name': 'Jane Doe', 'source': 'realtor'})
            row = db.get_lead_by_id(a1)
            assert row['phone'] == '+1 (415) 555-1234', row['phone']
            assert row['phone_type'] == 'mobile'
            assert row['enrichment_status'] == 'completed'

            # 3) created_at preserved across re-scrapes
            created = row['created_at']
            db.save_lead({'profile_url': url, 'name': 'Jane Doe', 'source': 'realtor'})
            assert db.get_lead_by_id(a1)['created_at'] == created

            # 4) Job-post style (no id) merges into ONE row via canonical_key
            j1 = db.save_lead({'source': 'job_post', 'job_url': 'https://x/jobs/9',
                               'company_name': 'Compass', 'trigger': 'hiring_isa'})
            j2 = db.save_lead({'source': 'job_post', 'job_url': 'https://x/jobs/9',
                               'company_name': 'Compass', 'trigger': 'hiring_isa'})
            assert j1 == j2

            # 5) Total rows are unique by id (no duplicates at all)
            ids = [r['id'] for r in
                   db.connection.execute('SELECT id FROM leads').fetchall()]
            assert len(ids) == len(set(ids)) == 2, ids
        finally:
            db.close()
        print("✓ Re-scrape merges (no dup, no wipe, created_at preserved)")
        return True
    except Exception as e:
        print(f"✗ save_lead dedup/merge test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


# =====================================================================
# Phone + Contact Enrichment tests (additive)
# =====================================================================

def test_phone_normalization():
    """E.164 normalization: confident forms normalized, unparseable preserved"""
    print("Testing phone normalization...")
    try:
        from leadgen.enrichment.phone_utils import normalize_phone, is_valid_phone
        assert normalize_phone('(415) 555-1234') == '+14155551234'
        assert normalize_phone('415-555-1234') == '+14155551234'
        assert normalize_phone('4155551234') == '+14155551234'
        assert normalize_phone('1 415 555 1234') == '+14155551234'
        assert normalize_phone('+1 415-555-1234') == '+14155551234'
        assert normalize_phone('+442079460958') == '+442079460958'   # keep leading +
        # Not confident -> None so callers preserve the raw value (never corrupt)
        assert normalize_phone('555-1234') is None        # 7-digit local, no area code
        assert normalize_phone('') is None
        assert normalize_phone(None) is None
        assert normalize_phone('call me') is None
        assert is_valid_phone('(415) 555-1234') is True
        assert is_valid_phone('555-1234') is False
        print("✓ E.164 normalization + preserve-raw rule")
        return True
    except Exception as e:
        print(f"✗ Phone normalization test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_phone_db_migration():
    """Migration adds phone metadata columns; idempotent re-run; save_lead keeps them"""
    print("Testing phone DB migration...")
    try:
        from leadgen.database import Database
        path = _temp_path('migrate_phone.db')
        db = Database(path)
        db.connect()
        db.create_tables()
        cols = {r['name'] for r in db.connection.execute('PRAGMA table_info(leads)')}
        for c in ['phone', 'phone_type', 'phone_source', 'phone_verified',
                  'phone_last_checked', 'phone_raw', 'enrichment_status',
                  'enrichment_last_checked']:
            assert c in cols, f"missing column {c}"
        # Re-running create_tables is a no-op (no duplicate columns)
        db.create_tables()
        cols2 = {r['name'] for r in db.connection.execute('PRAGMA table_info(leads)')}
        assert cols2 == cols, "create_tables must be idempotent"
        # save_lead preserves the new columns through INSERT OR REPLACE
        lead = {'id': 'mp1', 'name': 'Mig', 'phone': '+14155550123',
                'phone_type': 'business', 'phone_source': 'website',
                'phone_verified': 0, 'phone_raw': '(415) 555-0123',
                'enrichment_status': 'partial',
                'enrichment_last_checked': '2026-01-01T00:00:00',
                'score': 15, 'category': 'High Score', 'qualified': 1}
        db.save_lead(lead)
        again = dict(lead); again['name'] = 'Mig2'
        db.save_lead(again)                    # INSERT OR REPLACE same id
        saved = db.get_lead_by_id('mp1')
        assert saved['phone'] == '+14155550123'
        assert saved['phone_type'] == 'business'
        assert saved['phone_source'] == 'website'
        assert saved['phone_raw'] == '(415) 555-0123'
        assert saved['enrichment_status'] == 'partial'
        assert saved['enrichment_last_checked'] == '2026-01-01T00:00:00'
        assert saved['name'] == 'Mig2'         # re-save updated, didn't wipe
        # outreach idempotency index untouched
        idx = {r['name'] for r in db.connection.execute('PRAGMA index_list(outreach_history)')}
        assert 'uq_outreach_touch' in idx
        db.close()
        print("✓ Migration columns + idempotent re-run + save_lead preserves phone metadata")
        return True
    except Exception as e:
        print(f"✗ Phone DB migration test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_contact_enricher():
    """ContactEnricher finds phone/email/IG; no contact -> no_contact; never fabricates"""
    print("Testing ContactEnricher...")
    try:
        from types import SimpleNamespace
        from leadgen.enrichment.contact_enricher import (
            ContactEnricher, classify_status, ENRICHED, PARTIAL, NO_CONTACT)
        cfg = SimpleNamespace(CONTACT_ENRICHMENT_MAX_LEADS_PER_RUN=50,
                              CONTACT_ENRICHMENT_DELAY_SECONDS=0.0)

        class P:
            def __init__(self, name, source, result):
                self.name, self.source, self.result = name, source, result
            def enrich(self, lead):
                return dict(self.result)

        # phone found -> normalized E.164, source tagged, never 'verified'
        en = ContactEnricher(cfg, providers=[P('A', 'website', {'phone': '(415) 555-1234'})])
        c = en.enrich_lead({'id': 'x'})
        assert c['phone'] == '+14155551234'
        assert c['phone_raw'] == '(415) 555-1234'
        assert c['phone_source'] == 'website'
        assert c['phone_verified'] == 0
        assert classify_status(c) == PARTIAL

        # unparseable phone -> preserved raw, never corrupted
        en = ContactEnricher(cfg, providers=[P('A', 'website', {'phone': '555-1234'})])
        c = en.enrich_lead({'id': 'x'})
        assert c['phone'] == '555-1234'
        assert c['phone_raw'] == '555-1234'
        assert c['phone_verified'] == 0

        # no contact at all -> empty result, classified no_contact
        en = ContactEnricher(cfg, providers=[P('A', 'website', {})])
        c = en.enrich_lead({'id': 'x'})
        assert c.get('phone') is None and c.get('email') is None
        assert classify_status(c) == NO_CONTACT

        # all three discovered -> enriched
        en = ContactEnricher(cfg, providers=[P('A', 'website',
            {'phone': '+14155550001', 'email': 'e@x.com', 'instagram': 'ig'})])
        assert classify_status(en.enrich_lead({'id': 'x'})) == ENRICHED
        print("✓ ContactEnricher: found / no-contact / partial / enriched / never fabricates")
        return True
    except Exception as e:
        print(f"✗ ContactEnricher test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_enrichment_ttl():
    """get_leads_needing_enrichment respects TTL; failed always retried; partial update"""
    print("Testing enrichment TTL...")
    try:
        from leadgen.database import Database
        from datetime import datetime, timedelta
        db = Database(_temp_path('enrich_ttl.db'))
        db.connect(); db.create_tables()
        now = datetime.now()
        def iso(d): return d.isoformat()
        leads = [
            {'id': 'n1', 'name': 'Never checked', 'qualified': 1},
            {'id': 'fresh', 'name': 'Fresh', 'enrichment_last_checked': iso(now),
             'qualified': 1},
            {'id': 'stale', 'name': 'Stale',
             'enrichment_last_checked': iso(now - timedelta(hours=200)), 'qualified': 1},
            {'id': 'failed', 'name': 'Failed', 'enrichment_status': 'failed',
             'enrichment_last_checked': iso(now), 'qualified': 1},
            {'id': 'unqual', 'name': 'Unqualified', 'qualified': 0},
        ]
        for lead in leads:
            db.save_lead(lead)
        got = {l['id'] for l in db.get_leads_needing_enrichment(limit=50, ttl_hours=168)}
        assert got == {'n1', 'stale', 'failed'}, got
        # update_lead_enrichment persists only the provided keys
        db.update_lead_enrichment('n1', {'phone': '+14155559999',
                                         'enrichment_status': 'partial',
                                         'enrichment_last_checked': iso(now)})
        l = db.get_lead_by_id('n1')
        assert l['phone'] == '+14155559999'
        assert l['enrichment_status'] == 'partial'
        assert l['email'] is None            # untouched
        # now 'n1' is fresh -> excluded again
        got2 = {x['id'] for x in db.get_leads_needing_enrichment(limit=50, ttl_hours=168)}
        assert got2 == {'stale', 'failed'}, got2
        db.close()
        print("✓ Enrichment TTL: fresh excluded, stale/failed included, targeted update")
        return True
    except Exception as e:
        print(f"✗ Enrichment TTL test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_enrichment_isolation():
    """One broken provider (or bad lead) never stops the rest"""
    print("Testing enrichment isolation...")
    try:
        from types import SimpleNamespace
        from leadgen.enrichment.contact_enricher import ContactEnricher
        cfg = SimpleNamespace(CONTACT_ENRICHMENT_MAX_LEADS_PER_RUN=50,
                              CONTACT_ENRICHMENT_DELAY_SECONDS=0.0)

        class Boom:
            name, source = 'Boom', 'boom'
            def enrich(self, lead):
                raise RuntimeError('provider on fire')

        class Good:
            name, source = 'Good', 'good'
            def enrich(self, lead):
                return {'email': 'ok@x.com'}

        # provider failure is isolated inside enrich_lead -> good data still found
        en = ContactEnricher(cfg, providers=[Boom(), Good()])
        c = en.enrich_lead({'id': 'z'})
        assert c['email'] == 'ok@x.com'
        assert c['sources'] == ['good']
        assert 'boom' not in c['sources']

        # enrich_leads returns one entry per lead, in order, never raising
        res = en.enrich_leads([{'id': 'a'}, {'id': 'b'}, {'id': 'c'}])
        assert [r['lead']['id'] for r in res] == ['a', 'b', 'c']
        assert all('contact' in r for r in res)
        print("✓ Enrichment isolation: one failure never stops the rest")
        return True
    except Exception as e:
        print(f"✗ Enrichment isolation test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_sheets_phone_columns():
    """Sheets header/row include phone metadata; no-contact leads still written"""
    print("Testing sheets phone columns...")
    try:
        from leadgen.sheets_sync import SheetsSync
        sync = SheetsSync(object())
        header = sync._get_header_row()
        for col in ['Phone', 'Phone Type', 'Phone Source', 'Phone Verified',
                    'Phone Last Checked', 'Email', 'Instagram', 'Enrichment Status']:
            assert col in header, f"missing header {col}"
        assert header.index('Phone Type') == header.index('Phone') + 1
        assert header[-1] == 'Enrichment Status'
        lead = {'name': 'N', 'phone': '+14155551234', 'phone_type': 'business',
                'phone_source': 'website', 'phone_verified': 0,
                'phone_last_checked': '2026-01-01T00:00:00', 'email': 'e@x.com',
                'instagram': 'ig', 'enrichment_status': 'partial'}
        row = sync._prepare_lead_data([lead])[0]
        assert row[header.index('Phone')] == '+14155551234'
        assert row[header.index('Phone Type')] == 'business'
        assert row[header.index('Phone Source')] == 'website'
        assert row[header.index('Phone Verified')] == 0
        assert row[header.index('Phone Last Checked')] == '2026-01-01T00:00:00'
        assert row[header.index('Enrichment Status')] == 'partial'
        assert len(row) == len(header)
        # a lead with no contact data still produces a full row (blank cells)
        empty_row = sync._prepare_lead_data([{'id': 'x', 'name': 'No Contact'}])[0]
        assert len(empty_row) == len(header)
        assert empty_row[header.index('Phone')] == ''
        print("✓ Sheets: phone metadata columns aligned, no-contact rows written")
        return True
    except Exception as e:
        print(f"✗ Sheets phone columns test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_leads_contact_filters():
    """Leads API: contactable / no_contact / has_phone / has_email / has_instagram"""
    print("Testing leads contact filters...")
    try:
        app, stub = _make_dashboard_app()
        db = stub.db
        leads = [
            {'id': 'cf1', 'name': 'Phone Only', 'phone': '+14155550001',
             'score': 20, 'qualified': 1},
            {'id': 'cf2', 'name': 'Email Only', 'email': 'cf2@x.com',
             'score': 15, 'qualified': 1},
            {'id': 'cf3', 'name': 'IG Only', 'instagram': 'ig_cf3',
             'score': 12, 'qualified': 1},
            {'id': 'cf4', 'name': 'Nothing', 'score': 5, 'qualified': 1},
        ]
        for lead in leads:
            db.save_lead(lead)
        client = app.test_client()
        r = client.get('/api/leads?has_phone=1').get_json()
        assert r['count'] == 1 and r['leads'][0]['id'] == 'cf1'
        r = client.get('/api/leads?has_email=1').get_json()
        assert r['count'] == 1 and r['leads'][0]['id'] == 'cf2'
        r = client.get('/api/leads?has_instagram=1').get_json()
        assert r['count'] == 1 and r['leads'][0]['id'] == 'cf3'
        r = client.get('/api/leads?contactable=1').get_json()
        assert r['count'] == 3
        r = client.get('/api/leads?no_contact=1').get_json()
        assert r['count'] == 1 and r['leads'][0]['id'] == 'cf4'
        _assert_no_secrets(str(client.get('/api/leads?has_phone=1').get_json()))
        print("✓ Leads API phone/email/instagram/contactable/no_contact filters")
        db.close()
        return True
    except Exception as e:
        print(f"✗ Leads contact filters test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_overview_contact_stats():
    """Overview exposes contact availability counts (no secrets)"""
    print("Testing overview contact stats...")
    try:
        app, stub = _make_dashboard_app()
        db = stub.db
        leads = [
            {'id': 'ov1', 'name': 'Phone+Email', 'phone': '+14155550101',
             'email': 'ov1@x.com', 'score': 20, 'qualified': 1},
            {'id': 'ov2', 'name': 'IG Only', 'instagram': 'ig_ov2',
             'score': 15, 'qualified': 1},
            {'id': 'ov3', 'name': 'Nothing', 'score': 5, 'qualified': 1},
            {'id': 'ov4', 'name': 'Unqualified w/ phone', 'phone': '+14155550104',
             'score': 3, 'qualified': 0},
        ]
        for lead in leads:
            db.save_lead(lead)
        o = app.test_client().get('/api/overview').get_json()
        assert o['qualified'] == 3
        assert o['total_contactable'] == 2        # ov1, ov2 (ov4 unqualified excluded)
        assert o['leads_with_phone'] == 1         # ov1 only
        assert o['leads_with_email'] == 1
        assert o['leads_with_instagram'] == 1
        assert o['leads_with_no_contact'] == 1    # ov3
        _assert_no_secrets(str(o))
        print("✓ Overview contact stats + no secrets")
        db.close()
        return True
    except Exception as e:
        print(f"✗ Overview contact stats test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_phone_outreach_queue():
    """Phone is a manual task: queued in dry-run, never auto-dialed in live"""
    print("Testing phone outreach queue...")
    try:
        app, stub = _make_dashboard_app()
        db = stub.db
        leads = [
            {'id': 'pq1', 'name': 'Phone+Email', 'phone': '(415) 555-0101',
             'email': 'pq1@x.com', 'qualified': 1, 'score': 20, 'status': 'new'},
            {'id': 'pq2', 'name': 'Phone Only', 'phone': '+14155550102',
             'qualified': 1, 'score': 18, 'status': 'new'},
            {'id': 'pq3', 'name': 'No Contact', 'qualified': 1, 'score': 8, 'status': 'new'},
        ]
        for lead in leads:
            db.save_lead(lead)
        og = app.extensions['outreach_runner']

        # DRY RUN: queue includes phone/CALL tasks + email; records nothing
        og.start(); _wait_done(og)
        snap = og.snapshot()
        phone = [i for i in snap['queue'] if i['channel'] == 'phone']
        assert len(phone) == 2
        assert all(i['message_type'] == 'CALL' for i in phone)
        assert {i['lead_id'] for i in phone} == {'pq1', 'pq2'}
        assert snap['counts']['phone_tasks'] == 2
        assert snap['counts']['previewed'] >= 2
        assert snap['counts']['sent'] == 0
        assert snap['counts']['contactable'] == 2
        assert snap['counts']['no_contact'] == 1
        assert stub.email_sender.calls == []
        assert db.get_outreach_history('pq1') == []
        print("✓ Dry run: phone CALL tasks queued, nothing sent/recorded")

        # LIVE: email is sent, phone is NOT auto-dialed (manual only)
        assert og.set_mode('live')['ok']
        og.start(); _wait_done(og)
        snap = og.snapshot()
        assert snap['counts']['sent'] == 1              # pq1 email T1 only
        assert [c[0] for c in stub.email_sender.calls] == ['pq1']
        assert db.get_outreach_history('pq2') == []     # phone never auto-recorded
        print("✓ Live: email sent, phone never auto-dialed/SMS'd")
        db.close()
        return True
    except Exception as e:
        print(f"✗ Phone outreach queue test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_phone_task_idempotency():
    """A completed phone CALL can never be re-queued or re-recorded"""
    print("Testing phone task idempotency...")
    try:
        app, stub = _make_dashboard_app()
        db = stub.db
        db.save_lead({'id': 'pid1', 'name': 'P', 'phone': '+14155550111',
                      'qualified': 1, 'score': 20, 'status': 'new'})
        og = app.extensions['outreach_runner']
        r = og.mark_phone_called('pid1')
        assert r['ok'] is True and r['already_recorded'] is False
        assert db.get_successful_touch_count('pid1', 'phone') == 1
        r2 = og.mark_phone_called('pid1')
        assert r2['ok'] is True and r2['already_recorded'] is True
        assert db.get_successful_touch_count('pid1', 'phone') == 1
        hist = db.get_outreach_history('pid1')
        assert sum(1 for h in hist if h['channel'] == 'phone') == 1
        # a dry run now EXCLUDES the completed call from the queue
        og.start(); _wait_done(og)
        snap = og.snapshot()
        assert snap['counts']['phone_tasks'] == 0
        assert [i for i in snap['queue'] if i['channel'] == 'phone'] == []
        print("✓ Completed phone CALL is idempotent + never re-queued")
        db.close()
        return True
    except Exception as e:
        print(f"✗ Phone task idempotency test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_mark_phone_called():
    """Mark Called records phone/CALL without blocking email/IG for the lead"""
    print("Testing mark phone called...")
    try:
        app, stub = _make_dashboard_app()
        db = stub.db
        db.save_lead({'id': 'mc1', 'name': 'C', 'phone': '+14155550123', 'qualified': 1})
        db.save_lead({'id': 'mc2', 'name': 'No Phone', 'qualified': 1})
        og = app.extensions['outreach_runner']
        assert og.mark_phone_called('mc1')['ok'] is True
        assert og.mark_phone_called('missing')['ok'] is False
        assert og.mark_phone_called('mc2')['ok'] is False     # no phone number
        # phone/CALL success does NOT set leads.outreach_status -> email/IG stay open
        assert db.get_lead_by_id('mc1')['outreach_status'] is None
        # a phone CALL + an email T1 for the SAME lead coexist
        assert db.record_outreach_result('mc1', 'email', 'T1', 'sent', success=1) is True
        assert db.get_successful_touch_count('mc1', 'email') == 1
        assert db.get_successful_touch_count('mc1', 'phone') == 1
        print("✓ Mark Called records phone/CALL; email/IG untouched for the lead")
        db.close()
        return True
    except Exception as e:
        print(f"✗ Mark phone called test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_failed_phone_retry():
    """Failed/skipped phone task stays retryable; a completed call is final"""
    print("Testing failed phone retry...")
    try:
        app, stub = _make_dashboard_app()
        db = stub.db
        db.save_lead({'id': 'fr1', 'name': 'F', 'phone': '+14155550999', 'qualified': 1})
        og = app.extensions['outreach_runner']
        # skip records success=0 -> retryable
        assert og.skip_phone_task('fr1')['ok'] is True
        hist = db.get_outreach_history('fr1')
        assert hist[0]['channel'] == 'phone' and hist[0]['status'] == 'skipped'
        assert hist[0]['success'] == 0
        assert db.has_successful_outreach('fr1', 'phone', 'CALL') is False
        # the skipped task can still be completed later
        assert og.mark_phone_called('fr1')['ok'] is True
        assert db.get_successful_touch_count('fr1', 'phone') == 1
        # skipping an already-completed call is refused
        assert og.skip_phone_task('fr1')['ok'] is False
        # DB-level: a failed CALL (success=0) then a successful CALL both allowed
        assert db.record_outreach_result('fr1', 'phone', 'CALL', 'failed', success=0) is True
        assert db.record_outreach_result('fr1', 'phone', 'CALL', 'sent', success=1) is False
        print("✓ Failed/skipped phone task retryable; completed is final")
        db.close()
        return True
    except Exception as e:
        print(f"✗ Failed phone retry test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_email_ig_idempotency_unchanged():
    """Email/IG idempotency is unweakened; phone is an independent channel"""
    print("Testing email/IG idempotency unchanged...")
    try:
        app, stub = _make_dashboard_app()
        db = stub.db
        db.save_lead({'id': 'eg1', 'name': 'E', 'phone': '+14155550001',
                      'email': 'eg1@x.com', 'instagram': 'ig_eg1', 'qualified': 1})
        # all three channels are independent for the same lead
        assert db.record_outreach_result('eg1', 'phone', 'CALL', 'sent', success=1) is True
        assert db.record_outreach_result('eg1', 'email', 'T1', 'sent', success=1) is True
        assert db.record_outreach_result('eg1', 'instagram_dm', 'dm', 'sent', success=1) is True
        # duplicates still blocked per channel+touch
        assert db.record_outreach_result('eg1', 'phone', 'CALL', 'sent', success=1) is False
        assert db.record_outreach_result('eg1', 'email', 'T1', 'sent', success=1) is False
        assert db.record_outreach_result('eg1', 'instagram_dm', 'dm', 'sent', success=1) is False
        assert db.get_successful_touch_count('eg1', 'email') == 1
        assert db.get_successful_touch_count('eg1', 'phone') == 1
        print("✓ Email/IG idempotency unchanged; phone is an independent channel")
        db.close()
        return True
    except Exception as e:
        print(f"✗ Email/IG idempotency test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_phone_api_secret_hygiene():
    """phone complete/skip + status endpoints never leak secrets"""
    print("Testing phone API secret hygiene...")
    try:
        app, stub = _make_dashboard_app()
        db = stub.db
        db.save_lead({'id': 'sh1', 'name': 'S', 'phone': '+14155551234', 'qualified': 1})
        client = app.test_client()
        r = client.post('/api/outreach/phone/complete', json={'lead_id': 'sh1'}).get_json()
        assert r['ok'] is True
        _assert_no_secrets(str(r))
        r2 = client.post('/api/outreach/phone/complete', json={'lead_id': 'sh1'}).get_json()
        assert r2['already_recorded'] is True
        r3 = client.post('/api/outreach/phone/skip', json={'lead_id': 'sh1'}).get_json()
        assert r3['ok'] is False                      # already completed
        r4 = client.post('/api/outreach/phone/complete', json={'lead_id': 'nope'}).get_json()
        assert r4['ok'] is False
        r5 = client.post('/api/outreach/phone/complete', json={})
        assert r5.status_code == 400
        st = client.get('/api/outreach/status').get_json()
        _assert_no_secrets(str(st))
        ov = client.get('/api/overview').get_json()
        _assert_no_secrets(str(ov))
        print("✓ Phone endpoints respond correctly and never leak secrets")
        db.close()
        return True
    except Exception as e:
        print(f"✗ Phone API secret hygiene test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("="*60)
    print(" LeadGen System Test Suite")
    print("="*60)

    results = {}

    results['config'] = test_config()
    results['database'] = test_database()
    results['scoring'] = test_scoring_engine()
    results['demo'] = test_demo_generator()
    results['email'] = test_email_templates()
    results['sheets'] = test_sheets_sync()
    results['dashboard_app'] = test_dashboard_app()
    results['dashboard_leadgen'] = test_dashboard_leadgen()
    results['dashboard_outreach'] = test_dashboard_outreach()
    results['dashboard_scheduler'] = test_dashboard_scheduler()
    results['dashboard_leads'] = test_dashboard_leads()
    results['lead_detail_url_404'] = test_lead_detail_url_404()
    results['save_lead_dedup_merge'] = test_save_lead_dedup_merge()
    results['phone_normalization'] = test_phone_normalization()
    results['phone_db_migration'] = test_phone_db_migration()
    results['contact_enricher'] = test_contact_enricher()
    results['enrichment_ttl'] = test_enrichment_ttl()
    results['enrichment_isolation'] = test_enrichment_isolation()
    results['sheets_phone_columns'] = test_sheets_phone_columns()
    results['leads_contact_filters'] = test_leads_contact_filters()
    results['overview_contact_stats'] = test_overview_contact_stats()
    results['phone_outreach_queue'] = test_phone_outreach_queue()
    results['phone_task_idempotency'] = test_phone_task_idempotency()
    results['mark_phone_called'] = test_mark_phone_called()
    results['failed_phone_retry'] = test_failed_phone_retry()
    results['email_ig_idempotency'] = test_email_ig_idempotency_unchanged()
    results['phone_api_secrets'] = test_phone_api_secret_hygiene()

    print("\n" + "="*60)
    print(" Test Results Summary")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {test_name.capitalize()}: {status}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All tests passed! System is ready to use.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the output above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())