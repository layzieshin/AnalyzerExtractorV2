from dataclasses import dataclass


@dataclass(frozen=True)
class DbWriteResult:
    sqlite_path: str
    table_name: str
    status: str  # inserted|skipped|duplicate_pending
    run_id: int | None = None
    existing_run_id: int | None = None
    duplicate_candidate_id: int | None = None
