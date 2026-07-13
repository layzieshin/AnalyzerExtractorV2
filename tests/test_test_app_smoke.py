import json
import tkinter as tk
from pathlib import Path

import pytest

from interfaces.tk import test_app


def test_test_app_sections_are_defined() -> None:
    assert test_app.SECTION_KEYS == ("EXTRACTOR", "OPTIONS", "RULE SUITE", "LOGS", "DUPLIKATE", "ADMIN")


def test_test_app_class_constructable_when_tk_available(tmp_path) -> None:
    try:
        app = test_app.TestApp(project_root=tmp_path)
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    try:
        assert app.project_root == tmp_path.resolve()
        assert app.project_root / "rules" / "index.json" == tmp_path.resolve() / "rules" / "index.json"
        assert set(app._tabs) == set(test_app.SECTION_KEYS)
    finally:
        app.destroy()


def test_test_app_extractor_uses_friendly_controls_and_columns(tmp_path) -> None:
    try:
        app = test_app.TestApp(project_root=tmp_path)
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    try:
        button_texts = {
            app.btn_scan_watch.cget("text"),
            app.btn_pick_files.cget("text"),
            app.btn_start_extraction.cget("text"),
            app.btn_retry_failed.cget("text"),
            app.btn_refresh_queue.cget("text"),
            app.btn_auto_watch_start.cget("text"),
            app.btn_auto_watch_stop.cget("text"),
        }
        assert "Ergebnisse suchen" in button_texts
        assert app.btn_pick_files.cget("text").startswith("Dateien")
        assert "Extraktion starten" in button_texts
        assert "Erneut starten" in button_texts
        assert app.btn_stop_extraction.cget("text") == "Extraktion stoppen"
        assert app.btn_stop_extraction.cget("state") == tk.DISABLED
        assert "Aktualisieren" in button_texts
        assert "Automatische Suche starten" in button_texts
        assert "Automatische Suche stoppen" in button_texts
        assert "Direkt verarbeiten" not in button_texts
        assert "In Queue stellen" not in button_texts
        assert not hasattr(app, "btn_direct_submit")
        assert not hasattr(app, "btn_enqueue")

        headings = [app.tree_files.heading(col)["text"] for col in app.tree_files["columns"]]
        assert "Herkunft" in headings
        assert "Status" in headings
        assert "Verarbeitung" in headings
        assert "Queue" not in headings
        assert headings[-1] == "Job-ID"
    finally:
        app.destroy()


