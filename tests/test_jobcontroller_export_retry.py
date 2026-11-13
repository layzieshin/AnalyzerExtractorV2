import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.jobcontroller.api import get_job_diagnostic_sources, get_job_evidence, release_validated_run, retry_excel_export, submit
from src.jobcontroller.jobcontroller import JobController
from src.parser.model import ParsedDocument, ParsedPage


def _ruleset(assay_key: str, assay_name: str, filename: str) -> dict:
    return {
        "assay_name": assay_name,
        "assay_key": assay_key,
        "lot_rule": {"regex": r"Lot:\s*(\w+)"},
        "extract_rules": {
            "fields": [
                {"key": "plate_name", "regex": r"Plate:\s*(\w+)", "required": True},
                {"key": "test", "regex": r"Test:\s*(\w+)", "required": True},
                {"key": "date", "regex": r"Date:\s*([0-9\-]+)", "required": True},
                {"key": "time", "regex": r"Time:\s*([0-9:]+)", "required": True},
            ]
        },
        "excel_rules": {
            "excel_filename_template": filename,
            "sheetname_template": "{lot_id}",
            "column_mapping": {"test": "Test"},
        },
    }


def _write_project(root: Path, *, assays: list[tuple[str, str, str, str]]) -> None:
    (root / "rules").mkdir(parents=True)
    (root / "output" / "final").mkdir(parents=True)
    index = {
        "assays": [
            {"assay_key": assay_key, "ruleset_file": ruleset_file}
            for assay_key, _name, ruleset_file, _filename in assays
        ]
    }
    (root / "rules" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    for assay_key, assay_name, ruleset_file, filename in assays:
        (root / "rules" / ruleset_file).write_text(
            json.dumps(_ruleset(assay_key, assay_name, filename)),
            encoding="utf-8",
        )


def _lines(assay_name: str, assay_key: str, lot: str, plate: str, test: str) -> list[str]:
    return [
        assay_name,
        assay_key,
        f"Lot: {lot}",
        f"Plate: {plate}",
        f"Test: {test}",
        "Date: 2026-05-28",
        "Time: 12:00:00",
    ]


def _parse_one(pdf: Path) -> ParsedDocument:
    lines = _lines("Assay A", "(1111)", "LOTA", "PLATE1", "TESTX")
    return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})


def _parse_two(pdf: Path) -> ParsedDocument:
    lines = _lines("Assay A", "(1111)", "LOTA", "PLATE1", "TESTX") + _lines(
        "Assay B", "(2222)", "LOTB", "PLATE2", "TESTY"
    )
    return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})


def _state(root: Path, job_id: str) -> dict:
    return json.loads((root / "jobs" / f"{job_id}.json").read_text(encoding="utf-8"))


def _run_count(sqlite_path: Path) -> int:
    with sqlite3.connect(sqlite_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])


def _run_ids(sqlite_path: Path) -> list[int]:
    with sqlite3.connect(sqlite_path) as conn:
        return [int(row[0]) for row in conn.execute("SELECT id FROM runs ORDER BY id").fetchall()]


