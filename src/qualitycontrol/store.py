"""The sole append-only QC/device authority in the effective Results SQLite file.

Only explicit user mutations create schema. Browsing never creates a file,
directory, table, migration, or default inventory.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

from src.resultstore.api import list_result_runs

from .model import MutationContext, QCConfigurationError, QCConflictError, QCStoreError, canonical_json, content_hash, utc_now

SCHEMA_VERSION = 1
DEFAULT_DEVICE_ID = "DEFAULT_DEVICE"
_TABLES = frozenset({"qc_schema_migrations", "qc_inventory_versions", "qc_profile_versions", "qc_lot_versions", "qc_report_evidence"})
_DDL = (
    """CREATE TABLE qc_schema_migrations (
        version INTEGER PRIMARY KEY, source_sha256 TEXT NOT NULL,
        source_path TEXT NOT NULL, migrated_at_utc TEXT NOT NULL, migration_json TEXT NOT NULL)""",
    """CREATE TABLE qc_inventory_versions (
        version_id INTEGER PRIMARY KEY, predecessor_id INTEGER NOT NULL UNIQUE,
        snapshot_json TEXT NOT NULL, actor TEXT NOT NULL, created_at_utc TEXT NOT NULL,
        reason TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE, intent_hash TEXT NOT NULL)""",
    """CREATE TABLE qc_profile_versions (
        version_id INTEGER PRIMARY KEY, profile_id TEXT NOT NULL, predecessor_id INTEGER NOT NULL,
        snapshot_json TEXT NOT NULL, actor TEXT NOT NULL, created_at_utc TEXT NOT NULL,
        reason TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE, intent_hash TEXT NOT NULL,
        UNIQUE(profile_id, predecessor_id))""",
    """CREATE TABLE qc_lot_versions (
        version_id INTEGER PRIMARY KEY, lot_key TEXT NOT NULL, predecessor_id INTEGER NOT NULL,
        device_id TEXT NOT NULL, assay_key TEXT NOT NULL, kit_lot TEXT NOT NULL, state TEXT NOT NULL,
        snapshot_json TEXT NOT NULL, actor TEXT NOT NULL, created_at_utc TEXT NOT NULL,
        reason TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE, intent_hash TEXT NOT NULL,
        UNIQUE(lot_key, predecessor_id))""",
    """CREATE TABLE qc_report_evidence (
        evidence_id INTEGER PRIMARY KEY, lot_version_id INTEGER NOT NULL UNIQUE,
        model_json TEXT NOT NULL, model_sha256 TEXT NOT NULL, pdf_bytes BLOB NOT NULL,
        pdf_sha256 TEXT NOT NULL, algorithm_id TEXT NOT NULL, renderer_id TEXT NOT NULL,
        created_at_utc TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE)""",
)


def resolve_store_path(store_spec: Mapping[str, Any] | None) -> Path:
    if not isinstance(store_spec, Mapping) or store_spec.get("driver") != "sqlite" or not str(store_spec.get("path") or "").strip():
        raise QCStoreError("Der effektive SQLite-Ergebnisspeicher muss ausdrücklich angegeben werden.")
    return Path(str(store_spec["path"])).resolve()


def _connect_uri(path: Path, mode: str) -> sqlite3.Connection:
    try:
        return sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True, timeout=5, isolation_level=None)
    except sqlite3.OperationalError as exc:
        if "invalid uri authority" not in str(exc).lower():
            raise
        filename = path.as_posix()
        prefix = "file://" if filename.startswith("/") else "file:///"
        return sqlite3.connect(f"{prefix}{quote(filename, safe='/:')}?mode={mode}", uri=True, timeout=5, isolation_level=None)


def _schema_state(conn: sqlite3.Connection) -> str:
    tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    present = tables.intersection(_TABLES)
    if not present:
        return "uninitialized"
    if present != _TABLES:
        raise QCStoreError("Die QC-Tabellen sind unvollständig. Bitte Datenbestand klären.")
    versions = [int(row[0]) for row in conn.execute("SELECT version FROM qc_schema_migrations ORDER BY version")]
    if versions != [SCHEMA_VERSION]:
        raise QCStoreError("Die QC-Schemaversion wird nicht unterstützt.")
    return "ready"


@contextmanager
def read_connection(store_spec: Mapping[str, Any]) -> Iterator[sqlite3.Connection | None]:
    path = resolve_store_path(store_spec)
    if not path.is_file():
        yield None
        return
    try:
        conn = _connect_uri(path, "ro")
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            state = _schema_state(conn)
            yield conn if state == "ready" else None
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise QCStoreError(f"Der QC-Ergebnisspeicher konnte nicht gelesen werden: {exc}") from exc


@contextmanager
def write_connection(store_spec: Mapping[str, Any], *, initialize: bool = False,
                     migration: dict[str, Any] | None = None) -> Iterator[sqlite3.Connection]:
    path = resolve_store_path(store_spec)
    if not initialize and not path.is_file():
        raise QCStoreError("Die Geräteverwaltung ist noch nicht eingerichtet. Bitte Geräte übernehmen oder erfassen.")
    if initialize:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = (sqlite3.connect(str(path), timeout=5, isolation_level=None) if initialize
                else _connect_uri(path, "rw"))
    except sqlite3.Error as exc:
        raise QCStoreError(f"Der QC-Ergebnisspeicher konnte nicht geöffnet werden: {exc}") from exc
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        state = _schema_state(conn)
        if state != "ready":
            if not initialize:
                raise QCStoreError("Die Geräteverwaltung ist noch nicht eingerichtet.")
            for statement in _DDL:
                conn.execute(statement)
            data = dict(migration or {})
            conn.execute("INSERT INTO qc_schema_migrations VALUES (?, ?, ?, ?, ?)", (
                SCHEMA_VERSION, str(data.get("source_sha256") or ""), str(data.get("source_path") or ""),
                utc_now(), canonical_json(data)))
        yield conn
        conn.execute("COMMIT")
    except sqlite3.Error as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise QCStoreError(f"Der QC-Ergebnisspeicher konnte nicht geändert werden: {exc}") from exc
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def version_record(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    value = dict(row)
    value["snapshot"] = json.loads(value.pop("snapshot_json"))
    return value


def _latest_inventory(conn: sqlite3.Connection) -> dict[str, Any] | None:
    return version_record(conn.execute("SELECT * FROM qc_inventory_versions ORDER BY version_id DESC LIMIT 1").fetchone())


def _missing_inventory() -> dict[str, Any]:
    return {"version_id": 0, "predecessor_id": 0, "snapshot": {
        "devices": [{"device_id": DEFAULT_DEVICE_ID, "display_name": "", "active": True,
                     "serial_number": "", "lnr": "", "eva": "", "incomplete": True, "legacy": True}],
        "default_device_id": DEFAULT_DEVICE_ID, "migration_required": True,
    }}


def get_inventory(store_spec: Mapping[str, Any], *, include_history: bool = False,
                  include_unregistered: bool = False) -> dict[str, Any]:
    with read_connection(store_spec) as conn:
        result = _latest_inventory(conn) if conn is not None else None
        result = result or _missing_inventory()
        if include_history:
            result["history"] = [version_record(row) for row in conn.execute(
                "SELECT * FROM qc_inventory_versions ORDER BY version_id")] if conn is not None else []
    if not result["version_id"]:
        existing = {device["device_id"] for device in result["snapshot"]["devices"]}
        for identifier in sorted(_history_device_ids(store_spec).difference(existing)):
            result["snapshot"]["devices"].append({"device_id": identifier, "display_name": "", "active": True,
                "serial_number": "", "lnr": "", "eva": "", "incomplete": True, "legacy": True})
    elif include_unregistered:
        existing = {device["device_id"] for device in result["snapshot"]["devices"]}
        result["unregistered_devices"] = [{"device_id": identifier, "display_name": "", "active": True,
            "serial_number": "", "lnr": "", "eva": "", "incomplete": True, "legacy": True}
            for identifier in sorted(_history_device_ids(store_spec).difference(existing))]
    return result


def get_status(store_spec: Mapping[str, Any]) -> dict[str, Any]:
    path = resolve_store_path(store_spec)
    inventory = get_inventory(store_spec)
    ready = bool(inventory["version_id"])
    return {"status": "ok" if ready else "migration_required", "path": str(path),
            "message": "Geräteverwaltung aus dem Ergebnisspeicher." if ready else "Geräte übernehmen oder erfassen; DEFAULT_DEVICE ist unvollständig und für QC nicht verwendbar.",
            "using_fallback": not ready, "version_id": inventory["version_id"]}


def _history_device_ids(store_spec: Mapping[str, Any]) -> set[str]:
    return {str(row.get("device_id") or "") for row in list_result_runs(dict(store_spec), limit=None)["runs"]
            if str(row.get("device_id") or "").strip()}


def _normalize_inventory(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("devices"), list):
        raise QCConfigurationError("Eine vollständige Geräteliste ist erforderlich.")
    devices, ids = [], set()
    for raw in snapshot["devices"]:
        if not isinstance(raw, Mapping):
            raise QCConfigurationError("Ein Geräteeintrag ist ungültig.")
        device_id = str(raw.get("device_id") or "").strip()
        if not device_id or device_id in ids:
            raise QCConfigurationError("Gerätekennungen fehlen oder sind doppelt.")
        ids.add(device_id)
        device = {key: str(raw.get(key) or "").strip() for key in ("display_name", "serial_number", "lnr", "eva")}
        device.update(device_id=device_id, active=bool(raw.get("active", True)), legacy=bool(raw.get("legacy", False)))
        device["incomplete"] = not bool(device["display_name"] and any(device[key] for key in ("serial_number", "lnr", "eva")))
        devices.append(device)
    default = str(snapshot.get("default_device_id") or "").strip()
    if not devices or default not in ids:
        raise QCConfigurationError("Ein vorhandenes Standardgerät muss ausgewählt sein.")
    value = {"devices": devices, "default_device_id": default, "migration_required": False}
    if "migration" in snapshot:
        value["migration"] = json.loads(canonical_json(snapshot["migration"]))
    return value


def intent_hash(action: str, payload: Any, context: MutationContext) -> str:
    return content_hash({"action": action, "payload": payload, "actor": context.operator_initials, "reason": context.reason})


def repeated_request(conn: sqlite3.Connection, table: str, context: MutationContext, intent: str) -> dict[str, Any] | None:
    if table not in {"qc_inventory_versions", "qc_profile_versions", "qc_lot_versions"}:
        raise ValueError("invalid_qc_owner_table")
    row = conn.execute(f"SELECT * FROM {table} WHERE request_id=?", (context.request_id,)).fetchone()
    if row is None:
        return None
    if row["intent_hash"] != intent:
        raise QCConflictError("Diese Anfrage wurde bereits für andere Daten verwendet.")
    return version_record(row)


def _append_inventory(conn: sqlite3.Connection, snapshot: dict[str, Any], expected: int,
                      context: MutationContext, intent: str, *, imported: bool = False,
                      historical_ids: set[str] | None = None) -> dict[str, Any]:
    previous = _latest_inventory(conn)
    previous_id = int(previous["version_id"]) if previous else 0
    if previous_id != expected:
        raise QCConflictError("Die Geräteliste wurde geändert. Bitte neu laden.")
    old_ids = {row["device_id"] for row in previous["snapshot"]["devices"]} if previous else set()
    if not old_ids.issubset({row["device_id"] for row in snapshot["devices"]}):
        raise QCConfigurationError("Historische Geräte bleiben erhalten. Bitte deaktivieren statt entfernen.")
    old_legacy = {row["device_id"] for row in previous["snapshot"]["devices"] if row.get("legacy")} if previous else set()
    allowed_legacy = old_legacy | set(historical_ids or ()) | {DEFAULT_DEVICE_ID}
    for device in snapshot["devices"]:
        if device["incomplete"] and not (imported or (device["legacy"] and device["device_id"] in allowed_legacy)):
            raise QCConfigurationError("Neue Geräte brauchen einen Namen und mindestens SN, LNR oder EVA.")
    cursor = conn.execute("""INSERT INTO qc_inventory_versions
        (predecessor_id, snapshot_json, actor, created_at_utc, reason, request_id, intent_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)""", (expected, canonical_json(snapshot), context.operator_initials,
                                         utc_now(), context.reason or "Geräteliste geändert", context.request_id, intent))
    return version_record(conn.execute("SELECT * FROM qc_inventory_versions WHERE version_id=?", (cursor.lastrowid,)).fetchone())


def save_inventory(store_spec: Mapping[str, Any], snapshot: Mapping[str, Any], *, expected_version_id: int,
                   context: MutationContext) -> dict[str, Any]:
    normalized = _normalize_inventory(snapshot)
    historical_ids = _history_device_ids(store_spec)
    intent = intent_hash("save_inventory", {"snapshot": normalized, "expected": expected_version_id}, context)
    with write_connection(store_spec, initialize=int(expected_version_id) == 0) as conn:
        repeated = repeated_request(conn, "qc_inventory_versions", context, intent)
        if repeated:
            return repeated
        if historical_ids != _history_device_ids(store_spec):
            raise QCConflictError("Die historischen Geräteverweise wurden geändert. Bitte neu laden.")
        if not historical_ids.issubset({row["device_id"] for row in normalized["devices"]}):
            raise QCConfigurationError("Die Geräteliste muss historische Gerätekennungen erhalten.")
        return _append_inventory(conn, normalized, int(expected_version_id), context, intent, historical_ids=historical_ids)


def legacy_device_source(project_root: str | Path) -> dict[str, Any]:
    path = Path(project_root) / "config" / "devices.json"
    if not path.is_file():
        raise QCConfigurationError("config/devices.json fehlt. Geräte können stattdessen erfasst werden.")
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": raw}


def migrate_legacy_devices(store_spec: Mapping[str, Any], project_root: str | Path, *, expected_source_sha256: str,
                           context: MutationContext) -> dict[str, Any]:
    source = legacy_device_source(project_root)
    if source["sha256"] != expected_source_sha256:
        raise QCConflictError("Die alte Gerätedatei wurde geändert. Bitte erneut laden.")
    try:
        payload = json.loads(source["bytes"].decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise QCConfigurationError("Die alte Gerätedatei ist unlesbar; sie bleibt unverändert.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("devices"), list):
        raise QCConfigurationError("Die alte Gerätedatei enthält keine gültige Geräteliste.")
    devices, seen = [], set()
    for raw in payload["devices"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("device_id"), str) or not raw["device_id"].strip():
            raise QCConfigurationError("Eine alte Gerätekennung fehlt. Übernahme wurde abgebrochen.")
        identifier = raw["device_id"].strip()
        if identifier in seen:
            raise QCConfigurationError("Die alte Gerätedatei enthält doppelte Gerätekennungen.")
        seen.add(identifier)
        devices.append({**raw, "device_id": identifier, "legacy": True})
    historical_ids = _history_device_ids(store_spec)
    default = str(payload.get("default_device_id") or (devices[0]["device_id"] if devices else DEFAULT_DEVICE_ID)).strip()
    for identifier in sorted((historical_ids | {default}).difference(seen)):
        devices.append({"device_id": identifier, "display_name": "", "legacy": True})
    migration = {"source_sha256": source["sha256"], "source_path": source["path"],
                 "historical_device_ids": sorted(historical_ids), "component_schema_version": SCHEMA_VERSION}
    normalized = _normalize_inventory({"devices": devices, "default_device_id": default, "migration": migration})
    intent = intent_hash("migrate_devices", {"source": source["sha256"]}, context)
    with write_connection(store_spec, initialize=True, migration=migration) as conn:
        repeated = repeated_request(conn, "qc_inventory_versions", context, intent)
        if repeated:
            return repeated
        for row in conn.execute("SELECT * FROM qc_inventory_versions ORDER BY version_id"):
            record = version_record(row)
            if record["snapshot"].get("migration", {}).get("source_sha256") == source["sha256"]:
                return record
        if _latest_inventory(conn) is not None:
            raise QCConflictError("Die Geräteverwaltung ist bereits eingerichtet; bitte Geräte bearbeiten.")
        if legacy_device_source(project_root)["sha256"] != source["sha256"] or historical_ids != _history_device_ids(store_spec):
            raise QCConflictError("Die Übernahmequellen wurden geändert. Bitte erneut laden.")
        return _append_inventory(conn, normalized, 0, context, intent, imported=True)


def lot_identity(device_id: str, assay_key: str, kit_lot: str) -> str:
    return content_hash([device_id, assay_key, kit_lot])


def list_lots(store_spec: Mapping[str, Any], *, include_history: bool = False) -> list[dict[str, Any]]:
    with read_connection(store_spec) as conn:
        if conn is None:
            return []
        rows = [version_record(row) for row in conn.execute("SELECT * FROM qc_lot_versions ORDER BY version_id")]
    if include_history:
        return rows
    heads = {row["lot_key"]: row for row in rows}
    return list(heads.values())


def get_lot(store_spec: Mapping[str, Any], lot_key: str) -> dict[str, Any]:
    result = next((row for row in list_lots(store_spec) if row["lot_key"] == lot_key), None)
    if result is None:
        raise QCConfigurationError("Die QC-Charge wurde nicht gefunden.")
    return result


def get_report_evidence(store_spec: Mapping[str, Any], *, lot_version_id: int) -> dict[str, Any] | None:
    with read_connection(store_spec) as conn:
        row = conn.execute("SELECT * FROM qc_report_evidence WHERE lot_version_id=?", (int(lot_version_id),)).fetchone() if conn is not None else None
        if row is None:
            return None
        result = dict(row)
        result["model"] = json.loads(result.pop("model_json"))
        if hashlib.sha256(result["pdf_bytes"]).hexdigest() != result["pdf_sha256"] or content_hash(result["model"]) != result["model_sha256"]:
            raise QCStoreError("Der gespeicherte PDF-Nachweis ist beschädigt.")
        return result


def _capture(store_spec: Mapping[str, Any], profile_version_id: int, kit_lot: str) -> dict[str, Any]:
    from .sources import get_lot_sources

    return get_lot_sources(store_spec, profile_version_id=profile_version_id, kit_lot=kit_lot)


def _require_sources(store_spec: Mapping[str, Any], captured: dict[str, Any], expected: str) -> None:
    if not expected or captured["source_token"] != expected:
        raise QCConflictError("Messwerte, Validierungen oder Konfiguration wurden geändert. Bitte neu laden.")
    current = _capture(store_spec, captured["profile_version_id"], captured["kit_lot"])
    if current["source_token"] != captured["source_token"]:
        raise QCConflictError("Die Quellen wurden während der Bearbeitung geändert. Bitte neu laden.")
    if not captured["included"]:
        raise QCConfigurationError("Keine vollständigen, eindeutig validierten Messwerte für diese QC-Charge verfügbar.")


def _freeze_sd(raw: Mapping[str, Any] | None, sources: dict[str, Any], previous: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from .profiles import normalize_sd_reference

    controls = {row["control_id"]: row for row in sources["profile_snapshot"]["controls"]}
    if raw is None:
        raw = {identifier: control["sd_reference"] for identifier, control in controls.items() if control.get("sd_reference")}
    if not isinstance(raw, Mapping) or not set(raw).issubset(controls):
        raise QCConfigurationError("SD-Referenzen müssen zu den stabilen Kontrollen gehören.")
    result = {}
    for identifier, reference in raw.items():
        if isinstance(reference, Mapping) and reference.get("reference_id"):
            if not previous or reference != previous.get(identifier):
                raise QCConflictError("Die vorhandene SD-Referenz wurde geändert. Bitte neu laden.")
            result[identifier] = json.loads(canonical_json(reference))
            continue
        normalized = normalize_sd_reference(reference)
        if normalized is None:
            continue
        if normalized["kind"] == "confirmed_baseline":
            points = [point for point in sources["included"] if point["control_id"] == identifier]
            if len(points) < 2:
                raise QCConfigurationError("Eine bestätigte Referenzserie braucht mindestens zwei validierte Messungen.")
            normalized.update(source_token=sources["source_token"], measurements=points,
                              profile_version_id=sources["profile_version_id"], calculation="sample-sd-and-mean-deferred-to-p5")
        elif normalized["kind"] == "manual":
            normalized["profile_version_id"] = sources["profile_version_id"]
        normalized["reference_id"] = content_hash({"control_id": identifier, "reference": normalized})
        result[identifier] = normalized
    return result


def _append_lot(conn: sqlite3.Connection, snapshot: dict[str, Any], expected: int, context: MutationContext,
                intent: str) -> dict[str, Any]:
    key = lot_identity(snapshot["device_id"], snapshot["assay_key"], snapshot["kit_lot"])
    previous = version_record(conn.execute("SELECT * FROM qc_lot_versions WHERE lot_key=? ORDER BY version_id DESC LIMIT 1", (key,)).fetchone())
    if (previous["version_id"] if previous else 0) != expected:
        raise QCConflictError("Die Charge wurde geändert. Bitte neu laden.")
    cursor = conn.execute("""INSERT INTO qc_lot_versions
        (lot_key, predecessor_id, device_id, assay_key, kit_lot, state, snapshot_json, actor, created_at_utc, reason, request_id, intent_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
        key, expected, snapshot["device_id"], snapshot["assay_key"], snapshot["kit_lot"], snapshot["state"],
        canonical_json(snapshot), context.operator_initials, utc_now(), context.reason or "QC-Charge geändert", context.request_id, intent))
    return version_record(conn.execute("SELECT * FROM qc_lot_versions WHERE version_id=?", (cursor.lastrowid,)).fetchone())


