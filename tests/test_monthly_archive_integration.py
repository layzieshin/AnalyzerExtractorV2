"""Actual synthetic PDF -> pipeline -> SQLite -> validation -> monthly archive."""
import json
import sqlite3

import fitz
import pytest

from src.application.api import DesktopSettings, ExtractionController, ResultsController


def _flow(root, *, validate=True, combined=True, header_aliases=False):
    incoming = root / "Result"
    incoming.mkdir()
    rules = root / "rules"
    rules.mkdir()
    fields = [
        {"key": "PLATTE", "regex": r"Plattenname:\s*(\S+)", "required": True},
        {"key": "DATUM", "regex": r"Datum:\s*(\d{2}\.\d{2}\.\d{4})", "required": True},
        {"key": "ZEIT", "regex": r"Zeit:\s*(\d{2}:\d{2}:\d{2})", "required": True},
        {"key": "TEST", "regex": r"Test:\s*([^\n]+)", "required": True},
        {"key": "value", "regex": r"Value:\s*(\S+)", "required": True},
    ]
    if header_aliases:
        fields = [{**field, "key": {"PLATTE": "plate_name", "DATUM": "date"}.get(field["key"], field["key"])} for field in fields]
    rows = []
    for letter, key in zip("ABCD", ("1111", "2222", "3333", "4444")):
        name = f"Assay {letter}"
        filename = f"Assay{letter}.json"
        data = {"assay_name": name, "assay_key": f"({key})", "lot_rule": {"regex": r"Lot:\s*(\S+)"},
                "extract_rules": {"fields": fields},
                "excel_rules": {"excel_filename_template": "{assay_name}.xlsx", "sheetname_template": "{lot_id}",
                                "column_mapping": {row["key"]: row["key"] for row in fields}}}
        (rules / filename).write_text(json.dumps(data), encoding="utf-8")
        rows.append({"assay_key": f"({key})", "ruleset_file": filename})
    (rules / "index.json").write_text(json.dumps({"version": "1.0", "assays": rows}), encoding="utf-8")
    def block(letter, key):
        return "\n".join((f"Assay {letter}", "Plattenname: 20261125_Plate Zeit: 12:34:56",
            "Anwender: TEST Datum: 25.11.2026", rf"Test: C:\Assays\Assay {letter}.asy ({key})", "Lot: SYNTHETIC", f"Value: {letter}.5"))
    batches = [("unrelated filename.pdf", block("A", "1111")), ("another.pdf", block("B", "2222"))]
    if combined:
        batches.append(("combined.pdf", block("C", "3333") + "\n" + block("D", "4444")))
    paths = []
    for filename, text in batches:
        path = incoming / filename
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((40, 40), text)
            document.save(path)
        paths.append(path)
    res = incoming / "20261125_plate.RES"
    res.write_bytes(b"synthetic RES, do not interpret contents")
    store = root / "results.sqlite3"
    settings = DesktopSettings("sqlite", str(store), watch_input_path=str(incoming), watch_backup_path=str(incoming))
    extraction = ExtractionController(root, settings_provider=lambda: settings)
    assert extraction.enqueue_manual_pdfs(tuple(str(path) for path in paths)).queued == len(paths)
    for _ in paths:
        result = extraction.process_next()
        assert result.submit_status == result.queue_status == "DONE", result.message
    results = ResultsController(root, settings_provider=lambda: settings)
    cases = results.list_open_validation_cases()
    assert len(cases) == (4 if combined else 2)
    if validate:
        for case in cases:
            results.validate_report_run(case.report_id, case.run_id, "MK", expected_selection_token=case.selection_token,
                                        store_path=str(store))
    return incoming, store, results, paths, res


