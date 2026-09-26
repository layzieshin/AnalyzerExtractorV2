from __future__ import annotations

import inspect
import threading
import tkinter as tk
from types import MethodType, SimpleNamespace

import pytest

from interfaces.tk import test_app
from interfaces.tk.desktop_theme import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MIN_HEIGHT,
    MIN_WIDTH,
    configure_desktop_theme,
)
from interfaces.tk.views.results_view import ResultsView
from interfaces.tk.views.settings_view import SettingsView
from interfaces.tk.views.validation_view import ValidationView
from interfaces.tk.view_models import (
    DASHBOARD_RECENT_LIMIT,
    GENERIC_ACTION_FAILED_MESSAGE,
    build_batch_file_statuses,
    build_dashboard_recent_rows,
    format_duplicate_detail_lines,
    format_user_error_message,
    format_watch_cycle_summary,
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
    ReportAssayGroup,
    ReportDetail,
    ReportFieldValue,
    ReportRunOccurrence,
    ReportSummaryItem,
    RulesetInventoryItem,
    RunValidationItem,
    ValidationQueueItem,
    SettingsSaveError,
    SettingsValidationError,
    WatchCycleSummary,
    WatchTimingSettings,
)


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
        self._var_excel_after_validation = _FakeVar(True)
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
            reload_device_inventory=lambda: SimpleNamespace(devices=()),
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
            list_recent_reports=lambda limit=50: [],
            list_open_validation_cases=lambda limit=500: [],
            get_report_detail=lambda _report_id: None,
            open_report_pdf=lambda _report_id: "/pdf/path.pdf",
            list_duplicate_candidates=lambda status="pending": [],
            get_duplicate_candidate_detail=lambda _candidate_id: None,
            discard_duplicate_candidate=lambda _candidate_id: object(),
        ),
        rules=SimpleNamespace(
            list_inventory=lambda: [],
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
    app._last_watch_summary = None
    app._last_watch_error = ""
    app._WatchCycleSummary = WatchCycleSummary
    app._ApplicationWatchError = ApplicationWatchError
    app._SettingsValidationError = SettingsValidationError
    app._SettingsSaveError = SettingsSaveError
    app._dashboard_report_join_limit = 250
    app._device_label_map = {}
    app._watch_after_id = None
    app._watch_schedule_generation = 0
    app._refresh_generation = 0
    app._settings_save_latest_id = 0
    app._settings_save_latest = None
    app._settings_save_latest_edit_generation = 0
    app._settings_save_inflight_id = None
    app._scheduled_after: list[tuple[int, object]] = []
    app._views = {
        "dashboard": SimpleNamespace(
            render_watch_settings=lambda *_a, **_k: None,
            render_recent_rows=lambda *_a, **_k: None,
            render_watch_session_summary=lambda *_a, **_k: None,
            render_batch_statuses=lambda *_a, **_k: None,
            set_processing_busy=lambda *_a, **_k: None,
            set_activity_message=lambda *_a, **_k: None,
            set_actions_enabled=lambda *_a, **_k: None,
        ),
        "results": SimpleNamespace(render_report_list=lambda items: setattr(app, "_rendered_reports", items)),
        "validation": SimpleNamespace(
            set_default_operator_initials=lambda _value: None,
            render_cases=lambda items: setattr(app, "_rendered_validation_cases", items),
        ),
        "rules": SimpleNamespace(),
        "settings": SimpleNamespace(
            edit_generation=0,
            mark_saved_generation=lambda _generation: None,
            collect_settings=lambda **_kwargs: SimpleNamespace(watch_enabled=False),
            set_status_message=lambda _message: None,
        ),
        "diagnostics": SimpleNamespace(),
    }
    app._show_error_dialog = lambda *_a, **_k: setattr(app, "_error_shown", True)
    app._show_confirm_dialog = lambda *_a, **_k: True
    app._task_runner = _RecordingRunner()
    app.after = lambda delay_ms, callback: app._scheduled_after.append((delay_ms, callback)) or f"after-{len(app._scheduled_after)}"
    app.after_cancel = lambda _handle: None
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


def test_analyzer_desktop_open_rule_editor_uses_same_exe_in_frozen_mode(tmp_path, monkeypatch) -> None:
    app = test_app.AnalyzerDesktopApp.__new__(test_app.AnalyzerDesktopApp)
    app.project_root = tmp_path.resolve()
    calls: list[dict[str, object]] = []

    def fake_popen(command, cwd=None, env=None):  # noqa: ANN001
        calls.append({"command": command, "cwd": cwd, "env": env})

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr(test_app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(test_app.sys, "executable", str(tmp_path / "AnalyzerResultExtractorV2.exe"))
    monkeypatch.setattr(test_app.subprocess, "Popen", fake_popen)
    test_app.AnalyzerDesktopApp.open_rule_editor(app)
    assert calls == [
        {
            "command": [str(tmp_path / "AnalyzerResultExtractorV2.exe")],
            "cwd": str(tmp_path.resolve()),
            "env": calls[0]["env"],
        }
    ]
    env = calls[0]["env"]
    assert isinstance(env, dict)
    assert env["ARE_HOME"] == str(tmp_path.resolve())
    assert env["ARE_START_RULE_EDITOR"] == "1"


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
    app._views["results"] = SimpleNamespace(current_detail_report_id=lambda: "rep-1")
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
    )


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
        assert view._fields.item(view._fields.get_children()[0], "values") == ("RESULT", "42")
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
        render_cases=lambda items: rendered.append(tuple(items)),
    )
    calls: list[tuple[object, ...]] = []
    app._services.results.validate_report_run = lambda *args: calls.append(args)
    app._services.results.list_open_validation_cases = lambda: []

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
    app._services.results.open_report_pdf = lambda report_id: opened.append(report_id) or "/reports/report.pdf"

    test_app.AnalyzerDesktopApp._open_validation_pdf(app)
    assert app._task_runner.submissions[0][0] == "open-pdf-report-1"
    app._task_runner.invoke_success()
    assert opened == ["report-1"]


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

        def get_report_detail(report_id: str) -> ReportDetail:
            detail_calls.append(report_id)
            return _report_detail(report_id, f"{report_id}.pdf")

        def open_report_pdf(report_id: str) -> str:
            pdf_calls.append(report_id)
            return f"/pdf/{report_id}.pdf"

        app._services.results.get_report_detail = get_report_detail
        app._services.results.open_report_pdf = open_report_pdf
        view.render_report_list(
            (
                _report_summary(_MULTI_REPORT_ID, "multi.pdf"),
                _report_summary(_WATCH_REPORT_ID, "watch.pdf"),
            )
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
            )
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


