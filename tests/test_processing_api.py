from __future__ import annotations

from pathlib import Path

import pytest

from interfaces.common.queue_worker import (
    QueueWorkerConfig,
    QueueWorkerResult,
    default_worker_id,
    process_next_pending as adapter_process_next_pending,
)
from src.jobcontroller.model import JobResult
from src.jobqueue.api import enqueue_pdf_job, list_jobs
from src.processing.api import (
    ProcessingConfig,
    ProcessingResult,
    config_from_runtime_defaults,
    enqueue_pdf,
    list_processing_jobs,
    process_next_pending,
    retry_failed,
)


def _setup_job(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "proj"
    root.mkdir(parents=True, exist_ok=True)
    pdf = root / "sample.pdf"
    pdf.write_bytes(b"pdf-content")
    enqueue_pdf_job(str(root), str(pdf))
    return root, pdf


def test_adapter_reexports_match_processing_api(tmp_path: Path) -> None:
    root_a, _pdf_a = _setup_job(tmp_path / "a")
    root_b, _pdf_b = _setup_job(tmp_path / "b")
    config = ProcessingConfig(output_mode="both", sqlite_path=str(root_a / "out.sqlite3"))
    adapter_config = QueueWorkerConfig(output_mode="both", sqlite_path=str(root_b / "out.sqlite3"))

    direct = process_next_pending(root_a, config, worker_id="w-test", submit_func=_fail_submit)
    adapted = adapter_process_next_pending(root_b, adapter_config, worker_id="w-test", submit_func=_fail_submit)

    assert isinstance(direct, ProcessingResult)
    assert isinstance(adapted, QueueWorkerResult)
    assert direct.processed == adapted.processed
    assert direct.queue_status == adapted.queue_status
    assert default_worker_id()


def test_process_next_uses_runtime_submit_when_submit_func_is_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, pdf = _setup_job(tmp_path)
    config = ProcessingConfig(output_mode="both", sqlite_path=str(root / "out.sqlite3"))

    monkeypatch.setattr(
        "src.processing.service.submit",
        lambda *_args, **_kwargs: JobResult(
            job_id="x",
            pdf_path=str(pdf),
            status="DONE",
            details={},
        ),
    )

    result = process_next_pending(root, config, worker_id="w-default", submit_func=None)

    assert result.processed is True
    assert result.submit_status == "DONE"
    assert result.queue_status == "DONE"


def test_process_next_marks_done_on_submit_done(tmp_path: Path) -> None:
    root, pdf = _setup_job(tmp_path)
    config = ProcessingConfig(output_mode="both", sqlite_path=str(root / "out.sqlite3"))

    result = process_next_pending(
        root,
        config,
        worker_id="w-done",
        submit_func=lambda *_args, **_kwargs: JobResult(
            job_id="x",
            pdf_path=str(pdf),
            status="DONE",
            details={},
        ),
    )

    assert result.processed is True
    assert result.submit_status == "DONE"
    assert result.queue_status == "DONE"
    assert list_jobs(str(root))[0].status == "DONE"


def test_process_next_marks_failed_on_submit_failed(tmp_path: Path) -> None:
    root, pdf = _setup_job(tmp_path)
    config = ProcessingConfig(output_mode="both", sqlite_path=str(root / "out.sqlite3"))

    result = process_next_pending(
        root,
        config,
        worker_id="w-failed",
        submit_func=lambda *_args, **_kwargs: JobResult(
            job_id="x",
            pdf_path=str(pdf),
            status="FAILED",
            details={"error": "pipeline_error"},
        ),
    )

    assert result.processed is True
    assert result.submit_status == "FAILED"
    assert result.queue_status == "FAILED"
    assert list_jobs(str(root))[0].last_error == "pipeline_error"


def test_process_next_marks_done_on_skipped_already_done(tmp_path: Path) -> None:
    root, pdf = _setup_job(tmp_path)
    config = ProcessingConfig(output_mode="both", sqlite_path=str(root / "out.sqlite3"))

    result = process_next_pending(
        root,
        config,
        worker_id="w-skip",
        submit_func=lambda *_args, **_kwargs: JobResult(
            job_id="x",
            pdf_path=str(pdf),
            status="SKIPPED",
            details={"reason": "already_done"},
        ),
    )

    assert result.processed is True
    assert result.submit_status == "SKIPPED"
    assert result.queue_status == "DONE"


def test_process_next_requeues_deferred_skip(tmp_path: Path) -> None:
    root, pdf = _setup_job(tmp_path)
    config = ProcessingConfig(output_mode="both", sqlite_path=str(root / "out.sqlite3"))

    result = process_next_pending(
        root,
        config,
        worker_id="w-deferred",
        submit_func=lambda *_args, **_kwargs: JobResult(
            job_id="x",
            pdf_path=str(pdf),
            status="SKIPPED",
            details={"reason": "locked"},
        ),
    )

    assert result.processed is True
    assert result.queue_status == "PENDING"
    assert list_jobs(str(root))[0].last_error == "deferred:locked"


def test_process_next_marks_failed_on_submit_exception(tmp_path: Path) -> None:
    root, _pdf = _setup_job(tmp_path)
    config = ProcessingConfig(output_mode="both", sqlite_path=str(root / "out.sqlite3"))

    result = process_next_pending(root, config, worker_id="w-exc", submit_func=_boom_submit)

    assert result.processed is True
    assert result.submit_status == "FAILED"
    assert result.queue_status == "FAILED"
    assert "worker_submit_error" in result.message


def test_enqueue_list_retry_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "retry.pdf"
    pdf.write_bytes(b"retry")

    job = enqueue_pdf(root, str(pdf), source="manual")
    jobs = list_processing_jobs(root)
    assert len(jobs) == 1
    assert jobs[0].job_id == job.job_id
    assert jobs[0].status == "PENDING"

    claimed = process_next_pending(
        root,
        ProcessingConfig(output_mode="both", sqlite_path=str(root / "out.sqlite3")),
        worker_id="w1",
        submit_func=_fail_submit,
    )
    assert claimed.queue_status == "FAILED"

    retried = retry_failed(root, job.job_id)
    assert retried.status == "PENDING"


def test_config_from_runtime_defaults_uses_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARE_OUTPUT_MODE", "sqlite")
    monkeypatch.setenv("ARE_SQLITE_PATH", str(tmp_path / "custom.sqlite3"))
    monkeypatch.setenv("ARE_DEVICE_ID", "analyzer_i_1")

    cfg = config_from_runtime_defaults(tmp_path)

    assert cfg.output_mode == "sqlite"
    assert cfg.sqlite_path == str(tmp_path / "custom.sqlite3")
    assert cfg.device_id == "analyzer_i_1"


def _fail_submit(*_args, **_kwargs) -> JobResult:
    return JobResult(job_id="x", pdf_path="", status="FAILED", details={"error": "boom"})


def _boom_submit(*_args, **_kwargs) -> JobResult:
    raise RuntimeError("submit exploded")
