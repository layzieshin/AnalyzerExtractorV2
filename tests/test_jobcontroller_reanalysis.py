"""Proven-source/current-rule and bounded process qualification for P3b."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.dbwriter.api import ResultRevisionConflictError, ResultRevisionError, select_result_revision
from src.jobcontroller import reanalysis
from src.jobcontroller.api import reanalyze_run, submit
from src.resultstore.api import get_result_run
from src.resultvalidation.api import ValidationStateConflictError, validate_run
from src.ruleresolver.api import RuleSet


def _rule(key="(1111)", name="Assay A", *, updated=False):
    prefix = "New" if updated else "Old"
    return {
        "assay_key": key, "assay_name": name,
        "lot_rule": {"regex": rf"{prefix}Lot: (\w+)"},
        "extract_rules": {"fields": [
            {"key": "PLATTE", "regex": rf"{prefix}Plate: (\w+)"},
            {"key": "DATUM", "regex": r"Date: ([0-9-]+)"},
            {"key": "ZEIT", "regex": r"Time: ([0-9:]+)"},
            {"key": "TEST", "regex": r"Test: (\w+)"},
            {"key": "value", "regex": rf"{prefix}Value: (\w+)"},
        ]},
        "excel_rules": {"excel_filename_template": "{assay_name}.xlsx", "sheetname_template": "{lot_id}"},
    }


def _prepare(tmp_path, *, multiple=False):
    import fitz

    root = tmp_path / "project"
    (root / "rules").mkdir(parents=True)
    assays = [("(1111)", "Assay A", "a")]
    if multiple:
        assays.append(("(2222)", "Assay B", "b"))
    (root / "rules" / "index.json").write_text(json.dumps({"assays": [{"assay_key": key, "ruleset_file": f"{stem}.json"} for key, _, stem in assays]}), encoding="utf-8")
    lines = []
    for index, (key, name, stem) in enumerate(assays, 1):
        (root / "rules" / f"{stem}.json").write_text(json.dumps(_rule(key, name), indent=2), encoding="utf-8")
        lines.extend([name, key, f"OldLot: L{index}", f"NewLot: N{index}", f"OldPlate: P{index}", f"NewPlate: Q{index}",
                      "Date: 2026-11-11", "Time: 08:12:00", f"Test: T{index}", f"OldValue: old{index}", f"NewValue: new{index}"])
    pdf = root / "source.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), "\n".join(lines), fontsize=9)
        document.save(pdf)
    database = root / "results.sqlite"
    submitted = submit(str(pdf), str(root), sqlite_path=str(database), device_id="original-device")
    assert submitted.status == "DONE", submitted.details
    runs = [item["sqlite_run_id"] for item in submitted.details["writes"]]
    return root, pdf, database, submitted.job_id, runs


def _spec(path):
    return {"driver": "sqlite", "path": str(path)}


def _reanalyze(root, path, run, request="request", token=None):
    return reanalyze_run(root, _spec(path), run, expected_selection_token=token or get_result_run(_spec(path), run)["selection_token"],
                         request_id=request, operator_initials="RR")


def _inline(monkeypatch):
    # Most source-contract cases need no repeated process startup. Actual spawn,
    # parent-thread separation and process cleanup are tested separately below.
    monkeypatch.setattr(reanalysis, "_run_isolated", lambda pdf, source, ruleset, device:
                        reanalysis._extract_snapshot(source["current_pdf_path"], source, ruleset, device))


@pytest.mark.parametrize("legacy", [False, True])
def test_selected_second_assay_reextracts_current_rule_exact_source_and_original_device(tmp_path, monkeypatch, legacy):
    root, pdf, path, job, runs = _prepare(tmp_path, multiple=True)
    if legacy:
        with sqlite3.connect(path) as conn:
            # Build a genuine pre-P3b schema from the unchanged original table.
            columns = [row[1] for row in conn.execute("PRAGMA table_info(runs)")]
            rows = conn.execute("SELECT * FROM runs").fetchall()
            schema = conn.execute("SELECT sql FROM sqlite_master WHERE name='runs'").fetchone()[0]
        legacy_path = root / "legacy.sqlite"
        with sqlite3.connect(legacy_path) as conn:
            conn.execute(schema)
            conn.executemany(f"INSERT INTO runs VALUES ({','.join('?' for _ in columns)})", rows)
        path = legacy_path
    before_jobs = {str(file): (file.read_bytes(), file.stat().st_mtime_ns) for file in (root / "jobs").iterdir()}
    with sqlite3.connect(path) as conn:
        original_rows = conn.execute("SELECT * FROM runs ORDER BY id").fetchall()
    new_bytes = (json.dumps(_rule("(2222)", "Renamed current rule", updated=True), ensure_ascii=False, indent=3) + "\r\n").encode("utf-8")
    (root / "rules" / "b.json").write_bytes(new_bytes)
    _inline(monkeypatch)
    result = _reanalyze(root, path, runs[1])
    state = get_result_run(_spec(path), runs[1])
    candidate = state["pending_revision"]["result"]
    assert candidate["source_verified"] and not candidate["error"]
    assert candidate["payload"]["value"] == "new2"
    assert candidate["payload"]["PLATTE"] == "Q2" and candidate["lot_id"] == "N2"
    assert candidate["device_id"] == "original-device"
    assert "original-device|Q2|" in candidate["dedupe_key"]
    assert candidate["rule_source_text"].encode("utf-8") == new_bytes
    assert candidate["rule_sha256"] == hashlib.sha256(new_bytes).hexdigest()
    assert candidate["source_provenance"]["pdf_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert state["payload"]["value"] == "old2"
    assert get_result_run(_spec(path), runs[0])["payload"]["value"] == "old1"
    select_result_revision(str(path), runs[1], result["revision_id"], expected_selection_token=state["selection_token"],
                           action="accept_new", request_id="choose", decided_by="RR")
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT * FROM runs ORDER BY id").fetchall() == original_rows
    assert before_jobs == {str(file): (file.read_bytes(), file.stat().st_mtime_ns) for file in (root / "jobs").iterdir()}


def test_new_initial_processing_freezes_exact_rule_and_source_bounds(tmp_path):
    root, pdf, path, job, runs = _prepare(tmp_path)
    state = get_result_run(_spec(path), runs[0])
    source = state["source_provenance"]
    assert source["rule_source_text"].encode("utf-8") == (root / "rules" / "a.json").read_bytes()
    assert source["rule_sha256"] == hashlib.sha256((root / "rules" / "a.json").read_bytes()).hexdigest()
    normalized = (root / "jobs" / f"{job}_normalized.txt").read_text(encoding="utf-8")
    block = normalized[source["block_start"]:source["block_end"]]
    assert hashlib.sha256(block.encode()).hexdigest() == state["assay_block_hash"]
    assert source["pdf_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()


@pytest.mark.parametrize("problem", ["pdf_hash", "block_hash", "missing_device", "missing_pdf", "ambiguous_archive", "unknown_rule"])
def test_missing_or_conflicting_provenance_is_actionable_pending_rework(tmp_path, monkeypatch, problem):
    root, pdf, path, job, runs = _prepare(tmp_path)
    _inline(monkeypatch)
    if problem == "pdf_hash":
        pdf.write_bytes(b"different file")
    elif problem == "block_hash":
        with sqlite3.connect(path) as conn:
            conn.execute("UPDATE runs SET assay_block_hash=?", ("f"*64,))
    elif problem == "missing_device":
        with sqlite3.connect(path) as conn:
            conn.execute("UPDATE runs SET device_id='' ")
    elif problem == "missing_pdf":
        pdf.unlink()
    elif problem == "ambiguous_archive":
        monkeypatch.setattr(reanalysis, "resolve_current_path", lambda *_: SimpleNamespace(path_status="ambiguous"))
    elif problem == "unknown_rule":
        (root / "rules" / "index.json").write_text('{"assays":[]}', encoding="utf-8")
    result = _reanalyze(root, path, runs[0])
    state = get_result_run(_spec(path), runs[0])
    candidate = state["pending_revision"]["result"]
    assert candidate["error"] and not candidate["source_verified"]
    with pytest.raises(ResultRevisionError, match="Quelle"):
        select_result_revision(str(path), runs[0], result["revision_id"], expected_selection_token=state["selection_token"],
                               action="keep_old", request_id="choose", decided_by="RR")


def test_partial_optional_field_error_retains_whole_comparison(tmp_path, monkeypatch):
    root, _, path, _, runs = _prepare(tmp_path)
    _inline(monkeypatch)
    rule = _rule(updated=True)
    rule["extract_rules"]["fields"].append({"key": "optional", "regex": "NotPresent: (.+)", "required": False})
    (root / "rules" / "a.json").write_text(json.dumps(rule), encoding="utf-8")
    _reanalyze(root, path, runs[0])
    candidate = get_result_run(_spec(path), runs[0])["pending_revision"]["result"]
    assert candidate["source_verified"] and candidate["missing_fields"] == ["optional"]
    assert candidate["payload"]["value"] == "new1" and candidate["payload"]["optional"] is None
    assert candidate["error"] == "configured_fields_empty: optional"


def test_idempotent_request_uses_frozen_rule_and_rejects_reused_token(tmp_path, monkeypatch):
    root, _, path, _, runs = _prepare(tmp_path)
    _inline(monkeypatch)
    original_token = get_result_run(_spec(path), runs[0])["selection_token"]
    first = _reanalyze(root, path, runs[0], request="  request  ", token=original_token)
    monkeypatch.setattr(reanalysis, "_run_isolated", lambda *_: pytest.fail("repeat must not reparse"))
    (root / "rules" / "a.json").write_text("invalid changed rule", encoding="utf-8")
    assert _reanalyze(root, path, runs[0], token=original_token) == first
    with pytest.raises(ResultRevisionConflictError):
        _reanalyze(root, path, runs[0], token="another-screen")


def test_validation_during_expensive_extraction_prevents_candidate_publication(tmp_path, monkeypatch):
    root, _, path, _, runs = _prepare(tmp_path)
    def raced(pdf, source, ruleset, device):
        result = reanalysis._extract_snapshot(source["current_pdf_path"], source, ruleset, device)
        validate_run(_spec(path), runs[0], "VV", expected_selection_token="original:1")
        return result
    monkeypatch.setattr(reanalysis, "_run_isolated", raced)
    with pytest.raises(ResultRevisionConflictError, match="validiert"):
        _reanalyze(root, path, runs[0])
    assert get_result_run(_spec(path), runs[0])["result_revisions"] == []


def test_actual_spawn_from_background_keeps_parser_on_process_main_thread(tmp_path, monkeypatch):
    root, pdf, path, _, runs = _prepare(tmp_path)
    import src.parser.api as parser_api
    original_parse = parser_api.parse
    ui_thread = threading.get_ident()
    calls = []
    def parent_parse(pdf_path):
        assert threading.get_ident() == ui_thread, "background reanalysis must not use parent MuPDF"
        calls.append(pdf_path)
        return original_parse(pdf_path)
    monkeypatch.setattr(parser_api, "parse", parent_parse)
    outcomes = []
    thread = threading.Thread(target=lambda: outcomes.append(_reanalyze(root, path, runs[0])))
    thread.start()
    # A normal parse may run in the parent while the isolated reanalysis parses.
    parser_api.parse(str(pdf))
    thread.join(timeout=30)
    assert not thread.is_alive() and len(outcomes) == 1
    assert calls == [str(pdf)]
    candidate = get_result_run(_spec(path), runs[0])["pending_revision"]["result"]
    assert candidate["source_verified"] and not candidate["error"], candidate


@pytest.mark.parametrize("mode", ["timeout", "crash", "missing_result"])
def test_child_timeout_crash_cleanup_and_slot_release(tmp_path, monkeypatch, mode):
    class Process:
        exitcode = 1 if mode == "crash" else 0
        def __init__(self):
            self.alive = mode == "timeout"
            self.closed = False
            self.terminated = False
        def start(self): pass
        def join(self, timeout=None): pass
        def is_alive(self): return self.alive
        def terminate(self): self.terminated = True; self.alive = False
        def kill(self): self.alive = False
        def close(self): self.closed = True
    process = Process()
    monkeypatch.setattr(reanalysis.multiprocessing, "get_context", lambda method: SimpleNamespace(Process=lambda **_: process))
    original_temp = reanalysis.tempfile.TemporaryDirectory
    monkeypatch.setattr(reanalysis.tempfile, "TemporaryDirectory", lambda **kw: original_temp(dir=tmp_path, **kw))
    with pytest.raises(ResultRevisionError):
        reanalysis._run_isolated(b"pdf", {}, RuleSet("A", "A.json", {}), "D")
    assert process.closed and (mode != "timeout" or process.terminated)
    assert list(tmp_path.iterdir()) == []
    assert reanalysis._PROCESS_LOCK.acquire(blocking=False)
    reanalysis._PROCESS_LOCK.release()


def test_legacy_ambiguous_occurrence_and_block_mismatch_never_choose_first():
    source = {"assay_key": "A", "descriptors": [{"assay_key": "A", "assay_name": "Assay"}], "assay_block_hash": "f"*64}
    with pytest.raises(ResultRevisionError, match="Block"):
        reanalysis._proven_block("Assay\nA\nvalue", source)
    source["descriptors"] *= 2
    with pytest.raises(ResultRevisionError, match="mehrdeutig"):
        reanalysis._proven_block("Assay\nA\nvalue", source)


def test_failed_partial_new_job_blocks_public_reanalysis_selection_and_validation(tmp_path, monkeypatch):
    root, _, path, job, runs = _prepare(tmp_path, multiple=True)
    _inline(monkeypatch)
    revision = _reanalyze(root, path, runs[0])
    state_path = root / "jobs" / f"{job}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "FAILED"
    state["output_plan"]["assays"][1]["sqlite_status"] = "failed"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    token = get_result_run(_spec(path), runs[0])["selection_token"]
    with pytest.raises(ResultRevisionConflictError, match="abgeschlossen"):
        _reanalyze(root, path, runs[1])
    with pytest.raises(ResultRevisionConflictError, match="abgeschlossen"):
        select_result_revision(str(path), runs[0], revision["revision_id"], expected_selection_token=token,
                               action="accept_new", request_id="choose", decided_by="RR")
    with pytest.raises(ValidationStateConflictError, match="abgeschlossen"):
        validate_run(_spec(path), runs[1], "RR", expected_selection_token=f"original:{runs[1]}")


def test_terminal_job_change_during_child_rechecks_before_publication(tmp_path, monkeypatch):
    root, _, path, job, runs = _prepare(tmp_path)
    def raced(pdf, source, ruleset, device):
        candidate = reanalysis._extract_snapshot(source["current_pdf_path"], source, ruleset, device)
        state_path = root / "jobs" / f"{job}.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "FAILED"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return candidate
    monkeypatch.setattr(reanalysis, "_run_isolated", raced)
    with pytest.raises(ResultRevisionConflictError, match="abgeschlossen"):
        _reanalyze(root, path, runs[0])
    assert get_result_run(_spec(path), runs[0])["result_revisions"] == []


def test_queue_nonterminal_state_blocks_domain_actions(tmp_path, monkeypatch):
    root, _, path, job, runs = _prepare(tmp_path)
    monkeypatch.setattr("src.jobqueue.api.list_jobs", lambda *_, **__: [SimpleNamespace(job_id=job, status="FAILED")])
    with pytest.raises(ResultRevisionConflictError, match="DONE"):
        _reanalyze(root, path, runs[0])
    with pytest.raises(ValidationStateConflictError, match="DONE"):
        validate_run(_spec(path), runs[0], "RR")


def test_initial_submit_parses_verified_snapshot_and_rejects_live_replacement(tmp_path, monkeypatch):
    root, original, _, _, _ = _prepare(tmp_path)
    import src.parser.api as parser_api
    real_parse = parser_api.parse
    incoming = root / "incoming.pdf"
    # New PDF identity, so this exercises processing rather than already_done.
    incoming.write_bytes(original.read_bytes() + b"\n% new import")
    incoming_hash = hashlib.sha256(incoming.read_bytes()).hexdigest()
    observed = []
    def replacing_parse(snapshot_path):
        observed.append((snapshot_path, hashlib.sha256(Path(snapshot_path).read_bytes()).hexdigest()))
        assert Path(snapshot_path) != incoming
        incoming.write_bytes(b"replacement while parsing")
        return real_parse(snapshot_path)
    monkeypatch.setattr(parser_api, "parse", replacing_parse)
    target = root / "replacement.sqlite"
    result = submit(str(incoming), str(root), sqlite_path=str(target), device_id="original-device")
    assert result.status == "FAILED" and result.details["error"] == "source_pdf_changed_during_processing"
    assert observed[0][1] == incoming_hash and not Path(observed[0][0]).exists()
    assert not target.exists()


def test_genuine_second_assay_sink_failure_leaves_first_ineligible(tmp_path, monkeypatch):
    root, original, _, _, _ = _prepare(tmp_path, multiple=True)
    import src.dbwriter.api as writer_api
    real_write = writer_api.write_record_sqlite
    incoming = root / "partial.pdf"
    incoming.write_bytes(original.read_bytes() + b"\n% partial import")
    calls = []
    def fail_second(*args, **kwargs):
        calls.append(args[0].assay_key)
        if len(calls) == 2:
            raise RuntimeError("synthetic_second_sink_failure")
        return real_write(*args, **kwargs)
    monkeypatch.setattr(writer_api, "write_record_sqlite", fail_second)
    target = root / "partial.sqlite"
    result = submit(str(incoming), str(root), sqlite_path=str(target), device_id="original-device")
    assert result.status == "FAILED" and len(calls) == 2
    first = get_result_run(_spec(target), 1)
    assert first["source_provenance"]["project_root"] == str(root)
    assert get_result_run(_spec(target), 2) is None
    with pytest.raises(ResultRevisionConflictError, match="abgeschlossen"):
        _reanalyze(root, target, 1)
    with pytest.raises(ValidationStateConflictError, match="abgeschlossen"):
        validate_run(_spec(target), 1, "RR")