def test_results_validation_panel_names_correction_and_shows_history() -> None:
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

        view.set_default_operator_initials("  AB ")
        view.render_report_detail(_validated_report_detail())
        assert "Validiert von CD" in view._lbl_validation_status.cget("text")
        assert view._btn_save_validation.cget("text") == "Validierung speichern"
        assert view._btn_correct_validation.cget("text") == "Validierung korrigieren"
        assert str(view._btn_save_validation.cget("state")) == "disabled"
        assert str(view._btn_correct_validation.cget("state")) == "normal"
        assert len(view._validation_tree.get_children()) == 2
        assert view.validation_run_id() == 5
        assert view.validation_initials() == "AB"
        assert "Verarbeitung: Fertig" in view._lbl_detail_meta.cget("text")
        assert "Status: Validiert" in view._lbl_detail_meta.cget("text")
    finally:
        root.destroy()


def test_save_validation_refreshes_detail_and_list_without_confirmation() -> None:
    app = _make_app_stub()
    rendered: dict[str, object] = {}
    detail = _report_detail("rep-1", "a.pdf")
    calls: list[tuple[object, ...]] = []
    app._settings = SimpleNamespace(operator_initials="AB")
    app._views["results"] = SimpleNamespace(
        current_detail_report_id=lambda: "rep-1",
        validation_run_id=lambda: 5,
        validation_initials=lambda: " AB ",
        validation_comment=lambda: " note ",
        render_report_list=lambda items: rendered.__setitem__("list", items),
        render_report_detail=lambda item: rendered.__setitem__("detail", item),
        show_detail=lambda: rendered.__setitem__("shown", True),
        clear_validation_comment=lambda: rendered.__setitem__("cleared", True),
        set_default_operator_initials=lambda value: rendered.__setitem__("initials", value),
    )
    app._services.results.validate_report_run = lambda *args, **kwargs: calls.append(("save", args, kwargs))
    app._services.results.correct_report_run = lambda *args, **kwargs: calls.append(("correct", args, kwargs))
    app._services.results.get_report_detail = lambda _report_id: detail
    app._services.results.list_recent_reports = lambda limit=50: (_report_summary("rep-1", "a.pdf"),)
    app._show_confirm_dialog = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("confirm"))

    app._save_selected_validation()
    assert len(app._task_runner.submissions) == 1
    app._task_runner.invoke_success()
    assert calls[0][0] == "save"
    assert calls[0][1] == ("rep-1", 5, "AB", "note")
    assert rendered["shown"] is True
    assert rendered["cleared"] is True
    assert rendered["detail"] is detail
    assert rendered["list"]


