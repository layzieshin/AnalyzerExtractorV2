"""Native monthly adapters and exact existing navigation; no product files."""
from dataclasses import replace
from types import SimpleNamespace
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import pytest

from interfaces.tk import desktop_theme
from interfaces.tk.test_app import AnalyzerDesktopApp
from interfaces.tk.widgets.monthly_archive_dialog import MonthlyArchiveDialog
from src.application.api import DesktopSettings
from src.ingestion.api import ArchiveGroup, ArchiveSource, MonthlyArchivePreview
from test_desktop_ui_v21 import _fake_services, _make_app_stub, _RecordingRunner


def _settle(root):
    for _ in range(5):
        root.update_idletasks()
        root.update()


@pytest.fixture(params=[(1420, 930, 1.0), (960, 620, 1.25)], ids=["1420", "960-125"])
def shell(tmp_path, monkeypatch, request):
    width, height, scale = request.param
    original = desktop_theme.configure_desktop_theme
    saved = []
    def theme(root):
        saved.append((root, float(root.tk.call("tk", "scaling"))))
        root.tk.call("tk", "scaling", (4 / 3) * scale)
        original(root)
    monkeypatch.setattr(desktop_theme, "configure_desktop_theme", theme)
    services = _fake_services()
    settings = DesktopSettings("sqlite", str(tmp_path / "db.sqlite3"), archive_mode="monthly",
        watch_input_path=str(tmp_path / "Result"), operator_initials="MK")
    services.settings.load = lambda: settings
    app = None
    try:
        app = AnalyzerDesktopApp(project_root=tmp_path, services=services)
        app._task_runner.shutdown_runner()
        app._task_runner = _RecordingRunner()
        app._bootstrapped, app._settings, app._services = True, settings, services
        app.geometry(f"{width}x{height}+0+0")
        app.show_view("results", refresh=False)
        _settle(app)
        yield app
    finally:
        if saved:
            root, scaling = saved[0]
            try:
                root.tk.call("tk", "scaling", scaling)
            finally:
                root.destroy()


def _preview():
    first = ArchiveSource(r"C:\Result\ANA_2026-11-25.pdf", "a" * 64, 100, (1, 2, 100, 20), "pdf")
    second = ArchiveSource(r"C:\Result\unbekannt.pdf", "b" * 64, 120, (1, 3, 120, 21), "pdf")
    groups = (ArchiveGroup("ready", "20261125_Test", "2026-11-25", (first,), r"C:\Result\2026\11_November",
                          True, (), "c" * 64),
              ArchiveGroup("blocked", "20261125_Offen", "2026-11-25", (second,), r"C:\Result\2026\11_November",
                          False, ("Ein bekanntes Ergebnis dieser Platte ist noch nicht validiert und bleibt gesperrt.",), "d" * 64))
    return MonthlyArchivePreview("project", r"C:\Result", r"C:\Result", "store", "2026-11-25", groups, "token")


def _inside(widget, parent):
    assert widget.winfo_ismapped(), str(widget)
    assert widget.winfo_rootx() >= parent.winfo_rootx()
    assert widget.winfo_rooty() >= parent.winfo_rooty()
    assert widget.winfo_rootx() + widget.winfo_width() <= parent.winfo_rootx() + parent.winfo_width()
    assert widget.winfo_rooty() + widget.winfo_height() <= parent.winfo_rooty() + parent.winfo_height()


def test_monthly_shell_action_native_preview_targets_full_reason_and_res_choices(shell, monkeypatch):
    app = shell
    plan = replace(_preview(), store_path=app._settings.sqlite_path)
    calls = []
    def preview(*, cutoff, store_path, res_assignments, without_res, context_guard):
        assert context_guard() and store_path == app._settings.sqlite_path
        calls.append((cutoff, res_assignments, without_res))
        return plan
    app._services.results.preview_monthly_archive = preview
    app._views["results"]._btn_monthly_archive.invoke()
    _settle(app)
    dialog = next(child for child in app.winfo_children() if isinstance(child, MonthlyArchiveDialog))
    app._task_runner.invoke_success()
    _settle(app)
    assert dialog.selected_groups() == ("ready",)
    assert dialog._tree.item("ready", "values")[3] == "2026/11_November"
    assert dialog._btn_commit.cget("text") == "Ausgewählte Läufe ablegen"
    original_call = calls[-1]
    for widget in (dialog._cutoff_entry, dialog._btn_preview, dialog._btn_recover,
                   dialog._btn_assign, dialog._btn_no_res, dialog._btn_commit, dialog._btn_close):
        _inside(widget, dialog)
    heading = tkfont.Font(app, font=ttk.Style(app).lookup("Treeview.Heading", "font"))
    for column in dialog._tree.cget("columns"):
        assert dialog._tree.column(column, "width") >= heading.measure(dialog._tree.heading(column, "text")) + 20
    assert dialog._tree.xview() == (0.0, 1.0)
    row = dialog._tree.bbox("blocked:0")
    assert row and row[1] + row[3] <= dialog._tree.winfo_height()
    dialog._tree.selection_set("blocked")
    _settle(app)
    assert plan.groups[1].reasons[0] in dialog._details.cget("text")
    assert plan.groups[1].target_dir in dialog._details.cget("text")
    assert dialog._btn_commit.instate(("disabled",))
    dialog._tree.selection_set("blocked:0")
    _settle(app)
    monkeypatch.setattr("interfaces.tk.widgets.monthly_archive_dialog.messagebox.askyesno", lambda *_a, **_kw: True)
    dialog._btn_no_res.invoke()
    assert dialog.exceptions == {plan.groups[1].sources[0].path}
    assert calls[-1] == original_call  # Worker has not run in the Tk callback.
    app._task_runner.invoke_success()
    _settle(app)
    assert calls[-1][2] == tuple(dialog.exceptions)
    dialog.set_busy(False, "Kopierfehler: Original bleibt erhalten.")
    assert dialog._details.cget("text") == "Kopierfehler: Original bleibt erhalten."
    dialog.destroy()


