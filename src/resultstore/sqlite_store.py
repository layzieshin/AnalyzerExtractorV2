"""Read-only SQLite access for result ledger inspection."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

KNOWN_RUN_COLUMNS = (
    "id",
    "job_id",
    "pdf_path",
    "assay_key",
    "lot_id",
    "dedupe_key",
    "device_id",
    "dedupe_version",
    "dedupe_basis_json",
    "pdf_sha256",
    "assay_block_hash",
    "ruleset_file",
    "payload_json",
    "created_at",
)

CORE_ASSAY_COLUMN = "assay_key"
CORE_CHARGE_COLUMNS = ("assay_key", "lot_id")


def get_result_store_status(store_spec: dict[str, Any]) -> dict[str, Any]:
    path = _resolve_path(store_spec)
    base = {
        "available": False,
        "driver": "sqlite",
        "path": str(path),
        "message": "",
        "has_runs_table": False,
        "columns": [],
        "missing_core_columns": [],
        "schema_warnings": [],
    }
    if not path.is_file():
        base["message"] = "Datenbankdatei nicht gefunden."
        return base

    try:
        with _connect_readonly(path) as conn:
            columns = _table_columns(conn, "runs")
            if not columns:
                base["message"] = "Tabelle 'runs' nicht vorhanden."
                return base

            base["available"] = True
            base["has_runs_table"] = True
            base["columns"] = columns
            missing = _missing_core_columns(columns)
            base["missing_core_columns"] = missing
            if missing:
                base["schema_warnings"].append(
                    "Fehlende Kernspalten: " + ", ".join(missing)
                )
            base["message"] = "Datenbank bereit."
            return base
    except sqlite3.Error as exc:
        base["message"] = f"Datenbank konnte nicht gelesen werden: {exc}"
        return base


def list_result_assays(store_spec: dict[str, Any]) -> list[dict[str, str]]:
    status = get_result_store_status(store_spec)
    if not status.get("available") or CORE_ASSAY_COLUMN in status.get("missing_core_columns", []):
        return []

    path = _resolve_path(store_spec)
    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT assay_key
            FROM runs
            WHERE assay_key IS NOT NULL AND TRIM(assay_key) != ''
            ORDER BY assay_key
            """
        ).fetchall()
    return [{"assay_key": str(row[0])} for row in rows]


def list_result_charges(store_spec: dict[str, Any], assay_key: str) -> list[dict[str, str]]:
    status = get_result_store_status(store_spec)
    missing = set(status.get("missing_core_columns", []))
    if not status.get("available") or missing.intersection(CORE_CHARGE_COLUMNS):
        return []
    if not str(assay_key or "").strip():
        return []

    path = _resolve_path(store_spec)
    with _connect_readonly(path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT lot_id
            FROM runs
            WHERE assay_key = ?
              AND lot_id IS NOT NULL
              AND TRIM(lot_id) != ''
            ORDER BY lot_id
            """,
            (assay_key,),
        ).fetchall()
    return [{"lot_id": str(row[0]), "charge": str(row[0])} for row in rows]


def list_result_runs(
    store_spec: dict[str, Any],
    *,
    assay_key: str | None = None,
    charge: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    status = get_result_store_status(store_spec)
    if not status.get("available"):
        return {"runs": [], "limit": limit, "truncated": False, "total_returned": 0}

    path = _resolve_path(store_spec)
    columns = status.get("columns") or []
    select_cols = [col for col in KNOWN_RUN_COLUMNS if col in columns]
    if not select_cols:
        return {"runs": [], "limit": limit, "truncated": False, "total_returned": 0}

    where_parts: list[str] = []
    params: list[Any] = []
    if assay_key and CORE_ASSAY_COLUMN in columns:
        where_parts.append("assay_key = ?")
        params.append(assay_key)
    if charge and "lot_id" in columns:
        where_parts.append("lot_id = ?")
        params.append(charge)

    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    order_sql = "ORDER BY id DESC" if "id" in columns else ""
    query = f"SELECT {', '.join(select_cols)} FROM runs {where_sql} {order_sql} LIMIT ?"
    params.append(int(limit) + 1)

    with _connect_readonly(path) as conn:
        rows = conn.execute(query, params).fetchall()

    truncated = len(rows) > limit
    if truncated:
        rows = rows[:limit]

    runs = [_row_to_run(dict(zip(select_cols, row))) for row in rows]
    return {
        "runs": runs,
        "limit": limit,
        "truncated": truncated,
        "total_returned": len(runs),
    }


def get_result_run(store_spec: dict[str, Any], run_id: int) -> dict[str, Any] | None:
    status = get_result_store_status(store_spec)
    if not status.get("available") or "id" not in status.get("columns", []):
        return None

    path = _resolve_path(store_spec)
    columns = status.get("columns") or []
    select_cols = [col for col in KNOWN_RUN_COLUMNS if col in columns]
    if not select_cols:
        return None

    with _connect_readonly(path) as conn:
        row = conn.execute(
            f"SELECT {', '.join(select_cols)} FROM runs WHERE id = ?",
            (int(run_id),),
        ).fetchone()
    if row is None:
        return None
    return _row_to_run(dict(zip(select_cols, row)))


def _resolve_path(store_spec: dict[str, Any]) -> Path:
    driver = str(store_spec.get("driver") or "sqlite").strip().lower()
    if driver != "sqlite":
        raise ValueError(f"unsupported_result_store_driver:{driver}")
    return Path(str(store_spec.get("path") or "")).resolve()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if not rows:
        return []
    return [str(row[1]) for row in rows]


def _missing_core_columns(columns: list[str]) -> list[str]:
    missing: list[str] = []
    if CORE_ASSAY_COLUMN not in columns:
        missing.append(CORE_ASSAY_COLUMN)
    if "lot_id" not in columns:
        missing.append("lot_id")
    return missing


def _decode_json_field(raw: Any) -> tuple[Any, str | None]:
    if raw in (None, ""):
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        return {}, str(exc)
    return value if isinstance(value, dict) else {}, None


def _result_date(payload: dict[str, Any]) -> str:
    for key in ("DATUM", "date"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _row_to_run(row: dict[str, Any]) -> dict[str, Any]:
    payload, payload_error = _decode_json_field(row.get("payload_json"))
    dedupe_basis, dedupe_error = _decode_json_field(row.get("dedupe_basis_json"))
    run = {
        "id": row.get("id"),
        "job_id": row.get("job_id") or "",
        "pdf_path": row.get("pdf_path") or "",
        "assay_key": row.get("assay_key") or "",
        "lot_id": row.get("lot_id") or "",
        "charge": row.get("lot_id") or "",
        "dedupe_key": row.get("dedupe_key") or "",
        "device_id": row.get("device_id") or "",
        "dedupe_version": row.get("dedupe_version") or "",
        "pdf_sha256": row.get("pdf_sha256") or "",
        "assay_block_hash": row.get("assay_block_hash") or "",
        "ruleset_file": row.get("ruleset_file") or "",
        "created_at": row.get("created_at") or "",
        "payload": payload,
        "dedupe_basis": dedupe_basis,
        "result_date": _result_date(payload),
        "payload_parse_error": payload_error,
        "dedupe_basis_parse_error": dedupe_error,
    }
    return run
