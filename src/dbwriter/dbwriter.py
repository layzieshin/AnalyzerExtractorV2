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
                result = self._insert_or_candidate(
                    conn,
                    record,
                    ruleset,
                    job_id,
                    pdf_path,
                    pdf_sha256,
                    assay_block_hash,
                    str(path),
                )
                conn.commit()
                return result
            except sqlite3.OperationalError as e:
                conn.rollback()
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS duplicate_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                existing_run_id INTEGER NOT NULL,
                assay_key TEXT NOT NULL,
                dedupe_key TEXT NOT NULL,
                device_id TEXT,
                dedupe_version TEXT,
                dedupe_basis_json TEXT,
                candidate_payload_json TEXT NOT NULL,
                candidate_meta_json TEXT NOT NULL,
                pdf_sha256 TEXT NOT NULL DEFAULT '',
                assay_block_hash TEXT NOT NULL DEFAULT '',
                detected_at TEXT NOT NULL,
                decision_at TEXT,
                decision_by TEXT,
                decision_note TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS duplicate_decision_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                decided_at TEXT NOT NULL,
                decided_by TEXT NOT NULL,
                note TEXT NOT NULL
            )
            """
        )

    def _ensure_columns(self, conn: sqlite3.Connection, columns: dict[str, str]) -> None:
        existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        for name, sql_type in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {sql_type}")

    def _insert_or_candidate(
        self,
        conn: sqlite3.Connection,
        record: AssayRecord,
        ruleset: RuleSet,
        job_id: str,
        pdf_path: str,
        pdf_sha256: str,
        assay_block_hash: str,
        sqlite_path: str,
    ) -> DbWriteResult:
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
        if cur.rowcount:
            return DbWriteResult(
                sqlite_path=sqlite_path,
                table_name="runs",
                status="inserted",
                run_id=int(cur.lastrowid),
            )

        existing = conn.execute(
            "SELECT id FROM runs WHERE assay_key = ? AND dedupe_key = ?",
            (record.assay_key, record.dedupe_key),
        ).fetchone()
        if existing is None:
            return DbWriteResult(sqlite_path=sqlite_path, table_name="runs", status="skipped")

        existing_run_id = int(existing[0])
        candidate_id = self._ensure_duplicate_candidate(
            conn,
            record,
            ruleset,
            existing_run_id=existing_run_id,
            candidate_payload_json=payload,
            candidate_meta_json=json.dumps(
                {
                    "job_id": job_id,
                    "pdf_path": pdf_path,
                    "lot_id": record.lot_id,
                    "ruleset_file": ruleset.ruleset_file,
                },
                ensure_ascii=False,
            ),
            pdf_sha256=pdf_sha256 or "",
            assay_block_hash=assay_block_hash or "",
            detected_at=created_at,
        )
        return DbWriteResult(
            sqlite_path=sqlite_path,
            table_name="runs",
            status="duplicate_pending",
            existing_run_id=existing_run_id,
            duplicate_candidate_id=candidate_id,
        )

    def _ensure_duplicate_candidate(
        self,
        conn: sqlite3.Connection,
        record: AssayRecord,
        ruleset: RuleSet,
        *,
        existing_run_id: int,
        candidate_payload_json: str,
        candidate_meta_json: str,
        pdf_sha256: str,
        assay_block_hash: str,
        detected_at: str,
    ) -> int:
        existing = conn.execute(
            """
            SELECT id FROM duplicate_candidates
            WHERE status = 'pending'
              AND existing_run_id = ?
              AND pdf_sha256 = ?
              AND assay_block_hash = ?
            """,
            (existing_run_id, pdf_sha256, assay_block_hash),
        ).fetchone()
        if existing is not None:
            return int(existing[0])

        cur = conn.execute(
            """
            INSERT INTO duplicate_candidates (
                status, existing_run_id, assay_key, dedupe_key, device_id, dedupe_version,
                dedupe_basis_json, candidate_payload_json, candidate_meta_json,
                pdf_sha256, assay_block_hash, detected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "pending",
                existing_run_id,
                record.assay_key,
                record.dedupe_key,
                record.device_id,
                record.dedupe_version,
                json.dumps(record.dedupe_basis, ensure_ascii=False),
                candidate_payload_json,
                candidate_meta_json,
                pdf_sha256,
                assay_block_hash,
                detected_at,
            ),
        )
        return int(cur.lastrowid)

    def list_duplicate_candidates(self, sqlite_path: str, status: str = "pending") -> list[dict[str, object]]:
        path = Path(sqlite_path)
        if not path.exists():
            return []
        conn = sqlite3.connect(str(path))
        try:
            self._ensure_schema(conn)
            rows = conn.execute(
                """
                SELECT id, status, existing_run_id, assay_key, dedupe_key, device_id,
                       dedupe_version, dedupe_basis_json, pdf_sha256, assay_block_hash, detected_at,
                       decision_at, decision_by, decision_note
                FROM duplicate_candidates
                WHERE status = ?
                ORDER BY id
                """,
                (status,),
            ).fetchall()
            conn.commit()
        finally:
            conn.close()

        return [
            {
                "candidate_id": int(row[0]),
                "status": row[1],
                "existing_run_id": int(row[2]),
                "assay_key": row[3],
                "dedupe_key": row[4],
                "device_id": row[5],
                "dedupe_version": row[6],
                "dedupe_basis": _loads_json_object(row[7]),
                "pdf_sha256": row[8],
                "assay_block_hash": row[9],
                "detected_at": row[10],
                "decision_at": row[11],
                "decision_by": row[12],
                "decision_note": row[13],
            }
            for row in rows
        ]

    def get_duplicate_candidate(self, sqlite_path: str, candidate_id: int) -> dict[str, object] | None:
        path = Path(sqlite_path)
        if not path.exists():
            return None
        conn = sqlite3.connect(str(path))
        try:
            self._ensure_schema(conn)
            cand = conn.execute(
                """
                SELECT id, status, existing_run_id, assay_key, dedupe_key, device_id,
                       dedupe_version, dedupe_basis_json, candidate_payload_json,
                       candidate_meta_json, pdf_sha256, assay_block_hash, detected_at,
                       decision_at, decision_by, decision_note
                FROM duplicate_candidates
                WHERE id = ?
                """,
                (candidate_id,),
            ).fetchone()
            if cand is None:
                conn.commit()
                return None
            existing = conn.execute(
                """
                SELECT id, job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id,
                       dedupe_version, dedupe_basis_json, payload_json, created_at
                FROM runs
                WHERE id = ?
                """,
                (int(cand[2]),),
            ).fetchone()
            conn.commit()
        finally:
            conn.close()

        candidate_payload = _loads_json_object(cand[8])
        candidate = {
            "candidate_id": int(cand[0]),
            "status": cand[1],
            "existing_run_id": int(cand[2]),
            "assay_key": cand[3],
            "dedupe_key": cand[4],
            "device_id": cand[5],
            "dedupe_version": cand[6],
            "dedupe_basis": _loads_json_object(cand[7]),
            "payload": candidate_payload,
            "meta": _loads_json_object(cand[9]),
            "pdf_sha256": cand[10],
            "assay_block_hash": cand[11],
            "detected_at": cand[12],
            "decision_at": cand[13],
            "decision_by": cand[14],
            "decision_note": cand[15],
        }
        existing_payload: dict[str, object] = {}
        existing_obj: dict[str, object] | None = None
        if existing is not None:
            existing_payload = _loads_json_object(existing[9])
            existing_obj = {
                "run_id": int(existing[0]),
                "job_id": existing[1],
                "pdf_path": existing[2],
                "assay_key": existing[3],
                "lot_id": existing[4],
                "dedupe_key": existing[5],
                "device_id": existing[6],
                "dedupe_version": existing[7],
                "dedupe_basis": _loads_json_object(existing[8]),
                "payload": existing_payload,
                "created_at": existing[10],
            }
        return {
            "candidate": candidate,
            "existing": existing_obj,
            "field_comparison": _field_comparison(existing_payload, candidate_payload),
        }

    def discard_duplicate_candidate(
        self,
        sqlite_path: str,
        candidate_id: int,
        decided_by: str = "test-ui",
        note: str = "",
    ) -> dict[str, object]:
        path = Path(sqlite_path)
        conn = sqlite3.connect(str(path))
        try:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT status FROM duplicate_candidates WHERE id = ?",
                (int(candidate_id),),
            ).fetchone()
            if row is None:
                raise ValueError("candidate_not_found")
            if row[0] != "pending":
                raise ValueError("candidate_not_pending")

            decision_at = datetime.now(timezone.utc).isoformat()
            decision_by_value = str(decided_by or "test-ui")
            note_value = str(note or "")
            conn.execute(
                """
                UPDATE duplicate_candidates
                SET status = 'deleted',
                    decision_at = ?,
                    decision_by = ?,
                    decision_note = ?
                WHERE id = ?
                """,
                (decision_at, decision_by_value, note_value, int(candidate_id)),
            )
            conn.execute(
                """
                INSERT INTO duplicate_decision_log (
                    candidate_id, action, decided_at, decided_by, note
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (int(candidate_id), "discard", decision_at, decision_by_value, note_value),
            )
            conn.commit()
            return {
                "candidate_id": int(candidate_id),
                "status": "deleted",
                "action": "discard",
                "decision_at": decision_at,
                "decision_by": decision_by_value,
                "decision_note": note_value,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _loads_json_object(raw: object) -> dict[str, object]:
    if not raw:
        return {}
    try:
        data = json.loads(str(raw))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _field_comparison(existing: dict[str, object], candidate: dict[str, object]) -> list[dict[str, object]]:
    keys = sorted(set(existing) | set(candidate), key=str)
    return [
        {
            "field": key,
            "existing": existing.get(key),
            "candidate": candidate.get(key),
            "same": existing.get(key) == candidate.get(key),
        }
        for key in keys
    ]
