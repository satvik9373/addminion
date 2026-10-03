"""
RunnerState
Shared thread-safe pipeline state for both dashboard runners (Lead Generation
and Outreach). A runner writes to it; the web UI reads snapshots of it.
"""

import threading
from collections import deque
from datetime import datetime
from typing import Dict, List


class RunnerState:
    """Thread-safe snapshot of a pipeline run's live state."""

    def __init__(self, stages: List[str]):
        self._lock = threading.Lock()
        self.status = 'idle'          # idle | running | completed | failed | stopped
        self.current_stage = None
        self.stage_index = -1
        self.stages = list(stages)
        self.progress = 0             # 0-100
        self.message = ''
        self.error = None
        self.started_at = None
        self.finished_at = None
        self.stage_results = {}       # stage name -> result dict
        self.stage_errors = {}        # stage name -> error string
        self.run_id = None
        self.run_type = None
        self._log = deque(maxlen=200)

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                'status': self.status,
                'current_stage': self.current_stage,
                'stage_index': self.stage_index,
                'stages': list(self.stages),
                'progress': self.progress,
                'message': self.message,
                'error': self.error,
                'started_at': self.started_at,
                'finished_at': self.finished_at,
                'stage_results': dict(self.stage_results),
                'stage_errors': dict(self.stage_errors),
                'run_id': self.run_id,
                'run_type': self.run_type,
                'log': list(self._log),
            }

    def _set(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def _push_log(self, line: str):
        with self._lock:
            self._log.append(f"{datetime.now().strftime('%H:%M:%S')} {line}")
