"""Strict read-only report-device and pending-source projections."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _tables(conn):
    return {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def check_device_schema(conn):
    tables = _tables(conn)
    expected = {
        "report_device_assignments": {"assignment_id", "report_id", "predecessor_id", "pdf_sha256", "device_id", "snapshot_json", "actor", "reason", "request_id", "intent_hash", "created_at_utc"},
        "run_device_claims": {"claim_id", "assay_key", "identity_hash", "device_id", "run_id", "assignment_id", "revision_id", "created_at_utc"},
        "candidate_materializations": {"candidate_id", "run_id", "source_snapshot_json", "created_at_utc"},
    }
    versions = [int(row[0]) for row in conn.execute("SELECT version FROM dbwriter_schema_migrations ORDER BY version")] if "dbwriter_schema_migrations" in tables else []
    present = tables & expected.keys()
    if 2 in versions or present:
        if versions != [1, 2] or present != expected.keys() or any({str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")} != columns for table, columns in expected.items()):
            raise ValueError("Unvollständiges Bericht-Geräteschema; bitte Datenbestand klären.")


def assignment_head(conn, report_id):
    check_device_schema(conn)
    if "report_device_assignments" not in _tables(conn):
        return None
    cursor = conn.execute("SELECT * FROM report_device_assignments WHERE report_id=? ORDER BY assignment_id", (report_id,))
    names = [column[0] for column in cursor.description]
    previous, head = 0, None
    for row in cursor:
        value = dict(zip(names, row))
        if value["predecessor_id"] != previous:
            raise ValueError("Bericht-Gerätehistorie ist widersprüchlich.")
        value["snapshot"] = json.loads(value.pop("snapshot_json"))
        previous, head = value["assignment_id"], value
    return head


def project_device(conn, run):
    """Keep import identity; expose one separately evidenced effective device."""
    report_id = str(run.get("job_id") or run.get("report_id") or "")
    raw_device = str((run.get("original_result") or run).get("device_id") or "")
    run.update(import_device_id=raw_device, effective_device_id="", device_assignment_id=0,
               device_binding_status="unconfirmed", device_binding_token="")
    try:
        check_device_schema(conn)
        head = assignment_head(conn, report_id) if report_id else None
        if head:
            if head["pdf_sha256"] != run.get("pdf_sha256") or run.get("id") not in head["snapshot"]["run_ids"]:
                raise ValueError("Messung gehört nicht zum bestätigten Quellbericht.")
            run.update(effective_device_id=head["device_id"], device_assignment_id=head["assignment_id"],
                       device_binding_status="confirmed", device_binding_token=_hash(head))
        elif raw_device and raw_device != "DEFAULT_DEVICE" and "qc_inventory_versions" in _tables(conn):
            has_validations = "run_validations" in _tables(conn)
            # A named historical run with its original human validation remains
            # a labelled legacy observation; new imports are never confirmed by
            # their import/default setting alone.
            cursor = conn.execute("SELECT * FROM run_validations WHERE run_id=?", (run.get("id"),)) if has_validations else None
            rows = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor] if cursor else []
            replaced = {row.get("supersedes_validation_id") for row in rows if row.get("supersedes_validation_id") is not None}
            heads = [row for row in rows if row.get("validation_id") not in replaced]
            inventory_row = conn.execute("SELECT version_id,snapshot_json FROM qc_inventory_versions ORDER BY version_id DESC LIMIT 1").fetchone()
            inventory = json.loads(inventory_row[1]) if inventory_row else {}
            devices = [row for row in inventory.get("devices", []) if row.get("device_id") == raw_device and row.get("display_name") and row.get("active")]
            same_report = conn.execute("SELECT device_id,pdf_sha256 FROM runs WHERE job_id=?", (report_id,)).fetchall() if report_id else []
            unambiguous_report = bool(same_report and len({(row[0], row[1]) for row in same_report}) == 1)
            validation_matches = False
            if len(heads) == 1:
                validation = heads[0]
                token = str(validation.get("selection_token") or "")
                matches = (int(validation.get("revision_id") or 0) == int(run.get("revision_id") or 0)
                    and validation.get("selection_id") == run.get("selection_id")
                    and (token == run.get("selection_token") if token else not run.get("result_revisions") and not run.get("pending_revision")))
                validation_matches = bool(matches and not validation.get("device_assignment_id") and str(validation.get("operator_initials") or "").strip())
            source = run.get("source_provenance") or {}
            registered_legacy_import = not source.get("project_root") and not source.get("version")
            if len(devices) == 1 and (unambiguous_report or not report_id) and (registered_legacy_import or validation_matches):
                # A registered historical import identity may witness usage
                # without validating the measurement. It is NOT sufficient to
                # materialize another-device candidates: that additionally
                # needs the unique current human and full report proof below.
                run.update(effective_device_id=raw_device, device_binding_status="legacy")
                run["device_binding_evidence"] = {"inventory_version_id": inventory_row[0],
                    "validation_id": heads[0].get("validation_id") if validation_matches else None,
                    "provenance": "legacy-human-validation" if validation_matches else "registered-legacy-import",
                    "report_identity_verified": bool(validation_matches and unambiguous_report and len(str(run.get("pdf_sha256") or "")) == 64 and report_id == run["pdf_sha256"][:16])}
                run["device_binding_token"] = _hash(["legacy", run.get("id"), raw_device, run.get("pdf_sha256"), run["device_binding_evidence"]])
    except (KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        run["device_binding_status"] = "unreadable"
        run["device_binding_error"] = str(exc)
    return run


def list_pending_report_candidates(store_spec):
    """No DDL, default-store fallback, job write or candidate decision."""
    from .sqlite_store import _connect_readonly, _resolve_path
    path = _resolve_path(store_spec)
    if not path.is_file():
        return []
    with _connect_readonly(path) as conn:
        if "duplicate_candidates" not in _tables(conn):
            return []
        cursor = conn.execute("SELECT * FROM duplicate_candidates WHERE status='pending' ORDER BY id")
        names = [column[0] for column in cursor.description]
        result = []
        for row in cursor:
            value = dict(zip(names, row))
            value["meta"] = json.loads(value.pop("candidate_meta_json"))
            value["payload"] = json.loads(value.pop("candidate_payload_json"))
            value["dedupe_basis"] = json.loads(value.pop("dedupe_basis_json") or "{}")
            value["candidate_id"] = value.pop("id")
            value["report_id"] = str(value["meta"].get("job_id") or "")
            result.append(value)
        return result


def get_report_device_context(store_spec, report_id):
    from .sqlite_store import _connect_readonly, _resolve_path, get_report_runs, get_result_run
    from src.qualitycontrol.api import get_inventory
    path = _resolve_path(store_spec)
    report = get_report_runs(store_spec, report_id)
    candidates = [row for row in list_pending_report_candidates(store_spec) if row["report_id"] == report_id]
    runs = report["runs"] if report else []
    if not runs and not candidates:
        return None
    with _connect_readonly(path) as conn:
        head = assignment_head(conn, report_id)
    source_hashes = {str(row.get("pdf_sha256") or "") for row in [*runs, *candidates]}
    full_hash = next(iter(source_hashes)) if len(source_hashes) == 1 else ""
    source_ok = len(full_hash) == 64 and all(char in "0123456789abcdef" for char in full_hash) and str(report_id) == full_hash[:16]
    comparisons = []
    for candidate in candidates:
        existing = get_result_run(store_spec, int(candidate["existing_run_id"]))
        proof = existing or {}
        usable = proof.get("device_binding_status") == "confirmed" or (proof.get("device_binding_status") == "legacy" and proof.get("device_binding_evidence", {}).get("report_identity_verified"))
        comparisons.append({"candidate_id": candidate["candidate_id"], "existing_run_id": candidate["existing_run_id"],
            "device_id": proof.get("effective_device_id", "") if usable else "",
            "assignment_id": (existing or {}).get("device_assignment_id", 0),
            "selection_token": (existing or {}).get("selection_token", ""),
            "source_hash": _hash(existing)})
    inventory = get_inventory(store_spec)
    devices = [dict(row) for row in inventory["snapshot"]["devices"] if row["active"] and row.get("display_name") and row["device_id"] != "DEFAULT_DEVICE"]
    raw_devices = {row.get("import_device_id", row.get("device_id")) for row in runs}
    suggestion = head["device_id"] if head else next(iter(raw_devices)) if len(raw_devices) == 1 and next(iter(raw_devices)) in {row["device_id"] for row in devices} else devices[0]["device_id"] if len(devices) == 1 else ""
    context = {"report_id": report_id, "pdf_sha256": full_hash, "source_identity_verified": source_ok,
        "assignment": head, "assignment_id": head["assignment_id"] if head else 0, "device_id": head["device_id"] if head else "",
        "suggested_device_id": suggestion, "devices": devices, "inventory_version_id": inventory["version_id"],
        "inventory_hash": _hash(inventory["snapshot"]), "runs": runs, "candidates": candidates, "comparisons": comparisons,
        "store_path": str(Path(path).resolve())}
    context["context_token"] = _hash(context)
    return context
