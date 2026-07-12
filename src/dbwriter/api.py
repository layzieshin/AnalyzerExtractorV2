from __future__ import annotations

from src.extractor.api import AssayRecord
from src.ruleresolver.api import RuleSet

from .dbwriter import DbWriter
from .model import DbWriteResult

__all__ = ["DbWriteResult", "get_duplicate_candidate", "list_duplicate_candidates", "write_record_sqlite"]


def write_record_sqlite(
    record: AssayRecord,
    ruleset: RuleSet,
    sqlite_path: str,
    job_id: str = "",
    pdf_path: str = "",
    pdf_sha256: str = "",
    assay_block_hash: str = "",
    busy_timeout_ms: int = 5000,
    retry_count: int = 3,
    retry_sleep_s: float = 0.2,
) -> DbWriteResult:
    """Public API (DbWriter)"""
    return DbWriter().write_record(
        record,
        ruleset,
        sqlite_path,
        job_id=job_id,
        pdf_path=pdf_path,
        pdf_sha256=pdf_sha256,
        assay_block_hash=assay_block_hash,
        busy_timeout_ms=busy_timeout_ms,
        retry_count=retry_count,
        retry_sleep_s=retry_sleep_s,
    )


def list_duplicate_candidates(sqlite_path: str, status: str = "pending") -> list[dict[str, object]]:
    """Return duplicate review candidates from the SQLite ledger."""
    return DbWriter().list_duplicate_candidates(sqlite_path, status=status)


def get_duplicate_candidate(sqlite_path: str, candidate_id: int) -> dict[str, object] | None:
    """Return one duplicate candidate with existing run and field comparison."""
    return DbWriter().get_duplicate_candidate(sqlite_path, candidate_id)