def _snapshot(path: Path) -> tuple[str, int]:
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def _forbid_excel(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    def forbidden(*_args, **_kwargs):
        calls.append("called")
        raise AssertionError("retired Excel writer must never be called")
    monkeypatch.setattr("src.writer.api.write_record", forbidden)
    monkeypatch.setattr("src.writer.api.update_validation_metadata", forbidden)
    return calls


@pytest.mark.parametrize("mode", [None, "sqlite", "both", "excel", " ExCeL "])
def test_every_new_submit_mode_persists_only_sqlite_without_touching_workbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str | None
) -> None:
    root = tmp_path / "proj"
    _write_project(root, assays=[("(1111)", "Assay A", "AssayA.json", "Existing.xlsx")])
    pdf = root / "input.pdf"
    pdf.write_bytes(b"sqlite-only")
    workbook = root / "output" / "final" / "Existing.xlsx"
    Workbook().save(workbook)
    before = _snapshot(workbook)
    calls = _forbid_excel(monkeypatch)
    monkeypatch.setattr("src.parser.api.parse", lambda path: _parse_one(Path(path)))
    sqlite_path = root / "output" / "final" / "res.sqlite3"
    real_sqlite = __import__("src.dbwriter.api", fromlist=["write_record_sqlite"]).write_record_sqlite

    def check_plan_before_sink(*args, **kwargs):
        planned = _state(root, kwargs["job_id"])
        assert planned["output_plan"]["version"] == 2
        assert planned["output_plan"]["output_mode"] == "sqlite"
        assert planned["output_plan"]["assays"][0]["sqlite_run_id"] is None
        assert planned["output_plan"]["sqlite_status"] == "pending"
        assert planned["excel_status"] == "not_required"
        assert planned["export_retry_available"] is False
        return real_sqlite(*args, **kwargs)

    monkeypatch.setattr("src.dbwriter.api.write_record_sqlite", check_plan_before_sink)
    kwargs = {} if mode is None else {"output_mode": mode}
    result = submit(str(pdf), str(root), sqlite_path=str(sqlite_path), device_id="dev1", **kwargs)
    assert result.status == "DONE"
    state = _state(root, result.job_id)
    plan = state["output_plan"]
    assert plan["output_mode"] == "sqlite"
    assert plan["sqlite_status"] == "success"
    assert "excel_output_dir" not in plan
    assert state["excel_status"] == "not_required"
    assert state["export_retry_available"] is False
    entry = plan["assays"][0]
    assert entry["excel_status"] == "not_required"
    assert entry["sqlite_run_id"] == _run_ids(sqlite_path)[0]
    assert {item["sink"] for item in result.details["writes"][0]["outputs"]} == {"sqlite"}
    state_path = root / "jobs" / f"{result.job_id}.json"
    frozen = _snapshot(state_path)
    assert release_validated_run(root, result.job_id, entry["sqlite_run_id"], operator_initials="AB",
                                 validated_at_utc="2026-11-12T10:00:00Z", validation_id=1).status == "SKIPPED"
    assert retry_excel_export(root, result.job_id).status == "SKIPPED"
    assert _snapshot(state_path) == frozen
    assert _snapshot(workbook) == before
    assert list(root.rglob("*.xlsx")) == [workbook]
    assert list(root.rglob("*.tmp")) == []
    assert list(root.rglob("*.lock")) == []
    assert calls == []


def test_unknown_submit_mode_fails_before_side_effects(tmp_path: Path) -> None:
    pdf = tmp_path / "input.pdf"
    pdf.write_bytes(b"pdf")
    root = tmp_path / "new-root"
    result = submit(str(pdf), str(root), output_mode="unknown")
    assert result.status == "FAILED"
    assert "invalid output_mode" in result.details["error"]
    assert not root.exists()


@pytest.mark.parametrize("payload", ["{broken", "[]"])
def test_unreadable_existing_job_evidence_is_never_overwritten(tmp_path: Path, monkeypatch, payload: str) -> None:
    root = tmp_path / "proj"
    (root / "jobs").mkdir(parents=True)
    pdf = root / "input.pdf"
    pdf.write_bytes(b"unreadable-state")
    job_id = hashlib.sha256(pdf.read_bytes()).hexdigest()[:16]
    path = root / "jobs" / f"{job_id}.json"
    path.write_text(payload, encoding="utf-8")
    before = _snapshot(path)
    calls = _forbid_excel(monkeypatch)
    monkeypatch.setattr("src.parser.api.parse", lambda *_a, **_k: pytest.fail("no overwrite/re-extraction"))
    result = submit(str(pdf), str(root))
    assert result.status == "FAILED"
    assert result.details["error"] == "job_state_unreadable"
    assert _snapshot(path) == before
    assert not (root / "locks").exists()
    assert calls == []