def test_main_passes_project_root_to_test_app(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeApp:
        def __init__(self, project_root=None) -> None:
            captured["project_root"] = project_root

        def mainloop(self) -> None:
            captured["mainloop"] = True

    monkeypatch.setattr(test_app, "TestApp", FakeApp)

    test_app.main(project_root=tmp_path)

    assert captured["project_root"] == tmp_path
    assert captured["mainloop"] is True


def test_test_app_default_root_uses_are_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ARE_HOME", str(tmp_path))
    try:
        app = test_app.TestApp(project_root=None)
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    try:
        assert app.project_root == tmp_path.resolve()
        assert app.project_root / "rules" / "index.json" == tmp_path.resolve() / "rules" / "index.json"
    finally:
        app.destroy()


def test_test_app_refresh_queue_replaces_temporary_rows_with_worklist(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "queued.pdf"
    queue_job = {
        "job_id": "job1",
        "pdf_path": str(pdf),
        "status": "PENDING",
        "updated_at": "u",
        "source": "test-app-manual",
        "worker_id": "",
        "attempts": 0,
        "last_error": "",
    }
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [queue_job])

    try:
        app = test_app.TestApp(project_root=tmp_path)
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    try:
        app._upsert_file_rows(
            [
                {
                    "file": "temporary.pdf",
                    "path": str(tmp_path / "temporary.pdf"),
                    "source": "manual",
                    "queue_status": "",
                    "job_id": "",
                    "device_id": "",
                    "last_error": "",
                    "action": "bereit",
                }
            ]
        )

        app.refresh_queue()

        assert list(app._watch_rows.values())[0]["job_id"] == "job1"
        assert all(row["job_id"] for row in app._watch_rows.values())
    finally:
        app.destroy()


def test_test_app_worker_config_snapshot_contains_ui_values(tmp_path) -> None:
    try:
        app = test_app.TestApp(project_root=tmp_path)
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    try:
        app.var_output_mode.set("sqlite")
        app.var_sqlite_path.set(str(tmp_path / "out.sqlite3"))

        snapshot = app._build_worker_config_snapshot()

        assert snapshot.output_mode == "sqlite"
        assert snapshot.sqlite_path == str(tmp_path / "out.sqlite3")
        assert snapshot.device_id == app._selected_device_id()
    finally:
        app.destroy()


def test_test_app_auto_watch_start_stop_controls_after_callback(tmp_path) -> None:
    try:
        app = test_app.TestApp(project_root=tmp_path)
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    try:
        app.start_auto_watch()

        assert app._auto_watch_active is True
        assert app._auto_watch_after_id is not None

        app.stop_auto_watch()

        assert app._auto_watch_active is False
        assert app._auto_watch_after_id is None
        assert app.var_auto_watch_status.get() == "Auto-Suche: inaktiv"
    finally:
        app.destroy()


def test_test_app_auto_watch_skips_scan_while_busy(tmp_path) -> None:
    try:
        app = test_app.TestApp(project_root=tmp_path)
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    try:
        watch = tmp_path / "watch"
        watch.mkdir()
        (watch / "sample.pdf").write_bytes(b"a")
        app.var_watch_dir.set(str(watch))
        app._auto_watch_stable_window_s = 0
        app._auto_watch_active = True
        app._busy = True

        app._run_auto_watch_scan()

        assert app._watch_rows == {}
        assert app._auto_watch_after_id is not None
    finally:
        app._busy = False
        app.stop_auto_watch(log=False)
        app.destroy()


def _make_test_app(tmp_path):
    try:
        return test_app.TestApp(project_root=tmp_path)
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")


def test_test_app_refresh_queue_shows_queue_only_rows(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "queued.pdf"
    queue_job = {
        "job_id": "job1",
        "pdf_path": str(pdf),
        "status": "PENDING",
        "updated_at": "u",
        "source": "test-app-auto-watch",
        "worker_id": "",
        "attempts": 0,
        "last_error": "",
    }
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [queue_job])

    app = _make_test_app(tmp_path)
    try:
        app.refresh_queue()

        key = test_app.normalize_file_row_key(pdf)
        assert key in app._watch_rows
        row = app._watch_rows[key]
        assert row["job_id"] == "job1"
        assert row["queue_status"] == "PENDING"
        assert row["source"] == "test-app-auto-watch"
        assert row["action"] == "queued"
    finally:
        app.destroy()


def test_test_app_pick_manual_files_enqueues_immediately(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "manual.pdf"
    pdf.write_bytes(b"pdf")
    enqueue_calls: list[tuple[str, str, str]] = []
    logs: list[str] = []

    def fake_enqueue(project_root: str, pdf_path: str, source: str = "watchdog") -> dict[str, str]:
        enqueue_calls.append((project_root, pdf_path, source))
        return {
            "job_id": "job1",
            "pdf_path": pdf_path,
            "status": "PENDING",
            "updated_at": "u",
            "source": source,
            "worker_id": "",
            "attempts": 0,
            "last_error": "",
        }

    monkeypatch.setattr(test_app, "enqueue_pdf_job", fake_enqueue)
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [])
    monkeypatch.setattr(test_app.filedialog, "askopenfilenames", lambda **_kwargs: (str(pdf),))
    monkeypatch.setattr(test_app.TestApp, "_log", lambda self, message: logs.append(message))

    app = _make_test_app(tmp_path)
    try:
        app.pick_manual_files()

        assert enqueue_calls == [(str(tmp_path.resolve()), str(pdf), "test-app-manual")]
        assert any("Dateien hinzugefügt: 1 PDF(s), vorgemerkt=1, übersprungen=0, Fehler=0" in line for line in logs)
    finally:
        app.destroy()


def test_test_app_enqueue_paths_counts_existing_failed_as_skipped(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    pdf.write_bytes(b"pdf")

    def fake_enqueue(project_root: str, pdf_path: str, source: str = "watchdog") -> dict[str, str]:
        return {
            "job_id": "job1",
            "pdf_path": pdf_path,
            "status": "FAILED",
            "updated_at": "u",
            "source": source,
            "worker_id": "",
            "attempts": 1,
            "last_error": "no_assay_detected",
        }

    monkeypatch.setattr(test_app, "enqueue_pdf_job", fake_enqueue)

    app = _make_test_app(tmp_path)
    try:
        assert app._enqueue_paths((str(pdf),), source="test-app-manual") == (0, 1, 0)
    finally:
        app.destroy()


def test_test_app_auto_watch_enqueues_stable_pdfs(tmp_path, monkeypatch) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    pdf = watch / "sample.pdf"
    pdf.write_bytes(b"pdf")

    enqueue_calls: list[tuple[str, str, str]] = []
    refresh_calls: list[int] = []

    def fake_enqueue(project_root: str, pdf_path: str, source: str = "watchdog") -> dict[str, str]:
        enqueue_calls.append((project_root, pdf_path, source))
        return {
            "job_id": "job1",
            "pdf_path": pdf_path,
            "status": "PENDING",
            "updated_at": "u",
            "source": source,
            "worker_id": "",
            "attempts": 0,
            "last_error": "",
        }

    monkeypatch.setattr(test_app, "enqueue_pdf_job", fake_enqueue)
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [])
    monkeypatch.setattr(test_app.TestApp, "refresh_queue", lambda self: refresh_calls.append(1))

    app = _make_test_app(tmp_path)
    try:
        app.var_watch_dir.set(str(watch))
        app._auto_watch_stable_window_s = 0
        app._auto_watch_active = True
        refresh_calls.clear()

        app._run_auto_watch_scan()

        assert len(enqueue_calls) == 1
        assert enqueue_calls[0][0] == str(tmp_path.resolve())
        assert enqueue_calls[0][2] == "test-app-auto-watch"
        assert refresh_calls == [1]
        assert str(pdf.resolve(strict=False)) in app._auto_watch_suppressed_paths
    finally:
        app.stop_auto_watch(log=False)
        app.destroy()


def test_test_app_auto_watch_known_paths_include_queue_jobs(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "queued.pdf"
    queue_job = {
        "job_id": "job1",
        "pdf_path": str(pdf),
        "status": "PENDING",
        "updated_at": "u",
        "source": "test-app-auto-watch",
        "worker_id": "",
        "attempts": 0,
        "last_error": "",
    }
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [queue_job])

    app = _make_test_app(tmp_path)
    try:
        known = app._build_known_paths_for_scanner()
        assert str(pdf) in known
    finally:
        app.destroy()


def test_test_app_auto_watch_suppresses_repeat_enqueue_in_session(tmp_path, monkeypatch) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    pdf = watch / "sample.pdf"
    pdf.write_bytes(b"pdf")

    enqueue_calls: list[str] = []

    def fake_enqueue(project_root: str, pdf_path: str, source: str = "watchdog") -> dict[str, str]:
        enqueue_calls.append(pdf_path)
        return {
            "job_id": "job1",
            "pdf_path": pdf_path,
            "status": "PENDING",
            "updated_at": "u",
            "source": source,
            "worker_id": "",
            "attempts": 0,
            "last_error": "",
        }

    monkeypatch.setattr(test_app, "enqueue_pdf_job", fake_enqueue)
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [])
    monkeypatch.setattr(test_app.TestApp, "refresh_queue", lambda self: None)

    app = _make_test_app(tmp_path)
    try:
        app.var_watch_dir.set(str(watch))
        app._auto_watch_stable_window_s = 0
        app._auto_watch_active = True

        app._run_auto_watch_scan()
        app._run_auto_watch_scan()

        assert len(enqueue_calls) == 1
    finally:
        app.stop_auto_watch(log=False)
        app.destroy()


