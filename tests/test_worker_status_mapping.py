from pathlib import Path

from interfaces.headless import worker
from src.jobcontroller.model import JobResult
from src.jobqueue.api import enqueue_pdf_job, list_jobs


def test_worker_requeues_locked_skip(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "a.pdf"
    pdf.write_bytes(b"pdf-a")
    _ = enqueue_pdf_job(str(root), str(pdf))

    monkeypatch.setattr(
        worker,
        "submit",
        lambda *_args, **_kwargs: JobResult(
            job_id="x",
            pdf_path=str(pdf),
            status="SKIPPED",
            details={"reason": "locked"},
        ),
    )

    processed = worker.run_once(root)
    assert processed is True

    jobs = list_jobs(str(root))
    assert jobs[0].status == "PENDING"
    assert "deferred:locked" in jobs[0].last_error


def test_worker_passes_configured_device_id_to_submit(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "a.pdf"
    pdf.write_bytes(b"pdf-a")
    _ = enqueue_pdf_job(str(root), str(pdf))
    monkeypatch.setenv("ARE_DEVICE_ID", "analyzer_i_1")
    seen: dict[str, object] = {}

    def _submit(*_args, **kwargs):
        seen.update(kwargs)
        return JobResult(
            job_id="x",
            pdf_path=str(pdf),
            status="DONE",
            details={},
        )

    monkeypatch.setattr(worker, "submit", _submit)

    processed = worker.run_once(root)

    assert processed is True
    assert seen["device_id"] == "analyzer_i_1"


def test_worker_passes_none_device_id_without_env(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "a.pdf"
    pdf.write_bytes(b"pdf-a")
    _ = enqueue_pdf_job(str(root), str(pdf))
    monkeypatch.delenv("ARE_DEVICE_ID", raising=False)
    seen: dict[str, object] = {}

    def _submit(*_args, **kwargs):
        seen.update(kwargs)
        return JobResult(
            job_id="x",
            pdf_path=str(pdf),
            status="DONE",
            details={},
        )

    monkeypatch.setattr(worker, "submit", _submit)

    processed = worker.run_once(root)

    assert processed is True
    assert seen["device_id"] is None