@pytest.mark.parametrize("plan", [
    {"version": 2, "output_mode": "both", "sqlite_status": "success", "assays": []},
    {"version": 2, "output_mode": "excel", "assays": []},
    {"output_mode": "both", "assays": []},
    {"version": 99, "output_mode": "sqlite", "assays": []},
    None,
])
@pytest.mark.parametrize("status", ["DONE", "FAILED"])
def test_historical_plans_are_diagnostic_only_and_never_migrated_or_resumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: dict | None, status: str
) -> None:
    from src.application.api import create_desktop_services

    root = tmp_path / "proj"
    (root / "jobs").mkdir(parents=True)
    (root / "output" / "final").mkdir(parents=True)
    pdf = root / "original.pdf"
    pdf.write_bytes(b"historic")
    job_id = hashlib.sha256(pdf.read_bytes()).hexdigest()[:16]
    dump = root / "jobs" / f"{job_id}_normalized.txt"
    dump.write_text("historical diagnostic text", encoding="utf-8")
    state = {"job_id": job_id, "pdf_path": str(pdf), "status": status,
             "error": "excel_write_failed_after_save:(1111):old",
             "excel_status": "failed", "sqlite_status": "success", "structured_status": "success",
             "export_retry_available": True, "steps": [{"normalized_dump": str(dump)}]}
    if plan is not None:
        state["output_plan"] = plan
    state_path = root / "jobs" / f"{job_id}.json"
    state_path.write_text(json.dumps(state, indent=3), encoding="utf-8")
    workbook = root / "output" / "final" / "Existing.xlsx"
    Workbook().save(workbook)
    before = {path: _snapshot(path) for path in (state_path, workbook, dump)}
    file_inventory = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    calls = _forbid_excel(monkeypatch)
    monkeypatch.setattr("src.parser.api.parse", lambda *_a, **_k: pytest.fail("historical plan must not re-extract"))
    monkeypatch.setattr("src.dbwriter.api.write_record_sqlite", lambda *_a, **_k: pytest.fail("historical plan must not write SQLite"))
    evidence = get_job_evidence(root, job_id)
    assert evidence is not None and evidence.state_available
    assert evidence.error == state["error"]
    assert evidence.status == status
    assert evidence.context_text == "historical diagnostic text"
    assert evidence.retry_kind == "retired"
    assert get_job_diagnostic_sources(root, job_id).normalized_text == "historical diagnostic text"
    release = release_validated_run(root, job_id, 1, operator_initials="AB",
                                    validated_at_utc="2026-11-12T10:00:00Z", validation_id=1)
    retry = retry_excel_export(root, job_id)
    assert release.status == retry.status == "SKIPPED"
    assert release.details["reason"] == retry.details["reason"] == "excel_export_retired"
    outcome = create_desktop_services(root).extraction.retry_excel_export(job_id)
    assert outcome.processed is False
    assert outcome.submit_status == "SKIPPED"
    submitted = submit(str(pdf), str(root), output_mode="both")
    assert submitted.status == ("SKIPPED" if status == "DONE" else "FAILED")
    if status == "FAILED":
        assert submitted.details["error"] == "historical_output_plan_read_only"
    assert {path: _snapshot(path) for path in before} == before
    assert {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()} == file_inventory
    assert not (root / "locks").exists()
    assert calls == []


def test_retired_export_calls_do_not_even_create_an_app_root(tmp_path: Path) -> None:
    root = tmp_path / "absent"
    assert retry_excel_export(root, "../invalid").details["reason"] == "excel_export_retired"
    assert release_validated_run(root, "../invalid", 1, operator_initials="AB",
                                 validated_at_utc="now", validation_id=1).details["reason"] == "excel_export_retired"
    assert not root.exists()