def test_test_app_auto_watch_logs_queue_error_but_stays_active(tmp_path, monkeypatch) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    pdf = watch / "sample.pdf"
    pdf.write_bytes(b"pdf")
    logs: list[str] = []

    def fake_enqueue(project_root: str, pdf_path: str, source: str = "watchdog") -> dict[str, str]:
        raise RuntimeError("queue failed")

    monkeypatch.setattr(test_app, "enqueue_pdf_job", fake_enqueue)
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [])
    monkeypatch.setattr(test_app.TestApp, "_log", lambda self, message: logs.append(message))

    app = _make_test_app(tmp_path)
    try:
        app.var_watch_dir.set(str(watch))
        app._auto_watch_stable_window_s = 0
        app._auto_watch_active = True

        app._run_auto_watch_scan()

        assert app._auto_watch_active is True
        assert any("Fehler beim Vormerken" in line for line in logs)
        assert str(pdf.resolve(strict=False)) not in app._auto_watch_suppressed_paths
    finally:
        app.stop_auto_watch(log=False)
        app.destroy()


def test_test_app_start_extraction_reports_empty_worklist(tmp_path, monkeypatch) -> None:
    messages: list[tuple[str, str]] = []

    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [])
    monkeypatch.setattr(test_app, "messagebox", type("MB", (), {"showinfo": staticmethod(lambda title, msg: messages.append((title, msg)))})())

    app = _make_test_app(tmp_path)
    try:
        app.start_extraction()

        assert messages == [("Extraktion", "Keine wartenden Ergebnisse in der Arbeitsliste.")]
    finally:
        app.destroy()


def test_test_app_retry_failed_requires_selection(tmp_path, monkeypatch) -> None:
    messages: list[tuple[str, str]] = []

    monkeypatch.setattr(test_app, "messagebox", type("MB", (), {"showinfo": staticmethod(lambda title, msg: messages.append((title, msg)))})())

    app = _make_test_app(tmp_path)
    try:
        app.retry_selected_failed_jobs()

        assert messages == [("Arbeitsliste", "Bitte fehlgeschlagene Ergebnisse auswählen.")]
    finally:
        app.destroy()


def test_test_app_retry_failed_jobs_retries_only_failed_selection(tmp_path, monkeypatch) -> None:
    failed = tmp_path / "failed.pdf"
    done = tmp_path / "done.pdf"
    calls: list[tuple[str, str]] = []
    logs: list[str] = []
    refresh_calls: list[int] = []

    def fake_retry(project_root: str, job_id: str):
        calls.append((project_root, job_id))

    monkeypatch.setattr(test_app, "retry_failed_job", fake_retry)
    monkeypatch.setattr(test_app.TestApp, "_log", lambda self, message: logs.append(message))
    monkeypatch.setattr(test_app.TestApp, "refresh_queue", lambda self: refresh_calls.append(1))

    app = _make_test_app(tmp_path)
    try:
        refresh_calls.clear()
        app._upsert_file_rows(
            [
                {
                    "file": "failed.pdf",
                    "path": str(failed),
                    "source": "test-app-manual",
                    "queue_status": "FAILED",
                    "job_id": "failed1",
                    "device_id": "",
                    "last_error": "no_assay_detected",
                    "action": "queued",
                },
                {
                    "file": "done.pdf",
                    "path": str(done),
                    "source": "test-app-manual",
                    "queue_status": "DONE",
                    "job_id": "done1",
                    "device_id": "",
                    "last_error": "",
                    "action": "queued",
                },
            ]
        )
        app.tree_files.selection_set(
            test_app.normalize_file_row_key(failed),
            test_app.normalize_file_row_key(done),
        )

        app.retry_selected_failed_jobs()

        assert calls == [(str(tmp_path.resolve()), "failed1")]
        assert refresh_calls == [1]
        assert any("Erneut gestartet: 1 Ergebnis(se). Übersprungen: 1." in line for line in logs)
    finally:
        app.destroy()