def test_real_three_pdf_four_result_plate_previews_without_writes_and_archives(tmp_path):
    incoming, store, results, paths, res = _flow(tmp_path)
    before_db = store.read_bytes()
    before_jobs = {path: path.read_bytes() for path in (tmp_path / "jobs").glob("*.json")}
    plan = results.preview_monthly_archive(cutoff="2026-11-25")
    assert len(plan.groups) == 1 and plan.groups[0].eligible, plan.groups[0].reasons
    assert not (tmp_path / "storage/ingestion/monthly").exists()
    assert store.read_bytes() == before_db
    archived = results.commit_monthly_archive(plan)
    assert archived[0]["status"] == "complete"
    assert all(not path.exists() and (incoming / "2026/11_November" / path.name).is_file() for path in paths)
    assert (incoming / "2026/11_November/res" / res.name).is_file()
    assert store.read_bytes() == before_db and all(path.read_bytes() == data for path, data in before_jobs.items())
    detail = results.get_report_detail(results.list_recent_reports()[0].report_id, store_path=str(store))
    case = results.get_validation_case(detail.report_id, detail.assay_groups[0].occurrences[0].run_id, store_path=str(store))
    rejected = results.reanalyze_selected_cases((case,), "MK", request_id="validated-archive-stays-protected")
    assert rejected.items[0].revision_id is None and "bereits validiert" in rejected.items[0].error
    assert store.read_bytes() == before_db


def test_real_unvalidated_result_blocks_all_pdfs_of_plate(tmp_path):
    incoming, store, results, paths, res = _flow(tmp_path, validate=False)
    plan = results.preview_monthly_archive(cutoff="2026-11-25")
    assert len(plan.groups) == 1 and not plan.groups[0].eligible
    assert any("validiert" in reason for reason in plan.groups[0].reasons)
    assert results.commit_monthly_archive(plan) == () and all(path.exists() for path in paths)


def test_known_open_run_with_missing_printout_still_blocks_its_physical_plate(tmp_path):
    incoming, store, results, paths, res = _flow(tmp_path, validate=False)
    for case in results.list_open_validation_cases():
        if case.file_name != paths[0].name:
            results.validate_report_run(case.report_id, case.run_id, "MK", expected_selection_token=case.selection_token, store_path=str(store))
    paths[0].rename(tmp_path / "missing-printout.pdf")
    plan = results.preview_monthly_archive(cutoff="2026-11-25")
    assert len(plan.groups) == 1 and not plan.groups[0].eligible
    assert any("bekanntes Ergebnis" in reason for reason in plan.groups[0].reasons), plan.groups[0].reasons
    assert results.commit_monthly_archive(plan) == () and paths[1].exists() and res.exists()


def test_namesake_plate_from_another_input_does_not_block_selected_physical_plate(tmp_path):
    incoming, store, results, paths, res = _flow(tmp_path, combined=False)
    another_input = tmp_path / "another-device-input"
    another_input.mkdir()
    foreign = another_input / "another-report.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), "\n".join(("Assay A", "Plattenname: 20261125_Plate Zeit: 13:40:00",
            "Anwender: OTHER Datum: 25.11.2026", r"Test: C:\Assays\Assay A.asy (1111)", "Lot: FOREIGN", "Value: 50.0")))
        document.save(foreign)
    settings = DesktopSettings("sqlite", str(store), watch_input_path=str(incoming), watch_backup_path=str(incoming))
    extraction = ExtractionController(tmp_path, settings_provider=lambda: settings)
    assert extraction.enqueue_manual_pdfs((str(foreign),)).queued == 1
    assert extraction.process_next().submit_status == "DONE"
    assert len(results.list_open_validation_cases()) == 1  # Deliberately not validated.
    plan = results.preview_monthly_archive(cutoff="2026-11-25")
    assert len(plan.groups) == 1 and plan.groups[0].eligible, plan.groups[0].reasons


def test_validated_alias_headers_agree_with_the_same_authentic_pdf(tmp_path):
    incoming, store, results, paths, res = _flow(tmp_path, combined=False, header_aliases=True)
    plan = results.preview_monthly_archive(cutoff="2026-11-25")
    assert len(plan.groups) == 1 and plan.groups[0].eligible, plan.groups[0].reasons


def test_pdf_conflicting_dates_retains_plate_and_never_frees_its_res(tmp_path):
    incoming = tmp_path / "Result"
    incoming.mkdir()
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "index.json").write_text('{"assays": []}')
    pdf = incoming / "arbitrary.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 40), "\n".join(("Assay A", "Plattenname: 20261125_Test Zeit: 12:30:00",
            "Datum: 25.11.2026", r"Test: C:\Assay A.asy (1111)", "Datum: 24.11.2026")))
        document.save(pdf)
    res = incoming / "20261125_Test.res"
    res.write_bytes(b"synthetic RES")
    settings = DesktopSettings("sqlite", str(tmp_path / "results.sqlite3"), archive_mode="monthly", watch_input_path=str(incoming))
    plan = ResultsController(tmp_path, settings_provider=lambda: settings).preview_monthly_archive(cutoff="2026-11-25")
    assert len(plan.groups) == 1 and plan.groups[0].plate == "20261125_Test"
    assert not plan.groups[0].eligible and {source.kind for source in plan.groups[0].sources} == {"pdf", "res"}


