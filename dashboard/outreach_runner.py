"""
OutreachRunner
Pipeline 2 of the dashboard: process EXISTING qualified leads only.

It NEVER scrapes or scores new leads. It queries qualified leads, checks
eligibility + previous outreach history, builds a queue, then processes the
enabled channels (Email, Instagram) through the EXISTING leadgen modules
(email_sender, instagram_dm, demo_generator). Every attempt/result is recorded
to outreach_history.

MODES:
    dry_run (default) — builds and previews the exact queue; sends nothing,
                        records nothing.
    live              — actually sends email/IG through the existing modules
                        and records each attempt/result. Requires explicit
                        user action. Phone is ALWAYS a manual task in both
                        modes (never auto-dialed, never SMS'd).

CHANNELS: phone (manual call task), email (T1-T5 sequence), instagram_dm (dm).

DUPLICATE PROTECTION:
    - Pre-send DB check  : has_successful_outreach(lead, channel, touch)
    - Hard DB guarantee  : UNIQUE partial index on outreach_history
                           (lead_id, channel, message_type) WHERE success = 1
                           + INSERT OR IGNORE in record_outreach_result.
    So the same channel+touch can never be sent twice to the same lead, even if
    this runner is triggered twice. Phone uses message_type='CALL'.

OUTREACH STATUS enum (outreach_history.status / leads.outreach_status):
    pending | processing | sent | failed | replied | skipped
"""

import json
import logging
import os
import threading
from datetime import datetime
from typing import Dict, List, Optional

from .state import RunnerState

logger = logging.getLogger(__name__)

STAGES = ['Query Leads', 'Check Eligibility', 'Check Contact Availability',
          'Check History', 'Build Queue', 'Phone Tasks', 'Email', 'Instagram',
          'Record Results']

EMAIL_TOUCHES = 5  # T1..T5 sequence


