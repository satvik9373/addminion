"""
SchedulerManager
Persistent background scheduler for pipeline runs (APScheduler).

- Default OFF until explicitly enabled.
- Configurable frequency (hours).
- Overlap-safe: APScheduler max_instances=1 + the runner's own running guard.
  Each SchedulerManager is bound to exactly one runner (lead-gen or outreach),
  so a scheduler can never trigger the other pipeline.
- Persists {enabled, frequency_hours, next_run_at, last_run_at, last_status}
  to data/scheduler_config.json so it survives application restarts.
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


class SchedulerManager:
    def __init__(self, runner, config_path: str = 'data/scheduler_config.json'):
        self.runner = runner
        self.config_path = config_path
        self._lock = threading.Lock()
        self._scheduler = None
        self._job = None
        self._cfg = self._load()

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _defaults(self) -> dict:
        return {
            'enabled': False,
            'frequency_hours': 24,
            'next_run_at': None,
            'last_run_at': None,
            'last_status': None,
        }

    def _load(self) -> dict:
        cfg = self._defaults()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as fh:
                    stored = json.load(fh)
                for k in cfg:
                    if k in stored:
                        cfg[k] = stored[k]
            except Exception as e:
                logger.error(f"Failed to load scheduler config: {e}")
        return cfg

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.config_path) or '.', exist_ok=True)
            with open(self.config_path, 'w') as fh:
                json.dump(self._cfg, fh, indent=2)
        except Exception as e:
            logger.error(f"Failed to save scheduler config: {e}")

    # ------------------------------------------------------------------
    # APScheduler wiring
    # ------------------------------------------------------------------

    def _ensure_scheduler(self):
        if self._scheduler and self._scheduler.running:
            return
        self._scheduler = BackgroundScheduler(timezone=None)
        self._scheduler.start()

    def _add_job(self):
        self._ensure_scheduler()
        if self._job and self._job.next_run_time is not None:
            return
        self._job = self._scheduler.add_job(
            self._on_tick, 'interval',
            hours=self._cfg['frequency_hours'],
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

    def _compute_next_run(self):
        freq_h = float(self._cfg['frequency_hours'])
        base = datetime.now()
        stored = self._cfg.get('next_run_at')
        if stored:
            try:
                base = datetime.fromisoformat(stored)
                if base < datetime.now():
                    base = datetime.now()
            except (TypeError, ValueError):
                base = datetime.now()
        self._cfg['next_run_at'] = (base + timedelta(hours=freq_h)).isoformat()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enable(self) -> dict:
        with self._lock:
            self._cfg['enabled'] = True
            self._compute_next_run()
            self._add_job()
            self._save()
            return {'ok': True, 'status': self._status_dict()}

    def disable(self) -> dict:
        with self._lock:
            self._cfg['enabled'] = False
            self._cfg['next_run_at'] = None
            if self._job:
                try:
                    self._job.remove()
                except Exception:
                    pass
                self._job = None
            if self._scheduler:
                try:
                    self._scheduler.shutdown(wait=False)
                except Exception:
                    pass
                self._scheduler = None
            self._save()
            return {'ok': True, 'status': self._status_dict()}

    def set_frequency(self, frequency_hours) -> dict:
        try:
            freq = float(frequency_hours)
            if freq <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return {'ok': False, 'error': 'frequency_hours must be a positive number'}
        with self._lock:
            self._cfg['frequency_hours'] = freq
            if self._cfg['enabled']:
                self._compute_next_run()
                self._add_job()  # re-adds with the new interval
            self._save()
            return {'ok': True, 'status': self._status_dict()}

    def resume_after_restart(self):
        """Re-register the interval job if the config says enabled."""
        if self._cfg.get('enabled'):
            self._add_job()

    def status(self) -> dict:
        with self._lock:
            return self._status_dict()

    def _status_dict(self) -> dict:
        return {
            'enabled': self._cfg.get('enabled', False),
            'frequency_hours': self._cfg.get('frequency_hours'),
            'next_run_at': self._cfg.get('next_run_at'),
            'last_run_at': self._cfg.get('last_run_at'),
            'last_status': self._cfg.get('last_status'),
            'pipeline_running': bool(self.runner.running) if self.runner else False,
        }

    # ------------------------------------------------------------------

    def _on_tick(self):
        """Fired by APScheduler. Records the run then starts the pipeline."""
        now = datetime.now().isoformat()
        self._cfg['last_run_at'] = now
        self._cfg['last_status'] = 'triggered'
        self._compute_next_run()
        self._save()
        result = self.runner.start(run_type='scheduled')
        if not result.get('ok'):
            self._cfg['last_status'] = f"skipped: {result.get('error')}"
            self._save()