def test_refound_unvalidated_pdf_reanalysis_reads_verified_location_and_preserves_origin(tmp_path):
    incoming, store, results, paths, res = _flow(tmp_path, combined=False, validate=False)
    report = next(item for item in results.list_recent_reports() if item.file_name == paths[0].name)
    with sqlite3.connect(store) as conn:
        run_id = conn.execute("SELECT id FROM runs WHERE pdf_path=?", (str(paths[0]),)).fetchone()[0]
    case = results.get_validation_case(report.report_id, run_id, store_path=str(store))
    assert case is not None
    before = {path: path.read_bytes() for path in (tmp_path / "jobs").glob("*.json")}
    actual = tmp_path / "renamed-in-another-directory.pdf"
    paths[0].rename(actual)
    results.find_report_pdf(report.report_id, str(actual), store_path=str(store))
    assert not paths[0].exists()
    batch = results.reanalyze_selected_cases((case,), "MK", request_id="archive-location-reanalysis")
    assert len(batch.items) == 1 and batch.items[0].revision_id and not batch.items[0].error, batch
    with sqlite3.connect(store) as conn:
        original = conn.execute("SELECT pdf_path,payload_json FROM runs WHERE id=?", (case.run_id,)).fetchone()
        assert original[0] == str(paths[0]) and json.loads(original[1])["value"] == "A.5"
    assert all(path.read_bytes() == payload for path, payload in before.items())


def test_actual_duplicate_pending_receipt_is_not_a_monthly_validated_result(tmp_path):
    import hashlib
    from src.jobcontroller.api import verify_completed_job
    incoming, store, results, paths, res = _flow(tmp_path, combined=False)
    duplicate = incoming / "another-printout.pdf"
    with fitz.open(paths[0]) as document:
        document.set_metadata({"subject": "synthetic second export, same measurement"})
        document.save(duplicate)
    digest = hashlib.sha256(duplicate.read_bytes()).hexdigest()
    settings = DesktopSettings("sqlite", str(store), watch_input_path=str(incoming), watch_backup_path=str(incoming))
    extraction = ExtractionController(tmp_path, settings_provider=lambda: settings)
    assert extraction.enqueue_manual_pdfs((str(duplicate),)).queued == 1
    outcome = extraction.process_next()
    assert outcome.submit_status == "DONE"
    job = json.loads((tmp_path / "jobs" / f"{outcome.job_id}.json").read_text())
    receipt = verify_completed_job(tmp_path, outcome.job_id, expected_sha256=digest,
        expected_pdf_path=str(duplicate), store_path=str(store), device_id=job["device_id"], include_outputs=True)
    assert receipt["complete"] and receipt["duplicate_pending"] and receipt["run_ids"] == []
    plan = results.preview_monthly_archive(cutoff="2026-11-25")
    assert len(plan.groups) == 1 and not plan.groups[0].eligible
    assert results.commit_monthly_archive(plan) == () and duplicate.exists() and res.exists()


def test_find_report_exact_recursive_hash_and_stale_context_leave_evidence_unchanged(tmp_path):
    from src.application.api import PathOpenError
    from src.ingestion.api import MonthlyArchiveError
    incoming, store, results, paths, res = _flow(tmp_path, combined=False)
    report = next(item for item in results.list_recent_reports() if item.file_name == paths[0].name)
    before_db = store.read_bytes()
    before_jobs = {path: path.read_bytes() for path in (tmp_path / "jobs").glob("*.json")}
    folder = tmp_path / "find"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    first, second = folder / "renamed.pdf", nested / "same.pdf"
    first.write_bytes(paths[0].read_bytes())
    second.write_bytes(paths[0].read_bytes())
    locations = tmp_path / "storage/ingestion/locations/verified.json"
    with pytest.raises(PathOpenError, match="Keine oder mehrere"):
        results.find_report_pdf(report.report_id, str(paths[1]), store_path=str(store))
    with pytest.raises(PathOpenError, match="Keine oder mehrere"):
        results.find_report_pdf(report.report_id, str(folder), store_path=str(store))
    assert not locations.exists()
    first.unlink()
    with pytest.raises(MonthlyArchiveError, match="Auswahl oder Ergebnisspeicher"):
        results.find_report_pdf(report.report_id, str(folder), store_path=str(store), context_guard=lambda: False)
    assert not locations.exists()
    assert results.find_report_pdf(report.report_id, str(folder), store_path=str(store)) == str(second)
    assert store.read_bytes() == before_db and all(path.read_bytes() == payload for path, payload in before_jobs.items())


