from __future__ import annotations

import inspect
from dataclasses import replace
import threading
import tkinter as tk
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from interfaces.tk import test_app
from interfaces.tk.views.dashboard_view import DashboardView
from interfaces.tk.desktop_theme import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MIN_HEIGHT,
    MIN_WIDTH,
    configure_desktop_theme,
)
from interfaces.tk.views.results_view import ResultsView
from interfaces.tk.views.statistics_view import StatisticsView
from interfaces.tk.views.settings_view import SettingsView
from interfaces.tk.views.validation_view import ValidationView
from interfaces.tk.view_models import (
    DASHBOARD_RECENT_LIMIT,
    BatchFileStatus,
    DashboardRecentRow,
    GENERIC_ACTION_FAILED_MESSAGE,
    build_batch_file_statuses,
    build_dashboard_recent_rows,
    format_duplicate_detail_lines,
    format_user_error_message,
    format_watch_cycle_summary,
    import_device_label,
    occurrence_field_rows,
    occurrence_id,
    rules_inventory_item_id,
    user_error_dialog_parts,
)
from interfaces.tk.widgets.common import create_scrollable_tree
from src.application.api import (
    ApplicationWatchError,
    AssayCandidateItem,
    DuplicateCandidateDetail,
    DuplicateCandidateItem,
    DeviceInventoryItem,
    DuplicateExistingRunItem,
    DuplicateFieldComparisonItem,
    IngestionInstanceItem,
    ProcessingEnqueueOutcome,
    ProcessingOutcome,
    PathOpenError,
    ReportNotFoundError,
    ValidationConflictError,
    ReportAssayGroup,
    ReportDetail,
    ReportFieldValue,
    ReportRunOccurrence,
    ReportSummaryItem,
    RulesetInventoryItem,
    RunValidationItem,
    ValidationQueueItem,
    ReanalysisComparison,
    ResultComparisonField,
    SettingsSaveError,
    SettingsValidationError,
    WatchCycleSummary,
    WatchTimingSettings,
)


def _pending_validation_item(run_id=8):
    return replace(_validation_item(run_id=run_id), selection_token=f"original:{run_id}|pending:20",
        store_path="results.sqlite", comparison=ReanalysisComparison(20,
            (ResultComparisonField("RESULT", "42", "43", True), ResultComparisonField("same", "x", "x")),
            (ResultComparisonField("rule_sha256", "old-hash", "new-hash", True),), True, True, True))


def test_validation_multiselection_focus_drives_pdf_comparison_and_whole_choice():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    configure_desktop_theme(root)
    requests, choices = [], []
    view = ValidationView(root, on_refresh=lambda: None, on_save=lambda: None, on_open_pdf=lambda: None,
                          on_preview=requests.append, on_choose=choices.append)
    try:
        first, pending = _validation_item(run_id=7), _pending_validation_item()
        view.render_cases((first, pending))
        old_request = requests[-1]
        view._tree.selection_set(("7", "8"))
        view._tree.focus("8")
        view._on_select(None)
        assert view.selected_item() == pending and view.selected_items() == (first, pending)
        assert view.pdf_request()[2] == pending.run_id and view.pdf_request() != old_request
        rows = [view._fields.item(key, "values") for key in view._fields.get_children()]
        assert ("RESULT", "42", "43") in rows and ("same", "x", "x") in rows
        assert ("Nachweis: rule_sha256", "old-hash", "new-hash") in rows
        assert str(view._btn_save.cget("state")) == "disabled"
        view._btn_keep_old.invoke()
        view._btn_accept_new.invoke()
        assert choices == ["keep_old", "accept_new"]
        view.set_reanalysis_busy(True)
        assert str(view._btn_accept_new.cget("state")) == "disabled"
        view.set_reanalysis_busy(False)
        refreshed = replace(pending, selection_token="original:8|pending:21", comparison=replace(pending.comparison, revision_id=21, can_keep_old=False))
        view.render_cases((first, refreshed))
        assert view.selected_item() == refreshed and len(view.selected_items()) == 2
        assert str(view._btn_keep_old.cget("state")) == "disabled"
        view._tree.focus("7")
        view._on_select(None)
        assert view.selected_item() == first and view.pdf_request()[2] == first.run_id
    finally:
        root.destroy()


def test_shell_reanalysis_captures_all_selected_cases_without_human_validation():
    app = _make_app_stub(current_view="validation")
    app._validation_badge = None
    first, focused = _validation_item(), _pending_validation_item()
    app._settings.sqlite_path = "results.sqlite"
    first = replace(first, store_path="results.sqlite")
    selection = [(first, focused)]
    busy, calls, rendered = [], [], []
    app._views["validation"] = SimpleNamespace(selected_items=lambda: selection[0], selected_item=lambda: selection[0][-1],
        validation_initials=lambda: " RR ", set_reanalysis_busy=busy.append, render_cases=lambda items: rendered.append(items),
        reconcile_cases=lambda items: rendered.append(items))
    app._services.results.reanalyze_selected_cases = lambda cases, initials, **kwargs: calls.append((cases, initials, kwargs)) or SimpleNamespace(items=())
    app._services.results.list_open_validation_cases = lambda **binding: [focused]
    app._services.results.validate_report_run = lambda *_a, **_k: pytest.fail("reanalysis must not validate")
    test_app.AnalyzerDesktopApp._reanalyze_validation_cases(app)
    assert busy == [True] and calls == []
    selection[0] = (first,)
    app._task_runner.invoke_success()
    assert calls[0][0] == (first, focused) and calls[0][1] == "RR" and calls[0][2]["request_id"]
    assert busy == [True, False] and rendered == [[focused]]


def test_shell_choice_uses_focused_snapshot_and_separate_validation_token():
    app = _make_app_stub(current_view="validation")
    app._validation_badge = None
    case = _pending_validation_item()
    app._settings.sqlite_path = case.store_path
    selection = [case]
    busy, calls = [], []
    app._views["validation"] = SimpleNamespace(selected_item=lambda: selection[0],
        validation_initials=lambda: " RR ", validation_comment=lambda: " note ", set_reanalysis_busy=busy.append,
        render_cases=lambda *_a, **_k: None, reconcile_cases=lambda *_: None, clear_comment=lambda: None)
    app._services.results.choose_reanalysis_result = lambda *args, **kwargs: calls.append((args, kwargs))
    app._services.results.list_open_validation_cases = lambda **binding: []
    app._services.results.validate_report_run = lambda *_a, **_k: pytest.fail("choice must not validate")
    test_app.AnalyzerDesktopApp._choose_validation_result(app, "accept_new")
    selection[0] = _validation_item()
    app._task_runner.invoke_success()
    assert calls[0][0] == (case, "accept_new", "RR") and calls[0][1]["note"] == "note"
    assert busy == [True, False]
    chosen = replace(case, comparison=None, revision_id=20, selection_token="selection:30")
    selection[0] = chosen
    app._views["validation"].clear_comment = lambda: None
    validation_calls = []
    app._services.results.validate_report_run = lambda *args, **kwargs: validation_calls.append((args, kwargs))
    test_app.AnalyzerDesktopApp._save_pending_validation(app)
    selection[0] = _validation_item()
    app._task_runner.invoke_success()
    assert validation_calls[0][1]["expected_selection_token"] == "selection:30"
    assert validation_calls[0][1]["store_path"] == "results.sqlite"


def test_results_view_binding_is_from_displayed_occurrence_and_pending_only_navigates():
    root, view = _open_results_view()
    try:
        detail = _report_detail("report", "a.pdf")
        occurrence = ReportRunOccurrence(1, "L", "L", "D", "K", "", (ReportFieldValue("RESULT", "42"),),
            selection_token="displayed-token", store_path="displayed.sqlite", reanalysis_pending=True)
        groups = (ReportAssayGroup("A", "A.json", (occurrence,)),)
        view.render_report_detail(replace(detail, assay_groups=groups))
        first = view._occ_tree.get_children()[0]
        view._occ_tree.selection_set(first)
        view._handle_occurrence_select(None)
        assert view.validation_result_binding() == ("displayed-token", "displayed.sqlite")
        assert view.selected_validation_target() == ("report", 1, "displayed.sqlite", "displayed-token")
        assert str(view._btn_open_validation.cget("state")) == "normal"
        assert not hasattr(view, "_btn_save_validation")
        assert not hasattr(view, "_btn_correct_validation")
    finally:
        root.destroy()


@pytest.mark.parametrize("correct", [False, True])
def test_workplace_validation_and_correction_capture_the_displayed_binding(workplace, correct):
    app, view = workplace
    app._settings.sqlite_path = "displayed.sqlite"
    previous = RunValidationItem(1, 1, "AB", "2026-01-01T00:00:00Z", "first", None, None)
    item = replace(_validation_item(run_id=1), report_id="report", store_path="displayed.sqlite",
                   selection_token="displayed-token", current_validation=previous if correct else None)
    view.render_cases((), direct_case=item)
    view._var_initials.set(" RR ")
    view._var_comment.set(" note ")
    calls = []
    app._services.results.validate_report_run = lambda *args, **kwargs: calls.append(("validate", args, kwargs))
    app._services.results.correct_report_run = lambda *args, **kwargs: calls.append(("correct", args, kwargs))
    app._services.results.get_validation_case = lambda *_a, **_k: item
    app._save_pending_validation()
    view.render_cases((replace(item, selection_token="new-screen-token", store_path="other-store.sqlite"),))
    app._task_runner.submissions[-1][1]()
    assert calls[0][0] == ("correct" if correct else "validate")
    assert calls[0][1] == ("report", 1, "RR", "note")
    assert calls[0][2]["expected_selection_token"] == "displayed-token"
    assert calls[0][2]["store_path"] == "displayed.sqlite"


class _FakeVar:
    def __init__(self, value: object) -> None:
        self._value = value
        self._traces: list[object] = []

    def get(self) -> object:
        return self._value

    def set(self, value: object) -> None:
        self._value = value
        for callback in list(self._traces):
            callback()

    def trace_add(self, _mode: str, callback: object) -> None:
        self._traces.append(callback)


class _SettingsViewLogicStub:
    def __init__(self) -> None:
        self._edit_generation = 0
        self._clean_generation = 0
        self._suppress_dirty = False
        self._var_watch_enabled = _FakeVar(False)
        self._var_watch_input = _FakeVar("")
        self._var_watch_backup = _FakeVar("")
        self._var_watch_recursive = _FakeVar(False)
        self._var_sqlite = _FakeVar("")
        self._var_device = _FakeVar("")
        self._var_operator_initials = _FakeVar("")
        self._device_combo = SimpleNamespace(configure=lambda **_k: None)
        self._lbl_timing = SimpleNamespace(configure=lambda **_k: None)
        for method_name in (
            "_on_field_edited",
            "is_dirty",
            "mark_saved_generation",
            "_apply_settings_values",
            "_render_devices",
            "_render_timing",
            "render_settings",
        ):
            setattr(self, method_name, MethodType(getattr(SettingsView, method_name), self))
        SettingsView._bind_dirty_tracking(self)

    @property
    def edit_generation(self) -> int:
        return self._edit_generation


def _make_settings_view_logic_stub() -> _SettingsViewLogicStub:
    return _SettingsViewLogicStub()


class _RecordingRunner:
    def __init__(self) -> None:
        self.submissions: list[tuple[str, object, object, object]] = []
        self._active: set[str] = set()

    def submit(self, key, work, *, on_success, on_error):  # noqa: ANN001
        if key in self._active:
            return False
        self._active.add(key)
        self.submissions.append((key, work, on_success, on_error))
        return True

    def is_active(self, key: str) -> bool:
        return key in self._active

    def has_in_flight_workers(self) -> bool:
        return bool(self._active)

    def invoke_success(self, index: int = -1, result: object | None = None) -> None:
        key, work, on_success, _on_error = self.submissions[index]
        self._active.discard(key)
        payload = result if result is not None else work()
        on_success(payload)

    def invoke_error(self, index: int = -1, exc: BaseException | None = None) -> None:
        key, _work, _on_success, on_error = self.submissions[index]
        self._active.discard(key)
        on_error(exc or RuntimeError("failed"))

    @property
    def shutdown(self) -> bool:
        return False

    def shutdown_runner(self, *, join_timeout_s: float = 5.0) -> bool:
        return True


def _fake_services() -> SimpleNamespace:
    return SimpleNamespace(
        settings=SimpleNamespace(
            load=lambda: SimpleNamespace(
                watch_enabled=False,
                watch_input_path="",
                watch_backup_path="",
                watch_recursive=False,
                output_mode="both",
                sqlite_path="db.sqlite3",
                device_id=None,
            ),
            save=lambda settings: settings,
            get_device_inventory=lambda: SimpleNamespace(devices=()),
            get_watch_timing=lambda: SimpleNamespace(scan_interval_s=3.0, stable_window_s=2.0),
            get_build_info=lambda: {"version": "2.0.0", "status": "available"},
            reload_device_inventory=lambda: SimpleNamespace(devices=()),
            get_qc_configuration=lambda: SimpleNamespace(store_path=str(Path("db.sqlite3").resolve()), inventory={"snapshot": {"devices": []}}, profiles=()),
            open_output_folder=lambda: "/output",
        ),
        extraction=SimpleNamespace(
            list_ingestion_instances=lambda: [],
            enqueue_manual_pdfs=lambda paths: SimpleNamespace(
                outcomes=tuple(
                    ProcessingEnqueueOutcome(pdf_path=path, file_name=path, outcome="queued")
                    for path in paths
                )
            ),
            process_next=lambda: ProcessingOutcome(processed=False),
            run_watch_cycle=lambda: WatchCycleSummary(enabled=True, scanned_count=1),
            list_job_diagnoses=lambda: [],
            get_job_diagnosis=lambda _job_id: None,
            retry_failed=lambda _job_id: object(),
            retry_excel_export=lambda _job_id: ProcessingOutcome(processed=True, submit_status="DONE"),
        ),
        results=SimpleNamespace(
            list_recent_reports=lambda limit=50, **_binding: [],
            list_qc_lots=lambda: (),
            list_open_validation_cases=lambda limit=None, **_binding: [],
            get_report_detail=lambda _report_id, **_binding: None,
            open_report_pdf=lambda _report_id, **_binding: "/pdf/path.pdf",
            list_duplicate_candidates=lambda status="pending", store_path=None: [],
            get_duplicate_candidate_detail=lambda _candidate_id, *, store_path=None: None,
            discard_duplicate_candidate=lambda _candidate_id, *, store_path=None: object(),
        ),
        rules=SimpleNamespace(
            get_identity_case_count=lambda *, store_path: 0,
            list_inventory=lambda kind="all": [],
            validate_rules_integrity=lambda: {},
            discover_assay_candidates_for_job=lambda _job_id: (),
            create_draft_from_template_if_missing=lambda _k, _n: {},
        ),
    )


def _make_app_stub(*, current_view: str = "results", services: object | None = None) -> test_app.AnalyzerDesktopApp:
    app = test_app.AnalyzerDesktopApp.__new__(test_app.AnalyzerDesktopApp)
    app._current_view = current_view
    app._bootstrapped = True
    app._services = services or _fake_services()
    app._settings = app._services.settings.load()
    app._store_generation = 0
    app._navigation_generation = 0
    app._report_detail_generation = 0
    app._report_detail_request = None
    app._validation_direct_target = None
    app._validation_direct_request = None
    app._validation_navigation_generation = 0
    app._validation_pdf_pending = None
    app._validation_pdf_binding = None
    app._validation_badge = None
    app._view_store_paths = {"results": str(Path(app._settings.sqlite_path).resolve()), "dashboard": str(Path(app._settings.sqlite_path).resolve())}
    app._last_watch_summary = None
    app._last_watch_error = ""
    app._WatchCycleSummary = WatchCycleSummary
    app._ApplicationWatchError = ApplicationWatchError
    app._SettingsValidationError = SettingsValidationError
    app._SettingsSaveError = SettingsSaveError
    app._PathOpenError = PathOpenError
    app._ReportNotFoundError = ReportNotFoundError
    app._dashboard_report_join_limit = 250
    app._device_label_map = {}
    app._watch_after_id = None
    app._watch_schedule_generation = 0
    app._refresh_generation = 0
    app._qc_source_generation, app._qc_source_latest = 0, None
    app._settings_save_latest_id = 0
    app._settings_save_latest = None
    app._settings_save_latest_edit_generation = 0
    app._settings_save_inflight_id = None
    app._scheduled_after: list[tuple[int, object]] = []
    app._views = {
        "dashboard": SimpleNamespace(
            render_import_device=lambda *_a, **_k: None,
            render_open_case_count=lambda *_a, **_k: None,
            render_watch_settings=lambda *_a, **_k: None,
            render_recent_rows=lambda *_a, **_k: None,
            render_watch_session_summary=lambda *_a, **_k: None,
            render_batch_statuses=lambda *_a, **_k: None,
            set_processing_busy=lambda *_a, **_k: None,
            set_activity_message=lambda *_a, **_k: None,
            set_actions_enabled=lambda *_a, **_k: None,
        ),
        "results": SimpleNamespace(render_report_list=lambda items, **_binding: setattr(app, "_rendered_reports", items),
                                   invalidate_store_context=lambda: setattr(app, "_invalidated_results", True)),
        "statistics": SimpleNamespace(render_qc_lots=lambda items: setattr(app, "_rendered_qc_lots", items)),
        "validation": SimpleNamespace(
            set_default_operator_initials=lambda _value: None,
            render_cases=lambda items, **_binding: setattr(app, "_rendered_validation_cases", items),
            begin_direct_loading=lambda **intent: setattr(app, "_direct_loading", intent),
            end_direct_loading=lambda message: setattr(app, "_direct_error", message),
            invalidate_store_context=lambda: setattr(app, "_invalidated_validation", True),
        ),
        "rules": SimpleNamespace(),
        "settings": SimpleNamespace(
            edit_generation=0,
            mark_saved_generation=lambda _generation: None,
            collect_settings=lambda **_kwargs: SimpleNamespace(watch_enabled=False),
            set_status_message=lambda _message: None,
            render_qc_configuration=lambda state, **kwargs: setattr(app, "_rendered_qc_configuration", (state, kwargs)),
        ),
        "diagnostics": SimpleNamespace(),
    }
    app._show_error_dialog = lambda *_a, **_k: setattr(app, "_error_shown", True)
    app._show_info_dialog = lambda *_a, **_k: setattr(app, "_info_shown", True)
    app._show_confirm_dialog = lambda *_a, **_k: True
    app._task_runner = _RecordingRunner()
    app.after = lambda delay_ms, callback: app._scheduled_after.append((delay_ms, callback)) or f"after-{len(app._scheduled_after)}"
    app.after_cancel = lambda _handle: None
    app.title = lambda value: setattr(app, "_rendered_title", value)
    app.refresh_current_view = test_app.AnalyzerDesktopApp.refresh_current_view.__get__(
        app,
        test_app.AnalyzerDesktopApp,
    )
    app.open_rule_editor = lambda: setattr(app, "_rule_editor_opened", True)
    app._cancel_watch_schedule = test_app.AnalyzerDesktopApp._cancel_watch_schedule.__get__(
        app,
        test_app.AnalyzerDesktopApp,
    )
    return app


