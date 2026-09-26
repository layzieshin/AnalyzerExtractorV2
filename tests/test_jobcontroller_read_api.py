from __future__ import annotations

import json
from pathlib import Path

from src.jobcontroller.api import get_job_evidence


def test_get_job_evidence_returns_none_for_empty_job_id(tmp_path: Path) -> None:
    assert get_job_evidence(tmp_path, "") is None


def test_get_job_evidence_reports_missing_state(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "jobs").mkdir(parents=True)
    evidence = get_job_evidence(root, "missing-job")
    assert evidence is not None
    assert evidence.state_available is False
    assert evidence.job_id == "missing-job"


def test_get_job_evidence_extracts_dump_paths(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    jobs = root / "jobs"
    jobs.mkdir(parents=True)
    normalized = jobs / "job1_normalized.txt"
    normalized.write_text("line", encoding="utf-8")
    block_dump = jobs / "job1_block_a.txt"
    block_dump.write_text("block", encoding="utf-8")
    state = {
        "job_id": "job1",
        "pdf_path": str(root / "sample.pdf"),
        "status": "FAILED",
        "error": "no_assay_detected",
        "steps": [
            {
                "step": "debug",
                "normalized_dump": str(normalized),
                "block_dumps": {"(1111)": str(block_dump)},
            }
        ],
    }
    (jobs / "job1.json").write_text(json.dumps(state), encoding="utf-8")

    evidence = get_job_evidence(root, "job1")
    assert evidence is not None
    assert evidence.state_available is True
    assert evidence.normalized_dump_path == str(normalized)
    assert evidence.block_dump_paths == (("(1111)", str(block_dump)),)
    assert evidence.error == "no_assay_detected"
    assert evidence.context_available is True
    assert "line" in evidence.context_text
    assert evidence.context_truncated is False


def test_get_job_evidence_rejects_path_traversal_job_ids(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "jobs").mkdir(parents=True)
    for job_id in ("../x", "..\\x", "/etc/passwd", "C:\\Windows\\win.ini"):
        assert get_job_evidence(root, job_id) is None


def test_get_job_evidence_rejects_escaped_artifact_reference(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    jobs = root / "jobs"
    jobs.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    state = {
        "job_id": "job1",
        "pdf_path": str(root / "sample.pdf"),
        "status": "FAILED",
        "error": "no_assay_detected",
        "steps": [{"step": "debug", "normalized_dump": str(outside)}],
    }
    (jobs / "job1.json").write_text(json.dumps(state), encoding="utf-8")

    evidence = get_job_evidence(root, "job1")
    assert evidence is not None
    assert evidence.normalized_dump_path == ""
    assert evidence.context_available is False
    assert evidence.context_text == ""


def test_get_job_evidence_truncates_large_context(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    jobs = root / "jobs"
    jobs.mkdir(parents=True)
    normalized = jobs / "job1_normalized.txt"
    normalized.write_text("x" * 40000, encoding="utf-8")
    state = {
        "job_id": "job1",
        "pdf_path": str(root / "sample.pdf"),
        "status": "FAILED",
        "error": "no_assay_detected",
        "steps": [{"step": "debug", "normalized_dump": str(normalized)}],
    }
    (jobs / "job1.json").write_text(json.dumps(state), encoding="utf-8")

    evidence = get_job_evidence(root, "job1")
    assert evidence is not None
    assert evidence.context_available is True
    assert evidence.context_truncated is True
    assert len(evidence.context_text) == 32000


def test_read_bounded_text_reads_at_most_max_plus_one(tmp_path: Path, monkeypatch) -> None:
    from src.jobcontroller.jobcontroller import _read_bounded_text

    big = tmp_path / "big.txt"
    big.write_text("x" * 100000, encoding="utf-8")
    read_sizes: list[int] = []
    real_open = Path.open

    def tracking_open(self, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)
        original_read = handle.read

        def wrapped(size: int = -1) -> str:
            read_sizes.append(size)
            return original_read(size)

        handle.read = wrapped  # type: ignore[method-assign]
        return handle

    monkeypatch.setattr(Path, "open", tracking_open)
    text, truncated = _read_bounded_text(big, max_chars=32000)
    assert truncated is True
    assert len(text) == 32000
    assert read_sizes == [32001]


def test_get_job_evidence_uses_block_label_when_normalized_empty(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    jobs = root / "jobs"
    jobs.mkdir(parents=True)
    normalized = jobs / "job1_normalized.txt"
    normalized.write_text("", encoding="utf-8")
    block_dump = jobs / "job1_block_a.txt"
    block_dump.write_text("block-content", encoding="utf-8")
    state = {
        "job_id": "job1",
        "pdf_path": str(root / "sample.pdf"),
        "status": "FAILED",
        "error": "no_assay_detected",
        "steps": [
            {
                "step": "debug",
                "normalized_dump": str(normalized),
                "block_dumps": {"(1111)": str(block_dump)},
            }
        ],
    }
    (jobs / "job1.json").write_text(json.dumps(state), encoding="utf-8")

    evidence = get_job_evidence(root, "job1")
    assert evidence is not None
    assert evidence.context_source_label == "Assay-Block (1111)"
    assert evidence.context_text == "block-content"