def _lot_snapshot(sources: dict[str, Any], sd_references: dict[str, Any], state: str = "open") -> dict[str, Any]:
    return {key: sources[key] for key in ("device_id", "assay_key", "kit_lot", "profile_version_id", "inventory_version_id", "start_date")} | {
        "state": state, "source_manifest": sources, "sd_references": sd_references,
        "sd_evaluation": "unavailable" if not sd_references else "deferred-to-p5"}


def open_lot(store_spec: Mapping[str, Any], *, profile_version_id: int, kit_lot: str,
             expected_source_token: str, context: MutationContext, sd_references: Mapping[str, Any] | None = None) -> dict[str, Any]:
    captured = _capture(store_spec, profile_version_id, kit_lot)
    intent = intent_hash("open_lot", {"profile": profile_version_id, "kit_lot": kit_lot,
                                     "source": expected_source_token, "sd": sd_references}, context)
    with write_connection(store_spec) as conn:
        repeated = repeated_request(conn, "qc_lot_versions", context, intent)
        if repeated:
            return repeated
        _require_sources(store_spec, captured, expected_source_token)
        return _append_lot(conn, _lot_snapshot(captured, _freeze_sd(sd_references, captured)), 0, context, intent)


def configure_lot(store_spec: Mapping[str, Any], lot_key: str, *, expected_version_id: int,
                  profile_version_id: int, expected_source_token: str, sd_references: Mapping[str, Any] | None,
                  context: MutationContext) -> dict[str, Any]:
    previous = get_lot(store_spec, lot_key)
    captured = _capture(store_spec, profile_version_id, previous["kit_lot"])
    intent = intent_hash("configure_lot", {"lot": lot_key, "expected": expected_version_id, "profile": profile_version_id,
                                          "source": expected_source_token, "sd": sd_references}, context)
    with write_connection(store_spec) as conn:
        repeated = repeated_request(conn, "qc_lot_versions", context, intent)
        if repeated:
            return repeated
        if previous["state"] != "open":
            raise QCConflictError("Die Charge ist abgeschlossen. Änderungen brauchen eine ausdrückliche Wiederöffnung.")
        if (captured["device_id"], captured["assay_key"]) != (previous["device_id"], previous["assay_key"]):
            raise QCConfigurationError("Das Prüfprofil gehört zu einem anderen Gerät oder Assay.")
        _require_sources(store_spec, captured, expected_source_token)
        return _append_lot(conn, _lot_snapshot(captured, _freeze_sd(sd_references, captured, previous["snapshot"]["sd_references"])), expected_version_id, context, intent)


