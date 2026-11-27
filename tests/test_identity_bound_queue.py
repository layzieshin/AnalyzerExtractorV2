"""Synthetic durable case/attempt/SQLite reconciliation contracts (B)."""
import hashlib
import json
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from src.jobcontroller.api import submit, verify_completed_job
from src.jobcontroller.model import JobResult
from src.jobqueue.api import (claim_next_job, enqueue_pdf_job, list_jobs, mark_job_done, mark_job_failed,
                             mark_job_pending, recover_stale_jobs, release_job_attempt, retry_failed_job)
from src.jobqueue.queue import QueueError
from src.processing.api import ProcessingConfig, process_next_pending, retry_failed
from test_identity_case_processing import _flow


def _queue_path(root, job_id):
    return root / "jobs" / "queue" / f"{job_id}.json"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _args(source, store):
    return {"job_id": source["job_id"], "expected_sha256": source["pdf_sha256"],
            "expected_pdf_path": source["pdf_path"], "store_path": str(store), "device_id": source["device_id"]}


def _claim(root, store, source):
    return claim_next_job(str(root), "bound-worker", retry_failed=True, **_args(source, store))


def _receipt(root, store, source):
    args = _args(source, store)
    job_id = args.pop("job_id")
    return verify_completed_job(root, job_id, **args)


