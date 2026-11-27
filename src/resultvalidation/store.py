"""Append-only SQLite storage for run validations.

Run existence is decided only through ``src.resultstore.api``. This module
never inserts, updates, deletes, or alters measurement rows.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from src.resultstore.api import get_result_run, get_result_store_status
from src.jobcontroller.api import processing_eligibility_error

from .model import (
    OperatorInitialsRequiredError,
    ResultValidationError,
    RunNotFoundError,
    RunValidation,
    RunValidationList,
    UnsupportedValidationStoreError,
    ValidationAlreadyExistsError,
    ValidationAmbiguousError,
    ValidationMissingError,
    ValidationStoreBusyError,
    ValidationStoreMissingError,
    ValidationStoreUnreadableError,
    ValidationStateConflictError,
)

_BUSY_TIMEOUT_MS = 5000

_CREATE_RUN_VALIDATIONS = """
CREATE TABLE IF NOT EXISTS run_validations (
    validation_id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    operator_initials TEXT NOT NULL,
    validated_at_utc TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    supersedes_validation_id INTEGER,
    created_at_utc TEXT,
    revision_id INTEGER NOT NULL DEFAULT 0,
    selection_id INTEGER,
    selection_token TEXT NOT NULL DEFAULT '',
    request_id TEXT
)
"""

_CREATE_RUN_INDEX = """
CREATE INDEX IF NOT EXISTS idx_run_validations_run_id
ON run_validations(run_id)
"""

_SELECT_COLUMNS = """
validation_id, run_id, operator_initials, validated_at_utc,
comment, supersedes_validation_id, created_at_utc,
revision_id, selection_id, selection_token, request_id
"""


def get_run_validation(store_spec: Mapping[str, Any], run_id: int) -> RunValidation | None:
    """Return the effective validation for one existing run, or ``None``."""
    checked_run_id = _coerce_run_id(run_id)
    path = _require_runs(store_spec, [checked_run_id])
    with _immediate_connection(path) as conn:
        _ensure_schema(conn)
        heads = _effective_records(conn, checked_run_id)
    if not heads:
        return None
    if len(heads) > 1:
        raise ValidationAmbiguousError(checked_run_id)
    return heads[0]


def list_run_validations(
    store_spec: Mapping[str, Any],
    run_ids: Sequence[int],
) -> RunValidationList:
    """Return append-only history and the effective validation for each run."""
    ids = _coerce_run_ids(run_ids)
    path = _require_database_file(store_spec)
    _require_readable_ledger(store_spec)
    if not ids:
        return RunValidationList(records=(), latest_by_run_id={})
    for run_id in ids:
        _require_run(store_spec, run_id)
    with _immediate_connection(path) as conn:
        _ensure_schema(conn)
        records = _records_for_runs(conn, ids)
    return _validation_list(records)


def list_run_validations_readonly(
    store_spec: Mapping[str, Any], run_ids: Sequence[int],
) -> RunValidationList:
    """Strict non-migrating guard, safe beneath another owner's write lock.

    Legacy readers intentionally retain schema creation. This separate API uses
    a read-only connection and a single read transaction; missing metadata means
    no validation, and missing binding columns mean original revision zero.
    """
    ids = _coerce_run_ids(run_ids)
    path = _require_database_file(store_spec)
    try:
        conn = _connect_readonly(path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(run_validations)")}
            if not columns:
                return RunValidationList(records=(), latest_by_run_id={})
            selected = [name.strip() for name in _SELECT_COLUMNS.replace("\n", "").split(",")]
            defaults = {"revision_id": "0", "selection_id": "NULL", "selection_token": "''", "request_id": "NULL"}
            selection = ", ".join(name if name in columns else f"{defaults[name]} AS {name}" for name in selected)
            records: list[RunValidation] = []
            for chunk in _chunks(ids, 400):
                marks = ",".join("?" for _ in chunk)
                records.extend(_row_to_record(row) for row in conn.execute(
                    f"SELECT {selection} FROM run_validations WHERE run_id IN ({marks}) ORDER BY validation_id", chunk))
            return _validation_list(sorted(records, key=lambda record: record.validation_id))
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise _translate_sqlite_error(exc) from exc


def _connect_readonly(path: Path) -> sqlite3.Connection:
    try:
        return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        if "invalid uri authority" not in str(exc).lower():
            raise
        # SQLite builds without URI-authority support reject file://server/...
        # even though Windows supports the UNC path. An empty URI authority
        # keeps //server/share in the path instead. Both attempts retain mode=ro:
        # a file disappearing after the existence check must never be recreated.
        filename = path.as_posix()
        prefix = "file://" if filename.startswith("/") else "file:///"
        return sqlite3.connect(f"{prefix}{quote(filename, safe='/:')}?mode=ro", uri=True)


def validate_run(
    store_spec: Mapping[str, Any],
    run_id: int,
    operator_initials: str,
    comment: str = "",
    *,
    expected_selection_token: str | None = None,
    request_id: str | None = None,
    project_root: str | None = None,
) -> RunValidation:
    """Append the first validation. An existing validation is left unchanged."""
    initials = _require_initials(operator_initials)
    note = _normalize_comment(comment)
    if isinstance(request_id, str):
        request_id = request_id.strip()
    checked_run_id = _coerce_run_id(run_id)
    path = _require_runs(store_spec, [checked_run_id])
    stamp = _utc_iso()
    with _immediate_connection(path) as conn:
        _ensure_schema(conn)
        repeated = _repeated_request(conn, checked_run_id, request_id, initials, note, expected_selection_token, False)
        if repeated is not None:
            return repeated
        state = _require_selected_state(store_spec, checked_run_id, expected_selection_token, project_root)
        heads = _effective_records(conn, checked_run_id)
        if len(heads) > 1:
            raise ValidationAmbiguousError(checked_run_id)
        if heads:
            raise ValidationAlreadyExistsError(checked_run_id)
        stored = _insert_validation(
            conn,
            run_id=checked_run_id,
            operator_initials=initials,
            validated_at_utc=stamp,
            comment=note,
            supersedes_validation_id=None,
            created_at_utc=stamp,
            state=state,
            request_id=request_id,
        )
    return stored


def correct_validation(
    store_spec: Mapping[str, Any],
    run_id: int,
    operator_initials: str,
    comment: str = "",
    *,
    expected_selection_token: str | None = None,
    request_id: str | None = None,
    project_root: str | None = None,
) -> RunValidation:
    """Append a correction that points at the previous effective validation."""
    initials = _require_initials(operator_initials)
    note = _normalize_comment(comment)
    if isinstance(request_id, str):
        request_id = request_id.strip()
    checked_run_id = _coerce_run_id(run_id)
    path = _require_runs(store_spec, [checked_run_id])
    stamp = _utc_iso()
    with _immediate_connection(path) as conn:
        _ensure_schema(conn)
        repeated = _repeated_request(conn, checked_run_id, request_id, initials, note, expected_selection_token, True)
        if repeated is not None:
            return repeated
        state = _require_selected_state(store_spec, checked_run_id, expected_selection_token, project_root)
        heads = _effective_records(conn, checked_run_id)
        if not heads:
            raise ValidationMissingError(checked_run_id)
        if len(heads) > 1:
            raise ValidationAmbiguousError(checked_run_id)
        if heads[0].revision_id != state["revision_id"] or heads[0].selection_id != state["selection_id"]:
            raise ValidationStateConflictError("Die Validation gehoert zu einem anderen Ergebnisstand. Bitte Datenbestand klaeren.")
        stored = _insert_validation(
            conn,
            run_id=checked_run_id,
            operator_initials=initials,
            validated_at_utc=stamp,
            comment=note,
            supersedes_validation_id=heads[0].validation_id,
            created_at_utc=stamp,
            state=state,
            request_id=request_id,
        )
    return stored


def _require_runs(store_spec: Mapping[str, Any], run_ids: Sequence[int]) -> Path:
    path = _require_database_file(store_spec)
    _require_readable_ledger(store_spec)
    for run_id in run_ids:
        _require_run(store_spec, run_id)
    return path


def _require_database_file(store_spec: Mapping[str, Any]) -> Path:
    path = _resolve_sqlite_path(store_spec)
    if not path.is_file():
        raise ValidationStoreMissingError()
    return path


def _require_readable_ledger(store_spec: Mapping[str, Any]) -> None:
    try:
        status = get_result_store_status(dict(store_spec))
    except ValueError as exc:
        raise UnsupportedValidationStoreError() from exc
    if status.get("available") and "id" in (status.get("columns") or []):
        return
    message = str(status.get("message") or "").strip()
    if message == "Datenbankdatei nicht gefunden.":
        raise ValidationStoreMissingError()
    if message:
        raise ValidationStoreUnreadableError(message)
    raise ValidationStoreUnreadableError()


def _require_run(store_spec: Mapping[str, Any], run_id: int) -> None:
    try:
        found = get_result_run(dict(store_spec), run_id)
    except ValueError as exc:
        raise UnsupportedValidationStoreError() from exc
    if found is None:
        raise RunNotFoundError(run_id)


def _resolve_sqlite_path(store_spec: Mapping[str, Any]) -> Path:
    if not isinstance(store_spec, Mapping):
        raise UnsupportedValidationStoreError()
    driver = str(store_spec.get("driver") or "sqlite").strip().lower()
    if driver != "sqlite":
        raise UnsupportedValidationStoreError()
    raw_path = store_spec.get("path")
    if raw_path is None:
        raw_path = ""
    if not isinstance(raw_path, str):
        raise UnsupportedValidationStoreError()
    return Path(raw_path).resolve()


@contextmanager
def _immediate_connection(path: Path) -> Iterator[sqlite3.Connection]:
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(path), timeout=_BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {int(_BUSY_TIMEOUT_MS)}")
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        raise _translate_sqlite_error(exc) from exc
    try:
        yield conn
    except sqlite3.Error as exc:
        _rollback(conn)
        raise _translate_sqlite_error(exc) from exc
    except Exception:
        _rollback(conn)
        raise
    else:
        try:
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            _rollback(conn)
            raise _translate_sqlite_error(exc) from exc
    finally:
        conn.close()


def _rollback(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        return


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_RUN_VALIDATIONS)
    conn.execute(_CREATE_RUN_INDEX)
    conn.execute("CREATE TABLE IF NOT EXISTS resultvalidation_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    versions = [int(row[0]) for row in conn.execute("SELECT version FROM resultvalidation_schema_migrations")]
    if versions and versions != [1]:
        raise ValidationStoreUnreadableError("Unbekannte Validationsversion; bitte Datenbestand klaeren.")
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(run_validations)")}
    for name, sql_type in {"revision_id": "INTEGER NOT NULL DEFAULT 0", "selection_id": "INTEGER", "selection_token": "TEXT NOT NULL DEFAULT ''", "request_id": "TEXT"}.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE run_validations ADD COLUMN {name} {sql_type}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_run_validation_request ON run_validations(run_id, request_id) WHERE request_id IS NOT NULL")
    conn.execute("INSERT OR IGNORE INTO resultvalidation_schema_migrations VALUES (1, ?)", (_utc_iso(),))


def _require_selected_state(store_spec: Mapping[str, Any], run_id: int, expected: str | None, project_root: str | None = None) -> dict[str, Any]:
    # Caller already holds BEGIN IMMEDIATE. Other writers cannot change selection
    # between this public read-only projection and our append.
    state = get_result_run(dict(store_spec), run_id)
    if state is None:
        raise RunNotFoundError(run_id)
    if state.get("revision_error") or state.get("payload_parse_error"):
        raise ValidationStateConflictError("Ergebnis unlesbar; bitte Datenbestand klaeren.")
    source_root = state.get("source_provenance", {}).get("project_root")
    if not source_root and state.get("result_revisions"):
        source_root = state["result_revisions"][-1]["result"].get("source_provenance", {}).get("project_root")
    eligibility = processing_eligibility_error(project_root or source_root, state["job_id"], require_evidence=bool(source_root))
    if eligibility:
        raise ValidationStateConflictError(eligibility)
    if state.get("pending_revision"):
        raise ValidationStateConflictError("Bitte zuerst alte oder neue Werte im Vergleich auswaehlen.")
    if state.get("missing_fields"):
        raise ValidationStateConflictError("Nacharbeit erforderlich: leere konfigurierte Felder " + ", ".join(state["missing_fields"]))
    if expected is None:
        if state.get("selection_id") is not None or state.get("result_revisions"):
            raise ValidationStateConflictError("Dieser Ergebnisstand braucht eine aktuelle Auswahlkennung. Bitte aktualisieren.")
    elif expected != state["selection_token"]:
        raise ValidationStateConflictError("Die Messung hat sich geaendert. Bitte aktualisieren und erneut pruefen.")
    return state


def _repeated_request(conn: sqlite3.Connection, run_id: int, request_id: str | None, initials: str,
                      comment: str, token: str | None, correction: bool) -> RunValidation | None:
    if request_id is None:
        return None
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValidationStateConflictError("Die eindeutige Anfragekennung fehlt.")
    row = conn.execute(f"SELECT {_SELECT_COLUMNS} FROM run_validations WHERE run_id=? AND request_id=?", (run_id, request_id)).fetchone()
    if row is None:
        return None
    record = _row_to_record(row)
    if (record.operator_initials, record.comment, record.supersedes_validation_id is not None) != (initials, comment, correction) or (token is not None and token != record.selection_token):
        raise ValidationStateConflictError("Die Anfragekennung wurde bereits fuer andere Validationsdaten verwendet.")
    return record


def _effective_records(conn: sqlite3.Connection, run_id: int) -> list[RunValidation]:
    rows = conn.execute(
        f"""
        SELECT {_SELECT_COLUMNS}
        FROM run_validations AS candidate
        WHERE candidate.run_id = ?
          AND NOT EXISTS (
              SELECT 1
              FROM run_validations AS newer
              WHERE newer.run_id = candidate.run_id
                AND newer.supersedes_validation_id = candidate.validation_id
          )
        ORDER BY candidate.validation_id ASC
        """,
        (int(run_id),),
    ).fetchall()
    return [_row_to_record(row) for row in rows]


def _records_for_runs(conn: sqlite3.Connection, run_ids: Sequence[int]) -> list[RunValidation]:
    records: list[RunValidation] = []
    for chunk in _chunks(list(run_ids), 400):
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM run_validations
            WHERE run_id IN ({placeholders})
            ORDER BY validation_id ASC
            """,
            tuple(chunk),
        ).fetchall()
        records.extend(_row_to_record(row) for row in rows)
    records.sort(key=lambda record: record.validation_id)
    return records