@pytest.mark.parametrize("path,bad_value", [
    (("sqlite_path",), None), (("sqlite_path",), 123),
    (("sqlite_status",), None), (("sqlite_status",), []),
    (("assays",), None), (("assays",), "CORRUPT"), (("assays",), []),
    (("assays", 0), "CORRUPT"),
    (("assays", 0, "assay_record"), None), (("assays", 0, "assay_record"), []),
    (("assays", 0, "assay_record", "data"), None), (("assays", 0, "assay_record", "data"), "CORRUPT"),
    (("assays", 0, "ruleset"), None), (("assays", 0, "ruleset", "excel_rules"), []),
    (("assays", 0, "sqlite_run_id"), None), (("assays", 0, "sqlite_run_id"), "1"),
    (("assays", 0, "structured_status"), None), (("assays", 0, "structured_status"), []),
    (("assays", 0, "write_item"), None), (("assays", 0, "write_item"), "CORRUPT"),
    (("assays", 0, "write_item", "data"), None), (("assays", 0, "write_item", "data"), []),
    (("assays", 0, "write_item", "outputs"), None), (("assays", 0, "write_item", "outputs"), {}),
    (("assays", 0, "write_item", "outputs"), []),
    (("assays", 0, "write_item", "outputs", 0), "CORRUPT"),
    (("assays", 0, "write_item", "outputs", 0, "sink"), "excel"),
    (("assays", 0, "write_item", "outputs", 0, "run_id"), None),
    (("assays", 0, "write_item", "outputs", 0, "run_id"), True),
    (("assays", 0, "write_item", "duplicate_candidate_id"), None),
    (("assays", 0, "write_item", "existing_run_id"), "1"),
    (("assays", 0, "write_item", "missing_required"), [123]),
])
def test_corrupt_sqlite_plans_are_read_only_for_submit_evidence_and_retry(
    tmp_path: Path, monkeypatch, path: tuple, bad_value
) -> None:
    from src.jobqueue.api import claim_next_job, enqueue_pdf_job, mark_job_failed
    from src.processing.api import retry_failed

    root = tmp_path / "proj"
    _write_project(root, assays=[("(1111)", "Assay A", "AssayA.json", "Unused.xlsx")])
    pdf = root / "input.pdf"
    pdf.write_bytes(b"corrupt-sqlite-plan")
    monkeypatch.setattr("src.parser.api.parse", lambda item: _parse_one(Path(item)))
    sqlite_path = root / "output" / "final" / "res.sqlite3"
    seeded = submit(str(pdf), str(root), sqlite_path=str(sqlite_path), device_id="dev1")
    assert seeded.status == "DONE"
    state_path = root / "jobs" / f"{seeded.job_id}.json"
    state = _state(root, seeded.job_id)
    state["status"] = "FAILED"
    state["error"] = "sqlite_write_failed:interrupted"
    target = state["output_plan"]
    for key in path[:-1]:
        target = target[key]
    if bad_value is None:
        del target[path[-1]]
    else:
        target[path[-1]] = bad_value
    state_path.write_text(json.dumps(state, indent=3), encoding="utf-8")
    job = enqueue_pdf_job(str(root), str(pdf), source="manual")
    assert claim_next_job(str(root), "w") is not None
    mark_job_failed(str(root), job.job_id, "interrupted", worker_id="w")
    queue_path = root / "jobs" / "queue" / f"{job.job_id}.json"
    before = {item: _snapshot(item) for item in (state_path, sqlite_path, queue_path)}
    calls = _forbid_excel(monkeypatch)
    def forbidden(*_args, **_kwargs):
        calls.append("parser_or_sqlite")
        pytest.fail("corrupt plans must not parse or write any sink")
    monkeypatch.setattr("src.parser.api.parse", forbidden)
    monkeypatch.setattr("src.dbwriter.api.write_record_sqlite", forbidden)

    evidence = get_job_evidence(root, job.job_id)
    assert evidence.state_available and evidence.retry_kind == "retired"
    result = submit(str(pdf), str(root))
    assert result.status == "FAILED"
    assert result.details["error"] == "historical_output_plan_read_only"
    with pytest.raises(ValueError, match="historical_output_plan_read_only"):
        retry_failed(root, job.job_id)
    assert {item: _snapshot(item) for item in before} == before
    assert calls == []
    assert not list((root / "locks").glob("*.lock"))


def test_historical_plan_in_queue_fails_once_without_retry_or_completion(tmp_path: Path, monkeypatch) -> None:
    from src.processing.api import ProcessingConfig, enqueue_pdf, process_next_pending, retry_failed

    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "old.pdf"
    pdf.write_bytes(b"historical-queued")
    job = enqueue_pdf(root, str(pdf), source="manual")
    path = root / "jobs" / f"{job.job_id}.json"
    path.write_text(json.dumps({"job_id": job.job_id, "status": "FAILED", "sqlite_status": "success",
                                "excel_status": "failed", "output_plan": {"version": 2, "output_mode": "both"}}), encoding="utf-8")
    before = _snapshot(path)
    _forbid_excel(monkeypatch)
    monkeypatch.setattr("src.parser.api.parse", lambda *_a, **_k: pytest.fail("no extraction retry"))
    result = process_next_pending(root, ProcessingConfig(), worker_id="w")
    assert result.queue_status == "FAILED"
    assert result.message == "historical_output_plan_read_only"
    assert process_next_pending(root, ProcessingConfig(), worker_id="w").processed is False
    with pytest.raises(ValueError, match="historical_output_plan_read_only"):
        retry_failed(root, job.job_id)
    assert _snapshot(path) == before