def test_validated_aliases_conflict_even_when_display_prefers_one(tmp_path):
    incoming, store, results, paths, res = _flow(tmp_path)
    with sqlite3.connect(store) as conn:
        row = conn.execute("SELECT id,payload_json FROM runs LIMIT 1").fetchone()
        payload = json.loads(row[1])
        payload["plate_name"] = "another-plate"
        conn.execute("UPDATE runs SET payload_json=? WHERE id=?", (json.dumps(payload), row[0]))
    plan = results.preview_monthly_archive(cutoff="2026-11-25")
    assert not plan.groups[0].eligible and all(path.exists() for path in paths)


def test_real_evidence_recovers_after_actual_source_removal_before_receipt_without_reimport(tmp_path, monkeypatch):
    from src.ingestion.monthly_files import PlainHandle
    incoming, store, results, paths, res = _flow(tmp_path)
    plan = results.preview_monthly_archive(cutoff="2026-11-25")
    original = PlainHandle.remove
    interrupted = []
    def removed_before_receipt(self, expected):
        original(self, expected)
        if not interrupted and self.path.suffix == ".pdf":
            interrupted.append(self.path)
            raise RuntimeError("after actual removal before first receipt")
    before_db = store.read_bytes()
    before_jobs = {path: path.read_bytes() for path in (tmp_path / "jobs").glob("*.json")}
    monkeypatch.setattr(PlainHandle, "remove", removed_before_receipt)
    with pytest.raises(RuntimeError, match="before first receipt"):
        results.commit_monthly_archive(plan)
    assert interrupted and not interrupted[0].exists()
    assert not (tmp_path / "storage/ingestion/locations/verified.json").exists()
    monkeypatch.setattr(PlainHandle, "remove", original)
    assert results.recover_monthly_archive()[0]["status"] == "complete"
    assert all(not path.exists() for path in paths) and not res.exists()
    assert store.read_bytes() == before_db and all(path.read_bytes() == data for path, data in before_jobs.items())
    reports = results.list_recent_reports()
    assert len(reports) == 3 and all(report.path_available for report in reports)
    assert all("11_November" in report.current_pdf_path for report in reports)


def test_refound_pdf_missing_never_falls_back_to_different_original_for_viewer_or_preview(tmp_path):
    from src.application.api import PathOpenError, PdfPreviewError
    incoming, store, results, paths, res = _flow(tmp_path, combined=False)
    selected = next(report for report in results.list_recent_reports() if report.file_name == paths[0].name)
    original = paths[0]
    relocated = tmp_path / "renamed.pdf"
    original.rename(relocated)
    before_db = store.read_bytes()
    before_jobs = {path: path.read_bytes() for path in (tmp_path / "jobs").glob("*.json")}
    assert results.find_report_pdf(selected.report_id, str(relocated), store_path=str(store)) == str(relocated)
    relocated.unlink()
    original.write_bytes(paths[1].read_bytes())  # Another real PDF, not the stored result.
    opened = []
    results._path_opener = opened.append
    with pytest.raises(PathOpenError):
        results.open_report_pdf(selected.report_id, store_path=str(store))
    with pytest.raises(PdfPreviewError):
        results.render_report_pdf_page(selected.report_id, store_path=str(store))
    assert opened == [] and store.read_bytes() == before_db
    assert all(path.read_bytes() == data for path, data in before_jobs.items())


def test_report_preview_uses_exact_verified_snapshot_not_live_path(tmp_path, monkeypatch):
    from src.application.api import ReportPdfPage
    incoming, store, results, paths, res = _flow(tmp_path, combined=False)
    selected = next(report for report in results.list_recent_reports() if report.file_name == paths[0].name)
    original = paths[0].read_bytes()
    def render(report_id, snapshot, *, page_index, zoom):
        from pathlib import Path
        assert Path(snapshot).resolve() != paths[0].resolve()
        paths[0].write_bytes(paths[1].read_bytes())
        assert Path(snapshot).read_bytes() == original
        return ReportPdfPage(report_id, 0, 1, 1, 1, 1, b"verified-test-image")
    monkeypatch.setattr("src.application.results_controller.render_pdf_page", render)
    assert results.render_report_pdf_page(selected.report_id, store_path=str(store)).image_data == b"verified-test-image"


