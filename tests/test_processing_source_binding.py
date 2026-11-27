"""Real PDF/SQLite checks for the bounded SHA-to-parser handoff (correction A)."""
import hashlib
import json
from pathlib import Path

import fitz
import pytest

from src.jobcontroller.api import submit
from src.jobcontroller.jobcontroller import JobController
from src.jobcontroller.model import JobResult
from src.jobqueue.api import enqueue_pdf_job, list_jobs
from src.processing.api import ProcessingConfig, process_next_pending
from test_rulesuite_identity_cases import _project


def _pdf(path, value):
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "\n".join(("Assay A", "Lot: LOT_A", r"Test: C:\Assays\Assay A.asy (1111)", f"Value: {value}")))
        document.save(path)
    return path.read_bytes()


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _bytes_if_present(path):
    return path.read_bytes() if path.exists() else None


@pytest.mark.parametrize("replacement_already_done", [False, True])
def test_bound_queue_rejects_real_replacement_after_verify_then_processes_only_returned_original(tmp_path, monkeypatch, replacement_already_done):
    from src.parser.api import parse as real_parse
    from src.processing import service

    store = _project(tmp_path)
    original, replacement = tmp_path / "original.pdf", tmp_path / "replacement.pdf"
    original_bytes, replacement_bytes = _pdf(original, "10.5"), _pdf(replacement, "90.5")
    original_sha, replacement_sha = _sha(original_bytes), _sha(replacement_bytes)
    if replacement_already_done:
        assert submit(str(replacement), str(tmp_path), sqlite_path=str(store)).status == "DONE"
    replacement_state = tmp_path / "jobs" / f"{replacement_sha[:16]}.json"
    original_state = tmp_path / "jobs" / f"{original_sha[:16]}.json"
    before_replacement, before_database = _bytes_if_present(replacement_state), _bytes_if_present(store)
    queued = enqueue_pdf_job(str(tmp_path), str(original))
    config = ProcessingConfig(sqlite_path=str(store))
    parsed = []

    def parse_used_copy(path):
        parsed.append(_sha(Path(path).read_bytes()))
        return real_parse(path)

    monkeypatch.setattr("src.parser.api.parse", parse_used_copy)
    real_verify = service.verify_job_content_sha256

    def verify_then_replace(project_root, job_id, *, claim_lock_ttl_s=None):
        real_verify(project_root, job_id, claim_lock_ttl_s=claim_lock_ttl_s)
        original.write_bytes(replacement_bytes)

    with monkeypatch.context() as attack:
        attack.setattr(service, "verify_job_content_sha256", verify_then_replace)
        rejected = process_next_pending(tmp_path, config, job_id=queued.job_id, retry_failed=True,
            expected_sha256=original_sha, expected_pdf_path=str(original))
    assert rejected.job_id == queued.job_id and rejected.queue_status == rejected.submit_status == "FAILED"
    assert rejected.message == "source_changed_since_ingest"
    assert parsed == [] and not original_state.exists()
    assert _bytes_if_present(replacement_state) == before_replacement
    assert _bytes_if_present(store) == before_database
    assert {job.job_id for job in list_jobs(str(tmp_path))} == {original_sha[:16]}

    original.write_bytes(original_bytes)
    restored = process_next_pending(tmp_path, config, job_id=queued.job_id, retry_failed=True,
        expected_sha256=original_sha, expected_pdf_path=str(original))
    assert restored.queue_status == restored.submit_status == "DONE"
    assert parsed == [original_sha]
    import sqlite3

    with sqlite3.connect(store) as conn:
        values = {sha: json.loads(payload)["value"] for sha, payload in conn.execute("SELECT pdf_sha256,payload_json FROM runs")}
    assert values == ({replacement_sha: "90.5", original_sha: "10.5"} if replacement_already_done else {original_sha: "10.5"})
    assert _bytes_if_present(replacement_state) == before_replacement
    before_original, before_database = original_state.read_bytes(), store.read_bytes()
    queue_path = tmp_path / "jobs" / "queue" / f"{queued.job_id}.json"
    before_queue = queue_path.read_bytes()
    repeated = process_next_pending(tmp_path, config, job_id=queued.job_id, retry_failed=True,
        expected_sha256=original_sha, expected_pdf_path=str(original))
    assert not repeated.processed and queue_path.read_bytes() == before_queue
    direct_repeat = submit(str(original), str(tmp_path), sqlite_path=str(store), expected_sha256=original_sha)
    assert direct_repeat.status == "SKIPPED" and direct_repeat.details["reason"] == "already_done"
    assert original_state.read_bytes() == before_original and store.read_bytes() == before_database
    assert parsed == [original_sha]