def test_sqlite_failure_remains_retryable_and_never_enables_excel(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    _write_project(root, assays=[("(1111)", "Assay A", "AssayA.json", "Unused.xlsx")])
    pdf = root / "input.pdf"
    pdf.write_bytes(b"sqlite-failure")
    sqlite_path = root / "output" / "final" / "res.sqlite3"
    calls = _forbid_excel(monkeypatch)
    monkeypatch.setattr("src.parser.api.parse", lambda path: _parse_one(Path(path)))
    real_sqlite = __import__("src.dbwriter.api", fromlist=["write_record_sqlite"]).write_record_sqlite
    monkeypatch.setattr("src.dbwriter.api.write_record_sqlite", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("locked")))
    failed = submit(str(pdf), str(root), output_mode="both", sqlite_path=str(sqlite_path))
    assert failed.status == "FAILED"
    state = _state(root, failed.job_id)
    assert state["sqlite_status"] == "failed"
    assert state["excel_status"] == "not_required"
    assert state["export_retry_available"] is False
    assert get_job_evidence(root, failed.job_id).retry_kind == ""
    monkeypatch.setattr("src.dbwriter.api.write_record_sqlite", real_sqlite)
    resumed = submit(str(pdf), str(root), output_mode="excel", sqlite_path=str(sqlite_path))
    assert resumed.status == "DONE"
    assert _run_count(sqlite_path) == 1
    assert calls == []


def test_multi_assay_sqlite_commit_before_state_save_resumes_without_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proj"
    _write_project(
        root,
        assays=[
            ("(1111)", "Assay A", "AssayA.json", "A.xlsx"),
            ("(2222)", "Assay B", "AssayB.json", "B.xlsx"),
        ],
    )
    pdf = root / "sqlite-crash.pdf"
    pdf.write_bytes(b"sqlite-crash")
    sqlite_path = root / "output" / "final" / "res.sqlite3"
    monkeypatch.setattr("src.parser.api.parse", lambda path: _parse_two(Path(path)))
    original_save = JobController._save_state
    crashed = {"done": False}

    def abort_after_first_commit(self, path, state):
        plan = state.get("output_plan") if isinstance(state, dict) else None
        assays = plan.get("assays") if isinstance(plan, dict) else None
        if (
            not crashed["done"]
            and sqlite_path.exists()
            and _run_count(sqlite_path) == 1
            and isinstance(assays, list)
            and assays[0].get("sqlite_status") == "success"
        ):
            crashed["done"] = True
            raise SystemExit(17)
        return original_save(self, path, state)

    monkeypatch.setattr(JobController, "_save_state", abort_after_first_commit)
    with pytest.raises(SystemExit):
        submit(str(pdf), str(root), output_mode="both", sqlite_path=str(sqlite_path), device_id="dev1")
    persisted = _state(root, next((root / "jobs").glob("*.json")).stem)
    assert persisted["output_plan"]["assays"][0]["sqlite_status"] == "pending"
    assert persisted["output_plan"]["assays"][0]["sqlite_run_id"] is None
    assert _run_count(sqlite_path) == 1

    monkeypatch.setattr(JobController, "_save_state", original_save)
    resumed = submit(str(pdf), str(root), output_mode="both", sqlite_path=str(sqlite_path), device_id="dev1")
    assert resumed.status == "DONE"
    state = _state(root, resumed.job_id)
    entries = state["output_plan"]["assays"]
    assert [entry["sqlite_status"] for entry in entries] == ["success", "success"]
    assert all(entry["sqlite_run_id"] for entry in entries)
    assert entries[0]["write_item"]["outputs"][0]["status"] == "already_persisted"
    assert _run_count(sqlite_path) == 2
    with sqlite3.connect(sqlite_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM duplicate_candidates").fetchone()[0] == 0
