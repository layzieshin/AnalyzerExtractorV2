"""Synthetic persistence, concurrency and legacy qualification for P3b."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import threading
from pathlib import Path

import pytest

from src.dbwriter.api import (ResultRevisionConflictError, ResultRevisionError,
    append_result_revision, select_result_revision, write_record_sqlite)
from src.extractor.api import AssayRecord
from src.resultstore.api import get_report_runs, get_result_run, list_result_charges, list_result_runs
from src.resultvalidation.api import (ValidationStateConflictError,
    list_run_validations_readonly, validate_run)
from src.ruleresolver.api import RuleSet


def _spec(path):
    return {"driver": "sqlite", "path": str(path)}


def _rule(*keys):
    return RuleSet("A", "A.json", {"extract_rules": {"fields": [{"key": key, "required": False} for key in keys]}})


def _write(path, key="old", value="1", job="job"):
    return write_record_sqlite(AssayRecord("A", "L1", key, {"value": value}, "original-device"),
        _rule("value"), str(path), job_id=job, pdf_sha256="a"*64, assay_block_hash="b"*64).run_id


def _candidate(path, run_id, *, request="request", key="new", value="2", fields=("value",), error="", verified=True, token=None):
    state = get_result_run(_spec(path), run_id)
    snapshot = {
        "assay_key": "A", "lot_id": "L2", "device_id": "original-device", "dedupe_key": key,
        "dedupe_version": "v2", "dedupe_basis": {"device_id": "original-device"},
        "payload": {"value": value}, "ruleset_file": "A.json", "ruleset": _rule(*fields).data,
        "rule_sha256": "c"*64, "source_verified": verified, "error": error,
    }
    result = append_result_revision(str(path), run_id, expected_selection_token=token or state["selection_token"],
        request_id=request, snapshot=snapshot, created_by="RR")
    return result, snapshot, state["selection_token"]


def _choose(path, run_id, revision, action="accept_new", request="choice", token=None):
    return select_result_revision(str(path), run_id, revision,
        expected_selection_token=token or get_result_run(_spec(path), run_id)["selection_token"],
        action=action, request_id=request, decided_by="RR")


def test_candidate_choice_binding_and_original_rows_are_immutable(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    with sqlite3.connect(path) as conn:
        original = conn.execute("SELECT * FROM runs").fetchall()
    result, _, original_token = _candidate(path, run)
    pending = get_result_run(_spec(path), run)
    assert pending["payload"] == {"value": "1"}
    assert pending["pending_revision"]["revision_id"] == result["revision_id"]
    with pytest.raises(ValidationStateConflictError, match="zuerst"):
        validate_run(_spec(path), run, "RR", expected_selection_token=original_token)
    choice = _choose(path, run, result["revision_id"])
    effective = get_result_run(_spec(path), run)
    assert effective["payload"] == {"value": "2"}
    assert effective["lot_id"] == "L2" and effective["device_id"] == "original-device"
    assert effective["original_result"]["payload"] == {"value": "1"}
    assert effective["pending_revision"] is None
    with pytest.raises(ValidationStateConflictError):
        validate_run(_spec(path), run, "RR")
    with pytest.raises(ValidationStateConflictError):
        validate_run(_spec(path), run, "RR", expected_selection_token=original_token)
    saved = validate_run(_spec(path), run, "RR", expected_selection_token=choice["selection_token"], request_id="validate")
    assert saved.revision_id == result["revision_id"] and saved.selection_id == choice["selection_id"]
    assert validate_run(_spec(path), run, "RR", expected_selection_token=choice["selection_token"], request_id="validate") == saved
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM runs").fetchall() == original
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE run_result_revisions SET created_by='oops'")
    with pytest.raises(ResultRevisionConflictError, match="validiert"):
        _candidate(path, run, request="after-validation")


def test_selected_lot_filters_reports_and_complete_read(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    revision, _, _ = _candidate(path, run)
    _choose(path, run, revision["revision_id"])
    assert list_result_runs(_spec(path), charge="L1")["runs"] == []
    assert list_result_runs(_spec(path), charge="L2")["runs"][0]["payload"] == {"value": "2"}
    assert list_result_charges(_spec(path), "A") == [{"lot_id": "L2", "charge": "L2"}]
    assert get_report_runs(_spec(path), "job")["runs"][0]["revision_id"] == revision["revision_id"]
    with sqlite3.connect(path) as conn:
        conn.executemany("""INSERT INTO runs(job_id,pdf_path,assay_key,lot_id,dedupe_key,ruleset_file,payload_json,created_at)
            VALUES ('other','','A','L',?,'A.json','{}','')""", [(f"k{i}",) for i in range(502)])
    assert len(list_result_runs(_spec(path), limit=None)["runs"]) == 503


def test_alias_claim_is_atomic_retained_and_normal_ingestion_is_duplicate(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    revision, _, _ = _candidate(path, run)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM run_identity_aliases").fetchall() == []
    _choose(path, run, revision["revision_id"])
    second, _, _ = _candidate(path, run, request="r2", key="newer")
    _choose(path, run, second["revision_id"], request="c2")
    for key in ("old", "new", "newer"):
        duplicate = write_record_sqlite(AssayRecord("A", "L", key, {"value": "2"}, "original-device"),
            _rule("value"), str(path), job_id="different-import", pdf_sha256="d"*64, assay_block_hash="e"*64)
        assert duplicate.status == "duplicate_pending" and duplicate.existing_run_id == run
    assert _write(path) == run
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT dedupe_key FROM run_identity_aliases ORDER BY alias_id").fetchall() == [("new",), ("newer",)]
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_alias_collision_rolls_back_selection_and_claim(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    _write(path, key="occupied", job="other")
    revision, _, _ = _candidate(path, run, key="occupied")
    with pytest.raises(ResultRevisionConflictError, match="Duplikat"):
        _choose(path, run, revision["revision_id"])
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM run_result_selections").fetchall() == []
        assert conn.execute("SELECT * FROM run_identity_aliases").fetchall() == []
    assert get_result_run(_spec(path), run)["pending_revision"] is not None


@pytest.mark.parametrize("action", ["keep_old", "accept_new"])
def test_all_configured_fields_including_optional_block_incomplete_choices(tmp_path, action):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    revision, _, _ = _candidate(path, run, fields=("value", "optional"), error="configured_fields_empty: optional")
    with pytest.raises(ResultRevisionError, match="optional"):
        _choose(path, run, revision["revision_id"], action=action)
    with pytest.raises(ValidationStateConflictError):
        validate_run(_spec(path), run, "RR")
    retry, _, _ = _candidate(path, run, request="fixed-rule")
    _choose(path, run, retry["revision_id"], action="keep_old")
    state = get_result_run(_spec(path), run)
    assert len(state["result_revisions"]) == 2 and state["revision_id"] == 0
    assert state["result_revisions"][1]["supersedes_revision_id"] == revision["revision_id"]
    saved = validate_run(_spec(path), run, "RR", expected_selection_token=state["selection_token"])
    assert saved.revision_id == 0 and saved.selection_id is not None


def test_complete_old_choice_resolves_failed_candidate_but_unproven_source_cannot(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    revision, _, _ = _candidate(path, run, value=None, error="configured_fields_empty: value")
    _choose(path, run, revision["revision_id"], action="keep_old")
    revision, _, _ = _candidate(path, run, request="unproven", verified=False)
    with pytest.raises(ResultRevisionError, match="Quelle"):
        _choose(path, run, revision["revision_id"], action="keep_old", request="reject-source")


def test_idempotency_reuse_and_stale_candidate_choice(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    first, snapshot, token = _candidate(path, run)
    assert append_result_revision(str(path), run, expected_selection_token=token, request_id="request", snapshot=snapshot, created_by="RR") == first
    altered = copy.deepcopy(snapshot)
    altered["payload"]["value"] = "different"
    with pytest.raises(ResultRevisionConflictError, match="Anfragekennung"):
        append_result_revision(str(path), run, expected_selection_token=token, request_id="request", snapshot=altered, created_by="RR")
    pending_token = get_result_run(_spec(path), run)["selection_token"]
    second, _, _ = _candidate(path, run, request="retry")
    with pytest.raises(ResultRevisionConflictError):
        _choose(path, run, first["revision_id"], token=pending_token)
    selected_token = get_result_run(_spec(path), run)["selection_token"]
    choice = _choose(path, run, second["revision_id"], token=selected_token)
    assert _choose(path, run, second["revision_id"], token=selected_token) == choice
    with pytest.raises(ResultRevisionConflictError, match="Anfragekennung"):
        _choose(path, run, second["revision_id"], token=selected_token, action="keep_old")


def test_readonly_legacy_migration_and_failed_migration_rollback(tmp_path):
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE runs(id INTEGER PRIMARY KEY, assay_key TEXT, lot_id TEXT, payload_json TEXT)")
        conn.execute("INSERT INTO runs VALUES(1,'A','L','{\"value\":\"1\"}')")
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert get_result_run(_spec(path), 1)["revision_id"] == 0
    assert list_run_validations_readonly(_spec(path), [1]).records == ()
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    # A failed authoritative check also rolls back all migration DDL/metadata.
    with pytest.raises(ResultRevisionConflictError):
        append_result_revision(str(path), 1, expected_selection_token="stale", request_id="x", snapshot={}, created_by="RR")
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("runs",)]
    saved = validate_run(_spec(path), 1, "RR")
    assert saved.revision_id == 0 and saved.selection_id is None


def test_legacy_validation_binding_readonly_does_not_migrate(tmp_path):
    path = tmp_path / "legacy.sqlite"
    _write(path)
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE run_validations(validation_id INTEGER PRIMARY KEY,run_id INTEGER,
            operator_initials TEXT,validated_at_utc TEXT,comment TEXT,supersedes_validation_id INTEGER,created_at_utc TEXT)""")
        conn.execute("INSERT INTO run_validations VALUES(1,1,'RR','utc','legacy',NULL,NULL)")
    before = path.read_bytes(), path.stat().st_mtime_ns
    validation = list_run_validations_readonly(_spec(path), [1]).latest(1)
    assert validation.revision_id == 0 and validation.selection_id is None
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def _race(*operations):
    barrier = threading.Barrier(len(operations))
    results = []
    def work(operation):
        barrier.wait(timeout=10)
        try:
            operation()
            results.append("ok")
        except (ResultRevisionConflictError, ValidationStateConflictError) as exc:
            results.append(type(exc).__name__)
    threads = [threading.Thread(target=work, args=(operation,)) for operation in operations]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert all(not thread.is_alive() for thread in threads)
    assert results.count("ok") == 1
    return results


