import time
from pathlib import Path

import os
import shutil
import subprocess
import sys
import tempfile

import pytest

from src.ingestion.service import IngestionError
from src.jobqueue.api import list_jobs
from src.watchdog.service import WatchdogService


def test_watchdog_creates_queue_job_for_stable_pdf(tmp_path: Path):
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "new.pdf"
    pdf.write_bytes(b"x")

    svc = WatchdogService(
        str(root),
        str(watch),
        scan_interval_s=0.01,
        stable_window_s=0.01,
        watch_backup_path=str(backup),
    )
    _ = svc.scan_once()
    time.sleep(0.02)
    _ = svc.scan_once()

    jobs = list_jobs(str(root))
    assert len(jobs) == 1
    assert jobs[0].pdf_path == str(pdf)
    assert (root / "storage" / "ingestion").is_dir()


def test_watchdog_zero_stable_window_queues_existing_pdf_on_first_scan(tmp_path: Path):
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "ready.pdf"
    pdf.write_bytes(b"x")

    svc = WatchdogService(
        str(root),
        str(watch),
        scan_interval_s=0.01,
        stable_window_s=0,
        watch_backup_path=str(backup),
    )
    created = svc.scan_once()

    jobs = list_jobs(str(root))
    assert len(created) == 1
    assert len(jobs) == 1
    assert jobs[0].pdf_path == str(pdf)


def test_watchdog_without_backup_fails_before_queue(tmp_path: Path):
    root = tmp_path / "proj"
    watch = root / "watch"
    watch.mkdir(parents=True)
    (watch / "new.pdf").write_bytes(b"x")

    svc = WatchdogService(str(root), str(watch), stable_window_s=0)
    with pytest.raises(Exception, match="watch_backup_path_required"):
        svc.scan_once()
    assert list_jobs(str(root)) == []


def test_watchdog_run_forever_propagates_ingestion_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    watch.mkdir(parents=True)
    svc = WatchdogService(str(root), str(watch), scan_interval_s=0.01, stable_window_s=0)

    def boom() -> None:
        raise IngestionError("permanent_config_error")

    monkeypatch.setattr(svc, "scan_once", boom)
    with pytest.raises(IngestionError, match="permanent_config_error"):
        svc.run_forever()


def test_headless_watchdog_once_enabled_requires_two_observations(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    isolated = Path(tempfile.mkdtemp(prefix="are-watchdog-enabled-"))
    try:
        for name in ("src", "interfaces", "watchdog_main.py"):
            src = repo_root / name
            dest = isolated / name
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        home = tmp_path / "are-home"
        watch = home / "input" / "watch"
        backup = home / "backup"
        watch.mkdir(parents=True)
        backup.mkdir(parents=True)
        (watch / "stable.pdf").write_bytes(b"stable")
        settings = home / "storage" / "desktop_settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(
            (
                "{\n"
                f'  "output_mode": "both",\n'
                f'  "sqlite_path": "{str(home / "db.sqlite3").replace(chr(92), "/")}",\n'
                '  "watch_enabled": true,\n'
                f'  "watch_input_path": "{str(watch).replace(chr(92), "/")}",\n'
                f'  "watch_backup_path": "{str(backup).replace(chr(92), "/")}"\n'
                "}\n"
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["ARE_WATCHDOG_ONCE"] = "1"
        env["ARE_HOME"] = str(home)
        env["ARE_WATCH_STABLE_WINDOW_S"] = "0.05"
        result = subprocess.run(
            [sys.executable, str(isolated / "watchdog_main.py")],
            cwd=str(isolated),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert "watch_cycle_complete" in result.stdout
        assert (home / "storage" / "ingestion").is_dir()
        assert list((home / "storage" / "ingestion").glob("*.json"))
    except subprocess.SubprocessError as exc:
        pytest.skip(f"isolated watchdog enabled smoke unavailable: {exc}")
    finally:
        shutil.rmtree(isolated, ignore_errors=True)


def test_headless_watchdog_once_invalid_config_nonzero(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    isolated = Path(tempfile.mkdtemp(prefix="are-watchdog-invalid-"))
    try:
        for name in ("src", "interfaces", "watchdog_main.py"):
            src = repo_root / name
            dest = isolated / name
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        home = tmp_path / "are-home-invalid"
        home.mkdir()
        settings = home / "storage" / "desktop_settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(
            (
                "{\n"
                '  "output_mode": "both",\n'
                f'  "sqlite_path": "{str(home / "db.sqlite3").replace(chr(92), "/")}",\n'
                '  "watch_enabled": true,\n'
                f'  "watch_input_path": "{str(home / "watch").replace(chr(92), "/")}",\n'
                f'  "watch_backup_path": "{str(home / "watch").replace(chr(92), "/")}"\n'
                "}\n"
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["ARE_WATCHDOG_ONCE"] = "1"
        env["ARE_HOME"] = str(home)
        result = subprocess.run(
            [sys.executable, str(isolated / "watchdog_main.py")],
            cwd=str(isolated),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "watch_cycle_error" in result.stderr or "watch_input_backup_same_path" in result.stderr
    except subprocess.SubprocessError as exc:
        pytest.skip(f"isolated watchdog invalid smoke unavailable: {exc}")
    finally:
        shutil.rmtree(isolated, ignore_errors=True)


def test_headless_watchdog_once_disabled_by_default_safe(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    isolated = Path(tempfile.mkdtemp(prefix="are-watchdog-isolated-"))
    try:
        for name in ("src", "interfaces", "watchdog_main.py"):
            src = repo_root / name
            dest = isolated / name
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        env = os.environ.copy()
        env["ARE_WATCHDOG_ONCE"] = "1"
        env["ARE_HOME"] = str(tmp_path / "home")
        result = subprocess.run(
            [sys.executable, str(isolated / "watchdog_main.py")],
            cwd=str(isolated),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert "watch_disabled" in result.stdout
    except subprocess.SubprocessError as exc:
        pytest.skip(f"isolated watchdog smoke unavailable: {exc}")
    finally:
        shutil.rmtree(isolated, ignore_errors=True)
