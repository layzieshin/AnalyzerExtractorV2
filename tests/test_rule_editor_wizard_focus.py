import json
from pathlib import Path

from src.rulesuite.api import (
    REQUIRED_HEADER_FIELD_KEYS,
    check_required_fields,
    create_draft_from_template,
    load_draft,
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
    from rule_editor.wizard_ui import _REQUIRED_STATUS_LABELS

    assert NewRulesetWizard is not None
    assert "confirmed" in _REQUIRED_STATUS_LABELS