def test_test_app_process_queue_uses_common_worker(tmp_path, monkeypatch) -> None:
    calls: list[object] = []
    logs: list[str] = []
    refresh_calls: list[int] = []

    class Result:
        processed = True
        job_id = "job1"
        pdf_path = str(tmp_path / "sample.pdf")
        queue_status = "DONE"
        submit_status = "DONE"

    def fake_process(project_root, snapshot):
        calls.append((project_root, snapshot))
        return Result()

    monkeypatch.setattr(test_app, "process_next_pending", fake_process)
    monkeypatch.setattr(test_app.TestApp, "_log", lambda self, message: logs.append(message))
    monkeypatch.setattr(test_app.TestApp, "refresh_queue", lambda self: refresh_calls.append(1))

    app = _make_test_app(tmp_path)
    try:
        monkeypatch.setattr(app, "after", lambda _delay, callback=None: callback() if callback else None)

        app._process_queue_thread(app._build_worker_config_snapshot(), 1)

        assert len(calls) == 1
        assert any("1/1 sample.pdf -> DONE" in line for line in logs)
        assert any("Extraktion abgeschlossen: 1 Job(s) verarbeitet." in line for line in logs)
        assert len(refresh_calls) >= 2
    finally:
        app.destroy()


def test_test_app_stop_extraction_sets_cooperative_flag(tmp_path) -> None:
    app = _make_test_app(tmp_path)
    try:
        app._extraction_running = True
        app.btn_stop_extraction.configure(state=tk.NORMAL)

        app.stop_extraction()

        assert app._stop_extraction_event.is_set()
        assert app.btn_stop_extraction.cget("state") == tk.DISABLED
        assert "gestoppt" in app.var_status.get()
    finally:
        app.destroy()


def test_test_app_process_queue_respects_stop_before_next_job(tmp_path, monkeypatch) -> None:
    calls: list[int] = []
    logs: list[str] = []

    class Result:
        processed = True
        job_id = "job1"
        pdf_path = str(tmp_path / "sample.pdf")
        queue_status = "DONE"
        submit_status = "DONE"

    def fake_process(project_root, snapshot):
        calls.append(1)
        return Result()

    def fake_progress(self, result, processed_count, pending_count):
        logs.append(f"progress:{processed_count}/{pending_count}")
        self._stop_extraction_event.set()

    monkeypatch.setattr(test_app, "process_next_pending", fake_process)
    monkeypatch.setattr(test_app.TestApp, "_handle_extraction_progress", fake_progress)
    monkeypatch.setattr(test_app.TestApp, "_log", lambda self, message: logs.append(message))
    monkeypatch.setattr(test_app.TestApp, "refresh_queue", lambda self: None)

    app = _make_test_app(tmp_path)
    try:
        monkeypatch.setattr(app, "after", lambda _delay, callback=None: callback() if callback else None)

        app._process_queue_thread(app._build_worker_config_snapshot(), 2)

        assert len(calls) == 1
        assert "progress:1/2" in logs
        assert any("gestoppt" in line for line in logs)
    finally:
        app.destroy()


def test_test_app_watch_recursive_defaults_false(tmp_path) -> None:
    app = _make_test_app(tmp_path)
    try:
        assert app.var_watch_recursive.get() is False
    finally:
        app.destroy()


def test_test_app_auto_watch_passes_recursive_flag_to_scanner(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeScanner:
        def scan(self, watch_dir, known_paths, stable_window_s, now=None, *, recursive=False, excluded_dir_names=None):
            captured["recursive"] = recursive
            from interfaces.tk.watch_scan import WatchScanResult

            return WatchScanResult([], 0, 0)

    monkeypatch.setattr(test_app, "InAppWatchScanner", FakeScanner)
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [])

    app = _make_test_app(tmp_path)
    try:
        app.var_watch_recursive.set(True)
        app._auto_watch_active = True
        app._run_auto_watch_scan()
        assert captured["recursive"] is True
    finally:
        app.stop_auto_watch(log=False)
        app.destroy()


def test_test_app_manual_watch_scan_recursive_queues_results(tmp_path, monkeypatch) -> None:
    watch = tmp_path / "watch"
    nested = watch / "2026" / "nested.pdf"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"pdf")
    enqueue_calls: list[tuple[str, str, str]] = []
    logs: list[str] = []

    def fake_enqueue(project_root: str, pdf_path: str, source: str = "watchdog") -> dict[str, str]:
        enqueue_calls.append((project_root, pdf_path, source))
        return {
            "job_id": "job1",
            "pdf_path": pdf_path,
            "status": "PENDING",
            "updated_at": "u",
            "source": source,
            "worker_id": "",
            "attempts": 0,
            "last_error": "",
        }

    monkeypatch.setattr(test_app, "enqueue_pdf_job", fake_enqueue)
    monkeypatch.setattr(test_app.TestApp, "_log", lambda self, message: logs.append(message))
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [])

    app = _make_test_app(tmp_path)
    try:
        app.var_watch_dir.set(str(watch))
        app.var_watch_recursive.set(True)
        app.scan_watch_dir()

        assert enqueue_calls == [(str(tmp_path.resolve()), str(nested.resolve(strict=False)), "test-app-watch")]
        assert len(logs) == 1
        assert "Ergebnisse gesucht: 1 PDF(s), vorgemerkt=1, übersprungen=0, Fehler=0, rekursiv=ja" in logs[0]
    finally:
        app.destroy()


def test_test_app_auto_watch_recursive_enqueue(tmp_path, monkeypatch) -> None:
    watch = tmp_path / "watch"
    nested = watch / "2026" / "nested.pdf"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"pdf")
    enqueue_calls: list[tuple[str, str]] = []

    def fake_enqueue(project_root: str, pdf_path: str, source: str = "watchdog") -> dict[str, str]:
        enqueue_calls.append((pdf_path, source))
        return {
            "job_id": "job1",
            "pdf_path": pdf_path,
            "status": "PENDING",
            "updated_at": "u",
            "source": source,
            "worker_id": "",
            "attempts": 0,
            "last_error": "",
        }

    monkeypatch.setattr(test_app, "enqueue_pdf_job", fake_enqueue)
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [])
    monkeypatch.setattr(test_app.TestApp, "refresh_queue", lambda self: None)

    app = _make_test_app(tmp_path)
    try:
        app.var_watch_dir.set(str(watch))
        app.var_watch_recursive.set(True)
        app._auto_watch_stable_window_s = 0
        app._auto_watch_active = True
        app._run_auto_watch_scan()

        assert len(enqueue_calls) == 1
        assert enqueue_calls[0][1] == "test-app-auto-watch"
    finally:
        app.stop_auto_watch(log=False)
        app.destroy()


