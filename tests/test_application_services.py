from __future__ import annotations

from pathlib import Path

from src.application.api import (
    DesktopAppServices,
    ExtractionController,
    ResultsController,
    RuleSuiteController,
    SettingsController,
    create_desktop_services,
)


def test_create_desktop_services_exposes_four_controllers(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()

    services = create_desktop_services(root)

    assert isinstance(services, DesktopAppServices)
    assert isinstance(services.extraction, ExtractionController)
    assert isinstance(services.results, ResultsController)
    assert isinstance(services.rules, RuleSuiteController)
    assert isinstance(services.settings, SettingsController)
    assert services.extraction.project_root == root.resolve()
    assert services.results.project_root == root.resolve()
    assert services.rules.project_root == root.resolve()
    assert services.settings.project_root == root.resolve()


def test_public_api_exports_desktop_services_factory() -> None:
    from src.application import api as application_api

    assert "create_desktop_services" in application_api.__all__
    assert "DesktopAppServices" in application_api.__all__
    assert "ExtractionController" in application_api.__all__
    assert "ResultsController" in application_api.__all__
    assert "RuleSuiteController" in application_api.__all__
    assert "SettingsController" in application_api.__all__
    assert "ProcessingBatchSummary" in application_api.__all__
    assert "ProcessingOutcome" in application_api.__all__
    assert "RunValidationPlaceholder" not in application_api.__all__


def test_desktop_services_keep_live_settings_without_rebuild(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    services = create_desktop_services(root)

    updated = services.settings.load().__class__(
        output_mode="excel",
        sqlite_path=str(root / "live.sqlite3"),
        watch_input_path=str(root / "watch"),
        device_id="live-device",
    )
    services.settings.save(updated)

    assert services.settings.load().output_mode == "excel"
    assert services.settings.load().sqlite_path == str(root / "live.sqlite3")
    assert services.settings.load().device_id == "live-device"


def test_public_api_exports_phase3a_read_models() -> None:
    from src.application import api as application_api

    for name in (
        "IngestionInstanceItem",
        "JobDiagnosisItem",
        "ReportSummaryItem",
        "ReportDetail",
        "DuplicateCandidateItem",
        "DuplicateDecisionResult",
        "map_ingestion_display_status",
        "PathOpenError",
        "ReportNotFoundError",
    ):
        assert name in application_api.__all__


def test_public_api_does_not_export_generic_path_opener_symbols() -> None:
    from src.application import api as application_api

    for forbidden in ("PathOpener", "default_path_opener", "open_path"):
        assert forbidden not in application_api.__all__
