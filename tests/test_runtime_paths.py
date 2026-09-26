from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from gui_min_ext import run_startup_smoke_check
from src.runtime.paths import resolve_app_root


def _write_valid_rules(root: Path) -> None:
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


def test_resolve_app_root_uses_are_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "standalone-home"
    monkeypatch.setenv("ARE_HOME", str(home))

    assert resolve_app_root(__file__) == home.resolve()


def test_resolve_app_root_uses_exe_parent_when_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = tmp_path / "AnalyzerResultExtractorV2.exe"
    monkeypatch.delenv("ARE_HOME", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))

    assert resolve_app_root(__file__) == tmp_path.resolve()


def test_startup_smoke_check_accepts_valid_rules(tmp_path: Path) -> None:
    _write_valid_rules(tmp_path)

    run_startup_smoke_check(tmp_path)


def test_startup_smoke_check_rejects_invalid_rules(tmp_path: Path) -> None:
    rules = tmp_path / "rules"
    rules.mkdir(parents=True)
    (rules / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1111)", "ruleset_file": "Missing.json"}]}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="rules_integrity_failed"):
        run_startup_smoke_check(tmp_path)
