"""Phase 0 characterization tests for V2.1 UI migration baseline.

These tests document Ist-contracts without changing product behavior.
Activation or rule-inventory writes run only in isolated temporary project roots.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interfaces.common.queue_worker import QueueWorkerConfig, process_next_pending
from src.jobqueue.api import enqueue_pdf_job, list_jobs
from src.resultstore import api as resultstore_api
from src.runtime.config import VALID_OUTPUT_MODES, load_runtime_config

_REQUIRED_RESULTSTORE_READ_EXPORTS = {
    "get_result_run",
    "get_result_store_status",
    "list_result_assays",
    "list_result_charges",
    "list_result_runs",
}
_FORBIDDEN_RESULTSTORE_MUTATION_EXPORTS = {
    "write_result_run",
    "insert_result_run",
    "update_result_run",
    "delete_result_run",
    "save_result_run",
    "relocate_result_run",
    "relocate_run",
}


def test_resultstore_public_api_is_read_only() -> None:
    public_names = set(resultstore_api.__all__)
    lowered = {name.lower() for name in public_names}
    write_like = {
        name
        for name in lowered
        if any(token in name for token in ("write", "insert", "update", "delete", "save", "relocate"))
    }
    assert write_like == set()
    assert _REQUIRED_RESULTSTORE_READ_EXPORTS.issubset(public_names)
    assert public_names.isdisjoint(_FORBIDDEN_RESULTSTORE_MUTATION_EXPORTS)


def test_runtime_config_exposes_output_mode_and_sqlite_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARE_OUTPUT_MODE", "sqlite")
    monkeypatch.setenv("ARE_SQLITE_PATH", str(tmp_path / "custom" / "store.sqlite3"))

    cfg = load_runtime_config(tmp_path)

    assert cfg.output_mode == "sqlite"
    assert cfg.sqlite_path == str(tmp_path / "custom" / "store.sqlite3")
    assert cfg.output_mode in VALID_OUTPUT_MODES
    assert cfg.enable_sqlite is True
    assert cfg.enable_excel is False


def test_runtime_config_default_output_mode_is_both(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARE_OUTPUT_MODE", raising=False)
    cfg = load_runtime_config(tmp_path)
    assert cfg.output_mode == "both"
    assert cfg.enable_excel is True
    assert cfg.enable_sqlite is True


def test_enqueue_paths_passes_all_manual_selections_to_queue(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from interfaces.tk.test_app import TestApp

    root = tmp_path / "proj"
    root.mkdir()
    pdfs = []
    for idx in range(3):
        pdf = root / f"manual_{idx}.pdf"
        pdf.write_bytes(f"manual-pdf-{idx}".encode())
        pdfs.append(pdf)

    fake = SimpleNamespace(project_root=root, _log=lambda _msg: None)

    queued_count, skipped_count, error_count = TestApp._enqueue_paths(
        fake,
        [str(pdf) for pdf in pdfs],
        source="test-app-manual",
    )

    jobs = list_jobs(str(root))
    assert queued_count == 3
    assert skipped_count == 0
    assert error_count == 0
    assert len(jobs) == 3
    assert {job.pdf_path for job in jobs} == {str(pdf) for pdf in pdfs}
    assert all(job.source == "test-app-manual" for job in jobs)
    assert all(job.status == "PENDING" for job in jobs)


def test_pick_manual_files_uses_same_enqueue_paths_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import MethodType, SimpleNamespace

    from interfaces.tk import test_app
    from interfaces.tk.test_app import TestApp

    root = tmp_path / "proj"
    root.mkdir()
    pdfs = []
    for idx in range(3):
        pdf = root / f"picked_{idx}.pdf"
        pdf.write_bytes(f"picked-{idx}".encode())
        pdfs.append(pdf)

    monkeypatch.setattr(
        test_app.filedialog,
        "askopenfilenames",
        lambda **_kwargs: tuple(str(pdf) for pdf in pdfs),
    )

    fake = SimpleNamespace(
        project_root=root,
        _log=lambda _msg: None,
        refresh_queue=lambda: None,
    )
    fake._enqueue_paths = MethodType(TestApp._enqueue_paths, fake)

    TestApp.pick_manual_files(fake)

    jobs = list_jobs(str(root))
    assert len(jobs) == 3
    assert {job.pdf_path for job in jobs} == {str(pdf) for pdf in pdfs}
    assert all(job.source == "test-app-manual" for job in jobs)


def test_queue_worker_reports_no_pending_when_queue_empty(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    config = QueueWorkerConfig(output_mode="both", sqlite_path=str(root / "out.sqlite3"))

    result = process_next_pending(root, config)

    assert result.processed is False
    assert result.message == "no_pending_jobs"


def test_identical_bytes_at_two_paths_share_job_id_and_single_queue_entry(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    content = b"identical-content-bytes"
    pdf_a = root / "dir_a" / "copy_a.pdf"
    pdf_b = root / "dir_b" / "copy_b.pdf"
    pdf_a.parent.mkdir(parents=True)
    pdf_b.parent.mkdir(parents=True)
    pdf_a.write_bytes(content)
    pdf_b.write_bytes(content)
    assert pdf_a.read_bytes() == pdf_b.read_bytes()
    assert pdf_a != pdf_b

    first = enqueue_pdf_job(str(root), str(pdf_a), source="manual")
    second = enqueue_pdf_job(str(root), str(pdf_b), source="manual")

    jobs = list_jobs(str(root))
    queue_files = sorted((root / "jobs" / "queue").glob("*.json"))
    queue_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in queue_files]

    assert first.status == "PENDING"
    assert second.status == "PENDING"
    assert first.job_id == second.job_id
    assert len(jobs) == 1
    assert len(queue_payloads) == 1
    assert jobs[0].pdf_path == str(pdf_a)
    assert second.pdf_path == str(pdf_a)
    assert jobs[0].source == "manual"
    assert all("import_id" not in payload for payload in queue_payloads)
    assert all(not hasattr(job, "import_id") for job in jobs)


def test_same_pdf_path_re_enqueue_returns_existing_job(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "same.pdf"
    pdf.write_bytes(b"identical-content")

    first = enqueue_pdf_job(str(root), str(pdf), source="manual")
    second = enqueue_pdf_job(str(root), str(pdf), source="manual")

    assert first.status == "PENDING"
    assert second.job_id == first.job_id
    jobs = list_jobs(str(root))
    assert len(jobs) == 1


def test_watch_scan_stable_window_defers_processing_until_stable(tmp_path: Path) -> None:
    from interfaces.tk.watch_scan import InAppWatchScanner

    pdf = tmp_path / "incoming.pdf"
    pdf.write_bytes(b"chunk")
    scanner = InAppWatchScanner()

    assert scanner.scan(tmp_path, set(), stable_window_s=1.0, now=10.0).stable_new_paths == []
    assert scanner.scan(tmp_path, set(), stable_window_s=1.0, now=11.0).stable_new_paths == [str(pdf.resolve())]
