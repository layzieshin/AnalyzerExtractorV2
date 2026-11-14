"""Read-only projection of immutable results, candidates and human selections."""

from __future__ import annotations

import copy
import json
import sqlite3
from typing import Any


def _json(raw: object, kind: type = dict) -> Any:
    value = json.loads(str(raw))
    if not isinstance(value, kind):
        raise ValueError("result_revision_evidence_invalid")
    return value


def configured_fields(ruleset: dict[str, Any]) -> list[str]:
    fields = ruleset.get("extract_rules", {}).get("fields", [])
    return [str(field["key"]) for field in fields if isinstance(field, dict) and field.get("key")]


def missing_fields(payload: dict[str, Any], keys: list[str]) -> list[str]:
    return [key for key in keys if payload.get(key) is None or not str(payload[key]).strip()]


def project_run(conn: sqlite3.Connection, run: dict[str, Any]) -> dict[str, Any]:
    """Project one stable run without creating tables or acquiring a write lock."""
    original = copy.deepcopy(run)
    run_id = run.get("id")
    run.update(
        original_result=original, revision_id=0, selection_id=None,
        selection_token=f"original:{run_id}", pending_revision=None,
        result_revisions=[], result_selections=[], source_provenance={},
        configured_fields=[], missing_fields=[], revision_error="",
    )
    if run_id is None:
        return run
    tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    try:
        component_tables = {"run_source_provenance", "run_result_revisions", "run_result_selections", "run_identity_aliases", "dbwriter_schema_migrations"}
        present = tables.intersection(component_tables)
        if present and present != component_tables:
            raise ValueError("result_revision_schema_incomplete")
        if present and [int(row[0]) for row in conn.execute("SELECT version FROM dbwriter_schema_migrations ORDER BY version")] not in ([1], [1, 2]):
            raise ValueError("result_revision_schema_unknown")
        if present:
            expected = {
                "run_source_provenance": {"run_id", "snapshot_json"},
                "run_result_revisions": {"revision_id", "run_id", "request_id", "expected_selection_token", "supersedes_revision_id", "snapshot_json", "created_by", "created_at"},
                "run_result_selections": {"selection_id", "run_id", "revision_id", "resolves_revision_id", "previous_selection_token", "action", "request_id", "decided_by", "note", "created_at"},
                "run_identity_aliases": {"alias_id", "assay_key", "dedupe_key", "run_id", "revision_id", "created_at"},
            }
            if any({str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")} != columns for table, columns in expected.items()):
                raise ValueError("result_revision_schema_incomplete")
        from .report_devices import check_device_schema
        check_device_schema(conn)
        if "run_source_provenance" in tables:
            row = conn.execute("SELECT snapshot_json FROM run_source_provenance WHERE run_id=?", (run_id,)).fetchone()
            if row:
                run["source_provenance"] = _json(row[0])
        keys = configured_fields(run["source_provenance"].get("ruleset", {}))
        revision_tables = {"run_result_revisions", "run_result_selections"}
        present = tables.intersection(revision_tables)
        if present and present != revision_tables:
            raise ValueError("result_revision_schema_incomplete")
        if present:
            cursor = conn.execute("SELECT * FROM run_result_revisions WHERE run_id=? ORDER BY revision_id", (run_id,))
            revisions = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
            for revision in revisions:
                revision["result"] = _json(revision.pop("snapshot_json"))
            cursor = conn.execute("SELECT * FROM run_result_selections WHERE run_id=? ORDER BY selection_id", (run_id,))
            selections = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
            by_id = {int(row["revision_id"]): row for row in revisions}
            _validate_history(run_id, original, revisions, selections, by_id)
            run["result_revisions"] = revisions
            run["result_selections"] = selections
            if selections:
                selected = selections[-1]
                selected_id = int(selected["revision_id"])
                if selected_id:
                    result = by_id[selected_id]["result"]
                    for name in ("payload", "lot_id", "dedupe_key", "dedupe_version", "dedupe_basis", "ruleset_file"):
                        run[name] = copy.deepcopy(result[name])
                    run["charge"] = run["lot_id"]
                    run["payload_parse_error"] = None
                    run["dedupe_basis_parse_error"] = None
                run["revision_id"] = selected_id
                run["selection_id"] = int(selected["selection_id"])
                run["selection_token"] = f"selection:{selected['selection_id']}"
                contract = by_id[int(selected["resolves_revision_id"])]["result"]
                keys = configured_fields(contract.get("ruleset", {}))
            resolved = {int(row["resolves_revision_id"]) for row in selections}
            if revisions and int(revisions[-1]["revision_id"]) not in resolved:
                pending = revisions[-1]
                run["pending_revision"] = pending
                run["selection_token"] += f"|pending:{pending['revision_id']}"
                keys = configured_fields(pending["result"].get("ruleset", {}))
        run["configured_fields"] = keys
        run["missing_fields"] = missing_fields(run["payload"], keys)
        payload = run["payload"]
        run["result_date"] = str(payload.get("DATUM") or payload.get("date") or "")
    except (KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        run["revision_error"] = f"Ergebnishistorie unlesbar; bitte Datenbestand klaeren: {exc}"
    from .report_devices import project_device
    return project_device(conn, run)


def _validate_history(run_id, original, revisions, selections, by_id):
    base, selected_id = f"original:{run_id}", 0
    for revision in revisions:
        result = revision["result"]
        if result["assay_key"] != original["assay_key"] or result["device_id"] != original["device_id"] or not isinstance(result["payload"], dict):
            raise ValueError("result_revision_identity_invalid")
        supersedes = revision["supersedes_revision_id"]
        if supersedes is not None and (int(supersedes) not in by_id or int(supersedes) >= int(revision["revision_id"])):
            raise ValueError("result_revision_predecessor_invalid")
    for selection in selections:
        candidate_id = int(selection["resolves_revision_id"])
        candidate = by_id[candidate_id]
        result = candidate["result"]
        if selection["previous_selection_token"] != f"{base}|pending:{candidate_id}" or candidate["expected_selection_token"].split("|pending:")[0] != base:
            raise ValueError("result_selection_chain_invalid")
        chosen = int(selection["revision_id"])
        if selection["action"] == "accept_new":
            if chosen != candidate_id or result.get("error"):
                raise ValueError("result_selection_candidate_invalid")
        elif selection["action"] != "keep_old" or chosen != selected_id:
            raise ValueError("result_selection_action_invalid")
        payload = by_id[chosen]["result"]["payload"] if chosen else original["payload"]
        keys = configured_fields(result.get("ruleset", {}))
        if not result.get("source_verified") or not result.get("rule_sha256") or not keys or missing_fields(payload, keys):
            raise ValueError("result_selection_contract_invalid")
        selected_id, base = chosen, f"selection:{selection['selection_id']}"
    resolved = {int(row["resolves_revision_id"]) for row in selections}
    if revisions and int(revisions[-1]["revision_id"]) not in resolved:
        if revisions[-1]["expected_selection_token"].split("|pending:")[0] != base:
            raise ValueError("result_pending_chain_invalid")