def test_correct_validation_requires_explicit_confirmation() -> None:
    app = _make_app_stub()
    dialogs: list[tuple[str, str]] = []
    calls: list[str] = []
    app._views["results"] = SimpleNamespace(
        current_detail_report_id=lambda: "rep-1",
        validation_run_id=lambda: 5,
        validation_initials=lambda: "AB",
        validation_comment=lambda: "",
        render_report_list=lambda _items: None,
        render_report_detail=lambda _detail: None,
        show_detail=lambda: None,
        clear_validation_comment=lambda: None,
        set_default_operator_initials=lambda _value: None,
    )
    app._services.results.correct_report_run = lambda *_args, **_kwargs: calls.append("correct")
    app._services.results.get_report_detail = lambda _report_id: _report_detail("rep-1", "a.pdf")
    app._services.results.list_recent_reports = lambda limit=50: ()
    app._show_confirm_dialog = lambda _parent, title, message: dialogs.append((title, message)) or False

    app._correct_selected_validation()
    assert dialogs
    assert dialogs[0][0] == "Validierung korrigieren"
    assert "nicht überschrieben" in dialogs[0][1]
    assert "neuer Datensatz" in dialogs[0][1]
    assert app._task_runner.submissions == []
    assert calls == []

    app._show_confirm_dialog = lambda *_args, **_kwargs: True
    app._correct_selected_validation()
    _key, work, _ok, _err = app._task_runner.submissions[0]
    work()
    assert calls == ["correct"]


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
    view._var_excel_after_validation.set(True)
    view._var_sqlite.set("db.sqlite3")
    collected = SettingsView.collect_settings(view, device_id_map={})
    assert collected.operator_initials == "RR"
    assert collected.output_mode == "both"


def test_settings_view_disables_excel_but_keeps_sqlite() -> None:
    view = _make_settings_view_logic_stub()
    view._var_excel_after_validation.set(False)
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
    assert view._var_excel_after_validation.get() is False
    assert view._var_sqlite.get() == "/db.sqlite3"
    assert view._var_device.get() == "Default Lab (DEFAULT_DEVICE)"
    assert not SettingsView.is_dirty(view)


def test_settings_view_migrates_legacy_excel_to_both_on_save() -> None:
    view = _make_settings_view_logic_stub()
    SettingsView._apply_settings_values(view, _sample_settings_namespace(output_mode="excel"))
    assert view._var_excel_after_validation.get() is True
    assert SettingsView.collect_settings(view, device_id_map={}).output_mode == "both"


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


def test_retry_selected_export_failure_uses_export_only_path() -> None:
    app = _make_app_stub(current_view="diagnostics")
    calls: list[str] = []
    app._views["diagnostics"].selected_job_id = lambda: "job-1"
    app._services.extraction.get_job_diagnosis = lambda _job_id: SimpleNamespace(retry_kind="export_only")
    app._services.extraction.retry_excel_export = lambda job_id: calls.append(job_id) or ProcessingOutcome(
        processed=True,
        job_id=job_id,
        queue_status="DONE",
        submit_status="DONE",
    )
    app._services.extraction.retry_failed = lambda _job_id: (_ for _ in ()).throw(AssertionError("full retry"))
    app.refresh_current_view = lambda: calls.append("refresh")

    test_app.AnalyzerDesktopApp._retry_selected_job(app)
    app._task_runner.invoke_success()
    assert calls == ["job-1", "refresh"]


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
    app = _make_app_stub()
    app._show_confirm_dialog = lambda *_a, **_k: False
    app._views["diagnostics"].selected_duplicate_id = lambda: 7
    test_app.AnalyzerDesktopApp._discard_selected_duplicate(app)
    assert app._task_runner.submissions == []


def test_discard_selected_duplicate_confirmation_true_refreshes() -> None:
    app = _make_app_stub()
    discarded: list[int] = []
    refresh_calls = {"count": 0}
    app.refresh_current_view = lambda: refresh_calls.__setitem__("count", refresh_calls["count"] + 1)
    app._views["diagnostics"].selected_duplicate_id = lambda: 7
    app._services.results.discard_duplicate_candidate = lambda candidate_id: discarded.append(candidate_id)
    test_app.AnalyzerDesktopApp._discard_selected_duplicate(app)
    assert len(app._task_runner.submissions) == 1
    app._task_runner.invoke_success()
    assert discarded == [7]
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
        assert app.TASK_PROCESSING == "processing_queue"
    finally:
        app.destroy()


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
