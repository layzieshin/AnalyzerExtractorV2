import json
from pathlib import Path

from src.rulesuite.api import (
    REQUIRED_HEADER_FIELD_KEYS,
    check_candidates,
    check_required_fields,
    create_draft_from_ruleset,
    create_draft_from_template,
    load_draft,
    read_candidate_fields,
)


def _write_min_template(root: Path) -> None:
    fields = [
        {"key": key, "regex": rf"{key}:\s*(\S+)", "required": False}
        for key in REQUIRED_HEADER_FIELD_KEYS
    ]
    fields[-1]["search_from"] = {"line": 0}
    template = {
        "assay_name": "Template",
        "assay_key": "(0000)",
        "lot_rule": {"regex": r"Lot:\s*(\S+)"},
        "extract_rules": {"fields": fields},
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {key: key for key in REQUIRED_HEADER_FIELD_KEYS},
        },
    }
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "index.json").write_text(json.dumps({"assays": []}), encoding="utf-8")
    (root / "rules" / "template.json").write_text(json.dumps(template), encoding="utf-8")


def test_wizard_template_draft_and_required_status(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _write_min_template(root)

    draft = create_draft_from_template(str(root), "(7777)", "Wizard Assay")
    data = load_draft(draft)
    assert [f["key"] for f in data["extract_rules"]["fields"]] == list(REQUIRED_HEADER_FIELD_KEYS)

    text = "\n".join(f"{key}: VALUE" for key in REQUIRED_HEADER_FIELD_KEYS)
    report = check_required_fields(draft, text, group=1)
    assert report["all_confirmed"] is True


def test_wizard_module_imports_focus_helpers() -> None:
    from rule_editor.wizard import NewRulesetWizard
    from rule_editor.wizard_ui import _CANDIDATE_STATUS_LABELS, _REQUIRED_STATUS_LABELS

    assert NewRulesetWizard is not None
    assert "confirmed" in _REQUIRED_STATUS_LABELS
    assert "confirmed" in _CANDIDATE_STATUS_LABELS


def test_wizard_similar_flow_candidates(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "rules").mkdir(parents=True)
    index = {"assays": [{"assay_key": "(1111)", "ruleset_file": "Source.json"}]}
    (root / "rules" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    source = {
        "assay_name": "Source",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Lot:\s*(\S+)"},
        "extract_rules": {
            "fields": [
                {"key": "date", "regex": r"Datum:\s*(\S+)", "required": True},
                {"key": "time", "regex": r"Zeit:\s*(\S+)", "required": True},
                {"key": "user", "regex": r"Anwender:\s*(\S+)", "required": True},
                {"key": "plate_name", "regex": r"Platte:\s*(\S+)", "required": True},
                {"key": "lot_id", "regex": r"Charge:\s*(\S+)", "required": True},
                {"key": "VALIDATION", "regex": r"(OK)", "required": False},
                {"key": "assay_val", "regex": r"Assay:\s*(\S+)", "required": False},
            ]
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {
                "date": "Datum",
                "assay_val": "Assay Value",
            },
        },
    }
    (root / "rules" / "Source.json").write_text(json.dumps(source), encoding="utf-8")

    draft = create_draft_from_ruleset(str(root), "(1111)", "(8888)", "New Similar")
    data = load_draft(draft)
    assert [f["key"] for f in data["extract_rules"]["fields"]] == list(REQUIRED_HEADER_FIELD_KEYS)

    cands = read_candidate_fields(str(root), source_assay_key="(1111)")
    assert {f["key"] for f in cands["fields"]} == {"assay_val"}
    assert "date" not in {f["key"] for f in cands["fields"]}

    report = check_candidates(str(root), "Assay: ABC", draft, {"source_assay_key": "(1111)"})
    assert report["results"][0]["key"] == "assay_val"
    assert report["results"][0]["status"] == "confirmed"
