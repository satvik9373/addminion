"""
Database Module
Handles SQLite storage for leads and outreach history
"""

import re
import sqlite3
import json
import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        # One sqlite3 connection per thread. The pipeline runners execute in
        # background threads while the Flask request thread serves the UI; a
        # single shared connection would raise "bad parameter or API misuse"
        # the moment two cursors are active at once (two threads). SQLite file
        # locking keeps these connections consistent with each other.
        self._local = threading.local()

    @property
    def connection(self):
        """Thread-local sqlite3 connection, lazily created on first use."""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            import os
            os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def connect(self):
        """Ensure a connection exists for the calling thread and return it."""
        return self.connection

    def create_tables(self):
        """Create all necessary tables"""
        if not self.connection:
            self.connect()

        cursor = self.connection.cursor()

        # Leads table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id TEXT PRIMARY KEY,
                profile_url TEXT,
                name TEXT,
                email TEXT,
                phone TEXT,
                brokerage TEXT,
                team TEXT,
                role TEXT,
                title TEXT,
                bio TEXT,
                instagram TEXT,
                linkedin TEXT,
                website TEXT,
                zip_code TEXT,
                zip_codes TEXT,
                source TEXT,
                trigger TEXT,
                trigger_score REAL,
                annual_volume REAL,
                avg_sale REAL,
                active_listings TEXT,
                past_sales TEXT,
                monthly_spend TEXT,
                years_experience INTEGER,
                hiring_indication BOOLEAN DEFAULT 0,
                budget_confirmed BOOLEAN DEFAULT 0,
                score INTEGER,
                score_breakdown TEXT,
                category TEXT,
                icp_tier TEXT,
                qualified BOOLEAN DEFAULT 0,
                status TEXT DEFAULT 'new',
                demo_id TEXT,
                loom_link TEXT,
                demo_created_at TEXT,
                first_contact_attempt TIMESTAMP,
                last_contact_attempt TIMESTAMP,
                email_status TEXT,
                email_response TEXT,
                instagram_dm_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Outreach history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS outreach_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id TEXT,
                channel TEXT,
                message_type TEXT,
                subject TEXT,
                content TEXT,
                sent_at TIMESTAMP,
                response_received BOOLEAN DEFAULT 0,
                response_content TEXT,
                FOREIGN KEY (lead_id) REFERENCES leads (id)
            )
        ''')

        # Lead scores table for historical tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lead_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id TEXT,
                score INTEGER,
                score_breakdown TEXT,
                scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lead_id) REFERENCES leads (id)
            )
        ''')

        # Pipeline run history (dashboard)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_type TEXT DEFAULT 'manual',
                status TEXT DEFAULT 'running',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                stages_json TEXT,
                results_json TEXT,
                new_leads INTEGER DEFAULT 0,
                error TEXT
            )
        ''')

        self.connection.commit()
        logger.info("Database tables created successfully")

        # --- Migrations for existing databases (additive only) ---
        self.migrate()

    def migrate(self):
        """Additive migrations so an existing leadgen.db gains new columns/indexes
        without being recreated. Safe to run on every startup."""
        if not self.connection:
            self.connect()

        # Leads: aggregate outreach status for the dashboard
        self._ensure_column('leads', 'outreach_status',
                            'outreach_status TEXT')

        # Leads: phone is a first-class contact channel (additive metadata)
        self._ensure_column('leads', 'phone_type',
                            "phone_type TEXT DEFAULT 'unknown'")
        self._ensure_column('leads', 'phone_source',
                            "phone_source TEXT DEFAULT 'unknown'")
        self._ensure_column('leads', 'phone_verified',
                            'phone_verified INTEGER DEFAULT 0')
        self._ensure_column('leads', 'phone_last_checked',
                            'phone_last_checked TEXT')
        self._ensure_column('leads', 'phone_raw', 'phone_raw TEXT')

        # Leads: contact enrichment bookkeeping (TTL-aware re-enrichment)
        self._ensure_column('leads', 'enrichment_status',
                            'enrichment_status TEXT')
        self._ensure_column('leads', 'enrichment_last_checked',
                            'enrichment_last_checked TEXT')

        # Leads: stable cross-source identity used to merge re-scrapes of the
        # same person (dedup). No unique index — dedup is enforced in
        # save_lead via a lookup so a shared email/phone never hard-fails.
        self._ensure_column('leads', 'canonical_key', 'canonical_key TEXT')

        # Outreach history: per-attempt status + success flag
        self._ensure_column('outreach_history', 'status',
                            "status TEXT DEFAULT 'pending'")
        self._ensure_column('outreach_history', 'success',
                            'success INTEGER DEFAULT 0')

        # Hard idempotency guarantee: at most ONE successful row per
        # (lead, channel, touch). Partial index -> failed/pending rows are
        # unconstrained, so retries can be recorded without duplicating sends.
        self.connection.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS uq_outreach_touch
            ON outreach_history (lead_id, channel, message_type)
            WHERE success = 1
        ''')

        self.connection.commit()

    def _ensure_column(self, table: str, column: str, ddl: str):
        """ALTER TABLE ADD COLUMN if the column is missing."""
        try:
            cols = [row['name'] for row in
                    self.connection.execute(f'PRAGMA table_info({table})')]
            if column not in cols:
                self.connection.execute(f'ALTER TABLE {table} ADD COLUMN {ddl}')
        except Exception as e:
            logger.error(f"Migration failed for {table}.{column}: {e}")

    def _compute_canonical_key(self, lead: Dict) -> Optional[str]:
        """Stable identity across scrapes/sources so the same person is never
        inserted twice. Priority: explicit key -> profile_url -> job_url ->
        source+realtor_id -> email -> phone. Returns None when nothing stable
        is available (a freshly scraped lead with no web identity)."""
        if lead.get('canonical_key'):
            return lead['canonical_key']
        for key in ('profile_url', 'job_url'):
            val = lead.get(key)
            if val:
                return val.strip()
        src = lead.get('source')
        rid = lead.get('realtor_id')
        if src and rid:
            return f"{src}:{rid}".strip()
        email = lead.get('email')
        if email:
            return f"email:{str(email).strip().lower()}"
        phone = lead.get('phone')
        if phone:
            digits = re.sub(r'[^0-9]', '', str(phone))
            if digits:
                return f"phone:{digits}"
        return None

    def save_lead(self, lead: Dict, scored_lead: Dict = None) -> Optional[str]:
        """Save or update a lead with a safe merge upsert.

        The previous INSERT OR REPLACE deleted and re-inserted the row on every
        scrape, which (a) created duplicates when the scrape generated a new id,
        and (b) silently wiped enriched phone/email/Instagram and outreach state
        on re-scrape. This uses:

            INSERT ... ON CONFLICT(id) DO UPDATE SET
                col = COALESCE(excluded.col, leads.col)

        so a re-scrape updates only what the scrape actually provides and never
        destroys existing data; created_at is preserved.

        Dedup: a deterministic id is derived from the profile URL, and a
        canonical_key is stored for cross-source identity. When a lead with the
        same canonical_key already exists under a different id (e.g. a job-post
        lead re-scraped after enrichment), the incoming data is merged into that
        existing row instead of fabricating a duplicate.
        """
        if not self.connection:
            self.connect()

        # Deterministic id — never a timestamp (that fabricated duplicates).
        lead_id = lead.get('id') or lead.get('profile_url')
        canonical = self._compute_canonical_key(lead)

        # Cross-source dedup: merge into an existing row with the same key.
        if not lead_id and canonical:
            existing = self.connection.execute(
                'SELECT id FROM leads WHERE canonical_key = ? LIMIT 1',
                (canonical,)).fetchone()
            if existing:
                lead_id = existing['id']
        lead_id = lead_id or f"lead_{uuid.uuid4().hex[:16]}"
        lead['id'] = lead_id
        lead['canonical_key'] = canonical

        # Handle JSON fields
        lead['zip_codes'] = json.dumps(lead.get('zip_codes', [])) if lead.get('zip_codes') else None
        lead['active_listings'] = json.dumps(lead.get('active_listings', [])) if lead.get('active_listings') else None
        lead['past_sales'] = json.dumps(lead.get('past_sales', [])) if lead.get('past_sales') else None

        # Handle scored lead data
        if scored_lead:
            lead['score'] = scored_lead.get('score')
            lead['score_breakdown'] = json.dumps(scored_lead.get('score_breakdown', {}))
            lead['category'] = scored_lead.get('category')
            lead['icp_tier'] = scored_lead.get('icp_tier')
            lead['qualified'] = int(scored_lead.get('qualified', False))

        # Build params with defaults for all columns (missing keys -> None)
        columns = [
            'id', 'canonical_key', 'profile_url', 'name', 'email', 'phone', 'brokerage', 'team', 'role', 'title', 'bio',
            'instagram', 'linkedin', 'website', 'zip_code', 'zip_codes', 'source', 'trigger',
            'trigger_score', 'annual_volume', 'avg_sale', 'active_listings', 'past_sales',
            'monthly_spend', 'years_experience', 'hiring_indication', 'budget_confirmed',
            'score', 'score_breakdown', 'category', 'icp_tier', 'qualified', 'status',
            'demo_id', 'loom_link', 'demo_created_at', 'first_contact_attempt',
            'last_contact_attempt', 'email_status', 'instagram_dm_status',
            'phone_type', 'phone_source', 'phone_verified', 'phone_last_checked',
            'phone_raw', 'enrichment_status', 'enrichment_last_checked'
        ]
        params = {col: lead.get(col) for col in columns}
        # created_at is bound separately so the INSERT can default it; it is
        # excluded from the conflict-update so an existing row's created_at is
        # never overwritten.
        params['created_at'] = lead.get('created_at')

        # Merge upsert: every writable column falls back to the existing value
        # when the incoming scrape has NULL; created_at is never overwritten.
        update_cols = [c for c in columns if c not in ('id', 'created_at')]
        set_clause = ',\n'.join(
            f'{c} = COALESCE(excluded.{c}, leads.{c})' for c in update_cols
        )

        cursor = self.connection.cursor()
        cursor.execute(f'''
            INSERT INTO leads (
                {', '.join(columns)}, created_at, updated_at
            ) VALUES (
                {', '.join(f':{c}' for c in columns)},
                COALESCE(:created_at, CURRENT_TIMESTAMP),
                CURRENT_TIMESTAMP
            )
            ON CONFLICT(id) DO UPDATE SET
                {set_clause},
                updated_at = CURRENT_TIMESTAMP
        ''', params)

        self.connection.commit()
        return lead_id

    def get_unscored_leads(self, limit: int = 100) -> List[Dict]:
        """Get leads that haven't been scored yet"""
        cursor = self.connection.cursor()

        cursor.execute('''
            SELECT * FROM leads
            WHERE score IS NULL
            ORDER BY created_at DESC
            LIMIT ?
        ''', (limit,))

        leads = []
        for row in cursor.fetchall():
            lead = dict(row)
            # Parse JSON fields
            if lead.get('zip_codes'):
                lead['zip_codes'] = json.loads(lead['zip_codes'])
            if lead.get('active_listings'):
                lead['active_listings'] = json.loads(lead['active_listings'])
            if lead.get('past_sales'):
                lead['past_sales'] = json.loads(lead['past_sales'])
            leads.append(lead)

        return leads

    def update_lead_score(self, lead_id: str, scored_lead: Dict):
        """Update lead with scoring information"""
        cursor = self.connection.cursor()

        cursor.execute('''
            UPDATE leads
            SET score = :score,
                score_breakdown = :score_breakdown,
                category = :category,
                icp_tier = :icp_tier,
                qualified = :qualified
            WHERE id = :lead_id
        ''', {
            'score': scored_lead.get('score'),
            'score_breakdown': json.dumps(scored_lead.get('score_breakdown', {})),
            'category': scored_lead.get('category'),
            'icp_tier': scored_lead.get('icp_tier'),
            'qualified': int(scored_lead.get('qualified', False)),
            'lead_id': lead_id,
        })

        # Also save to history
        cursor.execute('''
            INSERT INTO lead_scores (lead_id, score, score_breakdown)
            VALUES (?, ?, ?)
        ''', (
            lead_id,
            scored_lead.get('score'),
            json.dumps(scored_lead.get('score_breakdown', {}))
        ))

        self.connection.commit()

    def update_lead_status(self, lead_id: str, status: str):
        """Update lead status"""
        cursor = self.connection.cursor()
        cursor.execute('UPDATE leads SET status = ? WHERE id = ?', (status, lead_id))
        self.connection.commit()

    def update_lead_demo_info(self, lead_id: str, demo_info: Dict):
        """Update lead with demo information"""
        cursor = self.connection.cursor()
        cursor.execute('''
            UPDATE leads
            SET demo_id = ?,
                loom_link = ?,
                demo_created_at = ?
            WHERE id = ?
        ''', (
            demo_info.get('demo_id'),
            demo_info.get('loom_link'),
            demo_info.get('created_at'),
            lead_id
        ))
        self.connection.commit()

    def update_lead_contact_info(self, lead_id: str, channel: str, status: str = None, response: str = None):
        """Update lead contact history"""
        cursor = self.connection.cursor()

        update_fields = []
        params = []

        if channel == 'email':
            update_fields.append('email_status = ?')
            params.append(status)
            if response:
                update_fields.append('email_response = ?')
                params.append(response)
        elif channel == 'instagram':
            update_fields.append('instagram_dm_status = ?')
            params.append(status)

        update_fields.append('last_contact_attempt = ?')
        params.append(datetime.now().isoformat())

        update_fields.append('first_contact_attempt = COALESCE(first_contact_attempt, ?)')
        params.append(datetime.now().isoformat())

        params.append(lead_id)

        cursor.execute(f'''
            UPDATE leads
            SET {', '.join(update_fields)}
            WHERE id = ?
        ''', params)

        self.connection.commit()

    def record_outreach(self, lead_id: str, channel: str, message_type: str,
                        subject: str, content: str, response_received: bool = False,
                        response_content: str = None):
        """Record outreach attempt in history"""
        cursor = self.connection.cursor()
        cursor.execute('''
            INSERT INTO outreach_history (lead_id, channel, message_type, subject, content, sent_at, response_received, response_content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            lead_id, channel, message_type, subject, content,
            datetime.now().isoformat(),
            int(response_received),
            response_content
        ))
        self.connection.commit()

    def get_qualified_leads_with_listings(self, min_score: int = 5, limit: int = 50) -> List[Dict]:
        """Get leads that have active listings and meet minimum score"""
        cursor = self.connection.cursor()

        cursor.execute('''
            SELECT * FROM leads
            WHERE score >= ?
              AND (active_listings IS NOT NULL AND active_listings != 'null')
              AND score IS NOT NULL
            ORDER BY score DESC, created_at DESC
            LIMIT ?
        ''', (min_score, limit))

        return self._rows_to_dicts(cursor.fetchall())

    def get_leads_for_outreach(self, categories: List[str] = None, min_score: int = 5, limit: int = 100) -> List[Dict]:
        """Get leads that need outreach"""
        cursor = self.connection.cursor()

        # Map category names
        if categories:
            category_filter = ' OR '.join([f"category LIKE '%{c}%'" for c in categories])
            query = f'''
                SELECT * FROM leads
                WHERE score >= ?
                  AND (email_status IS NULL OR email_status != 'completed')
                  AND ({category_filter})
                ORDER BY score DESC, created_at DESC
                LIMIT ?
            '''
            cursor.execute(query, (min_score, limit))
        else:
            cursor.execute('''
                SELECT * FROM leads
                WHERE score >= ?
                  AND (email_status IS NULL OR email_status != 'completed')
                ORDER BY score DESC, created_at DESC
                LIMIT ?
            ''', (min_score, limit))

        return self._rows_to_dicts(cursor.fetchall())

    def get_leads_with_email_history(self, limit: int = 100) -> List[Dict]:
        """Get leads that have email history for follow-ups"""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT * FROM leads
            WHERE email_status IS NOT NULL
            ORDER BY last_contact_attempt DESC
            LIMIT ?
        ''', (limit,))

        return self._rows_to_dicts(cursor.fetchall())

    def get_leads_by_status(self, status: str, limit: int = 100) -> List[Dict]:
        """Get leads by status"""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT * FROM leads
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (status, limit))

        return self._rows_to_dicts(cursor.fetchall())

    def get_all_scored_leads(self, limit: int = 1000) -> List[Dict]:
        """Get all leads that have been scored"""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT * FROM leads
            WHERE score IS NOT NULL
            ORDER BY score DESC, created_at DESC
            LIMIT ?
        ''', (limit,))

        return self._rows_to_dicts(cursor.fetchall())

    def get_leads_by_ids(self, lead_ids: List[str]) -> List[Dict]:
        """Get leads by IDs"""
        if not lead_ids:
            return []

        placeholders = ', '.join(['?' for _ in lead_ids])
        cursor = self.connection.cursor()
        cursor.execute(f'''
            SELECT * FROM leads
            WHERE id IN ({placeholders})
        ''', lead_ids)

        return self._rows_to_dicts(cursor.fetchall())

    def get_leads_with_email_responses(self, limit: int = 100) -> List[Dict]:
        """Get leads with email responses"""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT * FROM leads
            WHERE email_response IS NOT NULL
              AND email_response != ''
            ORDER BY last_contact_attempt DESC
            LIMIT ?
        ''', (limit,))

        return self._rows_to_dicts(cursor.fetchall())

    def count_leads_since(self, since_date: datetime) -> int:
        """Count leads added since a date"""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM leads
            WHERE created_at > ?
        ''', (since_date.isoformat(),))
        return cursor.fetchone()[0]

    def count_emails_sent_since(self, since_date: datetime) -> int:
        """Count emails sent since a date"""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM outreach_history
            WHERE channel = 'email'
              AND sent_at > ?
        ''', (since_date.isoformat(),))
        return cursor.fetchone()[0]

    # ------------------------------------------------------------------
    # Dashboard read/support methods (additive — existing methods unchanged)
    # ------------------------------------------------------------------

    def count_total_leads(self) -> int:
        """Count all leads in the database"""
        cursor = self.connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM leads')
        return cursor.fetchone()[0]

    def count_leads_by_category(self) -> Dict:
        """Count leads grouped by score category"""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT category, COUNT(*) as c FROM leads
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category
        ''')
        counts = {row['category']: row['c'] for row in cursor.fetchall()}
        # Ensure all buckets present
        return {
            'High Score': counts.get('High Score', 0),
            'Medium Score': counts.get('Medium Score', 0),
            'Low Score': counts.get('Low Score', 0),
            'Disqualified': counts.get('Disqualified', 0),
        }

    def count_qualified_leads(self) -> int:
        """Count qualified leads (score >= LOW threshold and qualified flag)"""
        cursor = self.connection.cursor()
        cursor.execute('SELECT COUNT(*) FROM leads WHERE qualified = 1')
        return cursor.fetchone()[0]

    def count_contacted_leads(self) -> int:
        """Count leads that have had any outreach attempt"""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM leads
            WHERE email_status IS NOT NULL AND email_status != ''
               OR instagram_dm_status IS NOT NULL AND instagram_dm_status != ''
        ''')
        return cursor.fetchone()[0]

    def count_replies(self) -> int:
        """Count leads with an email response or a positive outreach reply"""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM leads
            WHERE (email_response IS NOT NULL AND email_response != '')
               OR status IN ('interested', 'booked_call')
        ''')
        return cursor.fetchone()[0]

    def count_leads_from_latest_run(self) -> int:
        """Count leads created during the most recent pipeline run"""
        latest = self.get_latest_run()
        if not latest:
            return 0
        started = latest.get('started_at')
        if not started:
            return 0
        finished = latest.get('finished_at') or self._ts()
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM leads
            WHERE created_at >= ? AND created_at <= ?
        ''', (started, finished))
        return cursor.fetchone()[0]

    def get_leads(self, query: str = None, source: str = None, category: str = None,
                  status: str = None, min_score: int = None, max_score: int = None,
                  contactable: bool = None, no_contact: bool = None,
                  has_phone: bool = None, has_email: bool = None,
                  has_instagram: bool = None,
                  limit: int = 100, offset: int = 0) -> List[Dict]:
        """Search/filter leads. Any combination of filters is optional."""
        clauses = []
        params = []

        if query:
            clauses.append("(name LIKE ? OR email LIKE ? OR brokerage LIKE ? OR phone LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like, like])
        if source:
            clauses.append("source = ?")
            params.append(source)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if min_score is not None:
            clauses.append("score >= ?")
            params.append(min_score)
        if max_score is not None:
            clauses.append("score <= ?")
            params.append(max_score)

        # Contact-channel filters (phone/email/instagram are first-class)
        _has_phone = "(phone IS NOT NULL AND phone != '' AND phone != 'None')"
        _has_email = "(email IS NOT NULL AND email != '' AND email != 'None')"
        _has_ig = "(instagram IS NOT NULL AND instagram != '' AND instagram != 'None')"
        if has_phone:
            clauses.append(_has_phone)
        if has_email:
            clauses.append(_has_email)
        if has_instagram:
            clauses.append(_has_ig)
        if contactable:
            clauses.append(f"({_has_phone} OR {_has_email} OR {_has_ig})")
        if no_contact:
            clauses.append(f"(NOT ({_has_phone} OR {_has_email} OR {_has_ig}))")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])

        cursor = self.connection.cursor()
        cursor.execute(f'''
            SELECT * FROM leads
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', params)

        return self._rows_to_dicts(cursor.fetchall())

    def get_lead_by_id(self, lead_id: str) -> Optional[Dict]:
        """Get a single lead by ID"""
        cursor = self.connection.cursor()
        cursor.execute('SELECT * FROM leads WHERE id = ?', (lead_id,))
        row = cursor.fetchone()
        return self._rows_to_dicts([row])[0] if row else None

    def count_outreach_by_channel(self) -> Dict:
        """Count outreach records grouped by channel"""
        cursor = self.connection.cursor()
        cursor.execute('SELECT channel, COUNT(*) as c FROM outreach_history GROUP BY channel')
        return {row['channel']: row['c'] for row in cursor.fetchall()}

    def count_outreach_statuses(self) -> Dict:
        """Count leads by email_status and instagram_dm_status values"""
        out = {'email': {}, 'instagram_dm': {}}
        for col, bucket in (('email_status', 'email'), ('instagram_dm_status', 'instagram_dm')):
            cursor = self.connection.cursor()
            cursor.execute(f'SELECT {col} as s, COUNT(*) as c FROM leads WHERE {col} IS NOT NULL AND {col} != "" GROUP BY {col}')
            out[bucket] = {row['s']: row['c'] for row in cursor.fetchall()}
        return out

    def get_distinct_sources(self) -> List[str]:
        """List distinct lead sources present in the database"""
        cursor = self.connection.cursor()
        cursor.execute('SELECT DISTINCT source FROM leads WHERE source IS NOT NULL ORDER BY source')
        return [row['source'] for row in cursor.fetchall()]

    # --- Pipeline run history ---

    @staticmethod
    def _ts(value=None) -> str:
        """Normalize a timestamp to SQLite's 'YYYY-MM-DD HH:MM:SS' format."""
        if value is None:
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        s = str(value)
        s = s.replace('T', ' ')
        s = s.split('.')[0]
        return s

    def record_run(self, run_type: str, status: str, stages: Dict = None,
                   results: Dict = None, new_leads: int = 0,
                   error: str = None, started_at: str = None) -> int:
        """Insert a pipeline run row. Returns the new run id."""
        cursor = self.connection.cursor()
        import json as _json
        cursor.execute('''
            INSERT INTO pipeline_runs (run_type, status, started_at, finished_at,
                                       stages_json, results_json, new_leads, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            run_type, status,
            self._ts(started_at),
            None,
            _json.dumps(stages or {}),
            _json.dumps(results or {}),
            new_leads,
            error,
        ))
        self.connection.commit()
        return cursor.lastrowid

    def update_run(self, run_id: int, status: str = None, stages: Dict = None,
                   results: Dict = None, new_leads: int = None, error: str = None):
        """Update an existing pipeline run row (e.g. mark finished)"""
        import json as _json
        sets, params = [], []
        if status is not None:
            sets.append('status = ?'); params.append(status)
        if stages is not None:
            sets.append('stages_json = ?'); params.append(_json.dumps(stages))
        if results is not None:
            sets.append('results_json = ?'); params.append(_json.dumps(results))
        if new_leads is not None:
            sets.append('new_leads = ?'); params.append(new_leads)
        if error is not None:
            sets.append('error = ?'); params.append(error)
        sets.append('finished_at = ?'); params.append(self._ts())
        params.append(run_id)

        cursor = self.connection.cursor()
        cursor.execute(f'UPDATE pipeline_runs SET {", ".join(sets)} WHERE id = ?', params)
        self.connection.commit()

    def get_run_history(self, limit: int = 20) -> List[Dict]:
        """Fetch recent pipeline runs, newest first"""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT * FROM pipeline_runs
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        runs = []
        for row in cursor.fetchall():
            run = dict(row)
            for key in ('stages_json', 'results_json'):
                if run.get(key):
                    try:
                        run[key.replace('_json', '')] = json.loads(run.pop(key))
                    except Exception:
                        run.pop(key, None)
                else:
                    run.pop(key, None)
            runs.append(run)
        return runs

    def get_latest_run(self) -> Optional[Dict]:
        """Fetch the most recent pipeline run row"""
        runs = self.get_run_history(limit=1)
        return runs[0] if runs else None

    # ------------------------------------------------------------------
    # Outreach idempotency + stats (additive — supports the Outreach runner)
    # ------------------------------------------------------------------

    def has_successful_outreach(self, lead_id: str, channel: str,
                                message_type: str = None) -> bool:
        """True if a successful send already exists for lead+channel (+touch).

        This is the pre-send idempotency check. Combined with the UNIQUE
        partial index on (lead_id, channel, message_type) WHERE success = 1
        and INSERT OR IGNORE in record_outreach_result, duplicate sends are
        impossible even if the dashboard is triggered twice.
        """
        if message_type:
            cursor = self.connection.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM outreach_history
                WHERE lead_id = ? AND channel = ? AND message_type = ? AND success = 1
            ''', (lead_id, channel, message_type))
            return cursor.fetchone()[0] > 0
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM outreach_history
            WHERE lead_id = ? AND channel = ? AND success = 1
        ''', (lead_id, channel))
        return cursor.fetchone()[0] > 0

    def record_outreach_result(self, lead_id: str, channel: str, message_type: str,
                               status: str, subject: str = None, content: str = None,
                               success: int = 0) -> bool:
        """Record an outreach attempt/result into outreach_history.

        Returns True if a row was actually inserted. For successful sends
        (success=1) the INSERT OR IGNORE + unique partial index guarantees
        idempotency: a duplicate successful record is silently dropped and
        returns False.
        """
        cursor = self.connection.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO outreach_history
                (lead_id, channel, message_type, subject, content, sent_at,
                 response_received, response_content, status, success)
            VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
        ''', (
            lead_id, channel, message_type, subject, content,
            datetime.now().isoformat(), status, int(success),
        ))
        self.connection.commit()
        return cursor.rowcount > 0

    def get_outreach_history(self, lead_id: str, limit: int = 20) -> List[Dict]:
        """Return outreach_history rows for a lead, newest first."""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT * FROM outreach_history
            WHERE lead_id = ?
            ORDER BY id DESC LIMIT ?
        ''', (lead_id, limit))
        return self._rows_to_dicts(cursor.fetchall())

    def get_successful_touch_count(self, lead_id: str, channel: str) -> int:
        """How many successful touches a lead has on a channel (drives next touch)."""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM outreach_history
            WHERE lead_id = ? AND channel = ? AND success = 1
        ''', (lead_id, channel))
        return cursor.fetchone()[0]

    def update_lead_outreach_status(self, lead_id: str, status: str):
        """Set the aggregate outreach_status on a lead."""
        cursor = self.connection.cursor()
        cursor.execute('UPDATE leads SET outreach_status = ? WHERE id = ?', (status, lead_id))
        self.connection.commit()

    def get_qualified_leads_for_outreach(self, limit: int = 100) -> List[Dict]:
        """Leads eligible for outreach: qualified AND not already sent/replied.

        Unlike get_leads_for_outreach (which ignores the qualified flag and
        relies on email_status), this is the correct source for the Outreach
        pipeline. It never includes leads already fully outreached.
        """
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT * FROM leads
            WHERE qualified = 1
              AND (outreach_status IS NULL
                   OR outreach_status NOT IN ('sent', 'replied'))
            ORDER BY score DESC, created_at DESC
            LIMIT ?
        ''', (limit,))
        return self._rows_to_dicts(cursor.fetchall())

    def get_outreach_stats(self) -> Dict:
        """Aggregated outreach counts for the dashboard."""
        eligible = self.get_qualified_leads_for_outreach(limit=1000)
        stats = {
            'leads_ready': len(eligible),
            'phone_pending': sum(1 for l in eligible if l.get('phone')),
            'email_pending': sum(1 for l in eligible if l.get('email')),
            'ig_pending': sum(1 for l in eligible if l.get('instagram')),
            'contactable': sum(1 for l in eligible
                               if l.get('phone') or l.get('email')
                               or l.get('instagram')),
            'no_contact': 0,
            'sent': 0, 'failed': 0, 'skipped': 0, 'processing': 0,
            'replied': 0,
        }
        stats['no_contact'] = len(eligible) - stats['contactable']

        cursor = self.connection.cursor()
        cursor.execute("SELECT status, COUNT(*) c FROM outreach_history GROUP BY status")
        for row in cursor.fetchall():
            st = row['status']
            if st == 'sent':
                stats['sent'] += row['c']
            elif st == 'failed':
                stats['failed'] += row['c']
            elif st == 'skipped':
                stats['skipped'] += row['c']
            elif st == 'processing':
                stats['processing'] += row['c']

        cursor.execute('''SELECT COUNT(*) c FROM leads
                          WHERE outreach_status = 'replied'
                             OR (email_response IS NOT NULL AND email_response != '')''')
        stats['replied'] = cursor.fetchone()['c']
        return stats

    # ------------------------------------------------------------------
    # Contact enrichment (additive — supports the Contact Enrichment stage)
    # ------------------------------------------------------------------

    def update_lead_enrichment(self, lead_id: str, fields: Dict):
        """Persist discovered contact/enrichment data for a lead.

        Only keys present in `fields` are updated, so enrichment never wipes
        existing email/instagram/phone data. This is distinct from
        update_lead_contact_info() (which tracks contact *history* status).
        """
        if not isinstance(fields, dict) or not fields:
            return
        allowed = {'phone', 'phone_raw', 'phone_type', 'phone_source',
                   'phone_verified', 'phone_last_checked',
                   'email', 'instagram', 'enrichment_status',
                   'enrichment_last_checked'}
        sets, params = [], []
        for key, val in fields.items():
            if key in allowed and val is not None:
                sets.append(f'{key} = ?')
                params.append(val)
        if not sets:
            return
        params.append(lead_id)
        self.connection.execute(
            f"UPDATE leads SET {', '.join(sets)} WHERE id = ?", params)
        self.connection.commit()

    def get_leads_needing_enrichment(self, limit: int = 50,
                                     ttl_hours: int = 168) -> List[Dict]:
        """Qualified leads whose enrichment data is stale or missing.

        Skips leads enriched within `ttl_hours` (unless the last attempt
        FAILED, which is always retried). Prevents paying/working the same
        lead on every pipeline run.
        """
        cursor = self.connection.cursor()
        cutoff = (datetime.now() - timedelta(hours=ttl_hours)).isoformat()
        cursor.execute('''
            SELECT * FROM leads
            WHERE qualified = 1
              AND (
                    enrichment_last_checked IS NULL
                    OR enrichment_status = 'failed'
                    OR enrichment_last_checked < ?
                  )
            ORDER BY score DESC, created_at DESC
            LIMIT ?
        ''', (cutoff, limit))
        return self._rows_to_dicts(cursor.fetchall())

    def count_leads_with_phone(self) -> int:
        """Qualified leads with a usable phone number."""
        cursor = self.connection.cursor()
        cursor.execute('''SELECT COUNT(*) FROM leads
                          WHERE qualified = 1 AND phone IS NOT NULL
                            AND phone != '' AND phone != 'None' ''')
        return cursor.fetchone()[0]

    def count_leads_with_email(self) -> int:
        cursor = self.connection.cursor()
        cursor.execute('''SELECT COUNT(*) FROM leads
                          WHERE qualified = 1 AND email IS NOT NULL
                            AND email != '' AND email != 'None' ''')
        return cursor.fetchone()[0]

    def count_leads_with_instagram(self) -> int:
        cursor = self.connection.cursor()
        cursor.execute('''SELECT COUNT(*) FROM leads
                          WHERE qualified = 1 AND (
                              instagram IS NOT NULL AND instagram != ''
                              AND instagram != 'None'
                          ) ''')
        return cursor.fetchone()[0]

    def count_contactable_leads(self) -> int:
        """Qualified leads with at least one contact channel."""
        cursor = self.connection.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM leads
            WHERE qualified = 1
              AND (
                    (phone IS NOT NULL AND phone != '' AND phone != 'None')
                 OR (email IS NOT NULL AND email != '' AND email != 'None')
                 OR (instagram IS NOT NULL AND instagram != ''
                     AND instagram != 'None')
              )
        ''')
        return cursor.fetchone()[0]

    def count_leads_without_contact(self) -> int:
        """Qualified leads with no contact channel at all."""
        return max(0, self.count_qualified_leads() - self.count_contactable_leads())

    def _rows_to_dicts(self, rows) -> List[Dict]:
        """Convert SQLite rows to dictionaries"""
        leads = []
        for row in rows:
            lead = dict(row)
            # Parse JSON fields
            if lead.get('zip_codes'):
                try:
                    lead['zip_codes'] = json.loads(lead['zip_codes'])
                except:
                    pass
            if lead.get('active_listings'):
                try:
                    lead['active_listings'] = json.loads(lead['active_listings'])
                except:
                    pass
            if lead.get('past_sales'):
                try:
                    lead['past_sales'] = json.loads(lead['past_sales'])
                except:
                    pass
            if lead.get('score_breakdown'):
                try:
                    lead['score_breakdown'] = json.loads(lead['score_breakdown'])
                except:
                    pass
            leads.append(lead)
        return leads

    def close(self):
        """Close the calling thread's connection (thread-local)."""
        conn = getattr(self._local, 'conn', None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self._local.conn = None