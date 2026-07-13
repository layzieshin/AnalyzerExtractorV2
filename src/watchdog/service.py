from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Tuple

from src.jobqueue.api import QueueJob, enqueue_pdf_job


class WatchdogService:
    def __init__(
        self,
        project_root: str,
        watch_dir: str,
        scan_interval_s: float = 3.0,
        stable_window_s: float = 1.0,
    ) -> None:
        self.project_root = project_root
        self.watch_dir = Path(watch_dir)
        self.scan_interval_s = scan_interval_s
        self.stable_window_s = stable_window_s
        self._size_observations: Dict[str, Tuple[int, float]] = {}

    def scan_once(self) -> List[QueueJob]:
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        created: List[QueueJob] = []

        for pdf in sorted(self.watch_dir.glob("*.pdf")):
            if not pdf.is_file():
                continue
            if not self._is_stable(pdf):
                continue
            job = enqueue_pdf_job(self.project_root, str(pdf), source="watchdog")
            created.append(job)
        return created

    def run_forever(self) -> None:
        while True:
            self.scan_once()
            time.sleep(self.scan_interval_s)

    def _is_stable(self, path: Path) -> bool:
        key = str(path.resolve())
        size = path.stat().st_size
        now = time.time()
        if self.stable_window_s <= 0:
            self._size_observations[key] = (size, now)
            return True

        prev = self._size_observations.get(key)
        self._size_observations[key] = (size, now)
        if prev is None:
            return False

        prev_size, prev_ts = prev
        if prev_size != size:
            return False

        return (now - prev_ts) >= self.stable_window_s