def reopen_lot(store_spec: Mapping[str, Any], lot_key: str, *, expected_version_id: int,
               expected_source_token: str, context: MutationContext) -> dict[str, Any]:
    if not context.reason:
        raise QCConfigurationError("Bitte den Grund für die Wiederöffnung angeben.")
    previous = get_lot(store_spec, lot_key)
    captured = _capture(store_spec, previous["snapshot"]["profile_version_id"], previous["kit_lot"])
    intent = intent_hash("reopen_lot", {"lot": lot_key, "expected": expected_version_id, "source": expected_source_token}, context)
    with write_connection(store_spec) as conn:
        repeated = repeated_request(conn, "qc_lot_versions", context, intent)
        if repeated:
            return repeated
        if previous["state"] != "closed":
            raise QCConflictError("Nur eine abgeschlossene Charge kann wieder geöffnet werden.")
        _require_sources(store_spec, captured, expected_source_token)
        snapshot = _lot_snapshot(captured, previous["snapshot"]["sd_references"])
        snapshot["reopened_from_version_id"] = previous["version_id"]
        return _append_lot(conn, snapshot, expected_version_id, context, intent)


def close_lot(store_spec: Mapping[str, Any], lot_key: str, *, expected_version_id: int,
              expected_source_token: str, witness_kit_lot: str, expected_witness_source_token: str,
              analysis_model: Mapping[str, Any], pdf_bytes: bytes, pdf_sha256: str,
              algorithm_id: str, renderer_id: str, context: MutationContext,
              expected_chronology_token: str | None = None, profile_version_id: int | None = None) -> dict[str, Any]:
    """Atomically publish prepared evidence after rechecking complete usage.

    Existing callers may omit a chronology token; their current context is then
    captured before the lock and checked again under it. UI previews always pass
    their inspected token. No analysis or PDF rendering runs under the lock.
    """
    from .model import QCAnalysis
    from .sources import get_lot_chronology

    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-") or b"%%EOF" not in pdf_bytes[-1024:]:
        raise QCConfigurationError("Ein vollständiger gelieferter PDF-Nachweis ist erforderlich.")
    if hashlib.sha256(pdf_bytes).hexdigest() != pdf_sha256:
        raise QCConflictError("Die PDF-Prüfsumme stimmt nicht überein.")
    model = json.loads(canonical_json(analysis_model))
    analysis = QCAnalysis.freeze(model)
    if not analysis.is_supported or model.get("algorithm_id") != algorithm_id or model.get("renderer_id") != renderer_id:
        raise QCConfigurationError("Analyse- und PDF-Verfahrenskennungen fehlen oder widersprechen sich.")
    supplied_source = model.get("source_manifest", {})
    selected_profile = profile_version_id or supplied_source.get("profile_version_id")
    intent = intent_hash("close_lot", {"lot": lot_key, "expected": expected_version_id, "source": expected_source_token,
        "witness": expected_witness_source_token, "witness_lot": witness_kit_lot, "chronology": expected_chronology_token,
        "profile": selected_profile, "model": model, "pdf": pdf_sha256}, context)
    baseline_usage = expected_chronology_token
    if baseline_usage is None:
        baseline_usage = get_lot_chronology(store_spec, profile_version_id=selected_profile).snapshot_sha256
    with write_connection(store_spec) as conn:
        repeated = repeated_request(conn, "qc_lot_versions", context, intent)
        if repeated:
            return repeated
        previous = version_record(conn.execute("SELECT * FROM qc_lot_versions WHERE lot_key=? ORDER BY version_id DESC LIMIT 1", (lot_key,)).fetchone())
        if (previous["version_id"] if previous else 0) != expected_version_id:
            raise QCConflictError("Die Charge wurde geändert. Bitte neu laden.")
        if previous and previous["state"] != "open":
            raise QCConflictError("Die Charge ist bereits abgeschlossen; späte Werte brauchen eine Wiederöffnung.")
        if previous and previous["snapshot"]["profile_version_id"] != selected_profile:
            raise QCConflictError("Das ausgewählte Prüfprofil ist noch nicht an die Charge gebunden. Bitte zuerst die Konfiguration speichern.")
        kit_lot = previous["kit_lot"] if previous else supplied_source.get("kit_lot")
        captured = _capture(store_spec, selected_profile, kit_lot)
        if lot_identity(captured["device_id"], captured["assay_key"], captured["kit_lot"]) != lot_key:
            raise QCConflictError("Die Profil-/Chargenidentität stimmt nicht überein.")
        references = previous["snapshot"]["sd_references"] if previous else {}
        if supplied_source != captured or model.get("sd_references") != references:
            raise QCConflictError("Der Analyse-Nachweis gehört zu einem anderen Quellen- oder SD-Stand.")
        _require_sources(store_spec, captured, expected_source_token)
        usage = get_lot_chronology(store_spec, profile_version_id=selected_profile)
        if not baseline_usage or usage.snapshot_sha256 != baseline_usage:
            raise QCConflictError("Der vollständige Nutzungs- oder Konfigurationsstand wurde geändert. Bitte den Abschluss neu prüfen.")
        own = next((row for row in usage.to_dict()["lots"] if row["kit_lot"] == kit_lot), None)
        witnesses = [row for row in own["witnesses"] if row["kit_lot"] == witness_kit_lot] if own else []
        if not witnesses:
            raise QCConfigurationError("Eine sicher spätere Nutzung einer anderen Kit-Charge ist nicht belegt.")
        witness = _capture(store_spec, selected_profile, witness_kit_lot)
        if witness["source_token"] != expected_witness_source_token:
            raise QCConflictError("Die Quellen der belegenden Charge wurden geändert. Bitte neu prüfen.")
        snapshot = _lot_snapshot(captured, references, "closed")
        snapshot.update(successor_witness={"witness_version": "qc-usage-witness-v1", "kit_lot": witness_kit_lot,
            "chronology": usage.to_dict(), "chronology_sha256": usage.snapshot_sha256, "measurements": witnesses},
            evidence={"pdf_sha256": pdf_sha256, "model_sha256": analysis.model_sha256, "algorithm_id": algorithm_id, "renderer_id": renderer_id})
        closed = _append_lot(conn, snapshot, expected_version_id, context, intent)
        conn.execute("""INSERT INTO qc_report_evidence
            (lot_version_id, model_json, model_sha256, pdf_bytes, pdf_sha256, algorithm_id, renderer_id, created_at_utc, request_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (closed["version_id"], analysis.model_json, analysis.model_sha256,
                pdf_bytes, pdf_sha256, algorithm_id, renderer_id, utc_now(), context.request_id))
        return closed
