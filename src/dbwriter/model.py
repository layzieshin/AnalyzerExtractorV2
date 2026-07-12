from dataclasses import dataclass


@dataclass(frozen=True)
class DbWriteResult:
    sqlite_path: str
    table_name: str
    status: str  # inserted|skipped
