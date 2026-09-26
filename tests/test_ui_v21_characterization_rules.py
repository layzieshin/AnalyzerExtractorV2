"""Phase 0 RuleSuite lifecycle characterization in isolated temporary project roots."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.rulesuite.api import (
    activate_draft,
    create_draft,
    list_rulesuite_inventory,
    preview_extract,
    set_field_regex,
)


def _setup_isolated_rules_project(tmp_path: Path) -> Path:
    root = tmp_path / "isolated_proj"
    rules_dir = root / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "drafts").mkdir()

    index = {
        "assays": [
            {"assay_key": "(aaaa)", "ruleset_file": "AssayA.json"},
        ]
    }
    (rules_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")

    active = {
        "assay_name": "Assay A",
        "assay_key": "(aaaa)",
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
    (rules_dir / "AssayA.json").write_text(json.dumps(active), encoding="utf-8")
    return root


def test_create_draft_from_active_rule_in_isolated_copy(tmp_path: Path) -> None:
    root = _setup_isolated_rules_project(tmp_path)

    draft_path = create_draft(str(root), "(aaaa)")

    assert Path(draft_path).exists()
    assert "drafts" in draft_path.replace("\\", "/")
    inventory = list_rulesuite_inventory(str(root))
    kinds = {item.get("kind") for item in inventory}
    assert "active" in kinds
    assert "draft" in kinds


def test_preview_extract_runs_real_extractor_with_mocked_text_acquisition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _setup_isolated_rules_project(tmp_path)
    draft = create_draft(str(root), "(aaaa)")

    def _fake_get_assay_text(self, project_root, pdf_path, assay_key, assay_name, draft_path=None):
        return {
            "detected_assays": [assay_key],
            "assay_block": "Test: ABC\nLot: LOT1",
        }

    monkeypatch.setattr("src.rulesuite.rulesuite.RuleSuite.get_assay_text", _fake_get_assay_text)

    out = preview_extract(str(root), "dummy.pdf", "(aaaa)", draft_path=draft)
    assert out["assay_key"] == "(aaaa)"
    assert out["detected_assays"] == ["(aaaa)"]
    assert out["lot_id"] == "LOT1"
    assert out["data"] == {"test": "ABC"}


def test_activate_draft_snapshots_previous_active_bytes_before_overwrite(tmp_path: Path) -> None:
    """Gate 5: existing-rule activation keeps a byte-exact copy of the previous active JSON."""
    root = _setup_isolated_rules_project(tmp_path)
    active_path = root / "rules" / "AssayA.json"
    before = active_path.read_bytes()

    draft = create_draft(str(root), "(aaaa)")
    set_field_regex(draft, "test", r"Test:\s*(UPDATED)")

    target = activate_draft(str(root), "(aaaa)", draft)
    after_data = json.loads(Path(target).read_text(encoding="utf-8"))
    field = next(f for f in after_data["extract_rules"]["fields"] if f["key"] == "test")
    snapshots = sorted((root / "rules" / "history").glob("*.json"))

    assert target.endswith("AssayA.json")
    assert before != active_path.read_bytes()
    assert field["regex"] == r"Test:\s*(UPDATED)"
    assert len(snapshots) == 1
    assert snapshots[0].read_bytes() == before