def test_monthly_preview_late_callback_and_store_aba_never_enables_old_commit(shell):
    app = shell
    app._services.results.preview_monthly_archive = lambda **_kw: pytest.fail("stale store must fail before reading")
    app._open_monthly_archive()
    _settle(app)
    dialog = next(child for child in app.winfo_children() if isinstance(child, MonthlyArchiveDialog))
    task = app._task_runner.submissions[-1]
    app._store_generation += 2
    with pytest.raises(ValueError, match="Ergebnisspeicher"):
        task[1]()
    task[2](_preview())
    assert dialog.preview is None and dialog._btn_commit.instate(("disabled",))
    dialog.destroy()
    task[2](_preview())  # Closed window safely ignores late completion.


def test_monthly_settings_native_roundtrip_dirty_mode_and_import_actions_fit(shell):
    app = shell
    app.show_view("settings", refresh=False)
    view = app._views["settings"]
    view.render_settings(app._settings, devices=(), timing=app._services.settings.get_watch_timing())
    _settle(app)
    assert view.collect_settings(device_id_map={}).archive_mode == "monthly" and not view.is_dirty()
    for widget in (view._backup_entry, view._backup_pick, view._backup_clear, view._recursive_check):
        assert widget.instate(("disabled",))
    assert "Altimporte" in view._archive_hint.cget("text")
    _inside(view._btn_save, app)
    view._var_archive_mode.set("immediate")
    view._archive_mode_changed()
    _settle(app)
    assert view.is_dirty() and view.collect_settings(device_id_map={}).archive_mode == "immediate"
    assert not view._recursive_check.instate(("disabled",))
    view.render_settings(app._settings, devices=(), timing=app._services.settings.get_watch_timing())
    assert view.is_dirty()  # Refresh must not overwrite a changed local draft.


def test_monthly_choice_is_invalidated_if_pdf_disappears_or_changes(shell):
    app = shell
    dialog = MonthlyArchiveDialog(app, on_preview=lambda *_: None, on_commit=lambda *_: None,
        on_recover=lambda *_: None, initial_cutoff="2026-11-25")
    _settle(app)
    plan = _preview()
    source = plan.groups[0].sources[0]
    dialog.exceptions.add(source.path)
    dialog._choice_sha[source.path] = source.sha256
    dialog.render_preview(replace(plan, groups=plan.groups[1:]))
    assert not dialog.exceptions and dialog.preview is None and dialog._btn_commit.instate(("disabled",))
    dialog.destroy()


def test_report_refind_routes_to_displayed_detail_not_hidden_list_selection():
    app = _make_app_stub()
    store = app._settings.sqlite_path
    descriptor = [("shown-report", store)]
    app._views["results"] = SimpleNamespace(current_detail_descriptor=lambda: descriptor[0],
        selected_report_descriptor=lambda: ("unrelated-list-row", store))
    app._pick_pdf_search_path = lambda: "chosen-folder"
    calls, opened = [], []
    def find(report_id, search_path, *, store_path, context_guard):
        assert context_guard()
        calls.append((report_id, search_path, store_path))
        return "verified-current.pdf"
    app._services.results.find_report_pdf = find
    app._start_report_detail = lambda report_id, store_path, *, selected_guard: opened.append((report_id, store_path, selected_guard))
    app._find_report_pdf()
    app._task_runner.invoke_success()
    assert calls == [("shown-report", "chosen-folder", store)]
    assert opened == [("shown-report", store, False)]
    app._find_report_pdf()
    task = app._task_runner.submissions[-1]
    descriptor[0] = ("new-detail", store)
    with pytest.raises(ValueError, match="Auswahl"):
        task[1]()
    task[2]("late.pdf")
    assert len(opened) == 1


def test_failed_identity_refind_has_no_run_dependency_and_discards_store_aba():
    from test_changes_ui import _item
    app = _make_app_stub(current_view="changes")
    item = _item()
    source = item.sources[0]
    descriptor = (1, item.case_id, source.source_id, item.store_path, "candidate")
    app._views["changes"] = SimpleNamespace(selected_case=lambda: item, selected_source=lambda: source,
        selection_context=lambda: descriptor)
    app._pick_pdf_search_path = lambda: "folder"
    calls, refreshes = [], []
    def find(case_id, source_id, search_path, *, store_path, expected_identity_token, context_guard):
        assert context_guard()
        calls.append((case_id, source_id, search_path, store_path, expected_identity_token))
        return "current.pdf"
    app._services.rules.find_identity_pdf = find
    app.refresh_current_view = lambda: refreshes.append(True)
    app._find_identity_pdf()
    app._task_runner.invoke_success()
    assert calls == [(item.case_id, source.source_id, "folder", item.store_path, item.identity_token)]
    assert refreshes == [True]
    app._find_identity_pdf()
    task = app._task_runner.submissions[-1]
    app._store_generation += 2
    with pytest.raises(ValueError, match="Fallauswahl"):
        task[1]()
    task[2]("late.pdf")
    assert refreshes == [True]