class OutreachRunner:
    def __init__(self, system, state: Optional[RunnerState] = None,
                 config_path: str = 'data/outreach_config.json'):
        self.system = system
        self.state = state or RunnerState(STAGES)
        self._thread = None
        self._stop_flag = threading.Event()
        self._cfg_path = config_path
        self._cfg = self._load_cfg()

        self.queue: List[Dict] = []
        self.counts = {'leads_ready': 0, 'contactable': 0, 'no_contact': 0,
                       'previewed': 0, 'phone_tasks': 0,
                       'sent': 0, 'failed': 0, 'skipped': 0}
        self.current_channel = None

    # ------------------------------------------------------------------
    # Config: mode + enabled channels (persisted)
    # ------------------------------------------------------------------

    def _load_cfg(self) -> dict:
        cfg = {'mode': 'dry_run',
               'channels': {'phone': True, 'email': True, 'instagram_dm': True}}
        if os.path.exists(self._cfg_path):
            try:
                with open(self._cfg_path, 'r') as fh:
                    stored = json.load(fh)
                for k in ('mode', 'channels'):
                    if k in stored:
                        cfg[k] = stored[k]
            except Exception as e:
                logger.error(f"Failed to load outreach config: {e}")
        # Ensure new channels default to ON even for configs written before they
        # existed (old configs won't have the 'phone' key).
        defaults = {'phone': True, 'email': True, 'instagram_dm': True}
        defaults.update(cfg.get('channels', {}))
        cfg['channels'] = defaults
        return cfg

    def _save_cfg(self):
        try:
            os.makedirs(os.path.dirname(self._cfg_path) or '.', exist_ok=True)
            with open(self._cfg_path, 'w') as fh:
                json.dump(self._cfg, fh, indent=2)
        except Exception as e:
            logger.error(f"Failed to save outreach config: {e}")

    def get_mode(self) -> str:
        return self._cfg.get('mode', 'dry_run')

    def set_mode(self, mode: str) -> dict:
        if mode not in ('dry_run', 'live'):
            return {'ok': False, 'error': 'mode must be dry_run or live'}
        self._cfg['mode'] = mode
        self._save_cfg()
        return {'ok': True, 'mode': mode}

    def get_channels(self) -> dict:
        return dict(self._cfg.get('channels', {}))

    def set_channels(self, channels: dict) -> dict:
        allowed = {'phone', 'email', 'instagram_dm'}
        if not isinstance(channels, dict) or not set(channels).issubset(allowed):
            return {'ok': False, 'error': 'channels must be a subset of phone/email/instagram_dm'}
        cur = self.get_channels()
        for ch in allowed:
            if ch in channels:
                cur[ch] = bool(channels[ch])
        self._cfg['channels'] = cur
        self._save_cfg()
        return {'ok': True, 'channels': cur}

    # ------------------------------------------------------------------
    # Snapshot for the UI
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict:
        snap = self.state.snapshot()
        snap.update({
            'mode': self.get_mode(),
            'channels': self.get_channels(),
            'queue': list(self.queue),
            'counts': dict(self.counts),
            'current_channel': self.current_channel,
        })
        return snap

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.state.status == 'running'

    def start(self, run_type: str = 'manual') -> Dict:
        if self.running:
            return {'ok': False, 'error': 'Outreach pipeline already running'}
        self._stop_flag.clear()
        self.queue = []
        self.counts = {'leads_ready': 0, 'contactable': 0, 'no_contact': 0,
                       'previewed': 0, 'phone_tasks': 0,
                       'sent': 0, 'failed': 0, 'skipped': 0}
        self.current_channel = None
        self.state._set(
            status='running', current_stage=STAGES[0], stage_index=0,
            progress=0, message='Starting outreach...', error=None,
            started_at=datetime.now().isoformat(), finished_at=None,
            stage_results={}, stage_errors={}, run_type=run_type,
        )
        self._thread = threading.Thread(target=self._run, daemon=True, name='outreach-runner')
        self._thread.start()
        return {'ok': True}

    def stop(self) -> Dict:
        if self.running:
            self._stop_flag.set()
            self.state._set(message='Stop requested - finishing current stage...')
            return {'ok': True, 'message': 'Stop requested'}
        return {'ok': False, 'error': 'Not running'}

    # ------------------------------------------------------------------
    # Phone call tasks (MANUAL only — no automated dialing / SMS)
    # ------------------------------------------------------------------

    def mark_phone_called(self, lead_id: str) -> Dict:
        """Record a manually-completed phone call. Idempotent: a duplicate
        successful CALL for the same lead is silently ignored (partial UNIQUE
        index on (lead_id, channel, message_type) WHERE success=1)."""
        lead = self.system.db.get_lead_by_id(lead_id)
        if not lead:
            return {'ok': False, 'error': 'Lead not found'}
        if not lead.get('phone'):
            return {'ok': False, 'error': 'Lead has no phone number'}
        inserted = self.system.db.record_outreach_result(
            lead_id, 'phone', 'CALL', status='sent',
            subject='phone-call', content=lead.get('phone'), success=1)
        return {'ok': True, 'already_recorded': not inserted}

    def skip_phone_task(self, lead_id: str) -> Dict:
        """Skip a phone call task. Records a skipped (success=0) row, which is
        NOT covered by the idempotency index, so the task stays retryable."""
        lead = self.system.db.get_lead_by_id(lead_id)
        if not lead:
            return {'ok': False, 'error': 'Lead not found'}
        if self.system.db.has_successful_outreach(lead_id, 'phone', 'CALL'):
            return {'ok': False, 'error': 'Phone call already completed'}
        self.system.db.record_outreach_result(
            lead_id, 'phone', 'CALL', status='skipped',
            subject='phone-call', content=lead.get('phone'), success=0)
        return {'ok': True}

    # ------------------------------------------------------------------
    # Stage helpers (mirrors leadgen_runner)
    # ------------------------------------------------------------------

    def _begin_stage(self, name: str):
        self.state._set(current_stage=name, stage_index=STAGES.index(name),
                        progress=int(STAGES.index(name) / len(STAGES) * 100),
                        message=f'{name}...')
        self.state._push_log(f'▶ {name}')
        logger.info(f"[outreach] stage: {name}")

    def _end_stage(self, name: str, result):
        with self.state._lock:
            self.state.stage_results[name] = result
        self.state._set(progress=int((STAGES.index(name) + 1) / len(STAGES) * 100),
                        message=f'{name} complete')
        self.state._push_log(f'✔ {name} complete')

    def _fail_stage(self, name: str, error: str):
        with self.state._lock:
            self.state.stage_errors[name] = error
        self.state._push_log(f'✘ {name} FAILED: {error}')
        logger.error(f"[outreach] stage {name} failed: {error}")

    # ------------------------------------------------------------------
    # Eligibility
    # ------------------------------------------------------------------

    def _channel_eligible(self, lead: Dict, channel: str) -> bool:
        if channel == 'phone':
            return bool(lead.get('phone'))
        if channel == 'email':
            return bool(lead.get('email'))
        if channel == 'instagram_dm':
            return bool(lead.get('instagram'))
        return False

    def _next_email_touch(self, lead: Dict) -> int:
        sent = self.system.db.get_successful_touch_count(lead.get('id'), 'email')
        return min(sent + 1, EMAIL_TOUCHES)

    def _build_queue_item(self, lead: Dict, channel: str, message_type: str) -> Dict:
        if channel == 'phone':
            to = lead.get('phone')
        elif channel == 'email':
            to = lead.get('email')
        else:
            to = lead.get('instagram')
        return {
            'lead_id': lead.get('id'),
            'name': lead.get('name'),
            'channel': channel,
            'message_type': message_type,
            'to': to,
            'brokerage': lead.get('brokerage'),
            'phone_source': lead.get('phone_source'),
        }

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def _run(self):
        db = self.system.db
        if getattr(db, 'connection', None) is None:
            try:
                db.connect()
                db.create_tables()
            except Exception:
                pass

        started = self.state.started_at
        run_id = db.record_run(
            run_type=f"outreach-{self.state.run_type or 'manual'}",
            status='running', started_at=started)
        self.state._set(run_id=run_id)

        mode = self.get_mode()
        channels = self.get_channels()

        try:
            # 1. Query Leads
            self._begin_stage('Query Leads')
            leads = db.get_qualified_leads_for_outreach(limit=200)
            self.counts['leads_ready'] = len(leads)
            self._end_stage('Query Leads', {'leads': len(leads)})

            # 2. Check Eligibility
            self._begin_stage('Check Eligibility')
            eligible = []
            for lead in leads:
                chan_list = [c for c in ('phone', 'email', 'instagram_dm')
                             if channels.get(c) and self._channel_eligible(lead, c)]
                if chan_list:
                    eligible.append((lead, chan_list))
            self._end_stage('Check Eligibility', {'eligible': len(eligible)})

            # 3. Check Contact Availability (channel readiness breakdown)
            self._begin_stage('Check Contact Availability')
            contactable = [l for l in leads
                           if (l.get('phone') or l.get('email')
                               or l.get('instagram'))]
            self.counts['contactable'] = len(contactable)
            self.counts['no_contact'] = len(leads) - len(contactable)
            self._end_stage('Check Contact Availability',
                            {'contactable': len(contactable),
                             'no_contact': len(leads) - len(contactable)})

            # 4. Check History (DB idempotency)
            self._begin_stage('Check History')
            candidates = []
            for lead, chan_list in eligible:
                for ch in chan_list:
                    if ch == 'email':
                        touch = self._next_email_touch(lead)
                        msg_type = f'T{touch}'
                    elif ch == 'phone':
                        msg_type = 'CALL'
                    else:
                        msg_type = 'dm'
                    if db.has_successful_outreach(lead['id'], ch, msg_type):
                        self.counts['skipped'] += 1
                    else:
                        candidates.append((lead, ch, msg_type))
            self._end_stage('Check History', {'already_sent': self.counts['skipped']})

            # 4. Build Queue
            self._begin_stage('Build Queue')
            self.queue = [self._build_queue_item(l, ch, mt) for l, ch, mt in candidates]
            self._end_stage('Build Queue', {'queued': len(self.queue)})

            if self._stop_flag.is_set():
                raise StopIteration('stopped')

            # 5. Phone Tasks — manual call tasks only. Never auto-dialed and
            #    never SMS'd. In BOTH dry_run and live the phone channel only
            #    produces tasks the user executes from the UI (Mark Called /
            #    Skip). Idempotency is enforced by the CALL entry in
            #    outreach_history.
            self._begin_stage('Phone Tasks')
            phone_items = [i for i in self.queue if i['channel'] == 'phone']
            self.current_channel = 'phone' if phone_items else None
            self.counts['phone_tasks'] = len(phone_items)
            self.counts['previewed'] += len(phone_items)
            self._end_stage('Phone Tasks', {'tasks': len(phone_items)})

            if self._stop_flag.is_set():
                raise StopIteration('stopped')

            # 6. Email
            self._begin_stage('Email')
            email_items = [i for i in self.queue if i['channel'] == 'email']
            self.current_channel = 'email' if email_items else None
            if mode == 'dry_run':
                self.counts['previewed'] += len(email_items)
                self._end_stage('Email', {'would_send': len(email_items), 'mode': 'dry_run'})
            else:
                self._process_email_items(email_items, candidates)
                self._end_stage('Email', dict(self.counts))

            if self._stop_flag.is_set():
                raise StopIteration('stopped')

            # 7. Instagram
            self._begin_stage('Instagram')
            ig_items = [i for i in self.queue if i['channel'] == 'instagram_dm']
            self.current_channel = 'instagram_dm' if ig_items else None
            if mode == 'dry_run':
                self.counts['previewed'] += len(ig_items)
                self._end_stage('Instagram', {'would_send': len(ig_items), 'mode': 'dry_run'})
            else:
                self._process_ig_items(ig_items, candidates)
                self._end_stage('Instagram', dict(self.counts))

            # 8. Record Results
            self._begin_stage('Record Results')
            db.update_run(
                run_id, status='completed',
                stages={s: ('ok' if s not in self.state.stage_errors else 'failed')
                        for s in STAGES},
                results={'mode': mode, **self.counts}, new_leads=0)
            self.state._set(status='completed', message='Outreach complete',
                            progress=100, finished_at=datetime.now().isoformat())
            self.state._push_log(
                f"✔ Outreach complete ({mode}): {self.counts['sent']} sent, "
                f"{self.counts['failed']} failed, {self.counts['skipped']} skipped, "
                f"{self.counts['previewed']} previewed")
            logger.info("[outreach] complete")

        except StopIteration:
            db.update_run(run_id, status='stopped')
            self.state._set(status='stopped', message='Stopped by user',
                            progress=100, finished_at=datetime.now().isoformat())
            return

        except Exception as e:
            logger.exception("[outreach] fatal error")
            try:
                db.update_run(run_id, status='failed', error=str(e))
            except Exception:
                pass
            self.state._set(status='failed', error=str(e), message=f'Outreach failed: {e}',
                            finished_at=datetime.now().isoformat())
            self.state._push_log(f'✘ Outreach FAILED: {e}')

    # ------------------------------------------------------------------
    # LIVE senders (reuse existing leadgen modules)
    # ------------------------------------------------------------------

    def _process_email_items(self, items: List[Dict], candidates):
        db = self.system.db
        email_sender = self.system.email_sender
        for item in items:
            if self._stop_flag.is_set():
                return
            lead = self._find_lead(item, candidates)
            if lead is None:
                continue
            touch = int(item['message_type'][1:])
            # Belt-and-braces re-check right before sending
            if db.has_successful_outreach(item['lead_id'], 'email', item['message_type']):
                self.counts['skipped'] += 1
                continue
            # Module-level sequence gate (JSON history + day gaps)
            if not email_sender.can_send_next_email(item['lead_id']):
                self.counts['skipped'] += 1
                self.state._push_log(f'⏭ skip email {item["name"]} (sequence gate)')
                continue
            try:
                loom = None
                demo = self.system.demo_generator.get_demo_for_lead(lead)
                if demo:
                    loom = demo.get('loom_link')
                ok = email_sender.send_sequence_email(lead, touch, loom)
            except Exception as e:
                logger.error(f"[outreach] email send error for {item['lead_id']}: {e}")
                ok = False
            db.record_outreach_result(
                item['lead_id'], 'email', item['message_type'],
                status='sent' if ok else 'failed',
                subject=item['message_type'], success=1 if ok else 0)
            if ok:
                self.counts['sent'] += 1
                db.update_lead_outreach_status(item['lead_id'], 'sent')
                self.state._push_log(f'✓ email sent: {item["name"]} ({item["message_type"]})')
            else:
                self.counts['failed'] += 1
                db.update_lead_outreach_status(item['lead_id'], 'failed')
                self.state._push_log(f'✘ email failed: {item["name"]} ({item["message_type"]})')

    def _process_ig_items(self, items: List[Dict], candidates):
        db = self.system.db
        ig = self.system.instagram_dm
        if not ig:
            from leadgen.outreach.instagram_dm import InstagramDM
            ig = InstagramDM(self.system.config)
            self.system.instagram_dm = ig
        for item in items:
            if self._stop_flag.is_set():
                return
            lead = self._find_lead(item, candidates)
            if lead is None:
                continue
            if db.has_successful_outreach(item['lead_id'], 'instagram_dm', 'dm'):
                self.counts['skipped'] += 1
                continue
            if not ig.can_send_next_dm(item['lead_id']):
                self.counts['skipped'] += 1
                self.state._push_log(f'⏭ skip IG {item["name"]} (module gate)')
                continue
            try:
                if lead.get('instagram'):
                    ok = ig.send_dm(lead.get('instagram'), lead)
                else:
                    ok = False
            except Exception as e:
                logger.error(f"[outreach] IG send error for {item['lead_id']}: {e}")
                ok = False
            db.record_outreach_result(
                item['lead_id'], 'instagram_dm', 'dm',
                status='sent' if ok else 'failed', success=1 if ok else 0)
            if ok:
                self.counts['sent'] += 1
                db.update_lead_outreach_status(item['lead_id'], 'sent')
                self.state._push_log(f'✓ DM sent: {item["name"]}')
            else:
                self.counts['failed'] += 1
                db.update_lead_outreach_status(item['lead_id'], 'failed')
                self.state._push_log(f'✘ DM failed: {item["name"]}')

    @staticmethod
    def _find_lead(item: Dict, candidates) -> Optional[Dict]:
        for lead, ch, mt in candidates:
            if lead.get('id') == item['lead_id'] and ch == item['channel']:
                return lead
        return None