def _bound_results_stub(app, *, report_id="a", store="db.sqlite3"):
    state = {"selected": report_id, "store": store, "detail": None, "shown": 0}

    def render(detail):
        state["detail"] = detail

    def invalidate():
        state.update(selected="", store="", detail=None)

    view = SimpleNamespace(selected_report_descriptor=lambda: (state["selected"], state["store"]),
        current_detail_descriptor=lambda: (state["detail"].report_id, state["detail"].store_path) if state["detail"] else ("", ""),
        render_report_detail=render, show_detail=lambda: state.__setitem__("shown", state["shown"] + 1),
        invalidate_store_context=invalidate,
        render_report_list=lambda items, **binding: state.update(rows=tuple(items), store=binding.get("store_path", "")))
    app._views["results"] = view
    return view, state


@pytest.mark.parametrize("reverse", [False, True])
def test_report_detail_context_keeps_latest_selected_report_in_both_completion_orders(reverse):
    app = _make_app_stub()
    view, state = _bound_results_stub(app)
    app._services.results.get_report_detail = lambda report, **binding: replace(_report_detail(report, report + ".pdf"), store_path=binding["store_path"])
    app._open_selected_report()
    first = app._task_runner.submissions[0][1]()
    state["selected"] = "b"
    app._open_selected_report()
    second = app._task_runner.submissions[1][1]()
    results = [first, second]
    for index in ((1, 0) if reverse else (0, 1)):
        app._task_runner.invoke_success(index=index, result=results[index])
    assert state["detail"].report_id == "b" and state["detail"].store_path == "db.sqlite3"
    assert state["shown"] == 1 and len(app._task_runner.submissions) == 2


@pytest.mark.parametrize("change", ["selection", "navigation", "store"])
@pytest.mark.parametrize("error", [False, True])
def test_report_detail_context_discards_stale_reply_or_error(change, error):
    app = _make_app_stub()
    _view, state = _bound_results_stub(app)
    app._services.results.get_report_detail = lambda report, **binding: replace(_report_detail(report, report + ".pdf"), store_path=binding["store_path"])
    app._open_selected_report()
    detail = app._task_runner.submissions[0][1]()
    if change == "selection":
        state["selected"] = "b"
    elif change == "navigation":
        app._current_view = "settings"
        app._navigation_generation += 1
    else:
        app._settings.sqlite_path = "other.sqlite3"
    if error:
        app._task_runner.invoke_error(exc=RuntimeError("stale"))
    else:
        app._task_runner.invoke_success(result=detail)
    assert state["detail"] is None and not app.__dict__.get("_error_shown")
    assert app._report_detail_request is None and len(app._task_runner.submissions) == 1


def test_report_pdf_descriptor_uses_displayed_store_and_cancels_replaced_detail():
    app = _make_app_stub()
    _view, state = _bound_results_stub(app, report_id="other-list-selection")
    state["detail"] = replace(_report_detail("displayed", "a.pdf"), store_path="db.sqlite3")
    calls = []
    app._services.results.open_report_pdf = lambda report, **binding: calls.append((report, binding)) or "a.pdf"
    app._open_report_pdf()
    app._task_runner.invoke_success()
    assert calls == [("displayed", {"store_path": "db.sqlite3"})]
    app._open_report_pdf()
    state["detail"] = replace(_report_detail("same-id-in-another-store", "b.pdf"), store_path="other.sqlite3")
    app._task_runner.invoke_success()
    assert len(calls) == 1


def test_direct_context_error_clears_target_loading_and_allows_generic_refresh():
    app = _make_app_stub(current_view="validation")
    target = ("a", 7, "db.sqlite3", "original:7")
    app._begin_direct_validation(target)
    app._task_runner.invoke_error(exc=ValidationConflictError("changed"))
    assert app._validation_direct_target is None and app._validation_direct_request is None
    assert app._validation_pdf_pending is None and app._direct_error
    app.refresh_current_view()
    assert app._task_runner.submissions[-1][0] == app.TASK_REFRESH
    app._task_runner.invoke_success()
    assert app._rendered_validation_cases == [] and app._validation_direct_target is None


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("old_error", [False, True])
def test_refresh_direct_context_cannot_be_overwritten_or_restarted_by_old_queue_reply(reverse, old_error):
    app = _make_app_stub(current_view="validation")
    store = "db.sqlite3"
    direct = replace(_validation_item(), report_id="a", store_path=store, selection_token="original:7")
    open_case = replace(_validation_item(run_id=8), report_id="b", store_path=store)
    app._services.results.list_open_validation_cases = lambda **_binding: [open_case]
    calls, rendered = [], []
    app._services.results.get_validation_case = lambda report, run, **binding: calls.append((report, run, binding)) or direct
    app._views["validation"].render_cases = lambda items, **binding: rendered.append((tuple(items), binding))
    app.refresh_current_view()
    old_payload = app._task_runner.submissions[0][1]()
    app._navigation_generation += 2
    app._begin_direct_validation(("a", 7, store, "original:7"))
    direct_payload = app._task_runner.submissions[1][1]()

    def finish_old():
        if old_error:
            app._task_runner.invoke_error(index=0, exc=RuntimeError("old queue refresh"))
        else:
            app._task_runner.invoke_success(index=0, result=old_payload)

    if reverse:
        app._task_runner.invoke_success(index=1, result=direct_payload)
        finish_old()
    else:
        finish_old()
        app._task_runner.invoke_success(index=1, result=direct_payload)
    assert len(app._task_runner.submissions) == 2 and len(calls) == 1
    assert rendered == [((open_case,), {"direct_case": direct})]
    assert app._validation_direct_target == ("a", 7, store, "original:7")
    assert not app.__dict__.get("_error_shown")


def test_manual_queue_selection_cancels_direct_context_and_old_callback():
    app = _make_app_stub(current_view="validation")
    direct = replace(_validation_item(), report_id="a", store_path="db.sqlite3", selection_token="original:7")
    app._services.results.get_validation_case = lambda *_a, **_k: direct
    app._begin_direct_validation(("a", 7, "db.sqlite3", "original:7"))
    payload = app._task_runner.submissions[0][1]()
    app._validation_queue_selected()
    app._task_runner.invoke_success(result=payload)
    assert app._validation_direct_target is None and app._validation_direct_request is None
    assert "_rendered_validation_cases" not in app.__dict__
    assert len(app._task_runner.submissions) == 1


@pytest.mark.parametrize("old_error", [False, True])
def test_store_snapshot_pins_reads_and_late_refresh_never_reinstalls_old_settings(old_error):
    app = _make_app_stub(current_view="results")
    _view, state = _bound_results_stub(app)
    first = app._settings
    second = SimpleNamespace(**{**vars(first), "sqlite_path": "second.sqlite3"})
    live = [first]
    reads = []
    app._services.settings.load = lambda: live[0]
    app._services.results.list_open_validation_cases = lambda **binding: reads.append(("queue", binding["store_path"])) or []
    app._services.results.list_recent_reports = lambda **binding: reads.append(("reports", binding["store_path"])) or [_report_summary("same-id", "a.pdf" if live[0] is first else "b.pdf")]
    app.refresh_current_view()
    old_payload = app._task_runner.submissions[0][1]()
    expected_first = str(Path(first.sqlite_path).resolve())
    assert reads == [("queue", expected_first), ("reports", expected_first)]
    app._views["settings"].collect_settings = lambda **_kwargs: second
    app._services.settings.save = lambda _settings: second
    app._reschedule_watch = lambda: None
    live[0] = second
    app._save_settings()
    app._task_runner.invoke_success(index=1)
    assert app._settings is second and state["detail"] is None
    assert app._invalidated_validation
    assert state["store"] == "" and state["detail"] is None
    if old_error:
        app._task_runner.invoke_error(index=0, exc=RuntimeError("old store"))
    else:
        app._task_runner.invoke_success(index=0, result=old_payload)
    assert app._settings is second and not app.__dict__.get("_error_shown")
    app._task_runner.invoke_success(index=2)
    expected_second = str(Path(second.sqlite_path).resolve())
    assert state["store"] == expected_second and state["rows"][0].file_name == "b.pdf"
    assert reads[-2:] == [("queue", expected_second), ("reports", expected_second)]


def test_store_snapshot_alias_uses_controller_resolved_path_semantics(monkeypatch):
    original_resolve = Path.resolve
    canonical = Path("I:/canonical/results.sqlite3")

    def resolve(path, *args, **kwargs):
        return canonical if str(path) in {"alias.sqlite3", "canonical.sqlite3"} else original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    app = _make_app_stub()
    app._settings.sqlite_path = "alias.sqlite3"
    assert app._ui_store_matches("canonical.sqlite3")
    before = app._refresh_scope()
    same_store = SimpleNamespace(**{**vars(app._settings), "sqlite_path": "canonical.sqlite3"})
    assert app._accept_settings_snapshot(same_store) is False
    assert app._refresh_scope() == before and not app.__dict__.get("_invalidated_validation")


def test_direct_context_only_case_save_releases_generic_refresh_for_new_incoming_case():
    app = _make_app_stub(current_view="validation")
    first = replace(_validation_item(), report_id="a", store_path="db.sqlite3", selection_token="original:7")
    following = replace(_validation_item(run_id=8), report_id="b", store_path="db.sqlite3")
    items, selected = [[first]], [None]
    view = app._views["validation"]

    def render(cases, **binding):
        selected[0] = binding.get("direct_case") or (cases[0] if cases else None)

    view.render_cases = render
    view.selected_item = lambda: selected[0]
    view.validation_initials = lambda: "AB"
    view.validation_comment = lambda: ""
    view.clear_comment = lambda: None
    app._services.results.get_validation_case = lambda *_a, **_k: first
    app._services.results.list_open_validation_cases = lambda **_binding: items[0]
    calls = []

    def validate(*args, **binding):
        calls.append((args, binding))
        items[0] = []

    app._services.results.validate_report_run = validate
    app._begin_direct_validation(("a", 7, "db.sqlite3", "original:7"))
    app._task_runner.invoke_success()
    assert selected[0] is first and app._validation_direct_request is None
    app._save_pending_validation()
    app._task_runner.invoke_success()
    assert len(calls) == 1 and selected[0] is None
    assert app._validation_direct_target is None and app._validation_direct_request is None
    items[0] = [following]
    app.refresh_current_view()
    assert app._task_runner.submissions[-1][0] == app.TASK_REFRESH
    app._task_runner.invoke_success()
    assert selected[0] is following


def test_store_snapshot_coalesced_persisted_B_survives_failed_C_and_held_A():
    app = _make_app_stub(current_view="results")
    _view, state = _bound_results_stub(app)
    first = app._settings
    second = SimpleNamespace(**{**vars(first), "sqlite_path": "second.sqlite3"})
    third = SimpleNamespace(**{**vars(first), "sqlite_path": "third.sqlite3"})
    live, drafts, marked = [first], [second, third], []
    app._services.settings.load = lambda: live[0]
    app._views["settings"].collect_settings = lambda **_kwargs: drafts.pop(0)
    app._views["settings"].mark_saved_generation = marked.append
    app._reschedule_watch = lambda: None

    def persist(settings):
        if settings is third:
            raise SettingsSaveError("third failed")
        live[0] = settings
        return settings

    app._services.settings.save = persist
    app.refresh_current_view()
    held_first = app._task_runner.submissions[0][1]()
    app._save_settings()
    app._save_settings()
    app._task_runner.invoke_success(index=1)
    assert app._settings is second and live[0] is second and marked == []
    assert app._invalidated_validation and state["store"] == ""
    app._task_runner.invoke_error(index=2, exc=SettingsSaveError("third failed"))
    assert app._settings is second and live[0] is second and marked == []
    app._task_runner.invoke_success(index=0, result=held_first)
    assert app._settings is second
    app._task_runner.invoke_success(index=3)
    assert app._settings is second and state["store"] == str(Path(second.sqlite_path).resolve())


def test_legacy_alias_points_to_test_app() -> None:
    assert test_app.LegacyTestApp is test_app.TestApp


def test_main_defaults_to_analyzer_desktop_app() -> None:
    source = inspect.getsource(test_app.main)
    assert "AnalyzerDesktopApp(" in source
    assert "legacy_ui_enabled()" in source


def test_main_defaults_to_analyzer_desktop_app_instance(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeDesktop:
        def __init__(self, project_root: object) -> None:
            captured["class"] = "desktop"
            captured["project_root"] = project_root

        def mainloop(self) -> None:
            captured["mainloop"] = True

    monkeypatch.delenv("ARE_LEGACY_UI", raising=False)
    monkeypatch.setattr(test_app, "AnalyzerDesktopApp", FakeDesktop)
    monkeypatch.setattr(
        test_app,
        "LegacyTestApp",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("legacy must not be used")),
    )
    test_app.main(project_root=tmp_path)
    assert captured["class"] == "desktop"
    assert captured["project_root"] == tmp_path.resolve()
    assert captured["mainloop"] is True


def test_main_legacy_ui_flags_use_legacy_test_app(tmp_path, monkeypatch) -> None:
    for value in ("1", "true", "YES"):
        captured: dict[str, object] = {}

        class FakeLegacy:
            def __init__(self, project_root: object) -> None:
                captured["class"] = "legacy"
                captured["project_root"] = project_root

            def mainloop(self) -> None:
                captured["mainloop"] = True

        monkeypatch.setenv("ARE_LEGACY_UI", value)
        monkeypatch.setattr(test_app, "LegacyTestApp", FakeLegacy)
        monkeypatch.setattr(
            test_app,
            "AnalyzerDesktopApp",
            lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("desktop must not be used")),
        )
        test_app.main(project_root=tmp_path)
        assert captured["class"] == "legacy"
        assert captured["project_root"] == tmp_path.resolve()