def test_failed_manufacturer_case_refind_and_retry_keeps_origin_queue_and_job_provenance(tmp_path, monkeypatch):
    from test_identity_case_processing import _flow as identity_flow
    store, rules, extraction, case, first, second, settings = identity_flow(tmp_path, monkeypatch)
    selected = next(source for source in case["sources"] if source["pdf_path"].casefold() == str(first).casefold())
    original_path = selected["pdf_path"]
    relocated = tmp_path / "renamed-original.pdf"
    first.rename(relocated)
    before_case = (tmp_path / "storage/rulesuite/identity_cases.json").read_bytes()
    assert extraction.identity_pdf_location(selected["job_id"], pdf_path=original_path,
        expected_sha256=selected["pdf_sha256"], store_path=str(store), device_id=selected["device_id"], search_path=str(relocated)) == str(relocated)
    outcome = extraction.retry_identity_job(selected["job_id"], pdf_path=original_path,
        expected_sha256=selected["pdf_sha256"], store_path=str(store), device_id=selected["device_id"])
    assert outcome.queue_status == outcome.submit_status == "DONE", outcome
    queue = json.loads((tmp_path / "jobs/queue" / f"{selected['job_id']}.json").read_text())
    job = json.loads((tmp_path / "jobs" / f"{selected['job_id']}.json").read_text())
    assert queue["pdf_path"].casefold() == original_path.casefold() == job["pdf_path"].casefold()
    with sqlite3.connect(store) as conn:
        assert {row[0].casefold() for row in conn.execute("SELECT pdf_path FROM runs")} == {original_path.casefold()}
    assert (tmp_path / "storage/rulesuite/identity_cases.json").read_bytes() == before_case


def test_rulesuite_secondary_remains_verifiable_at_registered_identical_location_without_proof_rewrite(tmp_path):
    import hashlib
    from test_application_rules_controller import _authoring_fixture, _register_authoring_import
    from test_rulesuite import _v2_pdf
    from src.ingestion.api import register_pdf_location
    root, draft, settings, rules = _authoring_fixture(tmp_path)
    primary = _v2_pdf(root / "chosen.pdf")
    secondary = _v2_pdf(root / "input/known.pdf", value="OTHER")
    _register_authoring_import(root, secondary, status="PENDING")
    tested = rules.create_authoring_proof("(1111)", draft, str(primary))
    assert tested["status"] == "ready"
    before_proof = rules.verify_authoring_proof("(1111)", draft)["proof"]
    before = {path: path.read_bytes() for path in (root / "rules/drafts").iterdir() if path.is_file()}
    digest = hashlib.sha256(secondary.read_bytes()).hexdigest()
    actual = root / "renamed-same-source.pdf"
    secondary.rename(actual)
    register_pdf_location(root, secondary, digest, actual)
    verified = rules.verify_authoring_proof("(1111)", draft)
    assert verified["ok"], verified
    assert verified["proof"] == before_proof
    assert all(path.read_bytes() == payload for path, payload in before.items())
    fresh = rules.create_authoring_proof("(1111)", draft, str(primary))
    assert fresh["status"] == "ready" and fresh["secondary"]["path"] == str(actual)
    assert fresh["secondary"]["source"]["original_path"] == str(secondary)
    assert rules.verify_authoring_proof("(1111)", draft)["ok"]
    frozen = {path: path.read_bytes() for path in (root / "rules/drafts").iterdir() if path.is_file()}
    second_location = root / "second-move-identical.pdf"
    actual.rename(second_location)
    register_pdf_location(root, secondary, digest, second_location)
    moved_again = rules.verify_authoring_proof("(1111)", draft)
    assert moved_again["ok"], moved_again["errors"]
    assert all(path.read_bytes() == payload for path, payload in frozen.items())
    second_location.write_bytes(b"replacement must revoke the freshly created proof")
    assert not rules.verify_authoring_proof("(1111)", draft)["ok"]
