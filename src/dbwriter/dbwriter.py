from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from src.extractor.api import AssayRecord
from src.ruleresolver.api import RuleSet

from .model import DbWriteResult


class DbWriter:
    def write_record(
        self,
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
        path = Path(sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        last_error: Exception | None = None
        for attempt in range(1, retry_count + 1):
            conn = sqlite3.connect(str(path))
            try:
                conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
                self._ensure_schema(conn)
                status = self._insert_or_skip(conn, record, ruleset, job_id, pdf_path, pdf_sha256, assay_block_hash)
                conn.commit()
                return DbWriteResult(sqlite_path=str(path), table_name="runs", status=status)
            except sqlite3.OperationalError as e:
                last_error = e
                if "locked" not in str(e).lower() or attempt == retry_count:
                    raise
                time.sleep(retry_sleep_s)
            finally:
                conn.close()

        # should be unreachable; keeps typing explicit
        if last_error:
            raise last_error
        raise RuntimeError("sqlite_write_failed_unknown")

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                pdf_path TEXT NOT NULL,
                assay_key TEXT NOT NULL,
                lot_id TEXT NOT NULL,
                dedupe_key TEXT NOT NULL,
                device_id TEXT,
                dedupe_version TEXT,
                dedupe_basis_json TEXT,
                pdf_sha256 TEXT,
                assay_block_hash TEXT,
                ruleset_file TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(assay_key, dedupe_key)
            )
            """
        )
        self._ensure_columns(
            conn,
            {
                "device_id": "TEXT",
                "dedupe_version": "TEXT",
                "dedupe_basis_json": "TEXT",
                "pdf_sha256": "TEXT",
                "assay_block_hash": "TEXT",
            },
        )

    def _ensure_columns(self, conn: sqlite3.Connection, columns: dict[str, str]) -> None:
        existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        for name, sql_type in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {sql_type}")

    def _insert_or_skip(
        self,
        conn: sqlite3.Connection,
        record: AssayRecord,
        ruleset: RuleSet,
        job_id: str,
        pdf_path: str,
        pdf_sha256: str,
        assay_block_hash: str,
    ) -> str:
        payload = json.dumps(record.data, ensure_ascii=False)
        basis_payload = json.dumps(record.dedupe_basis, ensure_ascii=False)
        created_at = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO runs (
                job_id, pdf_path, assay_key, lot_id, dedupe_key,
                device_id, dedupe_version, dedupe_basis_json, pdf_sha256, assay_block_hash,
                ruleset_file, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                pdf_path,
                record.assay_key,
                record.lot_id,
                record.dedupe_key,
                record.device_id,
                record.dedupe_version,
                basis_payload,
                pdf_sha256,
                assay_block_hash,
                ruleset.ruleset_file,
                payload,
                created_at,
            ),
        )
        return "inserted" if cur.rowcount else "skipped"