def test_main_unknown_legacy_flag_uses_analyzer_desktop_app(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeDesktop:
        def __init__(self, project_root: object) -> None:
            captured["project_root"] = project_root

        def mainloop(self) -> None:
            return None

    monkeypatch.setenv("ARE_LEGACY_UI", "0")
    monkeypatch.setattr(test_app, "AnalyzerDesktopApp", FakeDesktop)
    test_app.main(project_root=tmp_path)
    assert captured["project_root"] == tmp_path.resolve()


def test_main_resolves_are_home_before_desktop_construction(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeDesktop:
        def __init__(self, project_root: object) -> None:
            captured["project_root"] = project_root

        def mainloop(self) -> None:
            return None

    monkeypatch.setenv("ARE_HOME", str(tmp_path))
    monkeypatch.delenv("ARE_LEGACY_UI", raising=False)
    monkeypatch.setattr(test_app, "AnalyzerDesktopApp", FakeDesktop)
    test_app.main(project_root=None)
    assert captured["project_root"] == tmp_path.resolve()


def test_run_entry_smoke_beats_editor_and_legacy(monkeypatch, tmp_path) -> None:
    calls: list[object] = []
    monkeypatch.setenv("ARE_SMOKE_EXIT", "1")
    monkeypatch.setenv("ARE_START_RULE_EDITOR", "1")
    monkeypatch.setenv("ARE_LEGACY_UI", "1")
    monkeypatch.setattr(
        test_app,
        "run_startup_smoke_check",
        lambda project_root: calls.append(("smoke", project_root)),
    )
    monkeypatch.setattr(test_app, "main", lambda **_k: calls.append("main"))
    test_app.run_entry(tmp_path / "test_app_main.py")
    assert calls == [("smoke", tmp_path.resolve())]


def test_run_entry_editor_beats_main_and_legacy(monkeypatch, tmp_path) -> None:
    import rule_editor_main

    calls: list[str] = []
    monkeypatch.delenv("ARE_SMOKE_EXIT", raising=False)
    monkeypatch.setenv("ARE_START_RULE_EDITOR", "1")
    monkeypatch.setenv("ARE_LEGACY_UI", "1")

    class FakeEditor:
        def __init__(self, project_root: object) -> None:
            self.project_root = project_root

        def mainloop(self) -> None:
            calls.append("editor")

    monkeypatch.setattr(rule_editor_main, "RuleEditorWindow", FakeEditor)
    monkeypatch.setattr(test_app, "main", lambda **_k: calls.append("main"))
    test_app.run_entry(tmp_path / "test_app_main.py")
    assert calls == ["editor"]


def test_run_entry_passes_resolved_root_to_main(monkeypatch, tmp_path) -> None:
    captured: list[object] = []
    monkeypatch.delenv("ARE_SMOKE_EXIT", raising=False)
    monkeypatch.delenv("ARE_START_RULE_EDITOR", raising=False)
    monkeypatch.setattr(test_app, "main", lambda project_root=None: captured.append(project_root))
    test_app.run_entry(tmp_path / "test_app_main.py")
    assert captured == [tmp_path.resolve()]


def test_analyzer_desktop_open_rule_editor_uses_existing_view_even_when_frozen(tmp_path, monkeypatch) -> None:
    app = test_app.AnalyzerDesktopApp.__new__(test_app.AnalyzerDesktopApp)
    app.project_root = tmp_path.resolve()
    calls: list[str] = []
    app.show_view = calls.append

    monkeypatch.setattr(test_app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(test_app.sys, "executable", str(tmp_path / "AnalyzerResultExtractorV2.exe"))
    monkeypatch.setattr(test_app.subprocess, "Popen", lambda *_a, **_k: pytest.fail("embedded editor must not launch a process"))
    test_app.AnalyzerDesktopApp.open_rule_editor(app)
    assert calls == ["rules"]


def test_rules_inventory_item_ids_are_unique_for_duplicate_assay_keys() -> None:
    items = [
        RulesetInventoryItem("active", "Active", "Assay-A", "A", "rules/A.json", "A.json", 1, True, None),
        RulesetInventoryItem("draft", "Draft", "Assay-A", "A", "rules/drafts/A.json", "A.json", 2, True, None),
    ]
    ids = [rules_inventory_item_id(item, index) for index, item in enumerate(items)]
    assert len(ids) == len(set(ids))


def test_dashboard_uses_ingestion_status_not_report_status() -> None:
    ingestions = [
        IngestionInstanceItem(
            ingestion_id="ing-1",
            job_id="job-1",
            file_name="sample.pdf",
            source_kind="manual",
            original_path="/tmp/sample.pdf",
            current_path="/tmp/sample.pdf",
            processing_status="DONE",
            queue_status="DONE",
            archive_status="NOT_REQUIRED",
            display_status="Wartet",
            friendly_message="",
            technical_detail="",
            updated_at="2026-09-22T10:15:00+00:00",
        )
    ]
    reports = [
        ReportSummaryItem(
            report_id="rep-1",
            job_id="job-1",
            pdf_path="/tmp/sample.pdf",
            file_name="sample.pdf",
            current_pdf_path="/tmp/sample.pdf",
            run_count=3,
            assay_count=2,
            latest_created_at="2026-09-22T10:15:00+00:00",
            display_status="Fertig",
        )
    ]
    rows = build_dashboard_recent_rows(ingestions, reports)
    assert rows[0].status == "Wartet"
    assert "3 Ergebnis(se)" in rows[0].summary
    assert "2 Assay(s)" in rows[0].summary
    assert rows[0].report_id == "rep-1"
    assert len(rows) <= DASHBOARD_RECENT_LIMIT


def test_build_batch_file_statuses_preserves_per_file_outcomes() -> None:
    enqueue = (
        ProcessingEnqueueOutcome(pdf_path="/a.pdf", file_name="a.pdf", outcome="queued"),
        ProcessingEnqueueOutcome(pdf_path="/b.pdf", file_name="b.pdf", outcome="error", message="pdf_not_found"),
    )
    processing = (
        ProcessingOutcome(processed=True, pdf_path="/a.pdf", file_name="a.pdf", queue_status="DONE", submit_status="ok"),
    )
    statuses = build_batch_file_statuses(enqueue, processing)
    assert statuses[0].status_label == "Erfolgreich"
    assert statuses[1].status_label == "Fehler"


def test_build_batch_file_statuses_registered_done_shows_success() -> None:
    enqueue = (ProcessingEnqueueOutcome(pdf_path="/a.pdf", file_name="a.pdf", outcome="registered"),)
    processing = (
        ProcessingOutcome(processed=True, pdf_path="/a.pdf", file_name="a.pdf", queue_status="DONE", submit_status="ok"),
    )
    statuses = build_batch_file_statuses(enqueue, processing)
    assert statuses[0].status_label == "Erfolgreich"


def test_dashboard_and_batch_show_saved_excel_failure() -> None:
    message = "Ergebnis gespeichert – Excel-Ausgabe fehlgeschlagen"
    ingestions = [
        IngestionInstanceItem(
            ingestion_id="ing-excel",
            job_id="job-excel",
            file_name="sample.pdf",
            source_kind="manual",
            original_path="/tmp/sample.pdf",
            current_path="/tmp/sample.pdf",
            processing_status="FAILED",
            queue_status="FAILED",
            archive_status="PENDING",
            display_status="Verarbeitung fehlgeschlagen",
            friendly_message=message,
            technical_detail="excel_write_failed_after_save:(1111):disk full",
        )
    ]
    reports = [
        ReportSummaryItem(
            report_id="rep-excel",
            job_id="job-excel",
            pdf_path="/tmp/sample.pdf",
            file_name="sample.pdf",
            current_pdf_path="/tmp/sample.pdf",
            run_count=1,
            assay_count=1,
            latest_created_at="2026-09-24T08:00:00+00:00",
            display_status="Fertig",
        )
    ]
    rows = build_dashboard_recent_rows(ingestions, reports)
    assert rows[0].summary == message
    enqueue = (ProcessingEnqueueOutcome(pdf_path="/tmp/sample.pdf", file_name="sample.pdf", outcome="registered"),)
    processing = (
        ProcessingOutcome(
            processed=True,
            pdf_path="/tmp/sample.pdf",
            file_name="sample.pdf",
            queue_status="FAILED",
            submit_status="FAILED",
            message="excel_write_failed_after_save:(1111):disk full",
        ),
        ProcessingOutcome(
            processed=True,
            pdf_path="/tmp/parse.pdf",
            file_name="parse.pdf",
            queue_status="FAILED",
            submit_status="FAILED",
            message="no_assay_detected",
        ),
    )
    statuses = build_batch_file_statuses(
        enqueue + (ProcessingEnqueueOutcome(pdf_path="/tmp/parse.pdf", file_name="parse.pdf", outcome="registered"),),
        processing,
    )
    assert statuses[0].detail == message
    assert statuses[1].detail == "no_assay_detected"


def test_build_batch_file_statuses_registered_failed_shows_error() -> None:
    enqueue = (ProcessingEnqueueOutcome(pdf_path="/a.pdf", file_name="a.pdf", outcome="registered"),)
    processing = (
        ProcessingOutcome(
            processed=True,
            pdf_path="/a.pdf",
            file_name="a.pdf",
            queue_status="FAILED",
            submit_status="FAILED",
            message="parse_failed",
        ),
    )
    statuses = build_batch_file_statuses(enqueue, processing)
    assert statuses[0].status_label == "Fehler"


def test_build_batch_file_statuses_registered_without_processing_stays_registered() -> None:
    enqueue = (ProcessingEnqueueOutcome(pdf_path="/a.pdf", file_name="a.pdf", outcome="registered"),)
    statuses = build_batch_file_statuses(enqueue, ())
    assert statuses[0].status_label == "Registriert"


def test_watch_summary_counts_registered_outcomes() -> None:
    summary = WatchCycleSummary(
        enabled=True,
        scanned_count=2,
        outcomes=(
            ProcessingEnqueueOutcome(pdf_path="/a.pdf", file_name="a.pdf", outcome="registered"),
            ProcessingEnqueueOutcome(pdf_path="/b.pdf", file_name="b.pdf", outcome="registered"),
        ),
    )
    text = format_watch_cycle_summary(summary)
    assert "2 registriert" in text


def test_watch_summary_error_replaces_success_display() -> None:
    text = format_watch_cycle_summary(None, error="watch_input_path_required")
    assert "Fehler" in text
    assert "Eingabeordner" in text
    assert "watch_input_path_required" not in text


def test_format_user_error_message_maps_known_codes() -> None:
    assert "Eingabeordner" in format_user_error_message("watch_input_path_required")
    assert "Archivordner" in format_user_error_message("watch_backup_path_required")
    assert format_user_error_message("watch_input_not_directory: /tmp/x") == "Der Eingabeordner ist kein Verzeichnis."
    assert "/tmp/x" not in format_user_error_message("watch_input_not_directory: /tmp/x")
    assert format_user_error_message("watch_backup_path_is_file: /tmp/x") == (
        "Der Archivpfad ist eine Datei und kein Ordner."
    )
    assert "/tmp/x" not in format_user_error_message("watch_backup_path_is_file: /tmp/x")
    assert "identisch" in format_user_error_message("watch_input_backup_same_path")
    assert format_user_error_message("invalid_output_mode: foo") == "Ungültiger Ausgabemodus."
    assert "foo" not in format_user_error_message("invalid_output_mode: foo")
    assert "deaktiviert" in format_user_error_message("watch_disabled")
    assert "Geräteauswahl" in format_user_error_message("invalid_device_id_type")
    assert "widersprechen" in format_user_error_message("conflicting_watch_dir_and_watch_input_path")
    assert "leer" in format_user_error_message("path_empty")
    assert format_user_error_message("path_not_found: /tmp/out") == "Der Pfad wurde nicht gefunden."
    assert "/tmp/out" not in format_user_error_message("path_not_found: /tmp/out")
    assert format_user_error_message("path_open_failed: denied") == "Der Pfad konnte nicht geöffnet werden."
    assert "denied" not in format_user_error_message("path_open_failed: denied")
    assert format_user_error_message("desktop_settings_save_failed: disk full") == (
        "Die Einstellungen konnten nicht gespeichert werden."
    )
    assert "disk full" not in format_user_error_message("desktop_settings_save_failed: disk full")
    assert "gerade verwendet" in format_user_error_message("validation_store_busy")
    assert "nicht gelesen" in format_user_error_message("validation_store_unreadable: corrupt")
    assert "kommentar" in format_user_error_message("validation_comment_invalid").lower()
    assert format_user_error_message("totally_unknown_code") == GENERIC_ACTION_FAILED_MESSAGE
    assert "totally_unknown_code" not in format_user_error_message("totally_unknown_code")

    message, details = user_error_dialog_parts("path_empty")
    assert message == format_user_error_message("path_empty")
    assert details == "path_empty"

    prefixed_cases = (
        "watch_input_not_directory: /tmp/x",
        "watch_backup_path_is_file: /tmp/x",
        "invalid_output_mode: foo",
        "path_not_found: /tmp/out",
        "path_open_failed: denied",
        "desktop_settings_save_failed: disk full",
    )
    for raw in prefixed_cases:
        primary, raw_details = user_error_dialog_parts(raw)
        assert primary == format_user_error_message(raw)
        assert raw_details == raw
        code, _sep, remainder = raw.partition(":")
        assert code not in primary
        if remainder.strip():
            assert remainder.strip() not in primary


def test_watch_summary_disabled_reason_is_friendly() -> None:
    summary = WatchCycleSummary(enabled=False, disabled_reason="watch_disabled")
    text = format_watch_cycle_summary(summary)
    assert "deaktiviert" in text
    assert "watch_disabled" not in text


def test_occurrence_ids_stable_for_two_groups_with_run_id_none() -> None:
    detail = ReportDetail(
        report_id="rep-1",
        job_id="job-1",
        pdf_path="/tmp/sample.pdf",
        file_name="sample.pdf",
        current_pdf_path="/tmp/sample.pdf",
        ingestion_id="ing-1",
        path_status="resolved",
        assay_groups=(
            ReportAssayGroup(
                assay_key="Assay-A",
                ruleset_file="A.json",
                occurrences=(
                    ReportRunOccurrence(
                        run_id=None,
                        lot_id="L1",
                        charge="C1",
                        device_id="D1",
                        dedupe_key="",
                        created_at="2026-09-22T10:15:00+00:00",
                        fields=(ReportFieldValue(field_key="result", value="pos"), ReportFieldValue(field_key="note", value="")),
                    ),
                ),
            ),
            ReportAssayGroup(
                assay_key="Assay-B",
                ruleset_file="B.json",
                occurrences=(
                    ReportRunOccurrence(
                        run_id=None,
                        lot_id="L2",
                        charge="C2",
                        device_id="D2",
                        dedupe_key="",
                        created_at="2026-09-22T10:16:00+00:00",
                        fields=(ReportFieldValue(field_key="flag", value="x"),),
                    ),
                ),
            ),
        ),
    )
    second_id = occurrence_id(
        detail.assay_groups[1],
        detail.assay_groups[1].occurrences[0],
        global_index=1,
        group_index=1,
        occ_index=0,
    )
    fields = occurrence_field_rows(detail, second_id)
    assert ("note", "") not in fields
    assert ("flag", "x") in fields


def test_duplicate_detail_formatter_includes_all_fields() -> None:
    detail = DuplicateCandidateDetail(
        candidate=DuplicateCandidateItem(
            candidate_id=7,
            status="pending",
            assay_key="Assay-A",
            dedupe_key="dk",
            existing_run_id=42,
            detected_at="2026-09-22",
            device_id="dev-1",
            dedupe_version="v1",
            pdf_sha256="sha",
            assay_block_hash="abh",
            decision_at="",
            decision_by="",
            decision_note="",
            dedupe_basis={"k": "v"},
            candidate_meta={"m": 1},
        ),
        existing=DuplicateExistingRunItem(
            run_id=42,
            job_id="job-1",
            pdf_path="/tmp/a.pdf",
            assay_key="Assay-A",
            lot_id="L1",
            charge="C1",
            dedupe_key="dk",
            device_id="dev-1",
            dedupe_version="v1",
            created_at="2026-09-21",
            dedupe_basis={"old": True},
        ),
        field_comparison=(
            DuplicateFieldComparisonItem("result", "1", "2", changed=True),
        ),
    )
    text = format_duplicate_detail_lines(detail)
    assert "existing_run_id" in text or "Bestehender Lauf-ID: 42" in text
    assert "Dedupe-Basis" in text
    assert "Charge: C1" in text


def test_create_scrollable_tree_wires_both_axes() -> None:
    source = inspect.getsource(create_scrollable_tree)
    assert "xscrollcommand" in source
    assert "yscrollcommand" in source


def test_refresh_same_view_coalesces_rejected_second_request_on_success() -> None:
    app = _make_app_stub(current_view="results")
    applied: list[object] = []
    app._apply_view_payload = lambda _view_key, payload: applied.append(payload.get("reports"))

    app.refresh_current_view()
    app.refresh_current_view()
    assert app._refresh_generation == 2
    assert len(app._task_runner.submissions) == 1

    app._task_runner.invoke_success(result={"view": "results", "reports": ["old"]})
    assert applied == []
    assert len(app._task_runner.submissions) == 2

    app._task_runner.invoke_success(result={"view": "results", "reports": ["new"]}, index=1)
    assert applied == [["new"]]


def test_refresh_same_view_coalesces_rejected_second_request_on_error() -> None:
    app = _make_app_stub(current_view="results")
    dialogs: list[tuple[str, str, str]] = []
    app._show_error_dialog = lambda _parent, title, message, **kwargs: dialogs.append(
        (title, message, kwargs.get("details", ""))
    )

    app.refresh_current_view()
    app.refresh_current_view()
    app._task_runner.invoke_error(exc=RuntimeError("stale-error"))
    assert dialogs == []
    assert len(app._task_runner.submissions) == 2

    app._task_runner.invoke_error(exc=RuntimeError("path_not_found: /tmp/out"), index=1)
    assert len(dialogs) == 1
    assert dialogs[0][1] == format_user_error_message("path_not_found: /tmp/out")
    assert dialogs[0][2] == "path_not_found: /tmp/out"


def test_refresh_stale_success_retriggers_current_view() -> None:
    app = _make_app_stub(current_view="results")
    app.refresh_current_view()
    key, _work, on_success, _on_error = app._task_runner.submissions[0]
    assert key == app.TASK_REFRESH
    app._current_view = "dashboard"
    app._task_runner.invoke_success(result={"view": "results", "settings": app._settings})
    assert len(app._task_runner.submissions) == 2
    assert "_rendered_reports" not in app.__dict__


def test_refresh_stale_error_retriggers_current_view() -> None:
    app = _make_app_stub(current_view="results")
    app.refresh_current_view()
    _key, _work, _on_success, on_error = app._task_runner.submissions[0]
    app._current_view = "dashboard"
    app._task_runner.invoke_error(exc=RuntimeError("stale"))
    assert len(app._task_runner.submissions) == 2
    assert not app.__dict__.get("_error_shown")


def test_submit_processing_resets_busy_when_submit_rejected() -> None:
    app = _make_app_stub()
    dashboard = app._views["dashboard"]
    busy_states: list[bool] = []
    dashboard.set_processing_busy = lambda value: busy_states.append(value)
    app._task_runner._active.add(app.TASK_PROCESSING)
    submitted = app._submit_processing(activity_message="x", work=lambda: None, on_success=lambda _r: None)
    assert submitted is False
    assert busy_states == [True, False]


def test_open_report_pdf_submits_runner_work() -> None:
    app = _make_app_stub()
    app._views["results"] = SimpleNamespace(current_detail_descriptor=lambda: ("rep-1", "db.sqlite3"))
    app._open_report_pdf()
    key, work, _ok, _err = app._task_runner.submissions[0]
    assert key == "open-pdf-rep-1"
    assert work() == "/pdf/path.pdf"


_MULTI_REPORT_ID = "multi-prior-detail"
_WATCH_REPORT_ID = "1db07474a4f4dff4"


def _report_summary(report_id: str, file_name: str) -> ReportSummaryItem:
    return ReportSummaryItem(
        report_id=report_id,
        job_id=report_id,
        pdf_path=file_name,
        file_name=file_name,
        current_pdf_path=file_name,
        run_count=1,
        assay_count=1,
        latest_created_at="2026-01-01T00:00:00",
    )


def _report_detail(report_id: str, file_name: str) -> ReportDetail:
    return ReportDetail(
        report_id=report_id,
        job_id=report_id,
        pdf_path=file_name,
        file_name=file_name,
        current_pdf_path=file_name,
        ingestion_id="",
        path_status="ok",
        assay_groups=(),
        store_path="db.sqlite3",
    )


def _open_results_view() -> tuple[tk.Tk, ResultsView]:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    configure_desktop_theme(root)
    view = ResultsView(
        root,
        on_refresh=lambda: None,
        on_open_selected=lambda: None,
        on_open_pdf=lambda: None,
        on_open_output_folder=lambda: None,
        on_back=lambda: None,
        on_occurrence_selected=lambda _occurrence_id: None,
    )
    return root, view


def _validation_item(*, run_id: int = 7, ambiguous: bool = False) -> ValidationQueueItem:
    return ValidationQueueItem(
        report_id="report-1",
        run_id=run_id,
        file_name="report.pdf",
        current_pdf_path="/reports/report.pdf",
        assay_key="(1111)",
        lot_id="LOT-A",
        device_id="DEV-1",
        created_at="2026-01-01T10:00:00Z",
        fields=(ReportFieldValue("RESULT", "42"),),
        validation_ambiguous=ambiguous,
        store_path="db.sqlite3",
        selection_token=f"original:{run_id}",
    )


@pytest.fixture
def workplace():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    configure_desktop_theme(root)
    app = _make_app_stub(current_view="validation")
    view = ValidationView(root, on_refresh=app.refresh_current_view, on_save=app._save_pending_validation,
                          on_open_pdf=app._open_validation_pdf, on_case_selected=app._validation_queue_selected)
    app._views["validation"] = view
    yield app, view
    root.destroy()


@pytest.mark.parametrize("eligible_next", [False, True])
def test_workplace_first_save_advances_only_visible_eligible_case_and_keeps_initials(workplace, eligible_next):
    app, view = workplace
    first = _validation_item()
    blocked = replace(_validation_item(run_id=8), missing_fields=("DATUM",))
    hidden = replace(_validation_item(run_id=9), device_id="OTHER")
    following = _validation_item(run_id=10)
    items = (first, blocked, hidden, *((following,) if eligible_next else ()))
    view.render_cases(items)
    view._filters["device"].select_values((first.device_id,))
    view._apply_filters()
    view._var_initials.set(" AB ")
    view._var_comment.set(" first only ")
    calls, badge = [], []
    app._validation_badge = SimpleNamespace(set_status=lambda text, **kwargs: badge.append(text))
    app._show_confirm_dialog = lambda *_a, **_k: pytest.fail("first validation needs no correction confirmation")
    app._services.results.validate_report_run = lambda *args, **binding: calls.append((args, binding))
    remaining = items[1:]
    app._services.results.list_open_validation_cases = lambda **binding: remaining
    app._save_pending_validation()
    app._task_runner.invoke_success()
    assert len(calls) == 1 and calls[0][0] == (first.report_id, first.run_id, "AB", "first only")
    assert view.validation_initials() == " AB " and view.validation_comment() == ""
    assert tuple(view._tree.get_children()) == (("8", "10") if eligible_next else ("8",))
    assert view.selected_item() == (following if eligible_next else None)
    assert badge == [str(len(remaining))]
    assert not view._focus_mode


def test_workplace_held_save_reconciles_badge_without_hijacking_new_selection_pdf_or_draft(workplace):
    app, view = workplace
    first, second = _validation_item(), _validation_item(run_id=8)
    view.render_cases((first, second))
    view._var_initials.set("AB")
    view._var_comment.set("A draft")
    calls, badge = [], []
    app._services.results.validate_report_run = lambda *args, **binding: calls.append((args, binding))
    app._services.results.list_open_validation_cases = lambda **binding: (second,)
    app._validation_badge = SimpleNamespace(set_status=lambda text, **kwargs: badge.append(text))
    app._save_pending_validation()
    payload = app._task_runner.submissions[0][1]()
    view._tree.selection_set("8")
    view._tree.focus("8")
    view._on_select(None)
    view._var_initials.set("CD")
    view._var_comment.set("B draft")
    view._set_pdf_zoom(1.5)
    before_pdf, before_context = view.pdf_request(), view.selection_context()
    app._task_runner.invoke_success(result=payload)
    assert len(calls) == 1 and calls[0][0][1] == first.run_id
    assert view.selected_item() == second and view.selected_items() == (second,)
    assert tuple(view._tree.get_children()) == ("8",) and badge == ["1"]
    assert view.validation_initials() == "CD" and view.validation_comment() == "B draft"
    assert view.pdf_request() == before_pdf and view.selection_context() == before_context


def test_workplace_last_filtered_case_save_keeps_empty_filter_scope(workplace):
    app, view = workplace
    first = replace(_validation_item(), assay_name="Assay A")
    remaining = replace(_validation_item(run_id=8), assay_name="Assay B")
    view.render_cases((first, remaining))
    view._filters["assay"].select_values(("Assay A",))
    view._var_initials.set("AB")
    app._services.results.validate_report_run = lambda *_a, **_k: None
    app._services.results.list_open_validation_cases = lambda **binding: (remaining,)
    app._save_pending_validation()
    app._task_runner.invoke_success()
    assert view._filters["assay"].selected_values == frozenset({"Assay A"})
    assert "Assay A" in view._filters["assay"]._variables
    assert view.selected_item() is None and view._tree.get_children() == ()
    assert view.validation_initials() == "AB"
    view._filters["assay"].select_values(())
    assert view.selected_item() == remaining


def test_workplace_advance_without_eligible_case_clears_previous_multiselection(workplace):
    app, view = workplace
    first = _validation_item()
    pending = replace(_pending_validation_item(), store_path=first.store_path)
    blocked = replace(_validation_item(run_id=9), activation_blocked_reason="Quelle noch nicht abgeschlossen")
    view.render_cases((first, pending, blocked))
    view._tree.selection_set(("7", "8", "9"))
    view._tree.focus("7")
    view._on_select(None)
    view._var_initials.set("AB")
    app._services.results.validate_report_run = lambda *_a, **_k: None
    app._services.results.list_open_validation_cases = lambda **binding: (pending, blocked)
    app._save_pending_validation()
    app._task_runner.invoke_success()
    view._on_select(None)  # A queued native Treeview event must not revive an old row.
    assert view._tree.selection() == () and view.selected_items() == () and view.selected_item() is None
    assert str(view._btn_save.cget("state")) == "disabled"


@pytest.mark.parametrize("old_refresh_first", [False, True])
def test_workplace_write_serializes_queue_snapshot_and_drops_prewrite_refresh(workplace, old_refresh_first):
    app, view = workplace
    first, second = _validation_item(), _validation_item(run_id=8)
    cases, calls, badge = [(first, second)], [], []
    view.render_cases(cases[0])
    view._var_initials.set("AB")
    app._validation_badge = SimpleNamespace(set_status=lambda text, **kwargs: badge.append(text))
    app._services.results.list_open_validation_cases = lambda **binding: cases[0]
    app.refresh_current_view()
    old_payload = app._task_runner.submissions[0][1]()

    def save(report, run, initials, comment, **binding):
        calls.append((report, run, initials, binding))
        cases[0] = tuple(case for case in cases[0] if case.run_id != run)

    app._services.results.validate_report_run = save
    app._save_pending_validation()
    saved_payload = app._task_runner.submissions[1][1]()
    view._tree.selection_set("8")
    view._tree.focus("8")
    view._on_select(None)
    view._var_comment.set("B draft")
    assert str(view._btn_save.cget("state")) == "disabled"
    app._save_pending_validation()  # Deliberate second intent has visible busy feedback, no second writer.
    assert app.__dict__.get("_info_shown") and len(app._task_runner.submissions) == 2
    for index in ((0, 1) if old_refresh_first else (1, 0)):
        app._task_runner.invoke_success(index=index, result=old_payload if index == 0 else saved_payload)
    assert len(app._task_runner.submissions) == 2 and len(calls) == 1
    assert tuple(view._tree.get_children()) == ("8",) and view.selected_item() == second
    assert view.validation_comment() == "B draft" and badge == ["1"]
    assert str(view._btn_save.cget("state")) == "normal"
    app._save_pending_validation()
    app._task_runner.invoke_success()
    assert [call[1] for call in calls] == [7, 8] and badge == ["1", "0"]
    assert view.selected_item() is None and not view._tree.get_children()


def test_workplace_direct_jump_during_save_defers_queue_read_until_fresh_write_reconciliation(workplace):
    app, view = workplace
    first, second = _validation_item(), _validation_item(run_id=8)
    cases, reads, badge = [(first, second)], [], []
    view.render_cases(cases[0])
    view._var_initials.set("AB")
    app._services.results.validate_report_run = lambda *_a, **_k: cases.__setitem__(0, (second,))
    app._services.results.list_open_validation_cases = lambda **binding: reads.append(tuple(cases[0])) or cases[0]
    app._services.results.get_validation_case = lambda *_a, **_k: second
    app._validation_badge = SimpleNamespace(set_status=lambda text, **kwargs: badge.append(text))
    app._save_pending_validation()
    app._navigation_generation += 2  # Results -> explicit exact B intent.
    app._begin_direct_validation((second.report_id, second.run_id, second.store_path, second.selection_token))
    view.set_focus_mode(False)  # Explicit disclosure while the exact load waits remains respected.
    assert len(app._task_runner.submissions) == 1 and reads == []
    assert view.selected_item() is None and app._validation_direct_request is not None
    app._task_runner.invoke_success(index=0)
    assert len(app._task_runner.submissions) == 2 and app._task_runner.submissions[1][0] == "validation-direct"
    app._task_runner.invoke_success(index=1)
    assert reads == [(second,), (second,)] and badge == ["1", "1"]
    assert view.selected_item() == second and tuple(view._tree.get_children()) == ("8",)
    assert app._validation_direct_target[1] == second.run_id and app._validation_direct_request is None
    assert not view._focus_mode


def test_direct_context_epoch_change_reissues_once_without_applying_old_queue_or_badge():
    app = _make_app_stub(current_view="validation")
    case = _validation_item()
    calls, rendered, badge = [], [], []
    app._services.results.get_validation_case = lambda *_a, **_k: calls.append(True) or case
    app._services.results.list_open_validation_cases = lambda **binding: (case,)
    app._views["validation"].render_cases = lambda items, **binding: rendered.append((items, binding))
    app._validation_badge = SimpleNamespace(set_status=lambda text, **kwargs: badge.append(text))
    target = (case.report_id, case.run_id, case.store_path, case.selection_token)
    app._begin_direct_validation(target)
    old = app._task_runner.submissions[0][1]()
    app._validation_write_epoch = 2  # A completed write invalidates a previously captured queue.
    app._task_runner.invoke_success(index=0, result=old)
    assert rendered == [] and badge == [] and app._validation_direct_target == target
    assert len(app._task_runner.submissions) == 2 and len(calls) == 1
    app._task_runner.invoke_success(index=1)
    assert rendered == [((case,), {"direct_case": case})] and badge == ["1"]
    assert app._validation_direct_request is None and len(calls) == 2


@pytest.mark.parametrize("destination", ["validation", "results"])
@pytest.mark.parametrize("old_refresh_first", [False, True])
def test_workplace_write_keeps_genuine_newer_refresh_or_navigation_intent(workplace, destination, old_refresh_first):
    app, view = workplace
    first, second = _validation_item(), _validation_item(run_id=8)
    cases = [(first, second)]
    view.render_cases(cases[0])
    view._var_initials.set("AB")
    app._services.results.list_open_validation_cases = lambda **binding: cases[0]
    app.refresh_current_view()
    old_payload = app._task_runner.submissions[0][1]()
    app._services.results.validate_report_run = lambda *_a, **_k: cases.__setitem__(0, (second,))
    app._save_pending_validation()
    app._current_view = destination
    app._navigation_generation += int(destination == "results")
    app._services.results.list_recent_reports = lambda **binding: (_report_summary("fresh", "fresh.pdf"),)
    app.refresh_current_view()
    assert len(app._task_runner.submissions) == 2
    if old_refresh_first:
        app._task_runner.invoke_success(index=0, result=old_payload)
        app._task_runner.invoke_success(index=1)
    else:
        app._task_runner.invoke_success(index=1)
        app._task_runner.invoke_success(index=0, result=old_payload)
    assert len(app._task_runner.submissions) == 3 and app._task_runner.submissions[2][0] == app.TASK_REFRESH
    app._task_runner.invoke_success(index=2)
    if destination == "validation":
        assert view.selected_item() == second and tuple(view._tree.get_children()) == ("8",)
    else:
        assert app._rendered_reports[0].report_id == "fresh" and app._current_view == "results"


def test_workplace_mutation_does_not_block_separate_results_read(workplace):
    app, view = workplace
    view.render_cases((_validation_item(),))
    view._var_initials.set("AB")
    app._services.results.validate_report_run = lambda *_a, **_k: None
    app._save_pending_validation()
    app._current_view = "results"
    app._navigation_generation += 1
    _results, state = _bound_results_stub(app)
    app._services.results.get_report_detail = lambda report, **binding: replace(_report_detail(report, "a.pdf"), store_path=binding["store_path"])
    app._open_selected_report()
    app._task_runner.invoke_success(index=1)
    app._task_runner.invoke_success(index=0)
    assert state["detail"].report_id == "a" and state["shown"] == 1


def test_workplace_bulk_reanalysis_preserves_real_bindings_and_separate_focused_choice(workplace):
    app, view = workplace
    first, second = _validation_item(), _validation_item(run_id=8)
    view.render_cases((first, second))
    view._tree.selection_set(("7", "8"))
    view._tree.focus("8")
    view._on_select(None)
    view._var_initials.set(" RR ")
    pending_first = replace(_pending_validation_item(run_id=7), store_path=first.store_path)
    pending_second = replace(_pending_validation_item(run_id=8), store_path=second.store_path)
    calls, reads = [], []
    app._services.results.validate_report_run = lambda *_a, **_k: pytest.fail("reanalysis/choice must not validate")
    app._services.results.reanalyze_selected_cases = lambda cases, initials, **binding: calls.append((cases, initials, binding)) or SimpleNamespace(items=())
    app._services.results.list_open_validation_cases = lambda **binding: reads.append(binding) or (pending_first, pending_second)
    app._reanalyze_validation_cases()
    app._task_runner.invoke_success()
    assert calls[0][:2] == ((first, second), "RR") and calls[0][2]["request_id"]
    assert [(case.run_id, case.selection_token, case.store_path) for case in calls[0][0]] == [
        (7, "original:7", "db.sqlite3"), (8, "original:8", "db.sqlite3")]
    assert reads == [{"store_path": "db.sqlite3"}]
    assert view.selected_item() == pending_second and view.selected_items() == (pending_first, pending_second)
    assert str(view._btn_save.cget("state")) == "disabled"
    chosen = replace(pending_second, comparison=None, revision_id=20, selection_token="selection:30")
    choices = []
    view._var_comment.set("full-revision choice")
    app._services.results.choose_reanalysis_result = lambda *args, **binding: choices.append((args, binding))
    app._services.results.list_open_validation_cases = lambda **binding: (pending_first, chosen)
    app._choose_validation_result("accept_new")
    app._task_runner.invoke_success()
    assert len(choices) == 1 and choices[0][0] == (pending_second, "accept_new", "RR")
    assert choices[0][1]["note"] == "full-revision choice" and choices[0][1]["request_id"]
    assert view.selected_item() == chosen and view.selected_item().revision_id == 20
    assert view.validation_initials() == " RR " and view.validation_comment() == ""
    assert str(view._btn_save.cget("state")) == "normal"


def test_workplace_completed_write_from_before_store_ABA_cannot_repaint_same_ids(workplace):
    app, view = workplace
    first = _validation_item()
    view.render_cases((first,))
    view._var_initials.set("AB")
    app._services.results.validate_report_run = lambda *_a, **_k: None
    app._save_pending_validation()
    old_payload = app._task_runner.submissions[0][1]()
    settings_a = SimpleNamespace(**vars(app._settings))
    app._accept_settings_snapshot(SimpleNamespace(**{**vars(settings_a), "sqlite_path": "other.sqlite3"}))
    app._accept_settings_snapshot(settings_a)
    fresh = replace(first, fields=(ReportFieldValue("RESULT", "99"),))
    view.render_cases((fresh,))
    view._var_comment.set("Fresh A draft")
    badge = []
    app._validation_badge = SimpleNamespace(set_status=lambda text, **kwargs: badge.append(text))
    app._task_runner.invoke_success(result=old_payload)
    assert app._store_generation == 2 and badge == []
    assert view.selected_item() == fresh and view.validation_comment() == "Fresh A draft"


@pytest.mark.parametrize("action", ["save", "reanalyze", "choose", "pdf"])
@pytest.mark.parametrize("change_before_submit", [False, True])
def test_workplace_store_switch_rejects_old_action_descriptor(workplace, action, change_before_submit):
    app, view = workplace
    case = replace(_pending_validation_item(), store_path="db.sqlite3") if action == "choose" else _validation_item()
    view.render_cases((case,))
    view._var_initials.set("AB")
    calls = []
    app._services.results.validate_report_run = lambda *_a, **_k: calls.append("save")
    app._services.results.reanalyze_selected_cases = lambda *_a, **_k: calls.append("reanalyze")
    app._services.results.choose_reanalysis_result = lambda *_a, **_k: calls.append("choose")
    app._services.results.open_report_pdf = lambda *_a, **_k: calls.append("pdf")
    if change_before_submit:
        app._settings.sqlite_path = "other.sqlite3"
    {"save": app._save_pending_validation, "reanalyze": app._reanalyze_validation_cases,
     "choose": lambda: app._choose_validation_result("accept_new"), "pdf": app._open_validation_pdf}[action]()
    if change_before_submit:
        assert app._task_runner.submissions == [] and app.__dict__.get("_info_shown")
    else:
        app._settings.sqlite_path = "other.sqlite3"
        work = app._task_runner.submissions[0][1]
        if action == "pdf":
            assert work() == ""
        else:
            with pytest.raises(ValidationConflictError, match="result_store_changed"):
                work()
        app._task_runner.invoke_error(exc=ValidationConflictError("result_store_changed"))
        assert not app.__dict__.get("_error_shown")
    assert calls == []


def test_validation_view_renders_context_and_disables_ambiguous_case() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    configure_desktop_theme(root)
    view = ValidationView(root, on_refresh=lambda: None, on_save=lambda: None, on_open_pdf=lambda: None)
    try:
        view.set_default_operator_initials("AB")
        view.render_cases((_validation_item(ambiguous=True),))
        assert view.selected_item() is not None
        assert view.validation_initials() == "AB"
        assert "Historie unklar" in view._tree.item("7", "values")
        assert str(view._btn_save.cget("state")) == "disabled"
        assert str(view._btn_open_pdf.cget("state")) == "normal"
        assert view._fields.item(view._fields.get_children()[0], "values") == ("RESULT", "42", "")
    finally:
        root.destroy()


def test_assay_tables_show_full_or_missing_names_and_preserve_row_identity(tmp_path):
    from interfaces.tk.views.diagnostics_view import DiagnosticsView
    from interfaces.tk.views.rules_view import RulesView
    root, results = _open_results_view()
    noop = lambda: None
    validation = ValidationView(root, on_refresh=noop, on_save=noop, on_open_pdf=noop)
    diagnostics = DiagnosticsView(root, on_refresh=noop, on_show_diagnosis=noop, on_retry_job=noop,
        on_create_draft=noop, on_show_duplicate=noop, on_discard_duplicate=noop)
    rules = RulesView(root, on_open_rule_editor=noop, on_refresh=noop, on_validate=noop)
    try:
        name = "Anti-PR3-hn-hr IgG – vollständiger Assayname"
        report = replace(_report_summary("report", "report.pdf"), assay_keys=("SECRET-KEY",), assay_names=(name,))
        results.render_report_list((report,))
        assert results._tree.item("report", "values")[2] == name
        validation.render_cases((replace(_validation_item(run_id=1), assay_name=name), _validation_item(run_id=2)))
        assert validation._tree.item("1", "values")[1] == name
        assert validation._tree.item("2", "values")[1] == "Assayname fehlt"
        item = AssayCandidateItem("candidate", "SECRET-KEY", "Dateihinweis", "input.pdf", "1", "line", "test_line", "high", assay_name=name)
        diagnostics.render_candidates((item,))
        diagnostics._candidate_tree.selection_set("candidate")
        assert diagnostics.selected_candidate().assay_key == "SECRET-KEY"
        assert diagnostics._candidate_tree.item("candidate", "values")[:2] == (name, "Dateihinweis")
        assert diagnostics._candidate_tree.heading("name", "text") == "Namenshinweis"
        diagnostics.render_duplicates((DuplicateCandidateItem(9, "pending", "SECRET-KEY", "dedupe", 1, "now", assay_name=name),))
        assert diagnostics._dup_tree.item("9", "values")[0] == name
        rules.render_inventory((RulesetInventoryItem("active", "Aktiv", "SECRET-KEY", name, "rule.json", "rule.json", 1, True, None),))
        rules.bind_editor(SimpleNamespace(project_root=tmp_path), tmp_path)
        assert rules._tree.item(rules._tree.get_children()[0], "values")[2] == name
        statistics = StatisticsView(root, on_refresh=noop)
        assert statistics._qc_include_explanations.get() is False
        assert not hasattr(results, "_qc_panel")
        for tree, column in ((results._tree, "assays"), (validation._tree, "assay"), (rules._tree, "name")):
            assert tree.column(column, "width") >= 200 and tree.cget("xscrollcommand")
    finally:
        root.destroy()


def test_validation_view_save_uses_task_runner_and_refreshes_badge() -> None:
    app = _make_app_stub(current_view="validation")
    item = _validation_item()
    rendered: list[tuple[object, ...]] = []
    cleared: list[bool] = []
    badge: list[tuple[str, str]] = []
    app._validation_badge = SimpleNamespace(set_status=lambda text, **kwargs: badge.append((text, kwargs["kind"])))
    app._show_info_dialog = lambda *_a, **_k: None
    app._views["validation"] = SimpleNamespace(
        selected_item=lambda: item,
        validation_initials=lambda: " AB ",
        validation_comment=lambda: " note ",
        clear_comment=lambda: cleared.append(True),
        render_cases=lambda items, **_intent: rendered.append(tuple(items)),
    )
    calls: list[tuple[object, ...]] = []
    app._services.results.validate_report_run = lambda *args, **binding: calls.append(args)
    app._services.results.list_open_validation_cases = lambda **binding: []

    test_app.AnalyzerDesktopApp._save_pending_validation(app)
    assert len(app._task_runner.submissions) == 1
    app._task_runner.invoke_success()
    assert calls == [("report-1", 7, "AB", "note")]
    assert rendered == [()]
    assert cleared == [True]
    assert badge == [("0", "good")]


def test_validation_view_opens_selected_report_pdf_via_task_runner() -> None:
    app = _make_app_stub(current_view="validation")
    item = _validation_item()
    app._views["validation"] = SimpleNamespace(selected_item=lambda: item)
    opened: list[str] = []
    app._services.results.open_report_pdf = lambda report_id, **binding: opened.append(report_id) or "/reports/report.pdf"

    test_app.AnalyzerDesktopApp._open_validation_pdf(app)
    assert app._task_runner.submissions[0][0] == "open-pdf-report-1"
    app._task_runner.invoke_success()
    assert opened == ["report-1"]


@pytest.mark.parametrize("width,height,scale", [(1420, 930, 1.0), (960, 620, 1.25)])
def test_results_mockup_native_list_and_detail_keep_real_data_and_exact_target(width, height, scale, tmp_path):
    from tkinter import ttk
    import tkinter.font as tkfont
    try:
        root = test_app.AnalyzerDesktopApp(project_root=tmp_path, services=_fake_services())
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    previous_scaling = None
    try:
        # Keep the actual shell geometry, without a late synthetic bootstrap
        # refresh replacing the deliberately rendered report fixture.
        root._task_runner.shutdown_runner()
        view = root._views["results"]
        previous_scaling = float(root.tk.call("tk", "scaling"))
        root.tk.call("tk", "scaling", (4 / 3) * scale)
        root.geometry(f"{width}x{height}")
        root.show_view("results", refresh=False)
        reports = tuple(replace(_report_summary(f"r-{index}", f"ANA_2026-11-26_{index}.pdf"),
            assay_names=("ANA Screen IgG",), device_ids=("Analyzer 1",), lot_ids=("ANA-2406",), report_status="Offen") for index in range(3))
        view.render_report_list(reports, store_path="displayed.sqlite")
        root.deiconify()
        for _ in range(5):
            root.update()
        assert view._list_card._rounded
        assert tuple(view._tree.cget("displaycolumns")) == ("file", "assays", "device", "lot", "time", "status")
        assert view._tree.item("r-0", "values")[5] == "ANA-2406"
        assert view._search_entry.winfo_rooty() == view._search_button.winfo_rooty()
        assert view._search_entry.winfo_height() == view._search_button.winfo_height()
        assert view._search_entry.winfo_width() >= (220 if width == 1420 else 350)
        whole_rows = [view._tree.bbox(row) for row in view._tree.get_children()]
        whole_rows = [box for box in whole_rows if box and box[1] + box[3] <= view._tree.winfo_height()]
        assert len(whole_rows) >= (3 if width == 1420 else 2)
        assert view._list_actions.winfo_rooty() + view._list_actions.winfo_height() <= view._list_panel.winfo_rooty() + view._list_panel.winfo_height()
        if width == 1420:
            assert view._tree.xview() == (0.0, 1.0) and view._tree.yview() == (0.0, 1.0)
        else:
            heading_font = tkfont.Font(root, font=ttk.Style(root).lookup("Results.Treeview.Heading", "font"))
            for column in view._tree.cget("displaycolumns"):
                assert view._tree.column(column, "width") >= heading_font.measure(view._tree.heading(column, "text")) + 24
            assert view._tree.xview() == (0.0, 1.0)
        detail = _validated_report_detail()
        group = detail.assay_groups[0]
        occurrence = replace(group.occurrences[0], assay_name="ANA Screen IgG", device_id="Analyzer 1", charge="ANA-2406", lot_id="ANA-2406",
            created_at="2026-11-25T08:14:00Z", selection_token="selection:30", store_path="displayed.sqlite",
            fields=tuple(ReportFieldValue(key, value) for key, value in (("PLATTE", "P-039"), ("DATUM", "25.11.2026"), ("ZEIT", "16:03"), ("PC_IST", "98,4"))))
        detail = replace(detail, file_name="ANA_2026-11-25.pdf", store_path="displayed.sqlite",
            assay_groups=(replace(group, assay_display_label="ANA Screen IgG", occurrences=(occurrence,)),))
        view.render_report_detail(detail)
        view.show_detail()
        for _ in range(5):
            root.update()
        assert view._detail_card._rounded and view._lbl_detail_title.cget("text") == "ANA Screen IgG"
        assert view.selected_validation_target() == (detail.report_id, occurrence.run_id, "displayed.sqlite", "selection:30")
        assert view.current_detail_descriptor() == (detail.report_id, "displayed.sqlite")
        assert view._field_tree.item(view._field_tree.get_children()[3], "values") == ("PC_IST", "98,4")
        if width == 1420:
            assert view._values_panel.winfo_manager() == "grid" and view._history_panel.winfo_manager() == "grid"
            assert view._values_panel.winfo_rootx() < view._history_panel.winfo_rootx()
            for tree in (view._occ_tree, view._field_tree, view._validation_tree):
                assert abs(sum(tree.column(column, "width") for column in tree.cget("columns")) - (tree.winfo_width() - 4)) <= 4
                assert all(str(tree.heading(column, "anchor")) == "w" for column in tree.cget("columns"))
            assert view._occ_tree.winfo_height() <= view._occ_tree.winfo_reqheight() + 2
            assert int(view._occ_tree.cget("height")) == 1
        else:
            assert str(view._values_panel) in view._read_tabs.tabs() and str(view._history_panel) in view._read_tabs.tabs()
            assert not view._occ_frame.winfo_manager() and not view._occ_label.winfo_manager()
            assert view._occ_tree.selection() and view.validation_run_id() == occurrence.run_id
        first = view._field_tree.bbox(view._field_tree.get_children()[0])
        assert first and first[1] + first[3] <= view._field_tree.winfo_height()
        assert view._field_tree.winfo_rooty() + first[1] + first[3] <= root.winfo_rooty() + height
        for button in view._detail_action_buttons:
            assert button.winfo_x() + button.winfo_width() <= view._detail_actions.winfo_width()
            assert button.winfo_rooty() + button.winfo_height() < root.winfo_rooty() + height
        if width == 960:
            view._read_tabs.select(view._history_panel)
            root.update()
            history_first = view._validation_tree.bbox(view._validation_tree.get_children()[0])
            assert history_first and history_first[1] + history_first[3] <= view._validation_tree.winfo_height()
            assert view._validation_tree.winfo_rooty() + history_first[1] + history_first[3] <= root.winfo_rooty() + height
            view._read_tabs.select(view._values_panel)
            many = (occurrence, replace(occurrence, run_id=6, selection_token="selection:6"), replace(occurrence, run_id=7, selection_token="selection:7"))
            view.render_report_detail(replace(detail, file_name="ANA_2026-11-25_Laborbericht_mit_mehreren_Messungen_und_vollstaendiger_Herkunftsangabe.pdf",
                assay_groups=(replace(detail.assay_groups[0], occurrences=many),)))
            for _ in range(5):
                root.update()
            assert view._occ_frame.winfo_manager() and int(view._occ_tree.cget("height")) == 2
            assert view._occ_tree.yview()[1] < 1.0
            assert view.selected_validation_target() == (detail.report_id, occurrence.run_id, "displayed.sqlite", "selection:30")
            first = view._field_tree.bbox(view._field_tree.get_children()[0])
            assert first and first[1] + first[3] <= view._field_tree.winfo_height()
            assert view._field_tree.winfo_rooty() + first[1] + first[3] <= root.winfo_rooty() + height
            assert view._detail_context._canvas.yview()[1] < 1.0
            view._detail_context._canvas.yview_moveto(1)
            root.update()
            assert view._lbl_validation_status.winfo_rooty() + view._lbl_validation_status.winfo_height() <= view._detail_context.winfo_rooty() + view._detail_context.winfo_height()
    finally:
        try:
            if previous_scaling is not None:
                root.tk.call("tk", "scaling", previous_scaling)
        finally:
            root.destroy()


def test_results_visual_filters_keep_existing_charge_date_search_and_reset():
    root, view = _open_results_view()
    try:
        first = replace(_report_summary("first", "ANA.pdf"), assay_names=("ANA Screen IgG",), lot_ids=("LOT-A",), latest_created_at="2026-11-25T08:14:00")
        second = replace(_report_summary("second", "MPO.pdf"), assay_names=("Anti-MPO IgG",), lot_ids=("LOT-B",), latest_created_at="2026-11-26T08:21:00")
        view.render_report_list((first, second), store_path="displayed.sqlite")
        view._var_search.set("MPO")
        view._var_lot.set("LOT-B")
        view._var_date_from.set("2026-11-26")
        view._var_date_to.set("2026-11-26")
        view._apply_filters()
        assert view._tree.get_children() == ("second",)
        view._tree.selection_set("second")
        assert view.selected_report_descriptor() == ("second", "displayed.sqlite")
        view._reset_filters()
        assert set(view._tree.get_children()) == {"first", "second"}
        assert view.selected_report_descriptor() == ("second", "displayed.sqlite")
        assert all(variable.get() == "" for variable in (view._var_search, view._var_lot, view._var_date_from, view._var_date_to))
    finally:
        root.destroy()


def test_results_view_keeps_live_selection_separate_from_rendered_detail() -> None:
    root, view = _open_results_view()
    try:
        view.render_report_list(
            (
                _report_summary(_MULTI_REPORT_ID, "multi.pdf"),
                _report_summary(_WATCH_REPORT_ID, "watch.pdf"),
            )
        )
        assert view.selected_report_id() == ""
        assert view.current_detail_report_id() == ""

        view.render_report_detail(_report_detail(_MULTI_REPORT_ID, "multi.pdf"))
        view.show_list()
        assert view.selected_report_id() == ""
        assert view.current_detail_report_id() == _MULTI_REPORT_ID

        view._tree.selection_set(_WATCH_REPORT_ID)
        assert view.selected_report_id() == _WATCH_REPORT_ID
        assert view.current_detail_report_id() == _MULTI_REPORT_ID

        view._tree.selection_remove(_WATCH_REPORT_ID)
        assert view.selected_report_id() == ""
        assert view.current_detail_report_id() == _MULTI_REPORT_ID
    finally:
        root.destroy()


def test_open_selected_report_and_pdf_do_not_confuse_prior_detail_with_watch_selection() -> None:
    root, view = _open_results_view()
    try:
        app = _make_app_stub()
        app._views["results"] = view
        detail_calls: list[str] = []
        pdf_calls: list[str] = []

        def get_report_detail(report_id: str, **binding) -> ReportDetail:
            detail_calls.append(report_id)
            return replace(_report_detail(report_id, f"{report_id}.pdf"), store_path=binding["store_path"])

        def open_report_pdf(report_id: str, **binding) -> str:
            pdf_calls.append(report_id)
            return f"/pdf/{report_id}.pdf"

        app._services.results.get_report_detail = get_report_detail
        app._services.results.open_report_pdf = open_report_pdf
        view.render_report_list(
            (
                _report_summary(_MULTI_REPORT_ID, "multi.pdf"),
                _report_summary(_WATCH_REPORT_ID, "watch.pdf"),
            ), store_path="db.sqlite3",
        )
        view.render_report_detail(_report_detail(_MULTI_REPORT_ID, "multi.pdf"))
        view.show_list()
        view._tree.selection_set(_WATCH_REPORT_ID)
        assert view.selected_report_id() == _WATCH_REPORT_ID
        assert view.current_detail_report_id() == _MULTI_REPORT_ID

        app._open_report_pdf()
        _key, pdf_work, _ok, _err = app._task_runner.submissions[0]
        assert pdf_work() == f"/pdf/{_MULTI_REPORT_ID}.pdf"
        assert pdf_calls == [_MULTI_REPORT_ID]

        view.render_report_list(
            (
                _report_summary(_MULTI_REPORT_ID, "multi.pdf"),
                _report_summary(_WATCH_REPORT_ID, "watch.pdf"),
            ), store_path="db.sqlite3",
        )
        assert view.selected_report_id() == _WATCH_REPORT_ID
        assert view.current_detail_report_id() == _MULTI_REPORT_ID

        app._open_selected_report()
        detail_key, detail_work, _detail_ok, _detail_err = app._task_runner.submissions[1]
        assert detail_key == f"report-detail-{_WATCH_REPORT_ID}"
        assert detail_work().report_id == _WATCH_REPORT_ID
        assert detail_calls == [_WATCH_REPORT_ID]
        app._task_runner.invoke_success(index=1)
        assert view.current_detail_report_id() == _WATCH_REPORT_ID
        assert view.selected_report_id() == _WATCH_REPORT_ID

        app._open_report_pdf()
        _pdf_key, watch_pdf_work, _watch_ok, _watch_err = app._task_runner.submissions[2]
        assert watch_pdf_work() == f"/pdf/{_WATCH_REPORT_ID}.pdf"
        assert pdf_calls == [_MULTI_REPORT_ID, _WATCH_REPORT_ID]
    finally:
        root.destroy()


def test_open_selected_report_without_live_selection_does_not_reuse_rendered_detail() -> None:
    root, view = _open_results_view()
    try:
        app = _make_app_stub()
        app._views["results"] = view
        dialogs: list[tuple[str, str]] = []
        app._show_info_dialog = lambda _parent, title, message, **_kwargs: dialogs.append((title, message))
        app._services.results.get_report_detail = lambda report_id: (_ for _ in ()).throw(
            AssertionError(f"unexpected detail load: {report_id}")
        )
        view.render_report_list((_report_summary(_MULTI_REPORT_ID, "multi.pdf"),))
        view.render_report_detail(_report_detail(_MULTI_REPORT_ID, "multi.pdf"))
        view.show_list()
        assert view.selected_report_id() == ""
        assert view.current_detail_report_id() == _MULTI_REPORT_ID

        app._open_selected_report()
        assert dialogs == [("Ergebnisse", "Bitte einen Bericht auswählen.")]
        assert app._task_runner.submissions == []
        assert view.current_detail_report_id() == _MULTI_REPORT_ID
    finally:
        root.destroy()


def _validated_report_detail() -> ReportDetail:
    previous = RunValidationItem(
        validation_id=1,
        run_id=5,
        operator_initials="AB",
        validated_at_utc="2026-09-23T13:00:00Z",
        comment="erste",
        supersedes_validation_id=None,
        created_at_utc="2026-09-23T13:00:00Z",
    )
    current = RunValidationItem(
        validation_id=2,
        run_id=5,
        operator_initials="CD",
        validated_at_utc="2026-09-23T13:04:00Z",
        comment="korrektur",
        supersedes_validation_id=1,
        created_at_utc="2026-09-23T13:04:00Z",
    )
    return ReportDetail(
        report_id="rep-val",
        job_id="rep-val",
        pdf_path="validated.pdf",
        file_name="validated.pdf",
        current_pdf_path="validated.pdf",
        ingestion_id="",
        path_status="resolved",
        display_status="Fertig",
        report_status="Validiert",
        assay_groups=(
            ReportAssayGroup(
                assay_key="Assay-A",
                ruleset_file="A.json",
                occurrences=(
                    ReportRunOccurrence(
                        run_id=5,
                        lot_id="LOT",
                        charge="LOT",
                        device_id="dev1",
                        dedupe_key="K",
                        created_at="2026-01-01T10:00:00Z",
                        fields=(ReportFieldValue(field_key="DATUM", value="2026-01-01"),),
                        current_validation=current,
                        validation_history=(previous, current),
                    ),
                ),
            ),
        ),
    )


def test_results_validation_history_is_read_only_and_navigates_exact_case() -> None:
    root, view = _open_results_view()
    try:
        summary = ReportSummaryItem(
            report_id="rep-val",
            job_id="rep-val",
            pdf_path="validated.pdf",
            file_name="validated.pdf",
            current_pdf_path="validated.pdf",
            run_count=1,
            assay_count=1,
            latest_created_at="2026-01-01T10:00:00Z",
            report_status="Teilweise validiert",
            display_status="Fertig",
        )
        view.render_report_list((summary,))
        listed = view._tree.item(summary.report_id, "values")
        assert listed[1] == "Teilweise validiert"

        view.render_report_detail(_validated_report_detail())
        assert "Validiert von CD" in view._lbl_validation_status.cget("text")
        assert str(view._btn_open_validation.cget("state")) == "normal"
        assert not hasattr(view, "_btn_save_validation") and not hasattr(view, "_btn_correct_validation")
        assert not hasattr(view, "_var_initials") and not hasattr(view, "_var_comment")
        assert len(view._validation_tree.get_children()) == 2
        assert view.validation_run_id() == 5
        assert view.selected_validation_target()[:2] == ("rep-val", 5)
        assert "Verarbeitung: Fertig" in view._lbl_detail_meta.cget("text")
        assert "Status: Validiert" in view._lbl_detail_meta.cget("text")
    finally:
        root.destroy()


def test_save_validation_refreshes_worklist_without_confirmation(workplace) -> None:
    app, view = workplace
    case = replace(_validation_item(run_id=5), report_id="rep-1")
    view.render_cases((case,))
    view._var_initials.set(" AB ")
    view._var_comment.set(" note ")
    calls: list[tuple[object, ...]] = []
    app._services.results.validate_report_run = lambda *args, **kwargs: calls.append(("save", args, kwargs))
    app._services.results.correct_report_run = lambda *args, **kwargs: calls.append(("correct", args, kwargs))
    app._services.results.list_open_validation_cases = lambda **binding: ()
    app._services.results.get_report_detail = lambda *_a, **_k: pytest.fail("Prüfplatz does not write through Results")
    app._show_confirm_dialog = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("confirm"))

    app._save_pending_validation()
    assert len(app._task_runner.submissions) == 1
    app._task_runner.invoke_success()
    assert calls[0][0] == "save"
    assert calls[0][1] == ("rep-1", 5, "AB", "note")
    assert view.validation_comment() == "" and view.validation_initials() == " AB "
    assert view.selected_item() is None and view._tree.get_children() == ()
    assert len(calls) == 1


def test_correct_validation_requires_explicit_confirmation_and_retains_same_revision(workplace) -> None:
    app, view = workplace
    dialogs: list[tuple[str, str]] = []
    calls = []
    original = RunValidationItem(1, 5, "AB", "2026-01-01T00:00:00Z", "first", None, None, revision_id=20)
    correction = replace(original, validation_id=2, operator_initials="CD", comment="correction", supersedes_validation_id=1)
    case = replace(_validation_item(run_id=5), report_id="rep-1", revision_id=20, selection_token="selection:30",
                   current_validation=original, validation_history=(original,))
    corrected = replace(case, current_validation=correction, validation_history=(original, correction))
    view.render_cases((_validation_item(run_id=9),), direct_case=case)
    view._var_initials.set("CD")
    view._var_comment.set("correction")
    app._services.results.correct_report_run = lambda *args, **binding: calls.append((args, binding)) or correction
    app._services.results.get_validation_case = lambda *_a, **_k: corrected
    app._services.results.list_open_validation_cases = lambda **binding: (_validation_item(run_id=9),)
    app._services.results.validate_report_run = lambda *_a, **_k: pytest.fail("correction must not perform first validation")
    app._show_confirm_dialog = lambda _parent, title, message: dialogs.append((title, message)) or False

    app._save_pending_validation()
    assert dialogs
    assert dialogs[0][0] == "Validierung korrigieren"
    assert "bleibt erhalten" in dialogs[0][1] and "ausdrücklich korrigieren" in dialogs[0][1]
    assert app._task_runner.submissions == []
    assert calls == []

    app._show_confirm_dialog = lambda *_args, **_kwargs: True
    app._save_pending_validation()
    app._task_runner.invoke_success()
    assert len(calls) == 1 and calls[0][0] == ("rep-1", 5, "CD", "correction")
    assert calls[0][1]["expected_selection_token"] == "selection:30"
    assert view.selected_item() == corrected and view.selected_item().revision_id == 20
    assert len(view._history.get_children()) == 2 and view._btn_save.cget("text") == "Validierung korrigieren"
    assert view.validation_initials() == "CD" and view.validation_comment() == ""
    assert app._validation_direct_target[:2] == ("rep-1", 5)


def test_render_report_list_drops_selection_when_selected_report_disappears() -> None:
    root, view = _open_results_view()
    try:
        view.render_report_list(
            (
                _report_summary(_MULTI_REPORT_ID, "multi.pdf"),
                _report_summary(_WATCH_REPORT_ID, "watch.pdf"),
            )
        )
        view.render_report_detail(_report_detail(_MULTI_REPORT_ID, "multi.pdf"))
        view._tree.selection_set(_WATCH_REPORT_ID)
        assert view.selected_report_id() == _WATCH_REPORT_ID

        view.render_report_list((_report_summary(_MULTI_REPORT_ID, "multi.pdf"),))
        assert view.selected_report_id() == ""
        assert view.current_detail_report_id() == _MULTI_REPORT_ID

        view._tree.selection_set(_MULTI_REPORT_ID)
        view.render_report_list(())
        assert view.selected_report_id() == ""
        assert view.current_detail_report_id() == _MULTI_REPORT_ID
    finally:
        root.destroy()


def test_open_output_folder_submits_runner_work() -> None:
    app = _make_app_stub()
    app._open_output_folder()
    key, work, _ok, _err = app._task_runner.submissions[0]
    assert key == "open-output-folder"
    assert work() == "/output"


def test_open_output_folder_error_dialog_uses_friendly_primary() -> None:
    app = _make_app_stub()
    dialogs: list[tuple[str, str, str]] = []
    app._show_error_dialog = lambda _parent, title, message, **kwargs: dialogs.append(
        (title, message, kwargs.get("details", ""))
    )
    app._services.settings.open_output_folder = lambda: (_ for _ in ()).throw(Exception("path_empty"))

    test_app.AnalyzerDesktopApp._open_output_folder(app)
    _key, work, _on_success, on_error = app._task_runner.submissions[0]
    with pytest.raises(Exception, match="path_empty"):
        work()
    on_error(Exception("path_empty"))
    assert dialogs
    assert dialogs[0][0] == "Ausgabeordner"
    assert dialogs[0][1] == format_user_error_message("path_empty")
    assert dialogs[0][2] == "path_empty"


def test_start_bootstrap_calls_factory_and_finishes() -> None:
    app = test_app.AnalyzerDesktopApp.__new__(test_app.AnalyzerDesktopApp)
    app.project_root = "/project"
    app._services = None
    app._bootstrapped = False
    app._task_runner = _RecordingRunner()
    app._views = {
        "dashboard": SimpleNamespace(
            set_actions_enabled=lambda *_a, **_k: None,
            set_activity_message=lambda *_a, **_k: None,
        )
    }
    factory_calls: list[object] = []
    services = _fake_services()

    def factory(root: object) -> object:
        factory_calls.append(root)
        return services

    app._create_desktop_services = factory
    app._schedule_watch = lambda: None
    app.refresh_current_view = lambda: setattr(app, "_refresh_called", True)

    test_app.AnalyzerDesktopApp._start_bootstrap(app)
    assert len(app._task_runner.submissions) == 1
    app._task_runner.invoke_success()
    assert factory_calls == ["/project"]
    assert app._services is services
    assert app._bootstrapped is True
    assert app.__dict__.get("_refresh_called") is True


def test_watch_schedule_generation_ignores_stale_callbacks() -> None:
    app = _make_app_stub()
    disabled = SimpleNamespace(watch_enabled=False)
    enabled = SimpleNamespace(watch_enabled=True)
    app._services.settings.load = lambda: disabled if app._watch_schedule_generation == 1 else enabled
    app._services.settings.get_watch_timing = lambda: SimpleNamespace(scan_interval_s=2.0)

    test_app.AnalyzerDesktopApp._schedule_watch(app)
    test_app.AnalyzerDesktopApp._schedule_watch(app)
    assert len(app._task_runner.submissions) == 2
    assert app._task_runner.submissions[0][0] == "watch-schedule-1"
    assert app._task_runner.submissions[1][0] == "watch-schedule-2"

    app._task_runner.invoke_success(
        index=0,
        result=(disabled, None, False),
    )
    assert app._scheduled_after == []

    app._task_runner.invoke_success(
        index=1,
        result=(enabled, SimpleNamespace(scan_interval_s=2.0), True),
    )
    assert len(app._scheduled_after) == 1
    assert app._scheduled_after[0][0] == 2000


def test_pick_and_process_pdfs_wires_enqueue_drain_and_statuses(monkeypatch) -> None:
    app = _make_app_stub()
    selected = ("/a.pdf", "/b.pdf")
    enqueued: list[tuple[str, ...]] = []
    rendered: list[object] = []
    app._views["dashboard"].render_batch_statuses = lambda statuses: rendered.append(tuple(statuses))

    def fake_askopenfilenames(**_kwargs):  # noqa: ANN003
        return selected

    monkeypatch.setattr(test_app.filedialog, "askopenfilenames", fake_askopenfilenames)

    process_calls = {"count": 0}

    def process_next() -> ProcessingOutcome:
        process_calls["count"] += 1
        if process_calls["count"] == 1:
            return ProcessingOutcome(
                processed=True,
                pdf_path="/a.pdf",
                file_name="a.pdf",
                queue_status="DONE",
                submit_status="ok",
            )
        if process_calls["count"] == 2:
            return ProcessingOutcome(
                processed=True,
                pdf_path="/b.pdf",
                file_name="b.pdf",
                queue_status="FAILED",
                submit_status="FAILED",
                message="parse_failed",
            )
        return ProcessingOutcome(processed=False)

    def enqueue_manual_pdfs(paths: tuple[str, ...] | list[str]) -> SimpleNamespace:
        enqueued.append(tuple(paths))
        return SimpleNamespace(
            outcomes=(
                ProcessingEnqueueOutcome(pdf_path="/a.pdf", file_name="a.pdf", outcome="queued"),
                ProcessingEnqueueOutcome(pdf_path="/b.pdf", file_name="b.pdf", outcome="queued"),
            )
        )

    app._services.extraction.enqueue_manual_pdfs = enqueue_manual_pdfs
    app._services.extraction.process_next = process_next

    test_app.AnalyzerDesktopApp._pick_and_process_pdfs(app)
    assert len(app._task_runner.submissions) == 1
    assert app._task_runner.submissions[0][0] == app.TASK_PROCESSING
    app._task_runner.invoke_success()
    assert enqueued == [("/a.pdf", "/b.pdf")]
    assert rendered
    labels = {row.status_label for row in rendered[0]}
    assert labels == {"Erfolgreich", "Fehler"}


def test_run_scheduled_watch_on_settings_view_does_not_refresh_form() -> None:
    app = _make_app_stub(current_view="settings")
    refresh_calls = {"count": 0}
    settings_rendered: list[object] = []
    app.refresh_current_view = lambda: refresh_calls.__setitem__("count", refresh_calls["count"] + 1)
    app._views["settings"].render_settings = lambda *_a, **_k: settings_rendered.append(True)
    rendered_summary: list[object] = []
    rendered_statuses: list[object] = []
    app._views["dashboard"].render_watch_session_summary = lambda summary, **kwargs: rendered_summary.append((summary, kwargs))
    app._views["dashboard"].render_batch_statuses = lambda statuses: rendered_statuses.append(tuple(statuses))
    app._services.settings.load = lambda: SimpleNamespace(watch_enabled=True)
    summary = WatchCycleSummary(
        enabled=True,
        scanned_count=1,
        outcomes=(
            ProcessingEnqueueOutcome(pdf_path="/a.pdf", file_name="a.pdf", outcome="registered"),
        ),
    )
    app._services.extraction.run_watch_cycle = lambda: summary
    process_calls = {"count": 0}

    def process_next() -> ProcessingOutcome:
        process_calls["count"] += 1
        if process_calls["count"] == 1:
            return ProcessingOutcome(
                processed=True,
                pdf_path="/a.pdf",
                file_name="a.pdf",
                queue_status="DONE",
                submit_status="ok",
            )
        return ProcessingOutcome(processed=False)

    app._services.extraction.process_next = process_next
    schedule_calls = {"count": 0}
    app._schedule_watch = lambda: schedule_calls.__setitem__("count", schedule_calls["count"] + 1)

    test_app.AnalyzerDesktopApp._run_scheduled_watch(app)
    app._task_runner.invoke_success()
    assert refresh_calls["count"] == 0
    assert settings_rendered == []
    assert rendered_summary
    assert rendered_statuses
    assert schedule_calls["count"] == 1


def test_save_settings_false_watch_enabled_reaches_controller_and_reschedules() -> None:
    app = _make_app_stub()
    collected = SimpleNamespace(watch_enabled=False, marker="collected")
    saved_settings = SimpleNamespace(watch_enabled=False, marker="saved")
    saved_received: list[object] = []
    statuses: list[str] = []
    app._views["settings"].collect_settings = lambda **_k: collected
    app._views["settings"].set_status_message = lambda message: statuses.append(message)
    app._services.settings.save = lambda settings: saved_received.append(settings) or saved_settings
    app._reschedule_calls = 0
    app._reschedule_watch = lambda: setattr(app, "_reschedule_calls", app._reschedule_calls + 1)

    test_app.AnalyzerDesktopApp._save_settings(app)
    _key, work, on_success, _on_error = app._task_runner.submissions[0]
    result = work()
    on_success(result)
    assert saved_received == [collected]
    assert collected.watch_enabled is False
    assert result.watch_enabled is False
    assert app._settings is saved_settings
    assert statuses == ["Einstellungen gespeichert."]
    assert app._reschedule_calls == 1


def test_save_settings_coalesces_latest_wins_while_first_save_active() -> None:
    app = _make_app_stub()
    # Watch scheduling is covered separately; this case isolates save coalescing.
    app._reschedule_watch = lambda: None
    statuses: list[str] = []
    saved_flags: list[bool] = []
    collect_queue = [SimpleNamespace(watch_enabled=True), SimpleNamespace(watch_enabled=False)]

    class _SettingsStub:
        edit_generation = 0

        def collect_settings(self, **_kwargs: object) -> SimpleNamespace:
            return collect_queue.pop(0)

        def set_status_message(self, message: str) -> None:
            statuses.append(message)

        def mark_saved_generation(self, _generation: int) -> None:
            return None

    app._views["settings"] = _SettingsStub()
    app._services.settings.save = lambda settings: saved_flags.append(settings.watch_enabled) or settings

    test_app.AnalyzerDesktopApp._save_settings(app)
    assert len(app._task_runner.submissions) == 1
    test_app.AnalyzerDesktopApp._save_settings(app)
    assert statuses == ["Speichern läuft bereits – bitte warten."]
    assert len(app._task_runner.submissions) == 1

    app._task_runner.invoke_success(index=0)
    assert saved_flags == [True]
    assert not any("gespeichert" in message.casefold() for message in statuses)
    assert len(app._task_runner.submissions) == 2

    app._task_runner.invoke_success(index=1)
    assert saved_flags == [True, False]
    assert statuses[-1] == "Einstellungen gespeichert."
    assert app._settings.watch_enabled is False


def test_settings_view_collects_trimmed_operator_initials() -> None:
    view = _make_settings_view_logic_stub()
    view._var_operator_initials.set("  RR  ")
    view._var_sqlite.set("db.sqlite3")
    collected = SettingsView.collect_settings(view, device_id_map={})
    assert collected.operator_initials == "RR"
    assert collected.output_mode == "sqlite"


@pytest.mark.parametrize("failure", [None, "configuration", "names", "store"])
def test_settings_configuration_read_is_deferred_isolated_and_never_loads_rule_fields(failure):
    app = _make_app_stub(current_view="settings")
    app._views["settings"].render_settings = lambda *_args, **_kwargs: None
    reads = []
    store = str(Path(app._settings.sqlite_path).resolve())
    state = SimpleNamespace(store_path=store, inventory={"snapshot": {"devices": []}}, profiles=())
    def configuration():
        reads.append("configuration")
        if failure == "configuration":
            raise RuntimeError("synthetic inaccessible QC configuration")
        return SimpleNamespace(**{**vars(state), "store_path": "other.sqlite3"}) if failure == "store" else state
    def inventory(kind):
        reads.append(("rules", kind))
        if failure == "names":
            raise RuntimeError("synthetic missing active rule")
        return [SimpleNamespace(assay_key="A", assay_name="ANA Screen IgG"), SimpleNamespace(assay_key="missing-name", assay_name="")]
    app._services.settings.get_qc_configuration = configuration
    app._services.rules.list_inventory = inventory
    app._services.rules.list_fields = lambda *_args: pytest.fail("The settings list must not read extraction fields")
    app.refresh_current_view()
    assert reads == []
    app._task_runner.invoke_success()
    rendered, options = app._rendered_qc_configuration
    assert not app.__dict__.get("_error_shown")
    if failure in ("configuration", "store"):
        assert rendered is None and options["error"]
    else:
        assert rendered is state
        assert options["assay_names"] == ({"A": "ANA Screen IgG"} if failure is None else {})
        assert bool(options["error"]) is (failure == "names")


@pytest.mark.parametrize("aba", [False, True])
def test_settings_configuration_rejects_old_store_generation_and_refreshes_latest(aba):
    app = _make_app_stub(current_view="settings")
    app._views["settings"].render_settings = lambda *_args, **_kwargs: None
    first = app._settings
    second = SimpleNamespace(**{**vars(first), "sqlite_path": "new-store.sqlite3"})
    live = [first]
    app._services.settings.load = lambda: live[0]
    app._services.settings.get_qc_configuration = lambda: SimpleNamespace(store_path=str(Path(live[0].sqlite_path).resolve()), inventory={"snapshot": {"devices": []}}, profiles=())
    app.refresh_current_view()
    old = app._task_runner.submissions[-1][1]()
    app._accept_settings_snapshot(second)
    live[0] = second
    if aba:
        app._accept_settings_snapshot(first)
        live[0] = first
    app._task_runner.invoke_success(index=0, result=old)
    assert "_rendered_qc_configuration" not in app.__dict__
    assert len(app._task_runner.submissions) == 2
    app._task_runner.invoke_success(index=1)
    assert app._rendered_qc_configuration[0].store_path == str(Path(live[0].sqlite_path).resolve())


def test_settings_view_disables_excel_but_keeps_sqlite() -> None:
    view = _make_settings_view_logic_stub()
    view._var_sqlite.set("db.sqlite3")
    assert SettingsView.collect_settings(view, device_id_map={}).output_mode == "sqlite"


def test_settings_view_dirty_form_preserves_unsaved_false_over_persisted_true() -> None:
    view = _make_settings_view_logic_stub()
    persisted_true = SimpleNamespace(
        watch_enabled=True,
        watch_input_path="/in",
        watch_backup_path="/bak",
        watch_recursive=False,
        output_mode="both",
        sqlite_path="/db.sqlite3",
        device_id=None,
    )
    SettingsView._apply_settings_values(view, persisted_true)
    view._var_watch_enabled.set(False)
    assert SettingsView.is_dirty(view)

    persisted_render = SimpleNamespace(
        watch_enabled=True,
        watch_input_path="/other",
        watch_backup_path="/other-bak",
        watch_recursive=True,
        output_mode="sqlite",
        sqlite_path="/other.sqlite3",
        device_id=None,
    )
    SettingsView.render_settings(
        view,
        persisted_render,
        devices=(),
        timing=WatchTimingSettings(scan_interval_s=3.0, stable_window_s=2.0),
    )
    assert view._var_watch_enabled.get() is False
    assert view._var_watch_input.get() == "/in"


def _sample_settings_namespace(**overrides: object) -> SimpleNamespace:
    values = {
        "watch_enabled": True,
        "watch_input_path": "/in",
        "watch_backup_path": "/bak",
        "watch_recursive": True,
        "output_mode": "sqlite",
        "sqlite_path": "/db.sqlite3",
        "device_id": "DEFAULT_DEVICE",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_settings_view_clean_first_render_applies_all_fields_with_default_device() -> None:
    view = _make_settings_view_logic_stub()
    devices = (
        DeviceInventoryItem(device_id="DEFAULT_DEVICE", display_name="Default Lab", active=True),
        DeviceInventoryItem(device_id="OTHER_DEVICE", display_name="Other Lab", active=True),
    )
    settings = _sample_settings_namespace()
    SettingsView.render_settings(
        view,
        settings,
        devices=devices,
        timing=WatchTimingSettings(scan_interval_s=5.0, stable_window_s=2.0),
    )
    assert view._var_watch_enabled.get() is True
    assert view._var_watch_input.get() == "/in"
    assert view._var_watch_backup.get() == "/bak"
    assert view._var_watch_recursive.get() is True
    assert not hasattr(view, "_var_excel_after_validation")
    assert view._var_sqlite.get() == "/db.sqlite3"
    assert view._var_device.get() == "Default Lab (DEFAULT_DEVICE)"
    assert not SettingsView.is_dirty(view)


def test_settings_view_normalizes_legacy_excel_to_sqlite_on_save() -> None:
    view = _make_settings_view_logic_stub()
    SettingsView._apply_settings_values(view, _sample_settings_namespace(output_mode="excel"))
    assert not hasattr(view, "_var_excel_after_validation")
    assert SettingsView.collect_settings(view, device_id_map={}).output_mode == "sqlite"


def test_settings_view_clean_first_render_none_device_id_falls_back_to_first_active() -> None:
    view = _make_settings_view_logic_stub()
    devices = (
        DeviceInventoryItem(device_id="FIRST_DEVICE", display_name="First Lab", active=True),
        DeviceInventoryItem(device_id="SECOND_DEVICE", display_name="Second Lab", active=True),
    )
    settings = _sample_settings_namespace(device_id=None)
    SettingsView.render_settings(
        view,
        settings,
        devices=devices,
        timing=WatchTimingSettings(scan_interval_s=4.0, stable_window_s=1.0),
    )
    assert view._var_device.get() == "First Lab (FIRST_DEVICE)"
    assert not SettingsView.is_dirty(view)


def test_settings_view_dirty_render_preserves_device_selection_and_edited_fields() -> None:
    view = _make_settings_view_logic_stub()
    initial_devices = (
        DeviceInventoryItem(device_id="DEV_A", display_name="Alpha", active=True),
    )
    SettingsView.render_settings(
        view,
        _sample_settings_namespace(device_id="DEV_A", watch_enabled=True),
        devices=initial_devices,
        timing=WatchTimingSettings(scan_interval_s=3.0, stable_window_s=2.0),
    )
    view._var_device.set("Beta (DEV_B)")
    view._var_watch_enabled.set(False)
    view._var_watch_input.set("/edited")
    assert SettingsView.is_dirty(view)

    configured_labels: list[tuple[str, ...]] = []

    def track_configure(**kwargs: object) -> None:
        values = kwargs.get("values")
        if values is not None:
            configured_labels.append(tuple(values))

    view._device_combo.configure = track_configure
    refreshed_devices = (
        DeviceInventoryItem(device_id="DEV_A", display_name="Alpha", active=True),
        DeviceInventoryItem(device_id="DEV_B", display_name="Beta", active=True),
    )
    SettingsView.render_settings(
        view,
        _sample_settings_namespace(
            device_id="DEV_A",
            watch_enabled=True,
            watch_input_path="/persisted",
            watch_backup_path="/persisted-bak",
            watch_recursive=False,
            output_mode="both",
            sqlite_path="/persisted.sqlite3",
        ),
        devices=refreshed_devices,
        timing=WatchTimingSettings(scan_interval_s=9.0, stable_window_s=7.0),
    )
    assert configured_labels == [("Alpha (DEV_A)", "Beta (DEV_B)")]
    assert view._var_device.get() == "Beta (DEV_B)"
    assert view._var_watch_enabled.get() is False
    assert view._var_watch_input.get() == "/edited"
    assert SettingsView.is_dirty(view)


def test_settings_view_mark_saved_generation_keeps_later_edits_dirty() -> None:
    view = _make_settings_view_logic_stub()
    persisted = SimpleNamespace(
        watch_enabled=True,
        watch_input_path="/in",
        watch_backup_path="/bak",
        watch_recursive=False,
        output_mode="both",
        sqlite_path="/db.sqlite3",
        device_id=None,
    )
    SettingsView._apply_settings_values(view, persisted)
    generation_at_save = view.edit_generation
    view._var_watch_enabled.set(False)
    SettingsView.mark_saved_generation(view, generation_at_save)
    assert SettingsView.is_dirty(view)


def test_save_disabled_watch_cancels_timer_without_scheduling_new_after() -> None:
    app = _make_app_stub()
    statuses: list[str] = []
    disabled = SimpleNamespace(watch_enabled=False)
    cancel_calls: list[str] = []
    after_calls: list[tuple[int, object]] = []

    class _SettingsStub:
        edit_generation = 0

        def collect_settings(self, **_kwargs: object) -> SimpleNamespace:
            return disabled

        def set_status_message(self, message: str) -> None:
            statuses.append(message)

        def mark_saved_generation(self, _generation: int) -> None:
            return None

    app._views["settings"] = _SettingsStub()
    app._services.settings.save = lambda settings: settings
    app._watch_after_id = "existing-timer"

    def after_cancel(handle: str) -> None:
        cancel_calls.append(handle)
        app._watch_after_id = None

    app.after_cancel = after_cancel
    app.after = lambda delay_ms, callback: after_calls.append((delay_ms, callback)) or "new-timer"
    app._services.settings.load = lambda: disabled

    test_app.AnalyzerDesktopApp._save_settings(app)
    app._task_runner.invoke_success(result=disabled)
    assert statuses[-1] == "Einstellungen gespeichert."
    assert cancel_calls == ["existing-timer"]
    assert app._watch_after_id is None
    assert after_calls == []


def test_save_settings_success_reschedules_watch() -> None:
    app = _make_app_stub()
    collected = SimpleNamespace(watch_enabled=True, marker="collected")
    saved_settings = SimpleNamespace(watch_enabled=True, marker="saved")
    statuses: list[str] = []
    saved_received: list[object] = []
    app._views["settings"].collect_settings = lambda **_k: collected
    app._views["settings"].set_status_message = lambda message: statuses.append(message)
    app._services.settings.save = lambda settings: saved_received.append(settings) or saved_settings
    app._reschedule_calls = 0
    app._reschedule_watch = lambda: setattr(app, "_reschedule_calls", app._reschedule_calls + 1)

    test_app.AnalyzerDesktopApp._save_settings(app)
    _key, work, on_success, _on_error = app._task_runner.submissions[0]
    result = work()
    on_success(result)
    assert saved_received == [collected]
    assert result is saved_settings
    assert statuses == ["Einstellungen gespeichert."]
    assert app._settings is saved_settings
    assert app._reschedule_calls == 1


def test_save_settings_validation_error_shows_friendly_status() -> None:
    app = _make_app_stub()
    statuses: list[str] = []
    collected = object()
    save_calls: list[object] = []
    app._views["settings"].collect_settings = lambda **_k: collected
    app._views["settings"].set_status_message = lambda message: statuses.append(message)

    def save(_settings: object) -> object:
        save_calls.append(_settings)
        raise SettingsValidationError("watch_input_path_required")

    app._services.settings.save = save

    test_app.AnalyzerDesktopApp._save_settings(app)
    _key, work, _on_success, on_error = app._task_runner.submissions[0]
    with pytest.raises(SettingsValidationError, match="watch_input_path_required"):
        work()
    on_error(SettingsValidationError("watch_input_path_required"))
    assert save_calls == [collected]
    assert statuses == [format_user_error_message("watch_input_path_required")]


def test_save_settings_save_error_shows_friendly_dialog_with_details() -> None:
    app = _make_app_stub()
    dialogs: list[tuple[str, str, str]] = []
    app._show_error_dialog = lambda _parent, title, message, **kwargs: dialogs.append(
        (title, message, kwargs.get("details", ""))
    )
    app._views["settings"].collect_settings = lambda **_k: object()
    app._services.settings.save = lambda _settings: (_ for _ in ()).throw(
        SettingsSaveError("desktop_settings_save_failed: disk full")
    )

    test_app.AnalyzerDesktopApp._save_settings(app)
    _key, work, _on_success, on_error = app._task_runner.submissions[0]
    with pytest.raises(SettingsSaveError, match="desktop_settings_save_failed"):
        work()
    on_error(SettingsSaveError("desktop_settings_save_failed: disk full"))
    assert dialogs
    assert dialogs[0][1] == "Die Einstellungen konnten nicht gespeichert werden."
    assert "disk full" not in dialogs[0][1]
    assert dialogs[0][2] == "desktop_settings_save_failed: disk full"


def test_create_draft_from_candidate_confirmation_false_does_nothing() -> None:
    app = _make_app_stub()
    app._show_confirm_dialog = lambda *_a, **_k: False
    app._views["diagnostics"].selected_candidate = lambda: AssayCandidateItem(
        candidate_id="cand-1",
        assay_key="Assay-A",
        assay_name_hint="Assay A",
        known_status="unknown",
        confidence="high",
        reason="test",
        line_no="1",
        line_text="Assay-A",
        test_file="sample.pdf",
    )
    test_app.AnalyzerDesktopApp._create_draft_from_candidate(app)
    assert app._task_runner.submissions == []


@pytest.mark.parametrize("retry_kind", ["retired", "export_only"])
def test_retry_selected_historical_export_never_calls_export_or_full_retry(retry_kind: str) -> None:
    app = _make_app_stub(current_view="diagnostics")
    calls: list[str] = []
    app._views["diagnostics"].selected_job_id = lambda: "job-1"
    app._services.extraction.get_job_diagnosis = lambda _job_id: SimpleNamespace(retry_kind=retry_kind)
    app._services.extraction.retry_excel_export = lambda _job_id: pytest.fail("retired export retry")
    app._services.extraction.retry_failed = lambda _job_id: pytest.fail("historical full retry")
    app.refresh_current_view = lambda: calls.append("refresh")

    test_app.AnalyzerDesktopApp._retry_selected_job(app)
    app._task_runner.invoke_success()
    assert calls == ["refresh"]


@pytest.mark.parametrize("retry_kind,queue_status,expected", [
    ("retired", "FAILED", "disabled"), ("retired", "DONE", "disabled"),
    ("export_only", "FAILED", "disabled"), ("full_processing", "FAILED", "normal"),
])
def test_diagnostics_retry_button_is_disabled_for_historical_exports(retry_kind, queue_status, expected) -> None:
    from interfaces.tk.views.diagnostics_view import DiagnosticsView
    states = []
    view = SimpleNamespace(
        selected_job_id=lambda: "job-1",
        _diagnoses_by_job={"job-1": SimpleNamespace(retry_kind=retry_kind, queue_status=queue_status)},
        _btn_retry=SimpleNamespace(configure=lambda **kwargs: states.append(kwargs["state"])),
    )
    DiagnosticsView._on_diagnosis_selected(view)
    assert states == [expected]


@pytest.mark.parametrize("late", ["selection", "selection-aba", "navigation", "store", "refresh", "error"])
def test_diagnosis_candidates_and_details_never_apply_after_context_change(late):
    app = _make_app_stub(current_view="diagnostics")
    selected, rendered, shown = ["job-a"], [], []
    selection_generation = [0]
    app._views["diagnostics"].selected_job_id = lambda: selected[0]
    app._views["diagnostics"].diagnosis_selection_context = lambda: (selected[0], selection_generation[0])
    app._views["diagnostics"].render_candidates = rendered.append
    app._services.extraction.get_job_diagnosis = lambda _job: SimpleNamespace(technical_detail="Technical A", friendly_message="Hint A", context_text="Context A", error_label="Error A", file_name="a.pdf")
    app._services.rules.discover_assay_candidates_for_job = lambda _job: ("candidate-a",)
    app._show_details_dialog = lambda *_args: shown.append(_args)
    app._show_diagnosis_details()
    payload = app._task_runner.submissions[-1][1]()
    if late in ("selection", "error"):
        selected[0] = "job-b"
    elif late == "selection-aba":
        selection_generation[0] += 2
    elif late == "navigation":
        app._navigation_generation += 1
        app._current_view = "results"
    elif late == "store":
        app._store_generation += 2  # A -> B -> A remains stale, even at the same path.
    else:
        app._refresh_generation += 1
    if late == "error":
        app._task_runner.invoke_error(exc=RuntimeError("old A"))
    else:
        app._task_runner.invoke_success(result=payload)
    assert not rendered and not shown and not app.__dict__.get("_error_shown")


def test_diagnosis_details_keep_exact_selected_job_and_existing_dialog():
    app = _make_app_stub(current_view="diagnostics")
    rendered, shown, reads = [], [], []
    app._views["diagnostics"].selected_job_id = lambda: "job-a"
    app._views["diagnostics"].diagnosis_selection_context = lambda: ("job-a", 0)
    app._views["diagnostics"].render_candidates = rendered.append
    app._services.extraction.get_job_diagnosis = lambda job: reads.append(job) or SimpleNamespace(technical_detail="Technical A", friendly_message="Hint A", context_text="Context A", error_label="Error A", file_name="a.pdf")
    app._services.rules.discover_assay_candidates_for_job = lambda job: reads.append(job) or ("candidate-a",)
    app._show_details_dialog = lambda *_args: shown.append(_args)
    app._show_diagnosis_details()
    assert reads == []
    app._task_runner.invoke_success()
    assert reads == ["job-a", "job-a"] and rendered == [("candidate-a",)]
    assert shown[0][1:] == ("Error A", "Hint A", "Technical A\n\nContext A")


@pytest.mark.parametrize("stale", [False, "selection", "selection-aba", "store"])
def test_duplicate_comparison_route_is_exact_read_only_and_discards_late_selection(monkeypatch, stale):
    from interfaces.tk.widgets import dialogs
    app = _make_app_stub(current_view="diagnostics")
    selected, opened, reads = [7], [], []
    selection_generation = [0]
    store = str(Path(app._settings.sqlite_path).resolve())
    app._views["diagnostics"].selected_duplicate_id = lambda: selected[0]
    app._views["diagnostics"].selected_duplicate_descriptor = lambda: (selected[0], store, selection_generation[0])
    app._views["diagnostics"].duplicate_selection_context = lambda: (selected[0], store, selection_generation[0])
    detail = DuplicateCandidateDetail(DuplicateCandidateItem(7, "pending", "private-key", "dedupe", 1, "2026-11-25T08:14:00Z", assay_name="ANA Screen IgG"), None,
        (DuplicateFieldComparisonItem("PC_IST", "100", "103", True),))
    app._services.results.get_duplicate_candidate_detail = lambda candidate, *, store_path: reads.append((candidate, store_path)) or detail
    app._services.results.discard_duplicate_candidate = lambda _candidate: pytest.fail("Comparison must not write")
    monkeypatch.setattr(dialogs, "show_duplicate_comparison_dialog", lambda parent, result, *, technical_details: opened.append((result, technical_details)))
    app._show_duplicate_details()
    assert reads == []
    payload = app._task_runner.submissions[-1][1]()
    if stale == "selection":
        selected[0] = 8
    elif stale == "selection-aba":
        selection_generation[0] += 2
    elif stale == "store":
        app._store_generation += 2
    app._task_runner.invoke_success(result=payload)
    assert reads == [(7, store)]
    assert not opened if stale else opened == [(detail, format_duplicate_detail_lines(detail))]


@pytest.mark.parametrize("moment", ["confirm", "selection-aba", "worker", "worker-store-aba", "ui"])
def test_diagnostics_duplicate_discard_never_rebinds_same_id_to_new_store(moment):
    app = _make_app_stub(current_view="diagnostics")
    first = app._settings
    second = SimpleNamespace(**{**vars(first), "sqlite_path": "other-store.sqlite3"})
    descriptor = [(7, str(Path(first.sqlite_path).resolve()), 0)]
    diagnostics = app._views["diagnostics"]
    diagnostics.selected_duplicate_descriptor = lambda: descriptor[0]
    diagnostics.duplicate_selection_context = lambda: descriptor[0]
    calls, refreshed = [], []
    app._services.results.discard_duplicate_candidate = lambda candidate, *, store_path: calls.append((candidate, store_path))
    app.refresh_current_view = lambda: refreshed.append(True)
    def confirm(*_args):
        if moment == "confirm":
            app._accept_settings_snapshot(second)
        elif moment == "selection-aba":
            descriptor[0] = (7, descriptor[0][1], 2)
        return True
    app._show_confirm_dialog = confirm
    app._discard_selected_duplicate()
    if moment in ("confirm", "selection-aba"):
        assert not app._task_runner.submissions and not calls
        assert app._info_shown
        return
    if moment == "ui":
        result = app._task_runner.submissions[-1][1]()
        app._accept_settings_snapshot(second)
        app._task_runner.invoke_success(result=result)
        assert calls == [(7, str(Path(first.sqlite_path).resolve()))]
    else:
        app._accept_settings_snapshot(second)
        if moment == "worker-store-aba":
            app._accept_settings_snapshot(first)
        app._task_runner.invoke_success()
        assert not calls
    assert not refreshed


def test_diagnostics_listing_is_bound_to_captured_payload_store_before_worker_and_ui():
    app = _make_app_stub(current_view="diagnostics")
    first, reads, shown = app._settings, [], []
    second = SimpleNamespace(**{**vars(first), "sqlite_path": "new-store.sqlite3"})
    current = [first]
    app._services.settings.load = lambda: current[0]
    app._services.results.list_duplicate_candidates = lambda *, status, store_path: reads.append((status, store_path)) or []
    app._views["diagnostics"].render_diagnoses = lambda _items: None
    app._views["diagnostics"].render_duplicates = lambda _items, *, store_path: shown.append(store_path)
    app._views["diagnostics"].render_candidates = lambda _items: None
    app.refresh_current_view()
    assert not reads
    old = app._task_runner.submissions[0][1]()
    assert reads == [("pending", str(Path(first.sqlite_path).resolve()))]
    current[0] = second
    app._accept_settings_snapshot(second)
    app._task_runner.invoke_success(index=0, result=old)
    assert not shown and len(app._task_runner.submissions) == 2
    app._task_runner.invoke_success(index=1)
    assert shown == [str(Path(second.sqlite_path).resolve())]


@pytest.mark.parametrize("width,height,scale", [(1420, 930, 1.0), (960, 620, 1.25)])
def test_diagnostics_native_layout_comparison_values_and_selection_guards(tmp_path, monkeypatch, width, height, scale):
    from tkinter import ttk
    import tkinter.font as tkfont
    from interfaces.tk import desktop_theme
    from interfaces.tk.widgets.dialogs import show_duplicate_comparison_dialog
    from src.application.api import JobDiagnosisItem
    original_theme, scaling_state = desktop_theme.configure_desktop_theme, []
    def scaled_theme(root):
        scaling_state.append((root, float(root.tk.call("tk", "scaling"))))
        root.tk.call("tk", "scaling", (4 / 3) * scale)
        return original_theme(root)
    monkeypatch.setattr(desktop_theme, "configure_desktop_theme", scaled_theme)
    try:
        app = test_app.AnalyzerDesktopApp(project_root=tmp_path, services=_fake_services())
    except BaseException as exc:
        if scaling_state:
            failed, previous = scaling_state[0]
            try:
                failed.tk.call("tk", "scaling", previous)
            finally:
                failed.destroy()
        if isinstance(exc, tk.TclError):
            pytest.skip(f"Tk not available: {exc}")
        raise
    try:
        app._task_runner.shutdown_runner()
        app._accept_settings_snapshot(app.services.settings.load())
        app.geometry(f"{width}x{height}")
        app.show_view("diagnostics", refresh=False)
        view = app._views["diagnostics"]
        view.render_diagnoses(())
        view.render_duplicates(())
        for _ in range(4):
            app.update()
        assert view._diag_card._rounded and view._dup_card._rounded
        assert not view._diag_frame.winfo_manager() and not view._dup_frame.winfo_manager()
        assert not view._candidate_panel.winfo_manager() and view._page._canvas.yview() == (0.0, 1.0)
        first = JobDiagnosisItem("job-a", "ANA_2026-11-25.pdf", "ANA_2026-11-25.pdf", "FAILED", "Felder nicht extrahiert", "configured_fields_empty:PC_IST", "Normalisierter Text",
            "Felder nicht extrahiert", "configured_fields_empty:PC_IST")
        historical = replace(first, job_id="job-b", file_name="Historischer_Ausgabeplan.pdf", queue_status="DONE", retry_kind="retired", error_label="Excel-Ausgabe", friendly_message="Historischer Ausgabeplan ist schreibgeschützt.")
        duplicate = DuplicateCandidateItem(7, "pending", "private-assay-key", "dedupe", 1, "2026-11-25T08:14:00Z", assay_name="ANA Screen IgG")
        store = str(Path(app._settings.sqlite_path).resolve())
        view.render_diagnoses((first,))
        view.render_duplicates((duplicate,), store_path=store)
        for _ in range(4):
            app.update()
        assert view._page._canvas.yview() == (0.0, 1.0)
        assert view._btn_compare.winfo_rooty() + view._btn_compare.winfo_height() <= app.winfo_rooty() + height
        view.render_diagnoses((first, historical))
        view.render_duplicates((duplicate,), store_path=store)
        view._diag_tree.selection_set("job-a")
        view._dup_tree.selection_set("7")
        for _ in range(4):
            app.update()
        assert view.selected_job_id() == "job-a" and view.selected_duplicate_id() == 7
        assert str(view._btn_retry.cget("state")) == "normal"
        assert view._diag_tree.item("job-a", "values")[2] == "Kontext: Normalisierter Text"
        assert view._dup_tree.item("7", "values") == ("ANA Screen IgG", "Offen", "25.11.2026 08:14")
        assert tuple(view._dup_tree.cget("displaycolumns")) == ("assay", "detected", "status")
        heading_font = tkfont.Font(app, font=ttk.Style(app).lookup("Diagnostics.Treeview.Heading", "font"))
        for tree in (view._diag_tree, view._dup_tree):
            assert tree.xview() == tree.yview() == (0.0, 1.0)
            for column in tree.cget("columns"):
                assert tree.column(column, "width") >= heading_font.measure(tree.heading(column, "text")) + 24
        candidate = AssayCandidateItem("candidate-a", "private-assay-key", "Dateihinweis", "ANA_2026-11-25.pdf", "3", "Assayblock", "test_line", "high", assay_name="ANA Screen IgG")
        view.render_candidates((candidate,))
        view._candidate_tree.selection_set("candidate-a")
        app.update()
        assert view.selected_candidate() is candidate and str(view._btn_draft.cget("state")) == "normal"
        view._diag_tree.selection_set("job-b")
        app.update()
        assert view.selected_candidate() is None and not view._candidate_panel.winfo_manager()
        assert str(view._btn_retry.cget("state")) == "disabled"
        old_job_context = view.diagnosis_selection_context()
        view._diag_tree.selection_set("job-a")
        app.update()
        view._diag_tree.selection_set("job-b")
        app.update()
        assert view.diagnosis_selection_context()[0] == old_job_context[0]
        assert view.diagnosis_selection_context()[1] == old_job_context[1] + 2
        descriptor = view.selected_duplicate_descriptor()
        view.render_duplicates((duplicate, replace(duplicate, candidate_id=8)), store_path=store)
        app.update()
        assert view.selected_duplicate_descriptor() == descriptor
        view._dup_tree.selection_set("8")
        app.update()
        view._dup_tree.selection_set("7")
        app.update()
        assert view.selected_duplicate_descriptor() == (7, store, descriptor[2] + 2)
        view._page._canvas.yview_moveto(1)
        app.update()
        for button in (view._btn_compare, view._btn_discard):
            assert button.winfo_rooty() + button.winfo_height() <= app.winfo_rooty() + height
            assert button.winfo_rootx() + button.winfo_width() <= app.winfo_rootx() + width
        assert view._btn_compare.winfo_rooty() == view._btn_discard.winfo_rooty()
        assert view._btn_compare.winfo_height() == view._btn_discard.winfo_height()
        unchanged = tuple(DuplicateFieldComparisonItem(f"SAME_{index}", "1", "1", False) for index in range(9))
        fields = (*unchanged, DuplicateFieldComparisonItem("PC_IST", "100", "103", True),
            DuplicateFieldComparisonItem("ZERO", 0, 0, False), DuplicateFieldComparisonItem("FLAG", False, False, False), DuplicateFieldComparisonItem("EMPTY", "", "", False))
        detail = DuplicateCandidateDetail(replace(duplicate, candidate_meta={"pdf_path": r"C:\Labor\Privater Testordner\ANA_Duplikat.pdf"}), None, fields)
        dialog = show_duplicate_comparison_dialog(app, detail, technical_details=format_duplicate_detail_lines(detail))
        for _ in range(4):
            app.update()
        tree = dialog._comparison_tree
        rows = [tree.item(row, "values") for row in tree.get_children()]
        assert rows[0] == ("PC_IST", "100", "103") and tree.item(tree.get_children()[0], "tags") == ("changed",)
        assert [row[0] for row in rows[1:10]] == [f"SAME_{index}" for index in range(9)]
        assert ("ZERO", "0", "0") in rows and ("FLAG", "False", "False") in rows and ("EMPTY", "", "") in rows
        assert len(rows) == len(fields) == 13 and tree.xview() == (0.0, 1.0)
        first_box = tree.bbox(tree.get_children()[0])
        assert first_box and tree.winfo_rooty() + first_box[1] + first_box[3] < dialog.winfo_rooty() + dialog.winfo_height()
        assert not dialog._technical_frame.winfo_manager()
        assert "Quelle: ANA_Duplikat.pdf" in dialog._comparison_context.cget("text")
        assert "Privater Testordner" not in dialog._comparison_context.cget("text")
        dialog._technical_toggle.invoke()
        app.update()
        assert dialog._technical_frame.winfo_manager()
        dialog._technical_toggle.invoke()
        assert not dialog._technical_frame.winfo_manager()
        dialog.destroy()
        empty_dialog = show_duplicate_comparison_dialog(app, replace(detail, field_comparison=()), technical_details="No values")
        app.update()
        assert str(empty_dialog.tk.call("focus", "-lastfor", empty_dialog)) == str(empty_dialog._comparison_close)
        empty_dialog.focus_force()
        empty_dialog.event_generate("<Escape>")
        app.update()
        assert not empty_dialog.winfo_exists()
        view.render_diagnoses(())
        view.render_duplicates(())
        for _ in range(4):
            app.update()
        assert view._page._canvas.yview() == (0.0, 1.0)
        assert str(view._btn_retry.cget("state")) == str(view._btn_compare.cget("state")) == str(view._btn_discard.cget("state")) == "disabled"
    finally:
        try:
            if scaling_state:
                app.tk.call("tk", "scaling", scaling_state[0][1])
        finally:
            app.destroy()


def test_create_draft_from_candidate_confirmation_true_submits_and_opens_editor() -> None:
    app = _make_app_stub()
    created: list[tuple[str, str]] = []
    app._views["diagnostics"].selected_candidate = lambda: AssayCandidateItem(
        candidate_id="cand-1",
        assay_key="Assay-A",
        assay_name_hint="Assay A",
        known_status="unknown",
        confidence="high",
        reason="test",
        line_no="1",
        line_text="Assay-A",
        test_file="sample.pdf",
    )
    app._services.rules.create_draft_from_template_if_missing = lambda key, name: created.append((key, name)) or {}
    test_app.AnalyzerDesktopApp._create_draft_from_candidate(app)
    assert len(app._task_runner.submissions) == 1
    app._task_runner.invoke_success()
    assert created == [("Assay-A", "Assay A")]
    assert app.__dict__.get("_rule_editor_opened") is True


def test_discard_selected_duplicate_confirmation_false_does_nothing() -> None:
    app = _make_app_stub(current_view="diagnostics")
    descriptor = (7, str(Path(app._settings.sqlite_path).resolve()), 0)
    app._views["diagnostics"].selected_duplicate_descriptor = lambda: descriptor
    app._views["diagnostics"].duplicate_selection_context = lambda: descriptor
    app._show_confirm_dialog = lambda *_a, **_k: False
    app._views["diagnostics"].selected_duplicate_id = lambda: 7
    test_app.AnalyzerDesktopApp._discard_selected_duplicate(app)
    assert app._task_runner.submissions == []


def test_discard_selected_duplicate_confirmation_true_refreshes() -> None:
    app = _make_app_stub(current_view="diagnostics")
    descriptor = (7, str(Path(app._settings.sqlite_path).resolve()), 0)
    app._views["diagnostics"].selected_duplicate_descriptor = lambda: descriptor
    app._views["diagnostics"].duplicate_selection_context = lambda: descriptor
    discarded: list[int] = []
    refresh_calls = {"count": 0}
    app.refresh_current_view = lambda: refresh_calls.__setitem__("count", refresh_calls["count"] + 1)
    app._views["diagnostics"].selected_duplicate_id = lambda: 7
    app._services.results.discard_duplicate_candidate = lambda candidate_id, *, store_path: discarded.append((candidate_id, store_path))
    test_app.AnalyzerDesktopApp._discard_selected_duplicate(app)
    assert len(app._task_runner.submissions) == 1
    app._task_runner.invoke_success()
    assert discarded == [(7, descriptor[1])]
    assert refresh_calls["count"] == 1


def test_run_scheduled_watch_renders_final_statuses_and_summary() -> None:
    app = _make_app_stub()
    rendered_summary: list[object] = []
    rendered_statuses: list[object] = []
    app._views["dashboard"].render_watch_session_summary = lambda summary, **kwargs: rendered_summary.append((summary, kwargs))
    app._views["dashboard"].render_batch_statuses = lambda statuses: rendered_statuses.append(tuple(statuses))
    app._services.settings.load = lambda: SimpleNamespace(watch_enabled=True)
    summary = WatchCycleSummary(
        enabled=True,
        scanned_count=1,
        outcomes=(
            ProcessingEnqueueOutcome(pdf_path="/a.pdf", file_name="a.pdf", outcome="registered"),
        ),
    )
    app._services.extraction.run_watch_cycle = lambda: summary
    process_calls = {"count": 0}

    def process_next() -> ProcessingOutcome:
        process_calls["count"] += 1
        if process_calls["count"] == 1:
            return ProcessingOutcome(
                processed=True,
                pdf_path="/a.pdf",
                file_name="a.pdf",
                queue_status="DONE",
                submit_status="ok",
            )
        return ProcessingOutcome(processed=False)

    app._services.extraction.process_next = process_next

    test_app.AnalyzerDesktopApp._run_scheduled_watch(app)
    assert len(app._task_runner.submissions) == 1
    app._task_runner.invoke_success()
    assert app._last_watch_summary is summary
    assert rendered_summary
    assert rendered_statuses
    assert rendered_statuses[0][0].status_label == "Erfolgreich"


def test_run_scheduled_watch_error_replaces_summary_with_friendly_message() -> None:
    app = _make_app_stub()
    app._last_watch_summary = WatchCycleSummary(enabled=True, scanned_count=9)
    rendered: list[tuple[object, dict[str, object]]] = []
    app._views["dashboard"].render_watch_session_summary = lambda summary, **kwargs: rendered.append((summary, kwargs))
    app._services.settings.load = lambda: SimpleNamespace(watch_enabled=True)
    app._services.extraction.run_watch_cycle = lambda: (_ for _ in ()).throw(
        ApplicationWatchError("watch_input_path_required")
    )
    errors: list[tuple[str, str, str]] = []
    app._show_error_dialog = lambda _parent, title, message, **kwargs: errors.append((title, message, kwargs.get("details", "")))

    test_app.AnalyzerDesktopApp._run_scheduled_watch(app)
    app._task_runner.invoke_error(exc=ApplicationWatchError("watch_input_path_required"))
    assert app._last_watch_summary is None
    assert "Eingabeordner" in app._last_watch_error
    assert rendered[-1][0] is None
    assert "Eingabeordner" in str(rendered[-1][1].get("error", ""))
    assert errors
    assert errors[0][1] == format_user_error_message("watch_input_path_required")


def test_analyzer_desktop_app_declares_product_views(tmp_path) -> None:
    try:
        app = test_app.AnalyzerDesktopApp(project_root=tmp_path, services=_fake_services())
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        assert set(app._views) == set(test_app.AnalyzerDesktopApp.VIEW_KEYS)
        assert app.VIEW_KEYS == ("dashboard", "results", "changes", "statistics", "validation", "rules", "settings", "diagnostics")
        assert app._nav_buttons["statistics"].cget("text") == "Statistik"
        assert app._nav_buttons["dashboard"].cget("text") == "Arbeitsübersicht"
        assert app._nav_buttons["validation"].cget("text") == "Prüfplatz"
        assert tuple(app._nav_buttons) == ("dashboard", "validation", "results", "changes", "statistics", "rules", "settings", "diagnostics")
        assert app._header_section.cget("text") == "Arbeitsübersicht"
        assert app._nav_buttons["changes"].cget("text") == "Änderungen"
        assert isinstance(app._views["statistics"], StatisticsView)
        assert app._views["statistics"]._qc_include_explanations.get() is False
        assert not hasattr(app._views["results"], "render_qc_lots")
        assert not hasattr(app._views["results"], "_qc_canvas")
        assert app.TASK_PROCESSING == "processing_queue"
    finally:
        app.destroy()


def test_mockup_theme_uses_palette_and_readable_primary_and_navigation_states():
    from interfaces.tk.desktop_theme import COLOR_BG, COLOR_CARD, COLOR_PRIMARY, COLOR_TEXT, FONT_FAMILY

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    try:
        style = configure_desktop_theme(root)
        assert (COLOR_BG, COLOR_CARD, COLOR_TEXT, COLOR_PRIMARY) == ("#f3f6fa", "#ffffff", "#16293c", "#175ba4")
        assert FONT_FAMILY == "Segoe UI"
        assert style.lookup("Header.TFrame", "background") == COLOR_CARD
        assert style.lookup("Nav.TButton", "background") == COLOR_CARD
        assert style.lookup("NavActive.TButton", "background") == "#eaf3fd"
        assert style.lookup("NavActive.TButton", "foreground") == "#134a83"
        assert style.lookup("Primary.TButton", "background") == COLOR_PRIMARY
        assert style.lookup("Primary.TButton", "foreground") == COLOR_CARD
        assert style.lookup("Primary.TButton", "background", ("active",)) == "#134a83"
        assert style.lookup("Primary.TButton", "foreground", ("disabled",)) == "#53677a"
    finally:
        root.destroy()


@pytest.mark.parametrize(
    "selected,default,devices,expected",
    (
        ("B", "A", (DeviceInventoryItem("A", "Analyzer 1", True), DeviceInventoryItem("B", "Analyzer 2", True)), "Analyzer 2"),
        (None, "A", (DeviceInventoryItem("A", "Analyzer 1", True),), "Analyzer 1"),
        ("A", "A", (DeviceInventoryItem("A", "Analyzer 1", False),), "Analyzer 1 · inaktiv"),
        ("missing", "A", (), "missing · nicht verfügbar"),
        (None, "", (), "Kein Gerät ausgewählt"),
    ),
)
def test_import_device_context_uses_existing_selected_or_default_inventory(selected, default, devices, expected):
    assert import_device_label(
        SimpleNamespace(device_id=selected), SimpleNamespace(default_device_id=default, devices=devices),
    ) == expected


def test_dashboard_payload_binds_real_device_and_open_case_count_without_ui_thread_reads():
    app = _make_app_stub(current_view="dashboard")
    app._validation_badge = None
    reads, rendered = [], []
    app._services.settings.get_device_inventory = lambda: reads.append("devices") or SimpleNamespace(
        default_device_id="A", devices=(DeviceInventoryItem("A", "Analyzer 1", True),),
    )
    app._services.results.list_open_validation_cases = lambda **binding: [_validation_item(run_id=7), _validation_item(run_id=8)]
    app._views["dashboard"].render_import_device = lambda label: rendered.append(("device", label))
    app._views["dashboard"].render_open_case_count = lambda count: rendered.append(("count", count))
    app._header_device = SimpleNamespace(configure=lambda **values: rendered.append(("header", values["text"])))
    payload = app._load_view_payload("dashboard")
    assert reads == ["devices"] and rendered == []
    app._apply_view_payload("dashboard", payload)
    assert reads == ["devices"]
    assert rendered == [("header", "Importgerät: Analyzer 1"), ("device", "Analyzer 1"), ("count", 2)]


@pytest.mark.parametrize("succeeds", [True, False])
def test_confirmed_import_device_save_updates_header_and_dashboard_without_new_reads(succeeds):
    app = _make_app_stub(current_view="dashboard")
    app._validation_badge = None
    reads, header_labels, dashboard_labels = [], [], []
    app._services.settings.get_device_inventory = lambda: reads.append("devices") or SimpleNamespace(
        default_device_id="A", devices=(DeviceInventoryItem("A", "Analyzer 1", True), DeviceInventoryItem("B", "Analyzer 2", True)),
    )
    app._header_device = SimpleNamespace(configure=lambda **values: header_labels.append(values["text"]))
    app._views["dashboard"].render_import_device = dashboard_labels.append
    app._apply_view_payload("dashboard", app._load_view_payload("dashboard"))
    assert header_labels == ["Importgerät: Analyzer 1"] and dashboard_labels == ["Analyzer 1"]
    proposed = SimpleNamespace(watch_enabled=False, device_id="B")
    app._views["settings"].collect_settings = lambda **_kwargs: proposed
    app._reschedule_watch = lambda: None
    app._save_settings()
    assert header_labels[-1] == "Importgerät: Analyzer 1" and dashboard_labels[-1] == "Analyzer 1"
    if succeeds:
        app._task_runner.invoke_success()
    else:
        app._task_runner.invoke_error(exc=SettingsSaveError("readonly"))
    expected = "Analyzer 2" if succeeds else "Analyzer 1"
    assert header_labels[-1] == f"Importgerät: {expected}"
    assert dashboard_labels[-1] == expected
    assert reads == ["devices"]


def test_dashboard_mockup_keeps_existing_actions_reports_and_compact_watch():
    from tkinter import ttk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    configure_desktop_theme(root)
    calls = []
    view = DashboardView(
        root,
        on_pick_and_process_pdfs=lambda: calls.append("import"),
        on_open_settings=lambda: calls.append("settings"),
        on_refresh=lambda: calls.append("refresh"),
        on_open_report=lambda report: calls.append(("report", report)),
        on_open_selected_report=lambda: calls.append("selected"),
        on_open_results=lambda: calls.append("results"),
        on_open_validation=lambda: calls.append("validation"),
    )
    try:
        assert view._lbl_open_count.cget("text") == "–"
        view.render_import_device("Analyzer 1")
        view.render_open_case_count(4)
        assert view._lbl_device.cget("text") == "Analyzer 1"
        assert "Analyzer 1" in view._lbl_import_context.cget("text")
        assert view._lbl_open_count.cget("text") == "4"
        assert int(view._recent_card.grid_info()["row"]) < int(view._watch_card.grid_info()["row"])
        assert view._scrollable._canvas.cget("background") == "#f3f6fa"
        view._btn_pick.invoke()
        view.set_processing_busy(True)
        view._btn_pick.invoke()
        view.set_processing_busy(False)
        assert calls == ["import"]
        view._btn_open_validation.invoke()
        assert calls[-1] == "validation"

        view.render_recent_rows((DashboardRecentRow("ingestion-1", "Fertig", "ANA.pdf", "Analyzer 1", "26.11.2026 08:14", "Manuell", "report-1"),))
        assert view._tree.set("ingestion-1", "file") == "ANA.pdf"
        assert view._tree.set("ingestion-1", "status") == "Fertig"
        view._tree.selection_set("ingestion-1")
        view._update_open_result_button()
        view._btn_open_result.invoke()
        view._handle_open_report(None)
        assert calls[-2:] == ["selected", ("report", "report-1")]
        view.render_recent_rows(())
        assert view.selected_report_id() is None
        assert str(view._btn_open_result.cget("state")) == "disabled"

        settings = SimpleNamespace(watch_enabled=False, watch_input_path="", watch_backup_path="", watch_recursive=False)
        view.render_watch_settings(settings)
        assert view._lbl_watch_input.cget("text") == "Kein Eingabeordner konfiguriert."
        assert "Kein Verschieben" in view._lbl_watch_backup.cget("text")
        view.render_watch_session_summary(None, error="watch_input_path_required")
        assert "Eingabeordner" in view._lbl_watch_session.cget("text")
        view.render_batch_statuses((BatchFileStatus("ANA.pdf", "ANA.pdf", "In Warteschlange"),))
        assert "ANA.pdf" in view._lbl_batch.cget("text")
        view.render_batch_statuses(())
        assert view._lbl_batch.winfo_manager() == ""

        def buttons(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button):
                    yield child
                yield from buttons(child)

        actions = {button.cget("text"): button for button in buttons(view)}
        for title in ("Gerät wechseln", "Alle Ergebnisse  →", "Aktualisieren", "Konfigurieren"):
            actions[title].invoke()
        assert calls[-4:] == ["settings", "results", "refresh", "settings"]
        view.set_actions_enabled(False)
        assert str(view._btn_pick.cget("state")) == "disabled"
        assert str(view._btn_open_validation.cget("state")) == "disabled"
    finally:
        root.destroy()


def test_statistics_refresh_uses_single_deferred_qc_owner_and_rejects_old_store():
    app = _make_app_stub(current_view="statistics")
    io = []
    case = SimpleNamespace(store_path=app._settings.sqlite_path)
    app._services.results.list_qc_lots = lambda: io.append("qc") or (case,)
    app._services.results.list_recent_reports = lambda **kwargs: pytest.fail("Statistics must not load a report list")
    app.refresh_current_view()
    assert io == [] and app._task_runner.submissions[-1][0] == "qc-lots"
    payload = app._task_runner.submissions[-1][1]()
    assert io == ["qc"]
    app._settings = SimpleNamespace(**{**vars(app._settings), "sqlite_path": "another.sqlite3"})
    app._task_runner.invoke_success(result=payload)
    assert "_rendered_qc_lots" not in app.__dict__
    app._settings = app._services.settings.load()
    app.refresh_current_view()
    app._task_runner.invoke_success(result=payload)
    assert app._rendered_qc_lots == (case,)


def _requested_window_size(widget: tk.Misc) -> tuple[int, int]:
    size = widget.geometry().split("+", 1)[0].split("-", 1)[0]
    width_s, height_s = size.split("x", 1)
    return int(width_s), int(height_s)


def test_desktop_shell_is_usable_at_minimum_size(tmp_path) -> None:
    assert (MIN_WIDTH, MIN_HEIGHT) == (960, 620)
    assert (DEFAULT_WIDTH, DEFAULT_HEIGHT) == (1180, 760)
    assert MIN_WIDTH < 1024 and MIN_HEIGHT < 768
    try:
        app = test_app.AnalyzerDesktopApp(project_root=tmp_path, services=_fake_services())
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        app.update_idletasks()
        assert app.minsize() == (MIN_WIDTH, MIN_HEIGHT)
        width, height = _requested_window_size(app)
        assert abs(width - DEFAULT_WIDTH) <= 80
        assert abs(height - DEFAULT_HEIGHT) <= 80

        app.geometry(f"{MIN_WIDTH}x{MIN_HEIGHT}")
        app.update_idletasks()
        app.update()
        for key in test_app.AnalyzerDesktopApp.VIEW_KEYS:
            button = app._nav_buttons[key]
            assert button.winfo_ismapped()
            assert button.winfo_width() >= 48
            assert button.winfo_height() >= 16
            app.show_view(key, refresh=False)
            app.update()
            view = app._views[key]
            assert view.winfo_manager() == "grid"
            assert view.winfo_ismapped()
            assert view.winfo_width() >= 300
            assert view.winfo_height() >= 120
    finally:
        app.destroy()


def test_window_version_comes_from_worker_payload_without_runtime_io_on_apply():
    app = _make_app_stub(current_view="results")
    app._validation_badge = None
    reads, titles = [], []
    app._services.settings.get_build_info = lambda: reads.append(True) or {"version": "2.0.0", "status": "available"}
    app.title = titles.append
    payload = app._load_view_payload("results")
    assert reads == [True] and titles == []
    app._apply_view_payload("results", payload)
    assert reads == [True] and len(titles) == 1
    assert "2.0.0" in titles[-1]
