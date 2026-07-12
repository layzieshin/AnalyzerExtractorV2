from __future__ import annotations

from src.extractor.api import AssayRecord
from src.ruleresolver.api import RuleSet

from .dbwriter import DbWriter
from .model import DbWriteResult


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