def test_real_connections_serialize_competing_candidates_and_choices(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    _race(lambda: _candidate(path, run, request="one", token="original:1"),
          lambda: _candidate(path, run, request="two", token="original:1"))
    state = get_result_run(_spec(path), run)
    revision = state["pending_revision"]["revision_id"]
    token = state["selection_token"]
    _race(lambda: _choose(path, run, revision, token=token, request="accept"),
          lambda: _choose(path, run, revision, token=token, request="keep", action="keep_old"))
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM run_result_revisions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM run_result_selections").fetchone()[0] == 1


def test_real_connections_reanalysis_validation_race_has_one_winner(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    _race(lambda: _candidate(path, run, token="original:1"),
          lambda: validate_run(_spec(path), run, "RR", expected_selection_token="original:1"))
    state = get_result_run(_spec(path), run)
    valid = list_run_validations_readonly(_spec(path), [run]).latest(run)
    assert (state["pending_revision"] is not None) != (valid is not None)


def test_choice_and_stale_validation_race_never_validates_uninspected_selection(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    revision, _, _ = _candidate(path, run)
    pending_token = get_result_run(_spec(path), run)["selection_token"]
    _race(lambda: _choose(path, run, revision["revision_id"], token=pending_token),
          lambda: validate_run(_spec(path), run, "RR", expected_selection_token=pending_token))
    assert list_run_validations_readonly(_spec(path), [run]).records == ()
    assert get_result_run(_spec(path), run)["pending_revision"] is None


def test_fault_after_alias_insert_rolls_back_then_restart_reuses_pending_candidate(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    revision, _, _ = _candidate(path, run)
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TRIGGER fail_selection BEFORE INSERT ON run_result_selections
                        BEGIN SELECT RAISE(ABORT, 'synthetic_interrupt_after_alias'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic_interrupt"):
        _choose(path, run, revision["revision_id"])
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM run_identity_aliases").fetchall() == []
        assert conn.execute("SELECT * FROM run_result_selections").fetchall() == []
        conn.execute("DROP TRIGGER fail_selection")
    assert get_result_run(_spec(path), run)["pending_revision"] is not None
    _choose(path, run, revision["revision_id"])
    assert get_result_run(_spec(path), run)["payload"] == {"value": "2"}


def test_normal_ingestion_and_alias_acceptance_serialize_identity_ownership(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    revision, _, _ = _candidate(path, run, key="shared")
    pending_token = get_result_run(_spec(path), run)["selection_token"]
    barrier = threading.Barrier(2)
    outcomes = []
    def choose():
        barrier.wait(timeout=10)
        try:
            _choose(path, run, revision["revision_id"], token=pending_token)
            outcomes.append("selected")
        except ResultRevisionConflictError:
            outcomes.append("collision")
    def ingest():
        barrier.wait(timeout=10)
        result = write_record_sqlite(AssayRecord("A", "L2", "shared", {"value": "2"}, "original-device"),
                                     _rule("value"), str(path), job_id="other-import")
        outcomes.append(result.status)
    threads = [threading.Thread(target=choose), threading.Thread(target=ingest)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert all(not thread.is_alive() for thread in threads)
    assert set(outcomes) in ({"selected", "duplicate_pending"}, {"collision", "inserted"})
    with sqlite3.connect(path) as conn:
        owners = conn.execute("SELECT id FROM runs WHERE dedupe_key='shared' UNION SELECT run_id FROM run_identity_aliases WHERE dedupe_key='shared'").fetchall()
    assert len(owners) == 1


def test_invalid_selected_history_and_unknown_component_fail_closed_without_writes(tmp_path):
    path = tmp_path / "results.sqlite"
    run = _write(path)
    revision, _, _ = _candidate(path, run)
    _choose(path, run, revision["revision_id"])
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TRIGGER immutable_run_result_selections_update")
        conn.execute("UPDATE run_result_selections SET previous_selection_token='invalid-chain'")
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert "chain_invalid" in get_result_run(_spec(path), run)["revision_error"]
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    with pytest.raises(ValidationStateConflictError, match="unlesbar"):
        validate_run(_spec(path), run, "RR", expected_selection_token="original:1")
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE dbwriter_schema_migrations SET version=99 WHERE version=2")
    assert "schema_unknown" in get_result_run(_spec(path), run)["revision_error"]
    # A marked v2 store must retain its complete history contract. Neither a
    # read nor a rejected write may recreate an emptied device-history table.
    partial = tmp_path / "partial-v2.sqlite"
    partial_run = _write(partial)
    with sqlite3.connect(partial) as conn:
        conn.execute("DROP TABLE candidate_materializations")
    before = partial.read_bytes(), partial.stat().st_mtime_ns
    state = get_result_run(_spec(partial), partial_run)
    assert state["revision_error"] and state["device_binding_status"] == "unreadable"
    with pytest.raises(ResultRevisionError, match="Bericht-Geräteschema"):
        _candidate(partial, partial_run)
    assert (partial.read_bytes(), partial.stat().st_mtime_ns) == before
