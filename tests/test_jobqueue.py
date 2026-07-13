import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.jobqueue.api import (
    claim_next_job,
    enqueue_pdf_job,
    list_jobs,
    mark_job_done,
    mark_job_failed,
    mark_job_pending,
    recover_stale_jobs,
    retry_failed_job,
)
from src.jobqueue.queue import JobQueue


def test_queue_lifecycle_done(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "a.pdf"
    pdf.write_bytes(b"pdf-a")

    enq = enqueue_pdf_job(str(root), str(pdf))
    assert enq.status == "PENDING"

    claimed = claim_next_job(str(root), worker_id="w1")
    assert claimed is not None
    assert claimed.status == "PROCESSING"

    done = mark_job_done(str(root), claimed.job_id)
    assert done.status == "DONE"


def test_queue_failed_status(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "b.pdf"
    pdf.write_bytes(b"pdf-b")

    enq = enqueue_pdf_job(str(root), str(pdf))
    claimed = claim_next_job(str(root), worker_id="w2")
    assert claimed is not None
    failed = mark_job_failed(str(root), enq.job_id, "x")
    assert failed.status == "FAILED"
    assert failed.last_error == "x"

    all_jobs = list_jobs(str(root))
    assert len(all_jobs) == 1


def test_queue_can_requeue_processing_job(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "c.pdf"
    pdf.write_bytes(b"pdf-c")

    enq = enqueue_pdf_job(str(root), str(pdf))
    claimed = claim_next_job(str(root), worker_id="w3")
    assert claimed is not None
    repending = mark_job_pending(str(root), enq.job_id, "deferred:locked", worker_id="w3")
    assert repending.status == "PENDING"


def test_recover_stale_processing_jobs(tmp_path: Path):
    root = tmp_path / "proj"
    queue = root / "jobs" / "queue"
    queue.mkdir(parents=True)
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    payload = {
        "job_id": "deadbeefdeadbeef",
        "pdf_path": str(root / "d.pdf"),
        "status": "PROCESSING",
        "created_at": old,
        "updated_at": old,
        "source": "watchdog",
        "worker_id": "worker-x",
        "attempts": 1,
        "last_error": "",
    }
    (queue / "deadbeefdeadbeef.json").write_text(json.dumps(payload), encoding="utf-8")

    n = recover_stale_jobs(str(root), processing_ttl_s=1.0)
    assert n == 1
    jobs = list_jobs(str(root))
    assert jobs[0].status == "PENDING"


def test_orphaned_claim_lock_does_not_block_stale_recovery(tmp_path: Path):
    root = tmp_path / "proj"
    queue = root / "jobs" / "queue"
    lock_dir = root / "jobs" / "queue_locks"
    queue.mkdir(parents=True)
    lock_dir.mkdir(parents=True)
    job_id = "deadbeefdeadbeef"
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    payload = {
        "job_id": job_id,
        "pdf_path": str(root / "d.pdf"),
        "status": "PROCESSING",
        "created_at": old,
        "updated_at": old,
        "source": "watchdog",
        "worker_id": "worker-x",
        "attempts": 1,
        "last_error": "",
    }
    (queue / f"{job_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    orphan_lock = lock_dir / f"{job_id}.claim.lock"
    orphan_lock.write_text("", encoding="utf-8")
    stale_mtime = time.time() - 300.0
    os.utime(orphan_lock, (stale_mtime, stale_mtime))

    n = recover_stale_jobs(str(root), processing_ttl_s=1.0, claim_lock_ttl_s=10.0)
    assert n == 1
    jobs = list_jobs(str(root))
    assert jobs[0].status == "PENDING"
    assert jobs[0].last_error == "stale_processing_requeued"
    assert not orphan_lock.exists()


def test_enqueue_failed_job_stays_failed_until_explicit_retry(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "e.pdf"
    pdf.write_bytes(b"pdf-e")

    enq = enqueue_pdf_job(str(root), str(pdf))
    claimed = claim_next_job(str(root), worker_id="w4")
    assert claimed is not None
    mark_job_failed(str(root), enq.job_id, "boom", worker_id="w4")

    still_failed = enqueue_pdf_job(str(root), str(pdf))
    assert still_failed.status == "FAILED"
    assert still_failed.last_error == "boom"

    again = enqueue_pdf_job(str(root), str(pdf))
    assert again.status == "FAILED"
    assert len(list_jobs(str(root))) == 1


def test_retry_failed_job_resets_failed_job(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "retry.pdf"
    pdf.write_bytes(b"pdf-retry")

    enq = enqueue_pdf_job(str(root), str(pdf))
    claimed = claim_next_job(str(root), worker_id="w-retry")
    assert claimed is not None
    mark_job_failed(str(root), enq.job_id, "no_assay_detected", worker_id="w-retry")

    retried = retry_failed_job(str(root), enq.job_id, reason="retry_requested_by_user")

    assert retried.status == "PENDING"
    assert retried.attempts == 0
    assert retried.worker_id == ""
    assert retried.last_error == "retry_requested_by_user"


def test_retry_failed_job_rejects_non_failed_statuses(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    pdf_done = root / "done.pdf"
    pdf_pending = root / "pending.pdf"
    pdf_processing = root / "processing.pdf"
    pdf_done.write_bytes(b"pdf-done")
    pdf_pending.write_bytes(b"pdf-pending")
    pdf_processing.write_bytes(b"pdf-processing")

    done = enqueue_pdf_job(str(root), str(pdf_done))
    claimed_done = claim_next_job(str(root), worker_id="w-done")
    assert claimed_done is not None
    mark_job_done(str(root), done.job_id, worker_id="w-done")

    pending = enqueue_pdf_job(str(root), str(pdf_pending))
    processing = enqueue_pdf_job(str(root), str(pdf_processing))
    claimed_processing = claim_next_job(str(root), worker_id="w-processing")
    assert claimed_processing is not None

    for job_id in (done.job_id, pending.job_id, processing.job_id):
        try:
            retry_failed_job(str(root), job_id)
        except Exception as e:
            assert "job_not_failed" in str(e)
        else:
            raise AssertionError("retry_failed_job accepted non-FAILED job")


def test_retry_failed_job_rejects_unknown_job_id(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()

    try:
        retry_failed_job(str(root), "missing")
    except Exception as e:
        assert "job_not_found: missing" in str(e)
    else:
        raise AssertionError("retry_failed_job accepted unknown job")


def test_max_attempts_blocks_further_claims(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "f.pdf"
    pdf.write_bytes(b"pdf-f")

    queue = JobQueue(max_attempts=2, claim_lock_ttl_s=10.0)
    queue.enqueue_pdf_job(str(root), str(pdf))

    first = queue.claim_next_job(str(root), worker_id="w5")
    assert first is not None
    queue.mark_job_pending(str(root), first.job_id, "retry", worker_id="w5")

    second = queue.claim_next_job(str(root), worker_id="w5")
    assert second is not None
    queue.mark_job_pending(str(root), second.job_id, "retry", worker_id="w5")

    third = queue.claim_next_job(str(root), worker_id="w5")
    assert third is None
    jobs = queue.list_jobs(str(root))
    assert jobs[0].status == "FAILED"
    assert jobs[0].last_error == "max_attempts_exceeded"
    assert jobs[0].attempts == 3


def test_watchdog_does_not_requeue_failed_when_max_attempts_exceeded(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "g.pdf"
    pdf.write_bytes(b"pdf-g")

    queue = JobQueue(max_attempts=1, claim_lock_ttl_s=10.0)
    queue.enqueue_pdf_job(str(root), str(pdf))
    claimed = queue.claim_next_job(str(root), worker_id="w6")
    assert claimed is not None
    queue.mark_job_failed(str(root), claimed.job_id, "fatal", worker_id="w6")

    jobs_before = queue.list_jobs(str(root))
    assert jobs_before[0].status == "FAILED"
    assert jobs_before[0].attempts == 1

    requeued = queue.enqueue_pdf_job(str(root), str(pdf))
    assert requeued.status == "FAILED"
    assert requeued.last_error == "fatal"


def test_parallel_claim_assigns_each_job_once(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    pdf_a = root / "h1.pdf"
    pdf_b = root / "h2.pdf"
    pdf_a.write_bytes(b"pdf-h1")
    pdf_b.write_bytes(b"pdf-h2")

    queue = JobQueue(claim_lock_ttl_s=10.0)
    queue.enqueue_pdf_job(str(root), str(pdf_a))
    queue.enqueue_pdf_job(str(root), str(pdf_b))
    queue.recover_stale_jobs(str(root), processing_ttl_s=9999.0)

    results: list = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def worker(wid: str) -> None:
        try:
            barrier.wait()
            job = queue.claim_next_job(str(root), worker_id=wid)
            results.append(job)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=("w-a",))
    t2 = threading.Thread(target=worker, args=("w-b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    claimed = [j for j in results if j is not None]
    assert len(claimed) == 2
    assert len({j.job_id for j in claimed}) == 2
    assert all(j.status == "PROCESSING" for j in claimed)