def test_test_app_auto_watch_retry_enqueue_after_failed_attempt(tmp_path, monkeypatch) -> None:
    watch = tmp_path / "watch"
    watch.mkdir()
    pdf = watch / "sample.pdf"
    pdf.write_bytes(b"pdf")
    enqueue_calls: list[str] = []
    attempts = {"count": 0}

    def fake_enqueue(project_root: str, pdf_path: str, source: str = "watchdog") -> dict[str, str]:
        enqueue_calls.append(pdf_path)
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("queue failed")
        return {
            "job_id": "job1",
            "pdf_path": pdf_path,
            "status": "PENDING",
            "updated_at": "u",
            "source": source,
            "worker_id": "",
            "attempts": 0,
            "last_error": "",
        }

    monkeypatch.setattr(test_app, "enqueue_pdf_job", fake_enqueue)
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [])
    monkeypatch.setattr(test_app.TestApp, "refresh_queue", lambda self: None)

    app = _make_test_app(tmp_path)
    try:
        app.var_watch_dir.set(str(watch))
        app._auto_watch_stable_window_s = 0
        app._auto_watch_active = True

        app._run_auto_watch_scan()
        assert str(pdf.resolve(strict=False)) not in app._auto_watch_suppressed_paths
        assert len(enqueue_calls) == 1

        app._run_auto_watch_scan()
        assert len(enqueue_calls) == 2
        assert str(pdf.resolve(strict=False)) in app._auto_watch_suppressed_paths
    finally:
        app.stop_auto_watch(log=False)
        app.destroy()


def test_test_app_start_selected_files_delegates_to_extraction(tmp_path, monkeypatch) -> None:
    called: list[int] = []

    monkeypatch.setattr(test_app.TestApp, "start_extraction", lambda self: called.append(1))

    app = _make_test_app(tmp_path)
    try:
        app.start_selected_files()

        assert called == [1]
    finally:
        app.destroy()


def test_test_app_rework_section_controls_exist(tmp_path) -> None:
    app = _make_test_app(tmp_path)
    try:
        assert hasattr(app, "tree_rework")
        assert hasattr(app, "txt_rework_detail")
        assert hasattr(app, "cmb_rework_filter")
        assert app.var_rework_filter.get() == "Alle"
        headings = [app.tree_rework.heading(col)["text"] for col in app.tree_rework["columns"]]
        assert "Datei" in headings
        assert "Fehler" in headings
        assert "Kontext" in headings
    finally:
        app.destroy()


