"""CLI smoke tests for interfaces/cli/rule_suite.py (rule_suite_main.py)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.rulesuite.api import create_draft, create_draft_from_template


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "rule_suite_main.py"), *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )


def _setup_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "rules").mkdir(parents=True)

    index = {
        "assays": [
            {"assay_key": "(1111)", "ruleset_file": "AssayA.json"},
        ]
    }
    (root / "rules" / "index.json").write_text(json.dumps(index), encoding="utf-8")

    assay_a = {
        "assay_name": "Assay A",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Lot:\s*(\w+)"},
        "extract_rules": {
            "fields": [
                {"key": "test", "regex": r"Test:\s*(\w+)", "required": True},
                {"key": "date", "regex": r"Date:\s*(\d{4}-\d{2}-\d{2})", "required": False},
            ],
            "dedupe_fields": ["test"],
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {"test": "TEST", "date": "DATE"},
        },
    }
    (root / "rules" / "AssayA.json").write_text(json.dumps(assay_a), encoding="utf-8")
    return root


def _write_template(root: Path) -> None:
    template = {
        "assay_name": "Template Assay",
        "assay_key": "(0000)",
        "lot_rule": {"regex": r"Kit\s+(\S+)\s+\d{6}"},
        "extract_rules": {
            "fields": [
                {"key": "DATUM", "regex": r"Datum:\s*([0-9.\-]+)", "required": False},
                {"key": "ZEIT", "regex": r"Zeit:\s*(\d{2}:\d{2}:\d{2})", "required": False},
                {"key": "ANWENDER", "regex": r"Anwender:\s*([^\s]+)", "required": False},
                {"key": "PLATTE", "regex": r"Platte:\s*(\S+)", "required": False},
                {"key": "CHARGE", "regex": r"Charge:\s*(\S+)", "required": False},
                {
                    "key": "VALIDATION",
                    "regex": r"(Validationskriterien\s+erf)",
                    "required": False,
                    "search_from": {"line": 0},
                },
            ]
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {
                "DATUM": "DATUM",
                "ZEIT": "ZEIT",
                "ANWENDER": "ANWENDER",
                "PLATTE": "PLATTE",
                "CHARGE": "CHARGE",
                "VALIDATION": "VALIDATION",
            },
        },
    }
    (root / "rules" / "template.json").write_text(json.dumps(template), encoding="utf-8")


def _confirmed_assay_text() -> str:
    return "\n".join(
        [
            "Datum: 09.07.2026",
            "Zeit: 10:15:00",
            "Anwender: LAB01",
            "Platte: P-12",
            "Charge: CH-99",
            "Validationskriterien erfuellt",
        ]
    )


def _make_template_draft(root: Path) -> str:
    _write_template(root)
    return create_draft_from_template(str(root), "(9100)", "Templated Assay")


def test_cli_readiness_structure_only_ok_with_warning(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = _make_template_draft(root)

    result = _run_cli(["readiness", "--draft-path", draft])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["required_field_status"] is None
    assert any("no_assay_text" in w for w in payload["warnings"])


def test_cli_readiness_with_assay_text_exit_zero(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = _make_template_draft(root)

    result = _run_cli(
        [
            "readiness",
            "--draft-path",
            draft,
            "--assay-text",
            _confirmed_assay_text(),
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["warnings"] == []
    assert payload["required_field_status"]["all_confirmed"] is True


def test_cli_readiness_missing_required_exit_one(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = _make_template_draft(root)

    result = _run_cli(
        [
            "readiness",
            "--draft-path",
            draft,
            "--assay-text",
            "Datum: 09.07.2026",
        ]
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["missing_required"]


def test_cli_check_required_without_text_exit_one(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = _make_template_draft(root)

    result = _run_cli(["check-required", "--draft-path", draft])
    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert "error" in payload
    assert "assay_text_required" in payload["error"]


def test_cli_locate_field_filters_single_key(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    text = "Test: ABC123\nDate: 2026-01-01"

    result = _run_cli(
        [
            "locate-field",
            "--draft-path",
            draft,
            "--assay-text",
            text,
            "--field-key",
            "test",
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["results"]) == 1
    assert payload["results"][0]["key"] == "test"
    assert payload["results"][0]["matched"] is True


def test_cli_preview_error_json_stderr_exit_one(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    missing_pdf = str(root / "does_not_exist.pdf")

    result = _run_cli(
        [
            "preview",
            "--pdf",
            missing_pdf,
            "--assay-key",
            "(1111)",
            "--draft-path",
            draft,
        ]
    )
    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert "error" in payload
    assert payload["error"]
