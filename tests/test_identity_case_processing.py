import hashlib
import json
from pathlib import Path

import pytest

from src.application.api import DesktopSettings, ExtractionController, RuleSuiteController
from src.jobcontroller.api import submit
from src.jobqueue.api import claim_next_job, enqueue_pdf_job, list_jobs, mark_job_failed
from src.processing.api import ProcessingConfig, process_next_pending
from src.rulesuite.api import RuleSuiteError
from test_rulesuite_identity_cases import _block, _parser, _project


def _flow(root, monkeypatch, *, queued=True, mixed=True):
    store = _project(root)
    settings = [DesktopSettings(output_mode="sqlite", sqlite_path=str(store))]
    extraction = ExtractionController(root, settings_provider=lambda: settings[0])
    rules = RuleSuiteController(root, settings_provider=lambda: settings[0],
        identity_job_retry=extraction.retry_identity_job, identity_jobs_reader=extraction.list_processing_items)
    first, second = root / "mixed.pdf", root / "single.pdf"
    first.write_bytes(b"mixed")
    second.write_bytes(b"single")
    docs = {b"mixed": (_block(key="(1111)", value="10.5") + "\n" if mixed else "") + _block(value="20.5"),
            b"single": _block(value="30.5")}
    _parser(monkeypatch, docs)
    if queued:
        assert extraction.enqueue_manual_pdfs((str(first), str(second))).queued == 2
        assert extraction.process_next().submit_status == "FAILED"
        assert extraction.process_next().submit_status == "FAILED"
    else:
        assert submit(str(first), str(root), sqlite_path=str(store)).status == "FAILED"
    case = rules.list_identity_cases(store_path=str(store))[0]
    candidate = case["candidate_assays"][0]
    created = rules.confirm_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"],
        source_assay_key=candidate["assay_key"], expected_rule_sha256=candidate["rule_sha256"], initialization="copy")
    draft = created["draft_path"]
    assert rules.create_authoring_proof("(2222)", draft, str(first))["status"] == "ready"
    rules.activate_draft("(2222)", draft, assay_name="Assay A")
    return store, rules, extraction, case, first, second, settings


