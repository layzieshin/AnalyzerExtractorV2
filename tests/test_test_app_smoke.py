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


def test_test_app_file_rows_preserve_manual_rows_when_watch_scans(tmp_path) -> None:
    try:
        app = test_app.TestApp(project_root=tmp_path)
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    try:
        manual = tmp_path / "manual.pdf"
        watch = tmp_path / "watch.pdf"
        app._upsert_file_rows([{"file": "manual.pdf", "path": str(manual), "source": "manual", "queue_status": "", "job_id": "", "device_id": "", "last_error": "", "action": "bereit"}])
        app._upsert_file_rows([{"file": "watch.pdf", "path": str(watch), "source": "watch", "queue_status": "", "job_id": "", "device_id": "", "last_error": "", "action": "bereit"}], replace_source="watch")

        sources = sorted(row["source"] for row in app._watch_rows.values())
        assert sources == ["manual", "watch"]
    finally:
        app.destroy()


def test_test_app_action_snapshot_contains_plain_values(tmp_path) -> None:
    try:
        app = test_app.TestApp(project_root=tmp_path)
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    try:
        pdf = tmp_path / "sample.pdf"
        app.var_output_mode.set("sqlite")
        app.var_sqlite_path.set(str(tmp_path / "out.sqlite3"))
        app._upsert_file_rows([{"file": "sample.pdf", "path": str(pdf), "source": "manual", "queue_status": "", "job_id": "", "device_id": "", "last_error": "", "action": "bereit"}])

        snapshot = app._build_action_snapshot()

        assert snapshot["project_root"] == str(tmp_path.resolve())
        assert snapshot["output_mode"] == "sqlite"
        assert snapshot["sqlite_path"] == str(tmp_path / "out.sqlite3")
        assert snapshot["rows"] == list(app._watch_rows.values())
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
        assert any("Queue-Fehler" in line for line in logs)
    finally:
        app.stop_auto_watch(log=False)
        app.destroy()


def test_test_app_direct_submit_blocks_queue_rows(tmp_path, monkeypatch) -> None:
    pdf = tmp_path / "sample.pdf"
    started: list[int] = []
    logs: list[str] = []

    monkeypatch.setattr(test_app.TestApp, "_start_background_action", lambda self, _msg: started.append(1) or True)
    monkeypatch.setattr(test_app, "messagebox", type("MB", (), {"showinfo": staticmethod(lambda *a, **k: None)})())
    monkeypatch.setattr(test_app.TestApp, "_log", lambda self, message: logs.append(message))

    app = _make_test_app(tmp_path)
    try:
        app._upsert_file_rows(
            [
                {
                    "file": "sample.pdf",
                    "path": str(pdf),
                    "source": "manual",
                    "queue_status": "PENDING",
                    "job_id": "job1",
                    "device_id": "",
                    "last_error": "",
                    "action": "queued",
                }
            ]
        )

        app.start_selected_files()

        assert started == []
        assert any("Queue-Jobs" in line for line in logs)
    finally:
        app.destroy()


def test_test_app_direct_submit_blocks_mixed_selection(tmp_path, monkeypatch) -> None:
    queued = tmp_path / "queued.pdf"
    plain = tmp_path / "plain.pdf"
    started: list[int] = []

    monkeypatch.setattr(test_app.TestApp, "_start_background_action", lambda self, _msg: started.append(1) or True)
    monkeypatch.setattr(test_app, "messagebox", type("MB", (), {"showinfo": staticmethod(lambda *a, **k: None)})())
    monkeypatch.setattr(test_app.TestApp, "_log", lambda self, _message: None)

    app = _make_test_app(tmp_path)
    try:
        app._upsert_file_rows(
            [
                {
                    "file": "queued.pdf",
                    "path": str(queued),
                    "source": "manual",
                    "queue_status": "PENDING",
                    "job_id": "job1",
                    "device_id": "",
                    "last_error": "",
                    "action": "queued",
                },
                {
                    "file": "plain.pdf",
                    "path": str(plain),
                    "source": "manual",
                    "queue_status": "",
                    "job_id": "",
                    "device_id": "",
                    "last_error": "",
                    "action": "bereit",
                },
            ]
        )
        app.tree_files.selection_set(
            test_app.normalize_file_row_key(queued),
            test_app.normalize_file_row_key(plain),
        )

        app.start_selected_files()

        assert started == []
    finally:
        app.destroy()
