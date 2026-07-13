import tkinter as tk

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
            app.btn_refresh_queue.cget("text"),
            app.btn_auto_watch_start.cget("text"),
            app.btn_auto_watch_stop.cget("text"),
        }
        assert "Ergebnisse suchen" in button_texts
        assert "Dateien hinzufügen" in button_texts
        assert "Extraktion starten" in button_texts
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
        assert any("Dateien hinzugefügt: 1 PDF(s), vorgemerkt=1, Fehler=0" in line for line in logs)
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


def test_test_app_process_queue_uses_common_worker(tmp_path, monkeypatch) -> None:
    calls: list[object] = []
    logs: list[str] = []

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
    monkeypatch.setattr(test_app.TestApp, "refresh_queue", lambda self: None)

    app = _make_test_app(tmp_path)
    try:
        monkeypatch.setattr(app, "after", lambda _delay, callback=None: callback() if callback else None)

        app._process_queue_thread(app._build_worker_config_snapshot(), 1)

        assert len(calls) == 1
        assert any("sample.pdf -> DONE" in line for line in logs)
        assert any("Extraktion abgeschlossen: 1 Job(s) verarbeitet." in line for line in logs)
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
        assert "Ergebnisse gesucht: 1 PDF(s), vorgemerkt=1, Fehler=0, rekursiv=ja" in logs[0]
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