def _validation_list(records: Sequence[RunValidation]) -> RunValidationList:
    grouped: dict[int, list[RunValidation]] = {}
    for record in records:
        grouped.setdefault(record.run_id, []).append(record)
    latest: dict[int, RunValidation] = {}
    for run_id, items in grouped.items():
        heads = _heads(items)
        if len(heads) != 1:
            raise ValidationAmbiguousError(run_id)
        latest[run_id] = heads[0]
    return RunValidationList(records=tuple(records), latest_by_run_id=latest)


def _heads(records: Sequence[RunValidation]) -> list[RunValidation]:
    superseded = {
        record.supersedes_validation_id
        for record in records
        if record.supersedes_validation_id is not None
    }
    return [record for record in records if record.validation_id not in superseded]


def _insert_validation(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    operator_initials: str,
    validated_at_utc: str,
    comment: str,
    supersedes_validation_id: int | None,
    created_at_utc: str | None,
    state: dict[str, Any],
    request_id: str | None,
) -> RunValidation:
    cursor = conn.execute(
        """
        INSERT INTO run_validations (
            run_id, operator_initials, validated_at_utc, comment,
            supersedes_validation_id, created_at_utc, revision_id, selection_id,
            selection_token, request_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(run_id),
            operator_initials,
            validated_at_utc,
            comment,
            supersedes_validation_id,
            created_at_utc,
            state["revision_id"], state["selection_id"], state["selection_token"], request_id,
        ),
    )
    if cursor.lastrowid is None:
        raise ValidationStoreUnreadableError()
    stored = _load_validation(conn, int(cursor.lastrowid))
    if stored is None:
        raise ValidationStoreUnreadableError()
    return stored


def _load_validation(conn: sqlite3.Connection, validation_id: int) -> RunValidation | None:
    row = conn.execute(
        f"""
        SELECT {_SELECT_COLUMNS}
        FROM run_validations
        WHERE validation_id = ?
        """,
        (int(validation_id),),
    ).fetchone()
    if row is None:
        return None
    return _row_to_record(row)


def _row_to_record(row: sqlite3.Row) -> RunValidation:
    supersedes = row["supersedes_validation_id"]
    created_at = row["created_at_utc"]
    return RunValidation(
        validation_id=int(row["validation_id"]),
        run_id=int(row["run_id"]),
        operator_initials=str(row["operator_initials"]),
        validated_at_utc=str(row["validated_at_utc"]),
        comment=str(row["comment"] if row["comment"] is not None else ""),
        supersedes_validation_id=None if supersedes is None else int(supersedes),
        created_at_utc=None if created_at is None else str(created_at),
        revision_id=int(row["revision_id"] or 0),
        selection_id=None if row["selection_id"] is None else int(row["selection_id"]),
        selection_token=str(row["selection_token"] or ""),
        request_id=str(row["request_id"] or ""),
    )


def _require_initials(operator_initials: object) -> str:
    if not isinstance(operator_initials, str):
        raise OperatorInitialsRequiredError()
    initials = operator_initials.strip()
    if not initials:
        raise OperatorInitialsRequiredError()
    return initials


def _normalize_comment(comment: object) -> str:
    if comment is None:
        return ""
    if not isinstance(comment, str):
        raise ResultValidationError("Kommentar muss Text sein.")
    return comment.strip()


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _coerce_run_id(run_id: object) -> int:
    if isinstance(run_id, bool) or not isinstance(run_id, int):
        raise RunNotFoundError(run_id)
    return run_id


def _coerce_run_ids(run_ids: object) -> list[int]:
    if isinstance(run_ids, (str, bytes)) or not isinstance(run_ids, Sequence):
        raise ResultValidationError("run_ids muss eine Folge von Run-IDs sein.")
    unique: list[int] = []
    seen: set[int] = set()
    for raw in run_ids:
        run_id = _coerce_run_id(raw)
        if run_id in seen:
            continue
        seen.add(run_id)
        unique.append(run_id)
    return unique


def _chunks(values: list[int], size: int) -> Iterator[list[int]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _translate_sqlite_error(exc: sqlite3.Error) -> ResultValidationError:
    text = str(exc).lower()
    if "locked" in text or "busy" in text:
        return ValidationStoreBusyError()
    return ValidationStoreUnreadableError()
