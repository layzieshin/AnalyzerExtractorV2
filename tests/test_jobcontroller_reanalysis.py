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
    from src.dbwriter.api import confirm_report_device
    from src.resultstore.api import get_report_device_context
    from src.qualitycontrol.api import ConfigurationContext, save_inventory
    root, _, path, job, runs = _prepare(tmp_path)
    save_inventory(_spec(path), {"default_device_id": "original-device", "devices": [
        {"device_id": "original-device", "display_name": "QA Gerät"}]}, expected_version_id=0, context=ConfigurationContext("inventory"))
    context = get_report_device_context(_spec(path), job)
    assigned = confirm_report_device(str(path), job, "original-device", expected_context_token=context["context_token"],
        request_id="assignment", actor="VV", project_root=str(root))
    def raced(pdf, source, ruleset, device):
        result = reanalysis._extract_snapshot(source["current_pdf_path"], source, ruleset, device)
        validate_run(_spec(path), runs[0], "VV", expected_selection_token="original:1", expected_device_assignment_id=assigned["assignment_id"])
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


def test_original_reports_keep_device_identity_through_materialization_reanalysis_and_revalidation(tmp_path):
    """Two unchanged original rules; every value and PDF is synthetic QA data."""
    import shutil
    import fitz
    from src.dbwriter.api import confirm_report_device, write_record_sqlite
    from src.extractor.api import AssayRecord
    from src.qualitycontrol.api import (ConfigurationContext, save_inventory, save_profile,
        get_lot_sources, get_lot_chronology, analyze_lot, MutationContext, QCConfigurationError, open_lot, close_lot)
    from src.application.api import DesktopSettings, ResultsController, QualityControlApplicationError
    from src.resultstore.api import (get_report_device_context, get_report_runs,
        list_pending_report_candidates, list_result_runs)

    root = tmp_path / 'original-reports'
    root.mkdir()
    shutil.copytree(Path(__file__).parents[1] / 'rules', root / 'rules')
    path = root / 'results.sqlite'
    spec = _spec(path)
    inventory = save_inventory(spec, {'default_device_id': 'A', 'devices': [
        {'device_id': value, 'display_name': 'QA Gerät ' + value} for value in ('A', 'B', 'C')]},
        expected_version_id=0, context=ConfigurationContext('inventory'))
    profile = save_profile(spec, {'profile_schema_version': 2, 'profile_id': 'ana', 'name': 'ANA QA',
        'assay_key': '(1c9e)', 'unit': 'QA-Skala',
        'controls': [{'control_id': 'positive', 'name': 'Positiv', 'fields': {'IST': 'PCS1_IST'}}]},
        expected_version_id=0, expected_inventory_version_id=inventory['version_id'], context=ConfigurationContext('profile'))

    def report(label, *, day='14.11.2026', lot='EQA77', value='101', dfs_plate='QA77'):
        pdf = root / (label + '.pdf')
        with fitz.open() as document:
            for name, key in (('ANA Screen IgG', '(1c9e)'), ('Anti-DFS70 IgG', '(0437)')):
                lines = [name, f'Test: C:\\QA\\{name}.asy {key}', 'Anwender: ' + label,
                    'Datum: ' + day, 'Plattenname: QA77 Zeit: 08:05:00', f'Kit {lot} 271130',
                    'C1 1,5 O.D. 0,5 O.D.', 'PCS1 100 Ziel 90 - 110', 'NCS1 20 Ziel 15 - 25',
                    'Validationskriterien erfüllt'] + ['QA FUELLZEILE'] * 33
                lines[36], lines[39], lines[42] = 'C1 1,51', 'PCS1 ' + value, 'NCS1 19'
                lines[35] = 'QA lot correction: EQA77'
                if key == '(0437)':
                    lines[4] = f'Plattenname: {dfs_plate} Zeit: 08:05:00'
                page = document.new_page()
                for index, line in enumerate(lines):
                    page.insert_text((36, 44 + 15 * index), line, fontsize=10)
            document.save(pdf)
        result = submit(str(pdf), str(root), sqlite_path=str(path), device_id='DEFAULT_DEVICE')
        assert result.status == 'DONE', result.details
        return result

    def confirm(result, device, request, *, reason=''):
        context = get_report_device_context(spec, result.job_id)
        return confirm_report_device(str(path), result.job_id, device,
            expected_context_token=context['context_token'], request_id=request, actor='QA', reason=reason, project_root=str(root))

    a, b = report('QAA'), report('QAB', value='103')
    assert len(list_result_runs(spec, limit=None)['runs']) == 2
    assert len(list_pending_report_candidates(spec)) == 2
    pending_report = get_report_runs(spec, b.job_id)
    assert pending_report['runs'] == [] and pending_report['pending_candidate_count'] == 2
    # Both whole reports have source proof, but an unconfirmed comparison is
    # never assumed to be a physically different device.
    stale_b = get_report_device_context(spec, b.job_id)
    assert all(not comparison['device_id'] for comparison in stale_b['comparisons'])
    first = confirm(a, 'A', 'a')
    with pytest.raises(ResultRevisionConflictError, match='geändert'):
        confirm_report_device(str(path), b.job_id, 'B', expected_context_token=stale_b['context_token'],
            request_id='stale', actor='QA', project_root=str(root))
    second = confirm(b, 'B', 'b')
    assert len(first['runs']) == len(second['runs']) == 2 and not second['candidates']
    # D still compares raw owner A; B already owns its confirmed identity.
    # Preserve D as a same-device duplicate and permit an independent assay
    # in a mixed third source report without adding another ANA measurement.
    duplicate = report('QAB_DUP', value='119')
    duplicate_context = confirm(duplicate, 'B', 'b-duplicate')
    assert duplicate_context['assignment_id'] and len(duplicate_context['candidates']) == 2 and not duplicate_context['runs']
    mixed = report('QAB_MIXED', value='119', dfs_plate='QA88')
    mixed_context = confirm(mixed, 'B', 'b-mixed')
    assert len(mixed_context['runs']) == 1 and len(mixed_context['candidates']) == 1
    assert mixed_context['runs'][0]['assay_key'] == '(0437)'
    assert len(list_result_runs(spec, limit=None)['runs']) == 5
    original_jobs = {file.name: file.read_bytes() for file in (root / 'jobs').iterdir() if file.is_file()}
    ana_b = next(row for row in second['runs'] if row['assay_key'] == '(1c9e)')
    ana_a = next(row for row in first['runs'] if row['assay_key'] == '(1c9e)')
    original_key = ana_a['dedupe_key']
    # A current-rule reanalysis of B may keep A's raw import key. A remains its
    # raw owner, while B keeps its separate confirmed semantic/device claim.
    rule_path = root / 'rules' / 'ANA Screen IgG.json'
    current_rule = json.loads(rule_path.read_text(encoding='utf-8'))
    rule_path.write_text(json.dumps(current_rule, ensure_ascii=False, indent=4), encoding='utf-8')
    revision = _reanalyze(root, path, ana_b['id'], request='b-reanalysis')
    state = get_result_run(spec, ana_b['id'])
    assert not state['pending_revision']['result']['error']
    assert state['pending_revision']['result']['dedupe_key'] == original_key
    _choose = lambda revision, request: select_result_revision(str(path), ana_b['id'], revision,
        expected_selection_token=get_result_run(spec, ana_b['id'])['selection_token'], action='accept_new', request_id=request, decided_by='QA')
    _choose(revision['revision_id'], 'b-choose')
    for field in current_rule['extract_rules']['fields']:
        if field['key'] == 'PLATTE':
            field['regex'] = field['regex'].replace('(.+?)', 'QA(.+?)')
    rule_path.write_text(json.dumps(current_rule, ensure_ascii=False), encoding='utf-8')
    revised = _reanalyze(root, path, ana_b['id'], request='b-new-identity')
    _choose(revised['revision_id'], 'b-new-choice')
    assert get_result_run(spec, ana_b['id'])['payload']['PLATTE'] == '77'
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT id FROM runs WHERE dedupe_key=?', (original_key,)).fetchone()[0] == ana_a['id']
        assert not conn.execute('SELECT run_id FROM run_identity_aliases WHERE dedupe_key=?', (original_key,)).fetchall()
    for row in list_result_runs(spec, limit=None)['runs']:
        validate_run(spec, row['id'], 'QA', expected_selection_token=row['selection_token'],
            expected_device_assignment_id=row['device_assignment_id'], project_root=str(root), request_id='v' + str(row['id']))
    for device, expected in (('A', '101'), ('B', '103')):
        source = get_lot_sources(spec, profile_version_id=profile['version_id'], kit_lot='EQA77', device_id=device)
        descriptive = analyze_lot(source, {}).to_dict()['computed_series'][0]['descriptive']
        assert descriptive['n'] == 1 and descriptive['mean']['value'] == expected
    # Correction appends whole-report membership and invalidates both existing
    # human bindings. A stale preview cannot silently validate the new device.
    old_row = get_result_run(spec, ana_b['id'])
    corrected = confirm(b, 'C', 'b-correction', reason='Synthetische Geräteberichtigung')
    assert corrected['assignment_id'] != second['assignment_id']
    with pytest.raises(ValidationStateConflictError, match='Gerät'):
        validate_run(spec, ana_b['id'], 'QA', expected_selection_token=old_row['selection_token'],
            expected_device_assignment_id=old_row['device_assignment_id'], project_root=str(root), request_id='stale-validation')
    assert get_lot_sources(spec, profile_version_id=profile['version_id'], kit_lot='EQA77', device_id='C')['included_count'] == 0
    for row in corrected['runs']:
        new = validate_run(spec, row['id'], 'QA', expected_selection_token=row['selection_token'],
            expected_device_assignment_id=corrected['assignment_id'], project_root=str(root), request_id='new-v' + str(row['id']))
        assert new.validation_kind == 'revalidation' and new.supersedes_validation_id
    assert get_lot_sources(spec, profile_version_id=profile['version_id'], kit_lot='EQA77', device_id='C')['included_count'] == 1
    assert original_jobs == {file.name: file.read_bytes() for file in (root / 'jobs').iterdir() if file.is_file()}
    # Restore only this temporary catalog, then prove chronology: an assigned
    # but unvalidated later report is a usage witness, not a QC measurement.
    shutil.copyfile(Path(__file__).parents[1] / 'rules' / rule_path.name, rule_path)
    later = report('QALATER', day='15.11.2026', lot='EQA78')
    confirm(later, 'A', 'later')
    def chronology():
        return get_lot_chronology(spec, profile_version_id=profile['version_id'], device_id='A').to_dict()
    assert next(lot for lot in chronology()['lots'] if lot['kit_lot'] == 'EQA77')['close_available']
    controller = ResultsController(root, settings_provider=lambda: DesktopSettings('sqlite', str(path)))
    a_source = get_lot_sources(spec, profile_version_id=profile['version_id'], kit_lot='EQA77', device_id='A')
    opened_a = open_lot(spec, profile_version_id=profile['version_id'], kit_lot='EQA77', device_id='A',
        expected_source_token=a_source['source_token'], context=MutationContext('QA', 'open-a'))
    a_case = next(case for case in controller.list_qc_lots() if case.device_id == 'A' and case.kit_lot == 'EQA77' and case.assay_key == '(1c9e)')
    prepared_a = controller.prepare_qc_lot_close(controller.get_qc_lot_detail(a_case))
    # An unknown-device run may have another selected and pending lot. It
    # creates no empty-device UI case, while both possible lots stay relevant.
    unknown_lot = report('QAPENDING_LOT', day='16.11.2026', lot='EQA79')
    unknown_run = next(row for row in get_report_runs(spec, unknown_lot.job_id)['runs'] if row['assay_key'] == '(1c9e)')
    correction_rule = json.loads(rule_path.read_text(encoding='utf-8'))
    correction_rule['lot_rule']['regex'] = r'QA lot correction: (EQA77)'
    rule_path.write_text(json.dumps(correction_rule, ensure_ascii=False), encoding='utf-8')
    pending_lot_revision = _reanalyze(root, path, unknown_run['id'], request='unknown-device-pending-lot')
    pending_state = get_result_run(spec, unknown_run['id'])
    assert not pending_state['pending_revision']['result']['error']
    assert pending_state['pending_revision']['result']['lot_id'] == 'EQA77' and pending_state['lot_id'] == 'EQA79'
    assert controller.list_qc_lots() and all(case.device_id for case in controller.list_qc_lots())
    current_usage = get_lot_chronology(spec, profile_version_id=profile['version_id'], device_id='A')
    uncertain_a = next(lot for lot in current_usage.to_dict()['lots'] if lot['kit_lot'] == 'EQA77')
    assert not uncertain_a['close_available'] and not uncertain_a['last_usage_reliable'] and not uncertain_a['witnesses']
    database_before = path.read_bytes(), path.stat().st_mtime_ns
    with pytest.raises(QualityControlApplicationError):
        controller.prepare_qc_lot_close(controller.get_qc_lot_detail(a_case))
    # Supply the *current* chronology token, not merely a stale preview. The
    # authoritative writer must independently reject this ambiguous usage.
    model_a = json.loads(prepared_a.analysis.model_json)
    with pytest.raises(QCConfigurationError, match='Nutzungsverlauf'):
        close_lot(spec, opened_a['lot_key'], expected_version_id=opened_a['version_id'],
            profile_version_id=profile['version_id'], expected_source_token=a_source['source_token'],
            witness_kit_lot=prepared_a.witness_kit_lot, expected_witness_source_token=prepared_a.witness_source_token,
            expected_chronology_token=current_usage.snapshot_sha256, analysis_model=model_a,
            pdf_bytes=prepared_a.pdf_bytes, pdf_sha256=prepared_a.pdf_sha256,
            algorithm_id=model_a['algorithm_id'], renderer_id=prepared_a.renderer_id, context=MutationContext('QA', 'reject-ambiguous-close'))
    assert (path.read_bytes(), path.stat().st_mtime_ns) == database_before
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM qc_lot_versions').fetchone()[0] == 1
        assert conn.execute('SELECT COUNT(*) FROM qc_report_evidence').fetchone()[0] == 0
    select_result_revision(str(path), unknown_run['id'], pending_lot_revision['revision_id'],
        expected_selection_token=pending_state['selection_token'], action='keep_old', request_id='unknown-keep-old', decided_by='QA')
    assert next(lot for lot in chronology()['lots'] if lot['kit_lot'] == 'EQA77')['close_available']
    shutil.copyfile(Path(__file__).parents[1] / 'rules' / rule_path.name, rule_path)
    unresolved = report('QAUNKNOWN', value='105')
    uncertain = next(lot for lot in chronology()['lots'] if lot['kit_lot'] == 'EQA77')
    assert not uncertain['close_available'] and 'duplicate_source_unresolved' in uncertain['reasons']
    # Same-device duplicate stays a clarification case on A; it must not make
    # C's unrelated confirmed population uncertain merely by sharing an assay.
    confirm(unresolved, 'A', 'same-device')
    c_later = report('QAC_LATER', day='17.11.2026', lot='EQA80')
    confirm(c_later, 'C', 'c-later')
    c_usage = get_lot_chronology(spec, profile_version_id=profile['version_id'], device_id='C').to_dict()
    assert next(lot for lot in c_usage['lots'] if lot['kit_lot'] == 'EQA77')['close_available']
    c_case = next(case for case in controller.list_qc_lots() if case.device_id == 'C' and case.kit_lot == 'EQA77' and case.assay_key == '(1c9e)')
    c_preview = controller.prepare_qc_lot_close(controller.get_qc_lot_detail(c_case))
    closed_c = controller.close_qc_lot(c_preview, operator_initials='QA', request_id='unrelated-device-close')
    assert closed_c['state'] == 'closed'
    foreign = write_record_sqlite(AssayRecord('OTHER', 'EQA77', 'foreign', {'DATUM': '14.11.2026'}, 'DEFAULT_DEVICE'),
        RuleSet('OTHER', 'OTHER.json', {}), str(path), job_id='foreign').run_id
    assert foreign
    c_usage = get_lot_chronology(spec, profile_version_id=profile['version_id'], device_id='C').to_dict()
    assert next(lot for lot in c_usage['lots'] if lot['kit_lot'] == 'EQA77')['close_available']
    retry = submit(str(root / 'QAA.pdf'), str(root), sqlite_path=str(path), device_id='DEFAULT_DEVICE')
    assert retry.status == 'SKIPPED'
