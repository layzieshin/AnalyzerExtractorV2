from __future__ import annotations

import time
from pathlib import Path
from typing import List

from src.ingestion.api import (
    SOURCE_WATCH_FOLDER,
    IngestionError,
    StabilityScannerState,
    observe_stable_pdfs,
    register_import,
)
from src.jobqueue.api import QueueJob, enqueue_pdf_job, list_jobs


class WatchdogService:
    def __init__(
        self,
        project_root: str,
        watch_dir: str,
        scan_interval_s: float = 3.0,
        stable_window_s: float = 1.0,
        watch_backup_path: str = "",
    ) -> None:
        self.project_root = project_root
        self.watch_dir = Path(watch_dir)
        self.scan_interval_s = scan_interval_s
        self.stable_window_s = stable_window_s
        self.watch_backup_path = watch_backup_path
        self._scanner_state = StabilityScannerState()

    def scan_once(self) -> List[QueueJob]:
        if not str(self.watch_backup_path or "").strip():
            raise IngestionError("watch_backup_path_required")

        created: List[QueueJob] = []
        before_ids = {job.job_id for job in list_jobs(self.project_root)}

        def enqueue(pdf_path: str, source: str, expected_sha256: str | None) -> QueueJob:
            return enqueue_pdf_job(
                self.project_root,
                pdf_path,
                source=source,
                expected_sha256=expected_sha256,
            )

        stable_pdfs = observe_stable_pdfs(
            self.watch_dir,
            stable_window_s=self.stable_window_s,
            state=self._scanner_state,
        )
        for pdf in stable_pdfs:
            register_import(
                self.project_root,
                pdf,
                source_kind=SOURCE_WATCH_FOLDER,
                enqueue=enqueue,
                watch_input_path=str(self.watch_dir),
                watch_backup_path=self.watch_backup_path,
                source_label="watchdog",
            )

        for job in list_jobs(self.project_root):
            if job.job_id not in before_ids:
                created.append(job)
        return created

    def run_forever(self) -> None:
        while True:
            self.scan_once()
            time.sleep(self.scan_interval_s)
