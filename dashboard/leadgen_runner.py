"""
LeadGenerationRunner
Pipeline 1 of the dashboard: discover, prepare and enrich leads.

Stages: Scraping -> Parsing -> Scoring -> Categorizing -> Contact Enrichment
        -> Google Sheets Sync.

It calls the EXISTING LeadGenSystem stage methods in sequence and NEVER
executes email or Instagram outreach — there is no outreach stage or method
call anywhere in this runner. Parsing/Categorizing resolve immediately because
they happen inside run_daily_scraping() (parsing) and run_scoring_cycle()
(categorization). Contact Enrichment runs BEFORE the final Sheets sync so the
sheet receives phone/email/instagram.

Stage -> method mapping:
    Scraping            -> system.run_daily_scraping()
    Parsing             -> (part of scraping: normalized + saved to DB)
    Scoring             -> system.run_scoring_cycle()
    Categorizing        -> (derived from scores during scoring)
    Contact Enrichment  -> system.run_contact_enrichment()
    Google Sheets Sync  -> system.sync_to_sheets()
"""

import logging
import threading
from datetime import datetime
from typing import Dict, Optional

from .state import RunnerState

logger = logging.getLogger(__name__)

STAGES = ['Scraping', 'Parsing', 'Scoring', 'Categorizing',
          'Contact Enrichment', 'Google Sheets Sync']


class LeadGenerationRunner:
    def __init__(self, system, state: Optional[RunnerState] = None):
        self.system = system
        self.state = state or RunnerState(STAGES)
        self._thread = None
        self._stop_flag = threading.Event()

    @property
    def running(self) -> bool:
        return self.state.status == 'running'

    def start(self, run_type: str = 'manual') -> Dict:
        if self.running:
            return {'ok': False, 'error': 'Lead Generation pipeline already running'}
        self._stop_flag.clear()
        self.state._set(
            status='running', current_stage=STAGES[0], stage_index=0,
            progress=0, message='Starting lead generation...', error=None,
            started_at=datetime.now().isoformat(), finished_at=None,
            stage_results={}, stage_errors={}, run_type=run_type,
        )
        self._thread = threading.Thread(target=self._run, daemon=True, name='leadgen-runner')
        self._thread.start()
        return {'ok': True}

    def stop(self) -> Dict:
        if self.running:
            self._stop_flag.set()
            self.state._set(message='Stop requested - finishing current stage...')
            return {'ok': True, 'message': 'Stop requested'}
        return {'ok': False, 'error': 'Not running'}

    # ------------------------------------------------------------------

    def _begin_stage(self, name: str):
        self.state._set(current_stage=name, stage_index=STAGES.index(name),
                        progress=int(STAGES.index(name) / len(STAGES) * 100),
                        message=f'{name}...')
        self.state._push_log(f'▶ {name}')
        logger.info(f"[leadgen] stage: {name}")

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
        logger.error(f"[leadgen] stage {name} failed: {error}")

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
            run_type=f"leadgen-{self.state.run_type or 'manual'}",
            status='running', started_at=started)
        self.state._set(run_id=run_id)

        stage_methods = {
            'Scraping': 'run_daily_scraping',
            'Scoring': 'run_scoring_cycle',
            'Contact Enrichment': 'run_contact_enrichment',
            'Google Sheets Sync': 'sync_to_sheets',
        }

        try:
            for idx in range(len(STAGES)):
                if self._stop_flag.is_set():
                    db.update_run(run_id, status='stopped')
                    self.state._set(status='stopped', message='Stopped by user',
                                    progress=100, finished_at=datetime.now().isoformat())
                    return

                stage = STAGES[idx]
                self._begin_stage(stage)

                if stage == 'Parsing':
                    self._end_stage(stage, {'saved': True})
                    continue
                if stage == 'Categorizing':
                    self._end_stage(stage, {'categorized': True})
                    continue

                method_name = stage_methods[stage]
                method = getattr(self.system, method_name)
                try:
                    result = method()
                    self._end_stage(stage, result)
                except Exception as e:
                    self._fail_stage(stage, str(e))
                    with self.state._lock:
                        self.state.stage_results[stage] = {'error': str(e)}

            new_leads = 0
            scraped = self.state.stage_results.get('Scraping') or {}
            if isinstance(scraped, dict):
                new_leads = scraped.get('saved_to_db') or scraped.get('total_new_leads') or 0

            db.update_run(
                run_id, status='completed',
                stages={s: ('ok' if s not in self.state.stage_errors else 'failed')
                        for s in STAGES},
                results=self.state.stage_results, new_leads=new_leads)
            self.state._set(status='completed', message='Lead generation complete',
                            progress=100, finished_at=datetime.now().isoformat())
            self.state._push_log('✔ Lead generation complete')
            logger.info("[leadgen] complete")

        except Exception as e:
            logger.exception("[leadgen] fatal error")
            try:
                db.update_run(run_id, status='failed', error=str(e))
            except Exception:
                pass
            self.state._set(status='failed', error=str(e), message=f'Pipeline failed: {e}',
                            finished_at=datetime.now().isoformat())
            self.state._push_log(f'✘ Pipeline FAILED: {e}')
