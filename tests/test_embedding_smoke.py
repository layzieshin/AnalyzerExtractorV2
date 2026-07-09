from __future__ import annotations

from pathlib import Path

from src.contentsplitter.api import AssayDescriptor
from src.extractor.api import AssayRecord, ExtractionError
from src.jobcontroller.api import JobResult, submit
from src.jobqueue.api import QueueJob, claim_next_job, list_jobs, mark_job_done, mark_job_failed, mark_job_pending, recover_stale_jobs
from src.ruleresolver.api import RuleResolverError, RuleSet, resolve_ruleset, validate_rules_integrity
from src.rulesuite.api import HEADER_FIELD_KEYS, REQUIRED_HEADER_FIELD_KEYS, check_required_fields, create_draft, create_draft_from_template, list_rulesets, preview_extract
from src.runtime.api import (
    RuntimeConfig,
    is_stale_lock,
    load_runtime_config,
    release_exclusive,
    resolve_app_root,
    try_acquire_exclusive,
)
from src.testui.api import classify_job_outcome, format_rules_report, format_write_outputs
from src.watchdog.api import run_watchdog_forever, scan_watch_once


def test_public_embedding_imports_are_available() -> None:
    assert submit is not None
    assert resolve_ruleset is not None
    assert validate_rules_integrity is not None
    assert scan_watch_once is not None
    assert run_watchdog_forever is not None
    assert claim_next_job is not None
    assert mark_job_done is not None
    assert mark_job_failed is not None
    assert mark_job_pending is not None
    assert recover_stale_jobs is not None
    assert list_jobs is not None
    assert create_draft is not None
    assert preview_extract is not None
    assert list_rulesets is not None
    assert classify_job_outcome is not None
    assert format_rules_report is not None
    assert format_write_outputs is not None
    assert HEADER_FIELD_KEYS
    assert REQUIRED_HEADER_FIELD_KEYS
    assert check_required_fields is not None
    assert create_draft_from_template is not None


def test_public_embedding_types_are_exported() -> None:
    assert JobResult.__name__ == "JobResult"
    assert QueueJob.__name__ == "QueueJob"
    assert RuleSet.__name__ == "RuleSet"
    assert AssayRecord.__name__ == "AssayRecord"
    assert AssayDescriptor.__name__ == "AssayDescriptor"
    assert issubclass(RuleResolverError, RuntimeError)
    assert issubclass(ExtractionError, RuntimeError)


def test_runtime_api_respects_are_home(tmp_path: Path, monkeypatch) -> None:
    runtime_home = tmp_path / "embedded-home"
    monkeypatch.setenv("ARE_HOME", str(runtime_home))

    assert resolve_app_root(__file__) == runtime_home.resolve()

    cfg = load_runtime_config(runtime_home)
    assert isinstance(cfg, RuntimeConfig)
    assert str(runtime_home / "output" / "final" / "results.sqlite3") == cfg.sqlite_path
    assert str(runtime_home / "input" / "watch") == cfg.watch_dir


def test_runtime_lock_helpers_work_for_embedding(tmp_path: Path) -> None:
    lock_path = tmp_path / "lockfile.lock"

    assert try_acquire_exclusive(lock_path, 60.0) is True
    assert is_stale_lock(lock_path, 60.0) is False
    release_exclusive(lock_path)