@pytest.mark.parametrize("original_already_done", [False, True])
def test_used_snapshot_aba_is_checked_before_done_or_pipeline_side_effects(tmp_path, monkeypatch, original_already_done):
    from src.jobcontroller import jobcontroller

    store = _project(tmp_path)
    original, replacement = tmp_path / "original.pdf", tmp_path / "replacement.pdf"
    original_bytes, replacement_bytes = _pdf(original, "10.5"), _pdf(replacement, "90.5")
    expected = _sha(original_bytes)
    if original_already_done:
        assert submit(str(original), str(tmp_path), sqlite_path=str(store)).status == "DONE"
    state = tmp_path / "jobs" / f"{expected[:16]}.json"
    before_state, before_database = _bytes_if_present(state), _bytes_if_present(store)
    real_copy = jobcontroller.shutil.copyfile
    copies = []

    def replace_during_capture(source, target):
        copies.append((str(source), str(target)))
        assert Path(source).resolve() == original.resolve()
        original.write_bytes(replacement_bytes)
        try:
            return real_copy(source, target)
        finally:
            original.write_bytes(original_bytes)

    monkeypatch.setattr(jobcontroller.shutil, "copyfile", replace_during_capture)
    rejected = submit(str(original), str(tmp_path), sqlite_path=str(store), expected_sha256=expected)
    assert rejected.status == "FAILED" and rejected.job_id == expected[:16]
    assert rejected.details["error"] == "source_changed_since_ingest"
    assert len(copies) == 1 and original.read_bytes() == original_bytes
    assert _bytes_if_present(state) == before_state and _bytes_if_present(store) == before_database
    if not original_already_done:
        assert not (tmp_path / "jobs").exists() and not (tmp_path / "locks").exists()


def test_bound_parser_uses_the_one_verified_private_copy_not_live_aba_source(tmp_path, monkeypatch):
    from src.jobcontroller import jobcontroller
    from src.parser.api import parse as real_parse

    store = _project(tmp_path)
    original, replacement = tmp_path / "original.pdf", tmp_path / "replacement.pdf"
    original_bytes, replacement_bytes = _pdf(original, "10.5"), _pdf(replacement, "90.5")
    expected, copies, parsed = _sha(original_bytes), [], []
    real_copy = jobcontroller.shutil.copyfile

    def copy(source, target):
        copies.append((str(source), str(target)))
        return real_copy(source, target)

    def parse_while_live_source_changes(path):
        assert Path(path).resolve() != original.resolve()
        parsed.append(_sha(Path(path).read_bytes()))
        original.write_bytes(replacement_bytes)
        try:
            return real_parse(path)
        finally:
            original.write_bytes(original_bytes)

    monkeypatch.setattr(jobcontroller.shutil, "copyfile", copy)
    monkeypatch.setattr("src.parser.api.parse", parse_while_live_source_changes)
    result = submit(str(original), str(tmp_path), sqlite_path=str(store), expected_sha256=expected)
    assert result.status == "DONE" and result.job_id == expected[:16]
    assert result.details["writes"][0]["data"] == {"value": "10.5"}
    assert result.details["writes"][0]["pdf_sha256"] == expected
    assert len(copies) == 1 and parsed == [expected]
    assert not Path(copies[0][1]).exists()  # The private source lifetime ended.


def test_normal_queue_keeps_existing_narrow_injected_submit_contract(tmp_path):
    pdf = tmp_path / "normal.pdf"
    pdf.write_bytes(b"normal narrow contract")
    queued = enqueue_pdf_job(str(tmp_path), str(pdf))
    calls = []

    def narrow(path, root, *, output_mode, sqlite_path, lock_ttl_s, sqlite_busy_timeout_ms,
               sqlite_retry_count, sqlite_retry_sleep_s, device_id):
        calls.append((path, root))
        return JobResult(queued.job_id, path, "DONE", {})

    result = process_next_pending(tmp_path, ProcessingConfig(), submit_func=narrow)
    assert result.queue_status == "DONE" and calls == [(str(pdf), str(tmp_path))]


def test_bound_submit_contract_error_never_falls_back_to_unbound_call(tmp_path):
    pdf = tmp_path / "bound.pdf"
    pdf.write_bytes(b"bound callback error")
    queued = enqueue_pdf_job(str(tmp_path), str(pdf))
    calls = []

    def incompatible(path, root, *, output_mode, sqlite_path, lock_ttl_s, sqlite_busy_timeout_ms,
                     sqlite_retry_count, sqlite_retry_sleep_s, device_id):
        calls.append((path, root))
        return JobResult(queued.job_id, path, "DONE", {})

    result = process_next_pending(tmp_path, ProcessingConfig(), submit_func=incompatible, job_id=queued.job_id,
        retry_failed=True, expected_sha256=queued.content_sha256, expected_pdf_path=str(pdf))
    assert result.queue_status == "FAILED" and result.message.startswith("worker_submit_error:")
    assert calls == []


def test_output_permission_error_is_not_relabelled_as_source_replacement(tmp_path, monkeypatch):
    pdf = tmp_path / "original.pdf"
    payload = _pdf(pdf, "10.5")
    controller = JobController()

    def denied(*args, **kwargs):
        raise PermissionError("synthetic output/state permission denied")

    monkeypatch.setattr(controller, "_submit_pipeline", denied)
    with pytest.raises(PermissionError, match="output/state permission denied"):
        controller.submit(str(pdf), str(tmp_path), expected_sha256=_sha(payload))


@pytest.mark.parametrize("invalid", ["not-a-hash", "0" * 63, "z" * 64, 42])
def test_invalid_bound_hash_rejects_before_source_capture_or_state(tmp_path, monkeypatch, invalid):
    from src.jobcontroller import jobcontroller

    pdf = tmp_path / "original.pdf"
    _pdf(pdf, "10.5")
    def forbidden(source, target):
        raise AssertionError("invalid SHA must not capture or enter the pipeline")
    monkeypatch.setattr(jobcontroller.shutil, "copyfile", forbidden)
    result = submit(str(pdf), str(tmp_path), expected_sha256=invalid)
    assert result.status == "FAILED" and result.details["error"] == "expected_sha256_invalid"
    assert not (tmp_path / "jobs").exists() and not (tmp_path / "locks").exists()
