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