def test_test_app_refresh_rework_items_renders_failed_jobs(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    queue_job = {
        "job_id": "job1",
        "pdf_path": str(pdf),
        "status": "FAILED",
        "updated_at": "u",
        "source": "test-app-manual",
        "worker_id": "",
        "attempts": 1,
        "last_error": "no_assay_detected",
    }
    monkeypatch.setattr(test_app, "list_jobs", lambda _root: [queue_job])

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()

        assert "job1" in app._rework_items
        assert len(app._rework_items_all) == 1
        assert app.tree_rework.get_children()
        assert app.tree_rework.item("job1", "values")[1] == "Assay nicht erkannt"
        assert "1 geladen, 1 angezeigt" in app.txt_logs.get("1.0", tk.END)
    finally:
        app.destroy()


def test_test_app_rework_filter_change_rerenders_without_reload(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    queue_jobs = [
        {
            "job_id": "job1",
            "pdf_path": str(pdf),
            "status": "FAILED",
            "updated_at": "u",
            "source": "test-app-manual",
            "worker_id": "",
            "attempts": 1,
            "last_error": "no_assay_detected",
        },
        {
            "job_id": "job2",
            "pdf_path": str(pdf),
            "status": "FAILED",
            "updated_at": "u",
            "source": "test-app-manual",
            "worker_id": "",
            "attempts": 1,
            "last_error": "ruleset missing assay_name for (6bd7)",
        },
    ]
    list_jobs_calls: list[int] = []

    def counting_list_jobs(_root):
        list_jobs_calls.append(1)
        return queue_jobs

    monkeypatch.setattr(test_app, "list_jobs", counting_list_jobs)

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()
        assert len(app._rework_items_all) == 2
        assert len(app.tree_rework.get_children()) == 2
        calls_after_refresh = len(list_jobs_calls)

        app.var_rework_filter.set("Regelset unvollständig")
        app._on_rework_filter_changed()

        assert len(app._rework_items_all) == 2
        assert len(list_jobs_calls) == calls_after_refresh
        assert [app.tree_rework.item(iid, "values")[3] for iid in app.tree_rework.get_children()] == ["job2"]
    finally:
        app.destroy()


def test_test_app_rework_selection_shows_detail(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    monkeypatch.setattr(
        test_app,
        "list_jobs",
        lambda _root: [
            {
                "job_id": "job1",
                "pdf_path": str(pdf),
                "status": "FAILED",
                "updated_at": "u",
                "source": "test-app-manual",
                "worker_id": "",
                "attempts": 1,
                "last_error": "no_assay_detected",
            }
        ],
    )

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()
        app.tree_rework.selection_set("job1")
        app.on_rework_selected()

        detail = app.txt_rework_detail.get("1.0", tk.END)
        assert "Assay nicht erkannt" in detail
    finally:
        app.destroy()


def test_test_app_show_rework_context_loads_dump_or_reports_missing(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    dump = tmp_path / "jobs" / "job1_normalized.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text("normalized", encoding="utf-8")
    import json

    (tmp_path / "jobs" / "job1.json").write_text(
        json.dumps(
            {
                "job_id": "job1",
                "error": "no_assay_detected",
                "steps": [{"step": "debug", "normalized_dump": str(dump)}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        test_app,
        "list_jobs",
        lambda _root: [
            {
                "job_id": "job1",
                "pdf_path": str(pdf),
                "status": "FAILED",
                "updated_at": "u",
                "source": "test-app-manual",
                "worker_id": "",
                "attempts": 1,
                "last_error": "no_assay_detected",
            }
        ],
    )

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()
        app.tree_rework.selection_set("job1")
        app.show_rework_context()
        detail = app.txt_rework_detail.get("1.0", tk.END)
        assert "normalized" in detail
        assert "0001 | normalized" in detail
        assert "PDF-Pfad:" in detail
        assert "Dump-Pfad:" in detail

        dump.unlink()
        app.show_rework_context()
        detail_missing = app.txt_rework_detail.get("1.0", tk.END)
        assert "nicht vorhanden" in detail_missing
    finally:
        app.destroy()


def test_test_app_rework_retry_updates_queue_and_rework(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    retry_calls: list[str] = []
    refresh_queue_calls: list[int] = []
    refresh_rework_calls: list[int] = []

    monkeypatch.setattr(
        test_app,
        "list_jobs",
        lambda _root: [
            {
                "job_id": "job1",
                "pdf_path": str(pdf),
                "status": "FAILED",
                "updated_at": "u",
                "source": "test-app-manual",
                "worker_id": "",
                "attempts": 1,
                "last_error": "no_assay_detected",
            }
        ],
    )
    monkeypatch.setattr(test_app, "retry_failed_job", lambda _root, job_id: retry_calls.append(job_id))
    monkeypatch.setattr(test_app.TestApp, "refresh_queue", lambda self: refresh_queue_calls.append(1))
    monkeypatch.setattr(test_app.TestApp, "refresh_rework_items", lambda self: refresh_rework_calls.append(1))

    app = _make_test_app(tmp_path)
    try:
        refresh_queue_calls.clear()
        refresh_rework_calls.clear()
        app._rework_items = {
            "job1": {
                "item_id": "job1",
                "job_id": "job1",
                "file": "failed.pdf",
                "pdf_path": str(pdf),
            }
        }
        app.tree_rework.insert("", tk.END, iid="job1", values=("failed.pdf", "Assay nicht erkannt", "Fehler", "job1", "-"))
        app.tree_rework.selection_set("job1")
        app.retry_selected_rework_items()

        assert retry_calls == ["job1"]
        assert refresh_queue_calls == [1]
        assert refresh_rework_calls == [1]
    finally:
        app.destroy()


def test_test_app_rework_rule_editor_uses_existing_start_path(tmp_path, monkeypatch) -> None:
    logs: list[str] = []
    started: list[int] = []

    monkeypatch.setattr(test_app.TestApp, "open_rule_editor", lambda self: started.append(1))
    monkeypatch.setattr(test_app.TestApp, "_log", lambda self, message: logs.append(message))
    monkeypatch.setattr(
        test_app,
        "list_jobs",
        lambda _root: [
            {
                "job_id": "job1",
                "pdf_path": str(tmp_path / "failed.pdf"),
                "status": "FAILED",
                "updated_at": "u",
                "source": "test-app-manual",
                "worker_id": "",
                "attempts": 1,
                "last_error": "no_assay_detected",
            }
        ],
    )

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()
        app.tree_rework.selection_set("job1")
        app.open_rule_editor_from_rework()

        assert started == [1]
        assert any("Rule Editor fuer Nacharbeit: PDF=" in line for line in logs)
        assert any("Dump=" in line for line in logs)
    finally:
        app.destroy()


def test_test_app_assay_candidate_button_exists(tmp_path) -> None:
    app = _make_test_app(tmp_path)
    try:
        assert hasattr(app, "tree_rework_candidates")
        assert hasattr(app, "preview_assay_candidates")
        assert app.lbl_rework_candidates.cget("text") == "Noch keine Kandidaten geprüft."
    finally:
        app.destroy()


def test_test_app_preview_assay_candidates_requires_no_assay_error(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    monkeypatch.setattr(
        test_app,
        "list_jobs",
        lambda _root: [
            {
                "job_id": "job1",
                "pdf_path": str(pdf),
                "status": "FAILED",
                "updated_at": "u",
                "source": "test-app-manual",
                "worker_id": "",
                "attempts": 1,
                "last_error": "ruleset missing assay_name for (6bd7)",
            }
        ],
    )
    shown: list[str] = []
    monkeypatch.setattr(test_app.messagebox, "showinfo", lambda _title, message: shown.append(message))

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()
        app.tree_rework.selection_set("job1")
        app.preview_assay_candidates()

        assert shown
        assert "Assay nicht erkannt" in shown[0]
        assert not app.tree_rework_candidates.get_children()
    finally:
        app.destroy()


def test_test_app_preview_assay_candidates_shows_missing_dump_message(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    monkeypatch.setattr(
        test_app,
        "list_jobs",
        lambda _root: [
            {
                "job_id": "job1",
                "pdf_path": str(pdf),
                "status": "FAILED",
                "updated_at": "u",
                "source": "test-app-manual",
                "worker_id": "",
                "attempts": 1,
                "last_error": "no_assay_detected",
            }
        ],
    )

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()
        app.tree_rework.selection_set("job1")
        app.preview_assay_candidates()

        assert app.lbl_rework_candidates.cget("text") == "Kein normalisierter Kontext vorhanden."
        assert not app.tree_rework_candidates.get_children()
    finally:
        app.destroy()


def test_test_app_preview_assay_candidates_shows_known_and_unknown(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    dump = tmp_path / "jobs" / "job1_normalized.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text(
        "\n".join(
            [
                "Test: ANA Screen IgG.asy (1c9e)",
                "Test: New Assay.asy (abcd)",
            ]
        ),
        encoding="utf-8",
    )
    import json

    (tmp_path / "jobs" / "job1.json").write_text(
        json.dumps(
            {
                "job_id": "job1",
                "error": "no_assay_detected",
                "steps": [{"step": "debug", "normalized_dump": str(dump)}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "rules").mkdir(parents=True, exist_ok=True)
    (tmp_path / "rules" / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1c9e)", "ruleset_file": "ANA Screen IgG.json"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        test_app,
        "list_jobs",
        lambda _root: [
            {
                "job_id": "job1",
                "pdf_path": str(pdf),
                "status": "FAILED",
                "updated_at": "u",
                "source": "test-app-manual",
                "worker_id": "",
                "attempts": 1,
                "last_error": "no_assay_detected",
            }
        ],
    )

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()
        app.tree_rework.selection_set("job1")
        app.preview_assay_candidates()

        rows = [app.tree_rework_candidates.item(iid, "values") for iid in app.tree_rework_candidates.get_children()]
        assert len(rows) == 2
        statuses = {row[0]: row[4] for row in rows}
        assert statuses["(1c9e)"] == "bekannt"
        assert statuses["(abcd)"] == "unbekannt"
        assert (tmp_path / "rules" / "index.json").read_text(encoding="utf-8") == json.dumps(
            {"assays": [{"assay_key": "(1c9e)", "ruleset_file": "ANA Screen IgG.json"}]}
        )
    finally:
        app.destroy()


def test_test_app_create_draft_from_known_candidate_is_blocked(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    dump = tmp_path / "jobs" / "job1_normalized.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text("Test: ANA Screen IgG.asy (1c9e)", encoding="utf-8")
    import json

    (tmp_path / "jobs" / "job1.json").write_text(
        json.dumps(
            {
                "job_id": "job1",
                "error": "no_assay_detected",
                "steps": [{"step": "debug", "normalized_dump": str(dump)}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "rules").mkdir(parents=True, exist_ok=True)
    (tmp_path / "rules" / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1c9e)", "ruleset_file": "ANA Screen IgG.json"}]}),
        encoding="utf-8",
    )
    (tmp_path / "rules" / "template.json").write_text(
        json.dumps(
            {
                "assay_name": "Template",
                "assay_key": "(0000)",
                "lot_rule": {"regex": ""},
                "extract_rules": {"fields": []},
                "excel_rules": {
                    "excel_filename_template": "{assay_name}.xlsx",
                    "sheetname_template": "{lot_id}",
                    "column_mapping": {},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        test_app,
        "list_jobs",
        lambda _root: [
            {
                "job_id": "job1",
                "pdf_path": str(pdf),
                "status": "FAILED",
                "updated_at": "u",
                "source": "test-app-manual",
                "worker_id": "",
                "attempts": 1,
                "last_error": "no_assay_detected",
            }
        ],
    )
    shown: list[str] = []
    monkeypatch.setattr(test_app.messagebox, "showinfo", lambda _title, message: shown.append(message))

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()
        app.tree_rework.selection_set("job1")
        app.preview_assay_candidates()
        app.tree_rework_candidates.selection_set("(1c9e)")
        app.create_draft_from_rework_candidate()

        assert shown
        assert "existiert bereits" in shown[-1]
        assert not list((tmp_path / "rules" / "drafts").glob("*.draft.json")) if (tmp_path / "rules" / "drafts").exists() else True
    finally:
        app.destroy()


def test_test_app_create_draft_from_unknown_candidate_creates_header_draft(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    dump = tmp_path / "jobs" / "job1_normalized.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text("Test: New Assay.asy (abcd)", encoding="utf-8")
    import json

    (tmp_path / "jobs" / "job1.json").write_text(
        json.dumps(
            {
                "job_id": "job1",
                "error": "no_assay_detected",
                "steps": [{"step": "debug", "normalized_dump": str(dump)}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "rules").mkdir(parents=True, exist_ok=True)
    (tmp_path / "rules" / "index.json").write_text(json.dumps({"assays": []}), encoding="utf-8")
    (tmp_path / "rules" / "template.json").write_text(
        json.dumps(
            {
                "assay_name": "Template",
                "assay_key": "(0000)",
                "lot_rule": {"regex": ""},
                "extract_rules": {
                    "fields": [
                        {"key": "DATUM", "regex": "", "required": False},
                        {"key": "ZEIT", "regex": "", "required": False},
                        {"key": "ANWENDER", "regex": "", "required": False},
                        {"key": "PLATTE", "regex": "", "required": False},
                        {"key": "CHARGE", "regex": "", "required": False},
                        {"key": "TEST", "regex": "", "required": False},
                        {"key": "VALIDATION", "regex": "", "required": False},
                        {"key": "HALTBARKEIT", "regex": "", "required": False},
                    ]
                },
                "excel_rules": {
                    "excel_filename_template": "{assay_name}.xlsx",
                    "sheetname_template": "{lot_id}",
                    "column_mapping": {},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        test_app,
        "list_jobs",
        lambda _root: [
            {
                "job_id": "job1",
                "pdf_path": str(pdf),
                "status": "FAILED",
                "updated_at": "u",
                "source": "test-app-manual",
                "worker_id": "",
                "attempts": 1,
                "last_error": "no_assay_detected",
            }
        ],
    )
    monkeypatch.setattr(test_app.messagebox, "askyesno", lambda *_args, **_kwargs: False)

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()
        app.tree_rework.selection_set("job1")
        app.preview_assay_candidates()
        assert "(abcd)" in app._rework_candidates_by_id
        app.tree_rework_candidates.selection_set("(abcd)")
        app.create_draft_from_rework_candidate()

        draft_path = tmp_path / "rules" / "drafts" / "abcd.draft.json"
        assert draft_path.exists()
        detail = app.txt_rework_detail.get("1.0", tk.END)
        assert str(draft_path) in detail
        assert (tmp_path / "rules" / "index.json").read_text(encoding="utf-8") == json.dumps({"assays": []})
    finally:
        app.destroy()


def test_test_app_create_draft_from_unchecked_candidate_warns_and_creates(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "failed.pdf"
    dump = tmp_path / "jobs" / "job1_normalized.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text("Test: Unchecked Assay.asy (ef01)", encoding="utf-8")
    import json

    (tmp_path / "jobs" / "job1.json").write_text(
        json.dumps(
            {
                "job_id": "job1",
                "error": "no_assay_detected",
                "steps": [{"step": "debug", "normalized_dump": str(dump)}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "rules").mkdir(parents=True, exist_ok=True)
    (tmp_path / "rules" / "template.json").write_text(
        json.dumps(
            {
                "assay_name": "Template",
                "assay_key": "(0000)",
                "lot_rule": {"regex": ""},
                "extract_rules": {
                    "fields": [
                        {"key": "DATUM", "regex": "", "required": False},
                        {"key": "ZEIT", "regex": "", "required": False},
                        {"key": "ANWENDER", "regex": "", "required": False},
                        {"key": "PLATTE", "regex": "", "required": False},
                        {"key": "CHARGE", "regex": "", "required": False},
                        {"key": "TEST", "regex": "", "required": False},
                        {"key": "VALIDATION", "regex": "", "required": False},
                        {"key": "HALTBARKEIT", "regex": "", "required": False},
                    ]
                },
                "excel_rules": {
                    "excel_filename_template": "{assay_name}.xlsx",
                    "sheetname_template": "{lot_id}",
                    "column_mapping": {},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        test_app,
        "list_jobs",
        lambda _root: [
            {
                "job_id": "job1",
                "pdf_path": str(pdf),
                "status": "FAILED",
                "updated_at": "u",
                "source": "test-app-manual",
                "worker_id": "",
                "attempts": 1,
                "last_error": "no_assay_detected",
            }
        ],
    )
    monkeypatch.setattr(test_app, "load_known_assay_keys", lambda _path: None)
    prompts: list[str] = []
    monkeypatch.setattr(
        test_app.messagebox,
        "askokcancel",
        lambda _title, message: prompts.append(message) or True,
    )
    monkeypatch.setattr(test_app.messagebox, "askyesno", lambda *_args, **_kwargs: False)

    app = _make_test_app(tmp_path)
    try:
        app.refresh_rework_items()
        app.tree_rework.selection_set("job1")
        app.preview_assay_candidates()
        app.tree_rework_candidates.selection_set("(ef01)")
        app.create_draft_from_rework_candidate()

        assert prompts
        assert "Index konnte nicht geprueft werden" in prompts[0]
        assert (tmp_path / "rules" / "drafts" / "ef01.draft.json").exists()
    finally:
        app.destroy()


def _write_valid_rules_for_smoke(root: Path) -> None:
    rules = root / "rules"
    rules.mkdir(parents=True)
    (rules / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1111)", "ruleset_file": "AssayA.json"}]}),
        encoding="utf-8",
    )
    (rules / "AssayA.json").write_text(
        json.dumps(
            {
                "assay_name": "Assay A",
                "assay_key": "(1111)",
                "lot_rule": {"regex": r"Lot:\s*(\w+)"},
                "extract_rules": {
                    "fields": [{"key": "test", "regex": r"Test:\s*(\w+)", "required": True}],
                    "dedupe_fields": ["test"],
                },
                "excel_rules": {
                    "excel_filename_template": "{assay_name}.xlsx",
                    "sheetname_template": "{lot_id}",
                    "column_mapping": {"test": "TEST"},
                },
            }
        ),
        encoding="utf-8",
    )


def test_test_app_startup_smoke_check_accepts_valid_rules(tmp_path) -> None:
    _write_valid_rules_for_smoke(tmp_path)
    test_app.run_startup_smoke_check(tmp_path)


def test_test_app_startup_smoke_check_rejects_invalid_rules(tmp_path) -> None:
    rules = tmp_path / "rules"
    rules.mkdir(parents=True)
    (rules / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1111)", "ruleset_file": "Missing.json"}]}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="rules_integrity_failed"):
        test_app.run_startup_smoke_check(tmp_path)
