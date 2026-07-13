import time
from pathlib import Path

from src.jobqueue.api import list_jobs
from src.watchdog.service import WatchdogService


def test_watchdog_creates_queue_job_for_stable_pdf(tmp_path: Path):
    root = tmp_path / "proj"
    watch = root / "watch"
    watch.mkdir(parents=True)
    pdf = watch / "new.pdf"
    pdf.write_bytes(b"x")

    svc = WatchdogService(str(root), str(watch), scan_interval_s=0.01, stable_window_s=0.01)
    _ = svc.scan_once()
    time.sleep(0.02)
    _ = svc.scan_once()

    jobs = list_jobs(str(root))
    assert len(jobs) == 1
    assert jobs[0].pdf_path == str(pdf)


def test_watchdog_zero_stable_window_queues_existing_pdf_on_first_scan(tmp_path: Path):
    root = tmp_path / "proj"
    watch = root / "watch"
    watch.mkdir(parents=True)
    pdf = watch / "ready.pdf"
    pdf.write_bytes(b"x")

    svc = WatchdogService(str(root), str(watch), scan_interval_s=0.01, stable_window_s=0)
    created = svc.scan_once()

    jobs = list_jobs(str(root))
    assert len(created) == 1
    assert len(jobs) == 1
    assert jobs[0].pdf_path == str(pdf)
