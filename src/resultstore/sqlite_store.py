"""Read-only SQLite access for result ledger inspection."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_UTC = timezone.utc
_UTC_MIN = datetime.min.replace(tzinfo=_UTC)

# Rows written during one PDF processing batch are grouped when their
# normalized pdf_path matches and created_at falls within this window.
LEGACY_REPORT_TIME_WINDOW_S = 5.0

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
            legacy_missing = _missing_legacy_report_columns(columns)
            if legacy_missing:
                base["schema_warnings"].append(
                    "Legacy-Berichte erfordern Spalten: " + ", ".join(legacy_missing)
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
    offset: int = 0,
) -> dict[str, Any]:
    status = get_result_store_status(store_spec)
    if not status.get("available"):
        return {"runs": [], "limit": limit, "offset": offset, "truncated": False, "total_returned": 0}

    path = _resolve_path(store_spec)
    columns = status.get("columns") or []
    select_cols = [col for col in KNOWN_RUN_COLUMNS if col in columns]
    if not select_cols:
        return {"runs": [], "limit": limit, "offset": offset, "truncated": False, "total_returned": 0}

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
    query = f"SELECT {', '.join(select_cols)} FROM runs {where_sql} {order_sql} LIMIT ? OFFSET ?"
    params.extend((int(limit) + 1, max(0, int(offset))))

    with _connect_readonly(path) as conn:
        rows = conn.execute(query, params).fetchall()

    truncated = len(rows) > limit
    if truncated:
        rows = rows[:limit]

    runs = [_row_to_run(dict(zip(select_cols, row))) for row in rows]
    return {
        "runs": runs,
        "limit": limit,
        "offset": max(0, int(offset)),
        "truncated": truncated,
        "total_returned": len(runs),
    }


def compute_report_id(
    job_id: str = "",
    *,
    pdf_path: str = "",
    created_at: str = "",
    run_id: int | None = None,
) -> str:
    """Deterministic report id aligned with ``_group_runs_into_reports``."""
    job_text = str(job_id or "").strip()
    if job_text:
        return job_text
    normalized_path = _normalize_pdf_path(pdf_path)
    basis = _legacy_report_id_basis(
        normalized_path,
        created_at_anchor=_canonical_created_at_iso(created_at),
        source_row_id=int(run_id) if run_id is not None else None,
    )
    return _hash_legacy_report_id(basis)


def list_report_summaries(store_spec: dict[str, Any], *, limit: int = 50) -> dict[str, Any]:
    status = get_result_store_status(store_spec)
    if not status.get("available"):
        return {"reports": [], "limit": limit, "total_returned": 0}

    path = _resolve_path(store_spec)
    columns = status.get("columns") or []
    select_cols = [col for col in KNOWN_RUN_COLUMNS if col in columns]
    if not select_cols:
        return {"reports": [], "limit": limit, "total_returned": 0}

    with _connect_readonly(path) as conn:
        grouped = _group_runs_into_reports(conn, select_cols, columns)

    summaries: list[dict[str, Any]] = []
    for report_id, runs in grouped.items():
        summaries.append(_report_summary_from_runs(report_id, runs))
    summaries.sort(
        key=lambda item: (
            str(item.get("latest_created_at") or ""),
            str(item.get("report_id") or ""),
        ),
        reverse=True,
    )
    capped = summaries[: int(limit)]
    return {"reports": capped, "limit": int(limit), "total_returned": len(capped)}


def get_report_runs(store_spec: dict[str, Any], report_id: str) -> dict[str, Any] | None:
    target = str(report_id or "").strip()
    if not target:
        return None
    status = get_result_store_status(store_spec)
    if not status.get("available"):
        return None

    path = _resolve_path(store_spec)
    columns = status.get("columns") or []
    select_cols = [col for col in KNOWN_RUN_COLUMNS if col in columns]
    if not select_cols:
        return None

    with _connect_readonly(path) as conn:
        grouped = _group_runs_into_reports(conn, select_cols, columns)
    matched = grouped.get(target)
    if not matched:
        return None
    return _report_detail_payload(target, matched)


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
    if not path.is_file():
        raise sqlite3.OperationalError(f"unable to open database file: {path}")

    if _is_unc_or_network_path(path):
        return _connect_direct_readonly(path)

    try:
        return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        if "invalid uri authority" in str(exc).lower():
            return _connect_direct_readonly(path)
        raise


def _is_unc_or_network_path(path: Path) -> bool:
    text = str(path)
    if text.startswith("\\\\"):
        return True
    return path.as_posix().startswith("//")


def _connect_direct_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA query_only = ON")
    return conn


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


def _missing_legacy_report_columns(columns: list[str]) -> list[str]:
    missing: list[str] = []
    if "pdf_path" not in columns:
        missing.append("pdf_path")
    if "created_at" not in columns:
        missing.append("created_at")
    return missing


def _normalize_pdf_path(pdf_path: str) -> str:
    text = str(pdf_path or "").strip()
    if not text:
        return ""
    return str(Path(text).resolve(strict=False))


def _parse_created_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_UTC)
    return parsed.astimezone(_UTC)


def _canonical_created_at_iso(value: Any) -> str | None:
    parsed = _parse_created_at(value)
    if parsed is None:
        return None
    return parsed.isoformat()


def _legacy_report_id_basis(
    normalized_path: str,
    *,
    created_at_anchor: str | None = None,
    source_row_id: int | None = None,
) -> str:
    path = normalized_path or "unknown"
    if created_at_anchor:
        return f"legacy|{path}|{created_at_anchor}"
    if source_row_id is not None:
        return f"legacy|{path}|row|{int(source_row_id)}"
    return f"legacy|{path}|unknown"


def _hash_legacy_report_id(basis: str) -> str:
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def _source_row_id(run: dict[str, Any], *, sqlite_rowid: int | None = None) -> int:
    run_id = run.get("id")
    if run_id is not None:
        return int(run_id)
    if sqlite_rowid is not None:
        return int(sqlite_rowid)
    internal = run.get("_source_rowid")
    if internal is not None:
        return int(internal)
    raise ValueError("missing_source_row_identity")


def _legacy_cluster_report_id(
    normalized_path: str,
    runs: list[dict[str, Any]],
    *,
    sqlite_rowid: int | None = None,
) -> str:
    parsed = [_parse_created_at(row.get("created_at")) for row in runs]
    valid_times = [item for item in parsed if item is not None]
    if len(valid_times) == len(runs) and valid_times:
        anchor = min(valid_times).isoformat()
        basis = _legacy_report_id_basis(normalized_path, created_at_anchor=anchor)
    else:
        basis = _legacy_report_id_basis(
            normalized_path,
            source_row_id=_source_row_id(runs[0], sqlite_rowid=sqlite_rowid),
        )
    return _hash_legacy_report_id(basis)


def _group_runs_into_reports(
    conn: sqlite3.Connection,
    select_cols: list[str],
    columns: list[str],
) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(f"SELECT rowid, {', '.join(select_cols)} FROM runs").fetchall()
    runs: list[dict[str, Any]] = []
    for row in rows:
        sqlite_rowid = int(row[0])
        run = _row_to_run(dict(zip(select_cols, row[1:])))
        run["_source_rowid"] = sqlite_rowid
        runs.append(run)
    grouped: dict[str, list[dict[str, Any]]] = {}

    has_job_id = "job_id" in columns
    legacy_capable = "pdf_path" in columns and "created_at" in columns

    job_groups: dict[str, list[dict[str, Any]]] = {}
    legacy_runs: list[dict[str, Any]] = []
    for run in runs:
        job_id = str(run.get("job_id") or "").strip() if has_job_id else ""
        if job_id:
            job_groups.setdefault(job_id, []).append(run)
        else:
            legacy_runs.append(run)

    for job_id, job_runs in job_groups.items():
        grouped[job_id] = list(job_runs)

    if not legacy_runs:
        return grouped
    if not legacy_capable:
        return grouped

    legacy_runs.sort(
        key=lambda row: (
            _normalize_pdf_path(str(row.get("pdf_path") or "")).casefold(),
            _parse_created_at(row.get("created_at")) or _UTC_MIN,
            _source_row_id(row),
        )
    )

    current_cluster: list[dict[str, Any]] = []
    current_path = ""
    current_anchor: datetime | None = None

    def flush_cluster() -> None:
        nonlocal current_cluster, current_path, current_anchor
        if not current_cluster:
            return
        report_id = _legacy_cluster_report_id(current_path, current_cluster)
        grouped.setdefault(report_id, []).extend(current_cluster)
        current_cluster = []
        current_path = ""
        current_anchor = None

    for run in legacy_runs:
        normalized_path = _normalize_pdf_path(str(run.get("pdf_path") or ""))
        parsed = _parse_created_at(run.get("created_at"))
        if not normalized_path or parsed is None:
            flush_cluster()
            report_id = _legacy_cluster_report_id(
                normalized_path or "unknown",
                [run],
                sqlite_rowid=int(run["_source_rowid"]),
            )
            grouped.setdefault(report_id, []).append(run)
            continue

        if not current_cluster:
            current_cluster = [run]
            current_path = normalized_path
            current_anchor = parsed
            continue

        delta = abs((parsed - current_anchor).total_seconds()) if current_anchor else LEGACY_REPORT_TIME_WINDOW_S + 1
        if normalized_path == current_path and delta <= LEGACY_REPORT_TIME_WINDOW_S:
            current_cluster.append(run)
            if current_anchor is None or parsed < current_anchor:
                current_anchor = parsed
            continue

        flush_cluster()
        current_cluster = [run]
        current_path = normalized_path
        current_anchor = parsed

    flush_cluster()
    return grouped


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


def _report_created_at_bounds(runs: list[dict[str, Any]]) -> tuple[str, str]:
    valid_times = [
        parsed
        for row in runs
        if (parsed := _parse_created_at(row.get("created_at"))) is not None
    ]
    if valid_times:
        earliest_dt = min(valid_times)
        latest_dt = max(valid_times)
        return earliest_dt.isoformat(), latest_dt.isoformat()
    raw_values = [str(row.get("created_at") or "") for row in runs]
    return min(raw_values), max(raw_values)


def _report_summary_from_runs(report_id: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    first = runs[0]
    job_id = str(first.get("job_id") or "")
    pdf_path = str(first.get("pdf_path") or "")
    pdf_sha256 = str(first.get("pdf_sha256") or "")
    assay_keys = sorted(
        {str(row.get("assay_key") or "") for row in runs if row.get("assay_key")},
        key=str.casefold,
    )
    device_ids = sorted(
        {str(row.get("device_id") or "") for row in runs if row.get("device_id")},
        key=str.casefold,
    )
    earliest, latest = _report_created_at_bounds(runs)
    return {
        "report_id": report_id,
        "job_id": job_id,
        "pdf_path": pdf_path,
        "pdf_sha256": pdf_sha256,
        "run_count": len(runs),
        "assay_count": len(assay_keys),
        "assay_keys": assay_keys,
        "device_ids": device_ids,
        "latest_created_at": latest,
        "earliest_created_at": earliest,
    }


def _report_detail_payload(report_id: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _report_summary_from_runs(report_id, runs)
    summary["runs"] = sorted(
        (_public_run_row(row) for row in runs),
        key=lambda row: (
            str(row.get("assay_key") or "").casefold(),
            str(row.get("created_at") or ""),
            int(row.get("id") or 0),
        ),
    )
    return summary


def _public_run_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "_source_rowid"}


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
