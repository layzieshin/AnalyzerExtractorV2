"""DbWriter-owned append-only reanalysis and identity claims.

All authoritative checks execute after BEGIN IMMEDIATE. Cross-owner reads use
strict read-only APIs, so they cannot recursively take this writer's lock.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from src.resultstore.api import get_result_run
from src.resultvalidation.api import list_run_validations_readonly
from src.jobcontroller.api import processing_eligibility_error

from .model import ResultRevisionConflictError, ResultRevisionError


def ensure_revision_schema(conn: sqlite3.Connection) -> None:
    """Additive component migration; caller owns its encompassing transaction."""
    conn.execute("CREATE TABLE IF NOT EXISTS dbwriter_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    versions = [int(row[0]) for row in conn.execute("SELECT version FROM dbwriter_schema_migrations")]
    if versions and versions not in ([1], [1, 2]):
        raise ResultRevisionError("Unbekannte DbWriter-Version; bitte Datenbestand klaeren.")
    expected = {
        "run_source_provenance": {"run_id", "snapshot_json"},
        "run_result_revisions": {"revision_id", "run_id", "request_id", "expected_selection_token", "supersedes_revision_id", "snapshot_json", "created_by", "created_at"},
        "run_result_selections": {"selection_id", "run_id", "revision_id", "resolves_revision_id", "previous_selection_token", "action", "request_id", "decided_by", "note", "created_at"},
        "run_identity_aliases": {"alias_id", "assay_key", "dedupe_key", "run_id", "revision_id", "created_at"},
    }
    if 2 in versions and any({str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")} != columns for table, columns in expected.items()):
        raise ResultRevisionError("Unvollständiges Ergebnisschema; bitte Datenbestand klären.")
    conn.execute("""CREATE TABLE IF NOT EXISTS run_source_provenance (
        run_id INTEGER PRIMARY KEY, snapshot_json TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS run_result_revisions (
        revision_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL,
        request_id TEXT NOT NULL, expected_selection_token TEXT NOT NULL,
        supersedes_revision_id INTEGER, snapshot_json TEXT NOT NULL,
        created_by TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(run_id, request_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS run_result_selections (
        selection_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL,
        revision_id INTEGER NOT NULL, resolves_revision_id INTEGER NOT NULL,
        previous_selection_token TEXT NOT NULL, action TEXT NOT NULL,
        request_id TEXT NOT NULL, decided_by TEXT NOT NULL, note TEXT NOT NULL,
        created_at TEXT NOT NULL, UNIQUE(run_id, previous_selection_token),
        UNIQUE(run_id, request_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS run_identity_aliases (
        alias_id INTEGER PRIMARY KEY, assay_key TEXT NOT NULL, dedupe_key TEXT NOT NULL,
        run_id INTEGER NOT NULL, revision_id INTEGER NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(assay_key, dedupe_key))""")
    conn.execute("INSERT OR IGNORE INTO dbwriter_schema_migrations VALUES (1, ?)", (_stamp(),))
    for table, columns in expected.items():
        if {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")} != columns:
            raise ResultRevisionError("Unbekanntes Ergebnisschema; bitte Datenbestand klaeren.")
    # A mistaken UPDATE/DELETE cannot silently rewrite the revision evidence.
    for table in ("run_source_provenance", "run_result_revisions", "run_result_selections", "run_identity_aliases"):
        for verb in ("UPDATE", "DELETE"):
            conn.execute(f"""CREATE TRIGGER IF NOT EXISTS immutable_{table}_{verb.lower()}
                BEFORE {verb} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable_result_evidence'); END""")
    from .report_devices import ensure_report_device_schema
    ensure_report_device_schema(conn)


def identity_owners(conn: sqlite3.Connection, assay_key: str, dedupe_key: str) -> set[int]:
    rows = conn.execute("""SELECT id FROM runs WHERE assay_key=? AND dedupe_key=?
        UNION SELECT run_id FROM run_identity_aliases WHERE assay_key=? AND dedupe_key=?""",
        (assay_key, dedupe_key, assay_key, dedupe_key)).fetchall()
    return {int(row[0]) for row in rows}


@contextmanager
def _write_connection(sqlite_path: str) -> Iterator[sqlite3.Connection]:
    path = Path(sqlite_path).resolve()
    if not path.is_file():
        raise ResultRevisionError("Ergebnisspeicher fehlt; bitte Einstellungen pruefen.")
    conn = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        ensure_revision_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _state(sqlite_path: str, run_id: int, expected_token: str, project_root: str | None = None) -> dict[str, Any]:
    spec = {"driver": "sqlite", "path": str(Path(sqlite_path).resolve())}
    state = get_result_run(spec, run_id)
    if state is None:
        raise ResultRevisionError("Die Messung wurde nicht gefunden. Bitte aktualisieren.")
    if state.get("revision_error") or state.get("payload_parse_error"):
        raise ResultRevisionError(str(state.get("revision_error") or "Alte Messwerte unlesbar; bitte Datenbestand klaeren."))
    if state["selection_token"] != expected_token:
        raise ResultRevisionConflictError("Die Messung hat sich geaendert. Bitte aktualisieren und erneut vergleichen.")
    source_root = state.get("source_provenance", {}).get("project_root")
    if not source_root and state.get("pending_revision"):
        source_root = state["pending_revision"]["result"].get("source_provenance", {}).get("project_root")
    eligibility = processing_eligibility_error(project_root or source_root, state["job_id"], require_evidence=bool(source_root))
    if eligibility:
        raise ResultRevisionConflictError(eligibility)
    if list_run_validations_readonly(spec, [run_id]).latest(run_id) is not None:
        raise ResultRevisionConflictError("Die Messung ist bereits validiert und darf nicht erneut analysiert werden.")
    return state


def _request_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResultRevisionError("Die eindeutige Anfragekennung fehlt.")
    return value.strip()


def append_result_revision(sqlite_path: str, run_id: int, *, expected_selection_token: str,
                           request_id: str, snapshot: dict[str, Any], created_by: str,
                           project_root: str | None = None) -> dict[str, Any]:
    request_id = _request_id(request_id)
    actor = _actor(created_by)
    frozen = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, allow_nan=False)
    with _write_connection(sqlite_path) as conn:
        previous = conn.execute("SELECT revision_id, expected_selection_token, snapshot_json, created_by FROM run_result_revisions WHERE run_id=? AND request_id=?", (run_id, request_id)).fetchone()
        if previous:
            if (previous[1], previous[2], previous[3]) != (expected_selection_token, frozen, actor):
                raise ResultRevisionConflictError("Die Anfragekennung wurde bereits fuer andere Daten verwendet.")
            revision_id = int(previous[0])
        else:
            state = _state(sqlite_path, run_id, expected_selection_token, project_root)
            if snapshot.get("device_id") != state["original_result"]["device_id"] or snapshot.get("assay_key") != state["assay_key"]:
                raise ResultRevisionError("Assay oder urspruengliches Geraet stimmen nicht ueberein.")
            pending = state.get("pending_revision")
            cursor = conn.execute("""INSERT INTO run_result_revisions
                (run_id, request_id, expected_selection_token, supersedes_revision_id, snapshot_json, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""", (run_id, request_id, expected_selection_token,
                pending["revision_id"] if pending else None, frozen, actor, _stamp()))
            revision_id = int(cursor.lastrowid)
    return {"run_id": run_id, "revision_id": revision_id, "request_id": request_id}


def select_result_revision(sqlite_path: str, run_id: int, revision_id: int, *,
                           expected_selection_token: str, action: str, request_id: str,
                           decided_by: str, note: str = "") -> dict[str, Any]:
    request_id = _request_id(request_id)
    actor = _actor(decided_by)
    if action not in {"keep_old", "accept_new"}:
        raise ResultRevisionError("Bitte alte oder neue Werte auswaehlen.")
    with _write_connection(sqlite_path) as conn:
        previous = conn.execute("SELECT selection_id, resolves_revision_id, previous_selection_token, action, decided_by, note, revision_id FROM run_result_selections WHERE run_id=? AND request_id=?", (run_id, request_id)).fetchone()
        if previous:
            if tuple(previous[1:6]) != (revision_id, expected_selection_token, action, actor, str(note)):
                raise ResultRevisionConflictError("Die Anfragekennung wurde bereits fuer eine andere Auswahl verwendet.")
            selection_id, selected_id = int(previous[0]), int(previous[6])
        else:
            state = _state(sqlite_path, run_id, expected_selection_token)
            pending = state.get("pending_revision")
            if not pending or int(pending["revision_id"]) != revision_id:
                raise ResultRevisionConflictError("Der Vergleich ist nicht mehr aktuell. Bitte aktualisieren.")
            candidate = pending["result"]
            if not candidate.get("source_verified") or not candidate.get("ruleset") or not candidate.get("rule_sha256"):
                raise ResultRevisionError("Quelle oder Regelstand ist ungeklaert. Bitte Nacharbeit durchfuehren und erneut analysieren.")
            chosen = candidate if action == "accept_new" else state
            keys = [str(field["key"]) for field in candidate["ruleset"].get("extract_rules", {}).get("fields", []) if field.get("key")]
            missing = [key for key in keys if chosen["payload"].get(key) is None or not str(chosen["payload"][key]).strip()]
            if not keys or missing or (action == "accept_new" and candidate.get("error")):
                detail = ", ".join(missing) or str(candidate.get("error") or "Feldvertrag fehlt")
                raise ResultRevisionError(f"Nacharbeit erforderlich: {detail}. Bitte Regelwerk pruefen und erneut analysieren.")
            selected_id = revision_id if action == "accept_new" else int(state["revision_id"])
            if action == "accept_new":
                owners = identity_owners(conn, str(candidate["assay_key"]), str(candidate["dedupe_key"]))
                device_id = state.get("effective_device_id")
                if device_id:
                    from .report_devices import _claim, assert_device_identity_available
                    assert_device_identity_available(conn, sqlite_path, candidate, device_id, run_id)
                    for other_id in owners - {run_id}:
                        other = get_result_run({"driver": "sqlite", "path": sqlite_path}, other_id) or {}
                        if not other.get("effective_device_id") or other["effective_device_id"] == device_id:
                            raise ResultRevisionConflictError("Die korrigierte Identität ist auf demselben oder einem ungeklärten Gerät schon belegt.")
                    _claim(conn, candidate, device_id, run_id, int(state.get("device_assignment_id") or 0), revision_id)
                elif owners - {run_id}:
                    raise ResultRevisionConflictError("Die korrigierte Identitaet gehoert bereits zu einer anderen Messung. Bitte Duplikat klaeren.")
                if not owners - {run_id}:
                    conn.execute("""INSERT OR IGNORE INTO run_identity_aliases
                        (assay_key, dedupe_key, run_id, revision_id, created_at) VALUES (?, ?, ?, ?, ?)""",
                        (candidate["assay_key"], candidate["dedupe_key"], run_id, revision_id, _stamp()))
            cursor = conn.execute("""INSERT INTO run_result_selections
                (run_id, revision_id, resolves_revision_id, previous_selection_token, action, request_id, decided_by, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (run_id, selected_id, revision_id,
                expected_selection_token, action, request_id, actor, str(note), _stamp()))
            selection_id = int(cursor.lastrowid)
    return {"run_id": run_id, "revision_id": selected_id, "selection_id": selection_id,
            "selection_token": f"selection:{selection_id}", "action": action}


def _actor(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResultRevisionError("Bitte Initialen angeben.")
    return value.strip()


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()