def test_first_hold_is_durable_and_all_generic_retry_surfaces_stay_closed(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    path = _queue_path(tmp_path, source["job_id"])
    record = _read(path)
    state = _read(tmp_path / "jobs" / f"{source['job_id']}.json")
    assert record["status"] == "FAILED" and record["identity_binding"] == state["identity_binding"]
    binding = record["identity_binding"]
    assert binding["content_sha256"] == source["pdf_sha256"] and binding["device_id"] == source["device_id"]
    assert Path(binding["store_path"]) == store.resolve() and Path(binding["pdf_path"]) == Path(source["pdf_path"])
    for retry in (retry_failed_job, retry_failed, extraction.retry_failed):
        with pytest.raises((QueueError, ValueError), match="bound_retry_required"):
            retry(source["job_id"]) if retry == extraction.retry_failed else retry(str(tmp_path), source["job_id"])
        assert _read(path)["status"] == "FAILED"
    assert process_next_pending(tmp_path, ProcessingConfig(sqlite_path=str(store))).processed is False
    assert not store.exists()


@pytest.mark.parametrize("defect", ["legacy", "missing_sha", "path", "ambiguous"])
def test_first_normal_worker_quarantines_one_old_pending_case_and_continues_unrelated_jobs(tmp_path, monkeypatch, defect):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    target = _queue_path(tmp_path, source["job_id"])
    row = _read(target)
    row.update(status="PENDING", attempts=1, last_error="deferred:locked")
    row.pop("identity_binding", None)
    row.pop("attempt_id", None)
    if defect == "missing_sha":
        row.pop("content_sha256")
    elif defect == "path":
        row["pdf_path"] = str(tmp_path / "wrong-path.pdf")
    elif defect == "ambiguous":
        catalogue = tmp_path / "storage" / "rulesuite" / "identity_cases.json"
        data = _read(catalogue)
        other = json.loads(json.dumps(data["cases"][case["case_id"]]))
        other.update(case_id="other-case", store_path=str(tmp_path / "foreign.sqlite3"))
        data["cases"]["other-case"] = other
        _write(catalogue, data)
    _write(target, row)
    ordinary = []
    for index in range(2):
        path = tmp_path / f"ordinary-{index}.pdf"
        path.write_bytes(f"independent-{index}".encode())
        ordinary.append(enqueue_pdf_job(str(tmp_path), str(path)).job_id)
    calls = []
    def narrow(path, root, *, output_mode, sqlite_path, lock_ttl_s, sqlite_busy_timeout_ms,
               sqlite_retry_count, sqlite_retry_sleep_s, device_id):
        job_id = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
        calls.append(job_id)
        return JobResult(job_id, path, "DONE", {})
    config = ProcessingConfig(sqlite_path=str(tmp_path / "wrong-current.sqlite3"), device_id="wrong-current")
    results = [process_next_pending(tmp_path, config, submit_func=narrow) for _ in range(3)]
    assert set(calls) == set(ordinary) and len(calls) == 2
    assert sum(item.processed for item in results) == 2
    assert _read(target)["status"] == "FAILED" and _read(target)["attempts"] == 1
    assert not store.exists() and not (tmp_path / "wrong-current.sqlite3").exists()


def test_deferred_exact_attempt_never_becomes_generic_pending_and_cannot_fake_done(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    job = _claim(tmp_path, store, source)
    assert job.identity_binding and job.attempt_id and job.worker_id == "bound-worker"
    try:
        assert recover_stale_jobs(str(tmp_path), processing_ttl_s=-1) == 0
        assert _claim(tmp_path, store, source) is None
        for token in (None, "foreign-token"):
            with pytest.raises(QueueError, match="attempt"):
                mark_job_done(str(tmp_path), job.job_id, worker_id=job.worker_id, attempt_id=token)
        with pytest.raises(QueueError, match="completion_evidence_missing"):
            mark_job_done(str(tmp_path), job.job_id, worker_id=job.worker_id, attempt_id=job.attempt_id)
        marked = mark_job_pending(str(tmp_path), job.job_id, "deferred:locked", worker_id=job.worker_id, attempt_id=job.attempt_id)
        assert marked.status == "FAILED" and marked.last_error == "deferred:locked"
        assert process_next_pending(tmp_path, ProcessingConfig(sqlite_path=str(store))).processed is False
    finally:
        release_job_attempt(job.attempt_id)


def test_unbound_public_claim_and_mark_remain_compatible_across_threads(tmp_path):
    pdf = tmp_path / "ordinary.pdf"
    pdf.write_bytes(b"ordinary public contract")
    queued = enqueue_pdf_job(str(tmp_path), str(pdf))
    claimed = claim_next_job(str(tmp_path), "same-worker")
    outcomes, errors = [], []
    def complete():
        try:
            outcomes.append(mark_job_done(str(tmp_path), queued.job_id, worker_id="same-worker"))
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=complete)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive() and errors == [] and outcomes[0].status == "DONE"
    assert recover_stale_jobs(str(tmp_path), processing_ttl_s=-1) == 0


def test_unbound_public_legacy_claim_and_mark_allow_an_actual_process_change(tmp_path):
    pdf = tmp_path / "legacy-process-contract.pdf"
    pdf.write_bytes(b"separate legacy callers")
    job = enqueue_pdf_job(str(tmp_path), str(pdf))
    claim_code = """
import sys,json
from src.jobqueue.api import claim_next_job
job=claim_next_job(sys.argv[1], 'legacy-worker')
print(json.dumps({'id':job.job_id,'status':job.status,'attempt':job.attempt_id}))
"""
    first = subprocess.run([sys.executable, "-B", "-c", claim_code, str(tmp_path)],
                           text=True, capture_output=True, timeout=15, check=True)
    assert json.loads(first.stdout) == {"id": job.job_id, "status": "PROCESSING", "attempt": ""}
    mark_code = """
import sys
from src.jobqueue.api import mark_job_done
print(mark_job_done(sys.argv[1],sys.argv[2],worker_id='legacy-worker').status)
"""
    second = subprocess.run([sys.executable, "-B", "-c", mark_code, str(tmp_path), job.job_id],
                            text=True, capture_output=True, timeout=15, check=True)
    assert second.stdout.strip() == "DONE" and list_jobs(str(tmp_path))[0].status == "DONE"


def test_new_explicit_manual_import_of_legacy_direct_case_is_bound_not_globally_available(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch, queued=False)
    source = case["sources"][0]
    assert rules.retry_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"]).errors
    assert list_jobs(str(tmp_path)) == []
    assert extraction.enqueue_manual_pdfs((str(first),)).queued == 1
    row = _read(_queue_path(tmp_path, source["job_id"]))
    assert row["identity_manual_submit"] is True and row["identity_binding"]["device_id"] == source["device_id"]
    # A worker whose current context differs cannot turn this into a free job.
    before = _queue_path(tmp_path, source["job_id"]).read_bytes()
    assert claim_next_job(str(tmp_path), "foreign", store_path=str(tmp_path / "other.sqlite3"), device_id="other") is None
    assert _queue_path(tmp_path, source["job_id"]).read_bytes() == before
    assert not (tmp_path / "other.sqlite3").exists()
    # The original manual route must still complete without an extra case click.
    done = extraction.process_next()
    assert done.queue_status == done.submit_status == "DONE"
    assert rules.list_identity_case_items(store_path=str(store))[0].completed
    assert _receipt(tmp_path, store, source)["complete"]


def test_legacy_direct_case_normal_manual_route_completes_without_an_extra_case_action(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch, queued=False)
    assert extraction.enqueue_manual_pdfs((str(first),)).queued == 1
    result = extraction.process_next()
    assert result.queue_status == result.submit_status == "DONE"
    assert rules.list_identity_case_items(store_path=str(store))[0].completed
    with sqlite3.connect(store) as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2


@pytest.mark.parametrize("damage", ["none", "thin", "foreign_store", "foreign_run", "missing_mixed_row", "device"])
def test_done_requires_actual_full_output_and_queue_recovery_never_reimports(tmp_path, monkeypatch, damage):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    done = extraction.retry_identity_job(source["job_id"], pdf_path=source["pdf_path"],
        expected_sha256=source["pdf_sha256"], store_path=str(store), device_id=source["device_id"])
    assert done.queue_status == "DONE" and _receipt(tmp_path, store, source)["complete"]
    state_path = tmp_path / "jobs" / f"{source['job_id']}.json"
    state = _read(state_path)
    if damage == "thin":
        state.pop("output_plan")
        state["steps"] = []
        _write(state_path, state)
    elif damage == "foreign_store":
        state["output_plan"]["sqlite_path"] = str(tmp_path / "foreign.sqlite3")
        _write(state_path, state)
    elif damage == "foreign_run":
        with sqlite3.connect(store) as conn:
            conn.execute("UPDATE runs SET job_id='foreign-job',pdf_sha256=?", ("f" * 64,))
    elif damage == "missing_mixed_row":
        with sqlite3.connect(store) as conn:
            conn.execute("DELETE FROM runs WHERE id=(SELECT MIN(id) FROM runs)")
    elif damage == "device":
        with sqlite3.connect(store) as conn:
            conn.execute("UPDATE runs SET device_id='foreign-device'")
    queue_path = _queue_path(tmp_path, source["job_id"])
    queued = _read(queue_path)
    queued.update(status="PROCESSING", last_error="crashed-before-queue-commit", worker_id="dead-worker")
    _write(queue_path, queued)
    before_db, before_state = store.read_bytes(), state_path.read_bytes()
    def forbid(*args, **kwargs):
        raise AssertionError("DONE reconciliation must not parse or submit again")
    monkeypatch.setattr("src.processing.service.submit", forbid)
    if damage == "foreign_store":
        with pytest.raises(ValueError, match="source_store_changed"):
            extraction.retry_identity_job(source["job_id"], pdf_path=source["pdf_path"],
                expected_sha256=source["pdf_sha256"], store_path=str(store), device_id=source["device_id"])
        result = None
    else:
        result = extraction.retry_identity_job(source["job_id"], pdf_path=source["pdf_path"],
            expected_sha256=source["pdf_sha256"], store_path=str(store), device_id=source["device_id"])
    assert (result is None or not result.processed) and store.read_bytes() == before_db and state_path.read_bytes() == before_state
    assert _receipt(tmp_path, store, source)["complete"] is (damage == "none")
    if damage == "none":
        assert result.queue_status == "DONE" and _read(queue_path)["status"] == "DONE"
    else:
        assert result is None or (result.queue_status == "FAILED" and "completion" in result.message)
        assert _read(queue_path)["status"] == "PROCESSING"  # Never pretend success or rewrite old evidence.
    assert rules.get_identity_case_count(store_path=str(store)) == 1  # The other actual source is still open.


def test_existing_full_receipt_and_duplicate_pending_are_valid_without_foreign_run_shortcut(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    # Same assay values already exist, but originate from a different PDF/job.
    foreign = tmp_path / "foreign-source.pdf"
    foreign.write_bytes(first.read_bytes())
    # Produce the legitimate output, then use an independently hashed PDF with
    # the same extracted record to force DbWriter's real candidate semantics.
    assert extraction.retry_identity_job(source["job_id"], pdf_path=source["pdf_path"],
        expected_sha256=source["pdf_sha256"], store_path=str(store), device_id=source["device_id"]).queue_status == "DONE"
    state_path = tmp_path / "jobs" / f"{source['job_id']}.json"
    state = _read(state_path)
    with sqlite3.connect(store) as conn:
        conn.execute("UPDATE runs SET job_id='earlier-job',pdf_sha256=?", ("e" * 64,))
    state["status"] = "FAILED"
    _write(state_path, state)
    row = _read(_queue_path(tmp_path, source["job_id"]))
    row["status"] = "FAILED"
    _write(_queue_path(tmp_path, source["job_id"]), row)
    result = extraction.retry_identity_job(source["job_id"], pdf_path=source["pdf_path"],
        expected_sha256=source["pdf_sha256"], store_path=str(store), device_id=source["device_id"])
    assert result.queue_status == "DONE" and _receipt(tmp_path, store, source)["complete"]
    state = _read(state_path)
    assert {entry["sqlite_status"] for entry in state["output_plan"]["assays"]} == {"duplicate_pending"}
    with sqlite3.connect(store) as conn:
        assert conn.execute("SELECT COUNT(*) FROM duplicate_candidates").fetchone()[0] == 2
        candidate_id = conn.execute("SELECT MIN(id) FROM duplicate_candidates").fetchone()[0]
        conn.execute("DELETE FROM duplicate_candidates WHERE id=?", (candidate_id,))
    assert not _receipt(tmp_path, store, source)["complete"]  # existing_run_id still exists, not sufficient.


def test_already_persisted_and_strong_legacy_receipt_remain_read_only_valid(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    args = dict(job_id=source["job_id"], pdf_path=source["pdf_path"], expected_sha256=source["pdf_sha256"],
                store_path=str(store), device_id=source["device_id"])
    assert extraction.retry_identity_job(**args).queue_status == "DONE"
    state_path = tmp_path / "jobs" / f"{source['job_id']}.json"
    state = _read(state_path)
    state["status"] = "FAILED"
    _write(state_path, state)
    queue_path = _queue_path(tmp_path, source["job_id"])
    queued = _read(queue_path)
    queued["status"] = "FAILED"
    _write(queue_path, queued)
    assert extraction.retry_identity_job(**args).queue_status == "DONE"
    state = _read(state_path)
    assert {entry["write_item"]["outputs"][0]["status"] for entry in state["output_plan"]["assays"]} == {"already_persisted"}
    assert _receipt(tmp_path, store, source)["complete"]
    state.pop("output_plan")
    _write(state_path, state)
    before_db, before_state = store.read_bytes(), state_path.read_bytes()
    assert _receipt(tmp_path, store, source) == {"complete": True, "reason": "", "kind": "legacy_sqlite_receipt"}
    assert store.read_bytes() == before_db and state_path.read_bytes() == before_state


@pytest.mark.parametrize("legacy_sha", [True, False])
def test_normal_worker_reconciles_only_real_complete_old_pending_without_reimport(tmp_path, monkeypatch, legacy_sha):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    assert extraction.retry_identity_job(source["job_id"], pdf_path=source["pdf_path"],
        expected_sha256=source["pdf_sha256"], store_path=str(store), device_id=source["device_id"]).queue_status == "DONE"
    queue_path = _queue_path(tmp_path, source["job_id"])
    row = _read(queue_path)
    row.update(status="PENDING", last_error="deferred:locked")
    row.pop("identity_binding", None)
    row.pop("attempt_id", None)
    if legacy_sha:
        row.pop("content_sha256")
    _write(queue_path, row)
    state_path = tmp_path / "jobs" / f"{source['job_id']}.json"
    before_state, before_db = state_path.read_bytes(), store.read_bytes()
    def forbid(*args, **kwargs):
        raise AssertionError("complete old job must never be resubmitted")
    monkeypatch.setattr("src.processing.service.submit", forbid)
    result = process_next_pending(tmp_path, ProcessingConfig(sqlite_path=str(tmp_path / "wrong-current.sqlite3"), device_id="wrong"))
    assert not result.processed and _read(queue_path)["status"] == "DONE"
    assert _read(queue_path)["content_sha256"] == source["pdf_sha256"]
    assert before_state == state_path.read_bytes() and before_db == store.read_bytes()
    assert not (tmp_path / "wrong-current.sqlite3").exists()


def test_completed_state_during_living_attempt_is_not_reconciled_by_another_worker(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    job = _claim(tmp_path, store, source)
    try:
        actual = submit(source["pdf_path"], str(tmp_path), sqlite_path=str(store), device_id=source["device_id"],
                        expected_sha256=source["pdf_sha256"])
        assert actual.status == "DONE" and _receipt(tmp_path, store, source)["complete"]
        held = extraction.retry_identity_job(source["job_id"], pdf_path=source["pdf_path"],
            expected_sha256=source["pdf_sha256"], store_path=str(store), device_id=source["device_id"])
        assert not held.processed and held.queue_status == "FAILED" and held.message == "identity_case_attempt_still_active"
        assert _read(_queue_path(tmp_path, job.job_id))["status"] == "PROCESSING"
        assert mark_job_done(str(tmp_path), job.job_id, worker_id=job.worker_id, attempt_id=job.attempt_id).status == "DONE"
    finally:
        release_job_attempt(job.attempt_id)


@pytest.mark.parametrize("wrong", ["store", "device", "path", "sha"])
def test_bound_exact_claim_rejects_any_foreign_context_before_new_attempt(tmp_path, monkeypatch, wrong):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    args = _args(source, store)
    field = {"store": "store_path", "device": "device_id", "path": "expected_pdf_path", "sha": "expected_sha256"}[wrong]
    args[field] = "0" * 64 if wrong == "sha" else "wrong-device" if wrong == "device" else str(tmp_path / "wrong")
    before = _read(_queue_path(tmp_path, source["job_id"]))
    with pytest.raises(QueueError, match="bound_retry_required"):
        claim_next_job(str(tmp_path), "wrong-worker", retry_failed=True, **args)
    after = _read(_queue_path(tmp_path, source["job_id"]))
    assert after["status"] == "FAILED" and after["attempts"] == before["attempts"]
    assert after["attempt_id"] == before["attempt_id"] and not store.exists()


def test_direct_submit_cannot_bypass_bound_store_device_or_missing_actual_done_evidence(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    state_path = tmp_path / "jobs" / f"{source['job_id']}.json"
    before = state_path.read_bytes()
    wrong_store = tmp_path / "other.sqlite3"
    for db, device in ((wrong_store, source["device_id"]), (store, "other-device")):
        rejected = submit(source["pdf_path"], str(tmp_path), sqlite_path=str(db), device_id=device)
        assert rejected.status == "FAILED" and rejected.details["error"] == "identity_case_bound_context_mismatch"
        assert state_path.read_bytes() == before and not store.exists() and not wrong_store.exists()
    state = _read(state_path)
    state["status"] = "DONE"
    _write(state_path, state)
    thin = state_path.read_bytes()
    rejected = submit(source["pdf_path"], str(tmp_path), sqlite_path=str(store), device_id=source["device_id"])
    assert rejected.status == "FAILED" and "completion" in rejected.details["error"]
    assert state_path.read_bytes() == thin and not store.exists()


def test_dead_process_attempt_recovers_but_living_owner_is_never_overtaken_even_after_zero_ttl(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    code = """
import json,sys,time
from src.jobqueue.api import claim_next_job
root, args = sys.argv[1], json.loads(sys.argv[2])
job = claim_next_job(root, 'child-owner', retry_failed=True, **args)
print(job.attempt_id, flush=True)
time.sleep(45)
"""
    child = subprocess.Popen([sys.executable, "-B", "-c", code, str(tmp_path), json.dumps(_args(source, store))],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        attempt = child.stdout.readline().strip()
        assert len(attempt) == 32 and child.poll() is None
        assert recover_stale_jobs(str(tmp_path), processing_ttl_s=-1) == 0
        assert _claim(tmp_path, store, source) is None
        assert _read(_queue_path(tmp_path, source["job_id"]))["attempt_id"] == attempt
    finally:
        child.terminate()
        child.communicate(timeout=10)
    assert recover_stale_jobs(str(tmp_path), processing_ttl_s=999999) == 1
    row = _read(_queue_path(tmp_path, source["job_id"]))
    assert row["status"] == "FAILED" and row["last_error"] == "identity_case_attempt_interrupted"
    next_job = _claim(tmp_path, store, source)
    try:
        assert next_job.attempt_id != attempt and next_job.status == "PROCESSING"
        with pytest.raises(QueueError, match="attempt_mismatch"):
            mark_job_failed(str(tmp_path), next_job.job_id, "late old callback", worker_id=next_job.worker_id, attempt_id=attempt)
        assert _read(_queue_path(tmp_path, next_job.job_id))["status"] == "PROCESSING"
        mark_job_failed(str(tmp_path), next_job.job_id, "test finished", worker_id=next_job.worker_id, attempt_id=next_job.attempt_id)
    finally:
        release_job_attempt(next_job.attempt_id)


def test_pipeline_lease_survives_ttl_and_owner_release_never_unlinks_foreign_marker(tmp_path):
    from src.runtime.api import try_acquire_scoped_exclusive
    lock = tmp_path / "pipeline.lock"
    owned = try_acquire_scoped_exclusive(lock, 1)
    try:
        assert owned is not None and try_acquire_scoped_exclusive(lock, -1) is None
        foreign = b'{"foreign":"marker must survive"}'
        lock.write_bytes(foreign)
    finally:
        owned.release()
    assert lock.read_bytes() == foreign
    assert try_acquire_scoped_exclusive(lock, 999999, legacy_stale=False) is None


def test_claim_reads_case_index_once_and_skips_archived_done_rows(tmp_path, monkeypatch):
    from src.rulesuite.api import list_assay_identity_job_bindings as real_reader
    from src.jobqueue.queue import JobQueue
    calls = []
    def reader(root):
        calls.append(root)
        return real_reader(root)
    monkeypatch.setattr("src.rulesuite.api.list_assay_identity_job_bindings", reader)
    queue = tmp_path / "jobs" / "queue"
    queue.mkdir(parents=True)
    for index in range(20):
        _write(queue / f"{index:016x}.json", {"job_id": f"{index:016x}", "status": "DONE"})
    ordinary = tmp_path / "pending.pdf"
    ordinary.write_bytes(b"one ordinary pending")
    enqueued = enqueue_pdf_job(str(tmp_path), str(ordinary))
    calls.clear()
    job = JobQueue().claim_next_job(str(tmp_path), "ordinary")
    try:
        assert job.job_id == enqueued.job_id and len(calls) == 1
        mark_job_done(str(tmp_path), job.job_id, worker_id=job.worker_id)
    finally:
        release_job_attempt(job.attempt_id)


def test_case_cannot_close_from_done_flags_without_actual_persisted_complete_proof(tmp_path, monkeypatch):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    result = rules.retry_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"])
    assert result.cases[0].completed and rules.get_identity_case_count(store_path=str(store)) == 0
    # Completion reads originals, never selected revisions/validation state.
    def forbid(*args, **kwargs):
        raise AssertionError("completion must not project or change validation")
    monkeypatch.setattr("src.resultstore.sqlite_store.project_run", forbid)
    assert all(_receipt(tmp_path, store, source)["complete"] for source in case["sources"])
    with sqlite3.connect(store) as conn:
        conn.execute("DELETE FROM runs WHERE job_id=?", (case["sources"][0]["job_id"],))
    assert all(job.status == "DONE" for job in list_jobs(str(tmp_path)))
    item = rules.list_identity_case_items(store_path=str(store))[0]
    assert not item.completed and item.can_retry and rules.get_identity_case_count(store_path=str(store)) == 1
    damaged = next(row for row in item.sources if row.job_id == case["sources"][0]["job_id"])
    assert not damaged.done and "vollständige" in damaged.message and "offen" in damaged.message


def test_receipt_raw_json_preserves_zero_false_and_empty_as_different_values():
    from src.jobcontroller.completion import _same_json
    assert _same_json({"zero": 0, "false": False, "empty": ""}, {"empty": "", "false": False, "zero": 0})
    assert not _same_json({"value": 0}, {"value": False})
    assert not _same_json({"value": ""}, {"value": None})


@pytest.mark.parametrize("status", ["PROCESSING", "DONE"])
def test_rejected_generic_retry_cannot_mutate_a_living_owner_or_completed_queue_bytes(tmp_path, monkeypatch, status):
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    source = case["sources"][0]
    job = None
    if status == "PROCESSING":
        job = _claim(tmp_path, store, source)
        assert job.attempt_id
    else:
        result = extraction.retry_identity_job(source["job_id"], pdf_path=source["pdf_path"],
            expected_sha256=source["pdf_sha256"], store_path=str(store), device_id=source["device_id"])
        assert result.queue_status == "DONE"
    path = _queue_path(tmp_path, source["job_id"])
    before = path.read_bytes()
    try:
        for retry in (retry_failed_job, retry_failed, extraction.retry_failed):
            with pytest.raises((QueueError, ValueError), match="bound_retry_required"):
                retry(source["job_id"]) if retry == extraction.retry_failed else retry(str(tmp_path), source["job_id"])
            assert path.read_bytes() == before
        assert _read(path)["status"] == status
        if job:
            assert recover_stale_jobs(str(tmp_path), processing_ttl_s=-1) == 0
            assert path.read_bytes() == before and _claim(tmp_path, store, source) is None
    finally:
        if job:
            mark_job_failed(str(tmp_path), job.job_id, "owner completed test", worker_id=job.worker_id, attempt_id=job.attempt_id)
            release_job_attempt(job.attempt_id)


def test_full_legacy_writer_receipts_without_plan_or_identity_step_close_display_and_badge(tmp_path, monkeypatch):
    from src.jobcontroller.api import get_job_evidence
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch)
    result = rules.retry_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"])
    assert result.cases[0].completed
    state_files = []
    for source in case["sources"]:
        path = tmp_path / "jobs" / f"{source['job_id']}.json"
        state = _read(path)
        state.pop("output_plan")
        state["steps"] = [step for step in state["steps"] if step["step"] != "assay_identity_changes"]
        _write(path, state)
        assert get_job_evidence(tmp_path, source["job_id"], include_context=False).store_path == ""
        assert _receipt(tmp_path, store, source)["kind"] == "legacy_sqlite_receipt"
        state_files.append((path, path.read_bytes()))
    before = store.read_bytes()
    item = rules.list_identity_case_items(store_path=str(store))[0]
    assert item.completed and item.status == "Erledigt" and all(row.done for row in item.sources)
    assert rules.get_identity_case_count(store_path=str(store)) == 0
    assert rules.prepare_identity_retry(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"]) == ()
    assert store.read_bytes() == before and all(path.read_bytes() == raw for path, raw in state_files)


def test_bound_manual_submit_freezes_original_device_after_default_changes_before_actual_pipeline(tmp_path, monkeypatch):
    from src.processing import service
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch, queued=False)
    source = case["sources"][0]
    assert extraction.enqueue_manual_pdfs((str(first),)).queued == 1
    current, calls = [source["device_id"]], []
    def default_device(root, *, store_spec):
        calls.append((current[0], str(store_spec["path"])))
        return current[0]
    monkeypatch.setattr("src.runtime.devices.get_default_device_id", default_device)
    real_verify = service.verify_job_content_sha256
    def change_default_after_claim(root, job_id, *, claim_lock_ttl_s=None):
        real_verify(root, job_id, claim_lock_ttl_s=claim_lock_ttl_s)
        current[0] = "new-default-device"
    monkeypatch.setattr(service, "verify_job_content_sha256", change_default_after_claim)
    result = extraction.process_next()
    assert result.queue_status == result.submit_status == "DONE" and current[0] == "new-default-device"
    assert calls == [(source["device_id"], str(store))]
    with sqlite3.connect(store) as conn:
        assert {row[0] for row in conn.execute("SELECT device_id FROM runs")} == {source["device_id"]}
    assert rules.list_identity_case_items(store_path=str(store))[0].completed


def test_bound_direct_pipeline_freezes_device_across_lock_acquisition_and_default_change(tmp_path, monkeypatch):
    from src.jobcontroller.jobcontroller import JobController
    store, rules, extraction, case, first, second, settings = _flow(tmp_path, monkeypatch, queued=False)
    source = case["sources"][0]
    current, reads = [source["device_id"]], []
    def default_device(root, *, store_spec):
        reads.append(current[0])
        return current[0]
    monkeypatch.setattr("src.runtime.devices.get_default_device_id", default_device)
    original_lock = JobController._acquire_lock
    def lock_then_change_default(self, path, ttl, *, bound=False):
        lease = original_lock(self, path, ttl, bound=bound)
        current[0] = "changed-while-acquiring-pipeline-lock"
        return lease
    monkeypatch.setattr(JobController, "_acquire_lock", lock_then_change_default)
    result = submit(source["pdf_path"], str(tmp_path), sqlite_path=str(store), expected_sha256=source["pdf_sha256"])
    assert result.status == "DONE" and reads == [source["device_id"]]
    with sqlite3.connect(store) as conn:
        assert {row[0] for row in conn.execute("SELECT device_id FROM runs")} == {source["device_id"]}
    state = _read(tmp_path / "jobs" / f"{source['job_id']}.json")
    assert state["device_id"] == source["device_id"] and _receipt(tmp_path, store, source)["complete"]
