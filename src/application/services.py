from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .extraction_controller import ExtractionController
from .results_controller import ResultsController
from .rules_controller import RuleSuiteController
from .settings_controller import SettingsController


@dataclass(frozen=True)
class DesktopAppServices:
    extraction: ExtractionController
    results: ResultsController
    rules: RuleSuiteController
    settings: SettingsController


def create_desktop_services(project_root: str | Path) -> DesktopAppServices:
    root = Path(project_root).resolve()
    settings = SettingsController(root)
    settings.load()
    provider = settings.load
    return DesktopAppServices(
        extraction=ExtractionController(root, settings_provider=provider),
        results=ResultsController(root, settings_provider=provider),
        rules=RuleSuiteController(root),
        settings=settings,
    )
