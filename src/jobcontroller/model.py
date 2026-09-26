from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True)
class JobResult:
    job_id: str
    pdf_path: str
    status: str  # DONE|FAILED|SKIPPED|PENDING|PROCESSING
    details: Dict[str, object]

