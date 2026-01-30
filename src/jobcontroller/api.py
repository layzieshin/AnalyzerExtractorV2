from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .jobcontroller import JobController
from .jobcontroller import JobResult



def submit(pdf_path: str, project_root: str) -> JobResult:
    """Public API (JobController)

    Contract:
    - job_id = sha256(file_bytes)[:16]
    - lock file under locks/<job_id>.lock (create-exclusive)
    - state file under jobs/<job_id>.json
    - serial pipeline
    """
    return JobController().submit(pdf_path, project_root)