def test_real_case_retry_uses_only_affected_jobs_and_repeat_has_no_second_measurement(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    foreign = tmp_path / "unrelated.pdf"
    foreign.write_bytes(b"unrelated pending")
    queued = enqueue_pdf_job(str(tmp_path), str(foreign))
    before = rules.list_identity_case_items(store_path=str(store))[0]
    assert before.status == "Verarbeitung offen" and not before.completed and before.can_retry
    result = rules.retry_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"])
    assert not result.errors and len(result.outcomes) == 2
    assert {item.submit_status for item in result.outcomes} == {"DONE"}
    assert result.cases[0].completed and result.cases[0].status == "Erledigt"
    remaining = next(item for item in list_jobs(str(tmp_path)) if item.job_id == queued.job_id)
    assert remaining.status == "PENDING" and remaining.attempts == 0
    import sqlite3

    with sqlite3.connect(store) as conn:
        rows = conn.execute("SELECT assay_key,payload_json FROM runs ORDER BY id").fetchall()
    assert len(rows) == 3
    assert {json.loads(payload)["value"] for _key, payload in rows} == {"10.5", "20.5", "30.5"}
    before_db = store.read_bytes()
    again = rules.retry_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"])
    assert again.outcomes == () and again.errors == () and store.read_bytes() == before_db


def test_direct_legacy_import_without_queue_stays_open_without_new_pending_record(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch, queued=False)
    result = rules.retry_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"])
    assert result.errors and result.errors[0][1] == "identity_case_queue_job_missing"
    assert not result.cases[0].completed and result.cases[0].can_retry
    assert list_jobs(str(tmp_path)) == [] and not store.exists()


@pytest.mark.parametrize("change", ["bytes", "path", "store"])
def test_source_or_store_replacement_is_not_imported_as_the_original_case(tmp_path, monkeypatch, change):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    if change == "bytes":
        first.write_bytes(b"different bytes")
    elif change == "path":
        first.rename(tmp_path / "renamed.pdf")
    else:
        settings[0] = DesktopSettings(output_mode="sqlite", sqlite_path=str(tmp_path / "other.sqlite3"))
        with pytest.raises(RuleSuiteError, match="store_changed"):
            rules.retry_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"])
        assert not (tmp_path / "other.sqlite3").exists()
        return
    result = rules.retry_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"])
    assert not result.cases[0].completed
    first_source = next(item for item in result.cases[0].sources if item.job_id == hashlib.sha256(b"mixed").hexdigest()[:16])
    assert not first_source.done
    assert any(item.queue_status == "FAILED" for item in result.outcomes)


def test_original_device_is_frozen_even_when_current_import_device_changes(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    original = case["sources"][0]["device_id"]
    settings[0] = DesktopSettings(output_mode="sqlite", sqlite_path=str(store), device_id="different-current-device")
    result = rules.retry_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"])
    assert not result.errors and result.cases[0].completed
    import sqlite3

    with sqlite3.connect(store) as conn:
        assert {row[0] for row in conn.execute("SELECT device_id FROM runs")} == {original}


def test_exact_failed_claim_never_exposes_pending_and_other_worker_cannot_take_it(tmp_path):
    target = tmp_path / "target.pdf"
    foreign = tmp_path / "foreign.pdf"
    target.write_bytes(b"failed target")
    foreign.write_bytes(b"ordinary queued")
    target_job = enqueue_pdf_job(str(tmp_path), str(target))
    claimed = claim_next_job(str(tmp_path), "initial", job_id=target_job.job_id)
    mark_job_failed(str(tmp_path), claimed.job_id, "old failure", worker_id="initial")
    foreign_job = enqueue_pdf_job(str(tmp_path), str(foreign))
    from src.jobcontroller.model import JobResult

    def work(path, root, *, output_mode, sqlite_path, lock_ttl_s, sqlite_busy_timeout_ms,
             sqlite_retry_count, sqlite_retry_sleep_s, device_id, expected_sha256):
        states = {job.job_id: job for job in list_jobs(root)}
        assert states[target_job.job_id].status == "PROCESSING"
        other = claim_next_job(root, "ordinary-worker")
        assert other.job_id == foreign_job.job_id
        assert sqlite_path == "chosen-A.sqlite3" and device_id == "original-device"
        assert expected_sha256 == target_job.content_sha256
        return JobResult(target_job.job_id, path, "DONE", {})

    result = process_next_pending(tmp_path, ProcessingConfig(sqlite_path="chosen-A.sqlite3", device_id="original-device"),
        worker_id="case-worker", submit_func=work, job_id=target_job.job_id, retry_failed=True,
        expected_sha256=target_job.content_sha256, expected_pdf_path=str(target))
    assert result.queue_status == "DONE"


def test_exact_claim_path_and_full_hash_must_both_match_without_attempt_increment(tmp_path):
    pdf = tmp_path / "original.pdf"
    pdf.write_bytes(b"one source")
    job = enqueue_pdf_job(str(tmp_path), str(pdf))
    from src.jobqueue.queue import QueueError

    with pytest.raises(QueueError, match="queue_path_mismatch"):
        claim_next_job(str(tmp_path), "w", job_id=job.job_id, expected_sha256=job.content_sha256,
            expected_pdf_path=str(tmp_path / "other.pdf"))
    with pytest.raises(QueueError, match="queue_identity_mismatch"):
        claim_next_job(str(tmp_path), "w", job_id=job.job_id, expected_sha256="0" * 64, expected_pdf_path=str(pdf))
    assert list_jobs(str(tmp_path))[0].attempts == 0 and list_jobs(str(tmp_path))[0].status == "PENDING"


def test_identity_hold_is_warning_presentation_not_fake_assay_metadata_or_queue_success(tmp_path, monkeypatch):
    from interfaces.tk.view_models import build_dashboard_recent_rows, build_batch_file_statuses, status_badge_kind
    from src.application.api import ProcessingOutcome, ProcessingEnqueueOutcome, map_ingestion_display_status

    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    instances = extraction.list_ingestion_instances()
    assert {item.display_status for item in instances} == {"Kennung klären"}
    assert {item.queue_status for item in instances} == {"FAILED"}
    rows = build_dashboard_recent_rows(instances, [])
    assert all(row.status == "Kennung klären" and status_badge_kind(row.status) == "warning" for row in rows)
    assert all(row.summary == "–" and "Änderungen" in row.notice and row.report_id is None for row in rows)
    enqueued = ProcessingEnqueueOutcome(str(first), first.name, "queued")
    processed = ProcessingOutcome(True, pdf_path=str(first), file_name=first.name, queue_status="FAILED",
        submit_status="FAILED", message="assay_identity_change_pending")
    assert build_batch_file_statuses((enqueued,), (processed,))[0].status_label == "Kennung klären"
    assert map_ingestion_display_status("FAILED", "NOT_REQUIRED", technical_detail="configured_fields_empty: test") == "Verarbeitung fehlgeschlagen"
    assert map_ingestion_display_status("FAILED", "NOT_REQUIRED", technical_detail="other: assay_identity_change_pending") == "Verarbeitung fehlgeschlagen"


def test_second_open_id_in_same_pdf_holds_every_assay_until_both_independent_rules_are_tested(tmp_path, monkeypatch):
    store = _project(tmp_path)
    settings = DesktopSettings(output_mode="sqlite", sqlite_path=str(store))
    extraction = ExtractionController(tmp_path, settings_provider=lambda: settings)
    rules = RuleSuiteController(tmp_path, settings_provider=lambda: settings,
        identity_job_retry=extraction.retry_identity_job, identity_jobs_reader=lambda: extraction.list_processing_items(create_missing=False))
    pdf = tmp_path / "two-new-ids.pdf"
    pdf.write_bytes(b"two-new-ids")
    _parser(monkeypatch, {b"two-new-ids": "\n".join((_block(key="(1111)", value="10.5"), _block(key="(2222)", value="20.5"), _block(key="(3333)", value="30.5")))})
    extraction.enqueue_manual_pdfs((str(pdf),))
    assert extraction.process_next().submit_status == "FAILED" and not store.exists()

    def activate(key):
        case = next(row for row in rules.list_identity_cases(store_path=str(store)) if row["assay_key"] == key)
        selected = next(row for row in case["candidate_assays"] if row["assay_key"] == "(1111)")
        created = rules.confirm_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"],
            source_assay_key="(1111)", expected_rule_sha256=selected["rule_sha256"], initialization="copy", assay_name="Assay A")
        tested = rules.create_authoring_proof(key, created["draft_path"], str(pdf))
        assert tested["status"] == "ready" and tested["secondary"]["status"] == "not_available"
        rules.activate_draft(key, created["draft_path"], assay_name="Assay A")
        return case

    first = activate("(2222)")
    held = rules.retry_identity_case(first["case_id"], store_path=str(store), expected_identity_token=first["identity_token"])
    assert held.outcomes[0].submit_status == "FAILED" and not store.exists()
    assert not any(item.completed for item in held.cases)
    second = activate("(3333)")
    done = rules.retry_identity_case(second["case_id"], store_path=str(store), expected_identity_token=second["identity_token"])
    assert done.outcomes[0].submit_status == "DONE" and all(item.completed for item in done.cases)
    import sqlite3
    with sqlite3.connect(store) as conn:
        values = {key: json.loads(payload)["value"] for key, payload in conn.execute("SELECT assay_key,payload_json FROM runs")}
        sources = [json.loads(row[0]) for row in conn.execute("SELECT snapshot_json FROM run_source_provenance")]
    assert values == {"(1111)": "10.5", "(2222)": "20.5", "(3333)": "30.5"}
    assert {source["pdf_sha256"] for source in sources} == {hashlib.sha256(pdf.read_bytes()).hexdigest()}
    assert len({source["assay_block_hash"] for source in sources}) == 3
    assert (tmp_path / "rules" / "Assay A.2222.json").is_file() and (tmp_path / "rules" / "Assay A.3333.json").is_file()


def test_badge_count_never_parses_pdf_or_reads_diagnostic_dump_and_corrupt_is_not_zero(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    def forbid(*args, **kwargs):
        raise AssertionError("status badge must not read rule inventory/PDF/diagnostic text")
    monkeypatch.setattr(rules, "list_inventory", forbid)
    monkeypatch.setattr(rules, "_rule_pdf_source", forbid)
    monkeypatch.setattr("src.jobcontroller.jobcontroller._read_diagnostic_context", forbid)
    assert rules.get_identity_case_count(store_path=str(store)) == 1
    catalogue = tmp_path / "storage" / "rulesuite" / "identity_cases.json"
    catalogue.write_text("{unreadable", encoding="utf-8")
    with pytest.raises(RuleSuiteError, match="json_read_failed"):
        rules.get_identity_case_count(store_path=str(store))
