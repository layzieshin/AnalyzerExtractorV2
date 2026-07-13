import json
from pathlib import Path

import pytest

from src.rulesuite.api import (
    activate_draft,
    activate_new_draft,
    add_field,
    adopt_candidate_field,
    adopt_candidate_fields,
    batch_check_fields,
    check_authoring_readiness,
    check_candidates,
    check_required_fields,
    clone_ruleset_to_draft,
    create_blank_draft,
    create_draft,
    create_draft_from_ruleset,
    create_draft_from_template,
    create_draft_from_template_if_missing,
    deactivate_ruleset,
    delete_inventory_item,
    delete_ruleset,
    diff_draft_vs_active,
    draft_path_for_assay,
    duplicate_field,
    derive_draft,
    list_fields,
    list_rulesets,
    list_rulesuite_inventory,
    load_draft,
    locate_fields,
    open_inactive_as_draft,
    move_field,
    preview_extract,
    read_candidate_fields,
    remove_field,
    rename_field,
    REQUIRED_HEADER_FIELD_KEYS,
    save_draft,
    set_dedupe_fields,
    set_excel_rules,
    set_field_regex,
    set_lot_rule,
    sync_column_mapping_from_fields,
    test_regex,
    update_field,
    validate_draft,
)
from src.rulesuite.header_aliases import LEGACY_HEADER_ALIAS_KEYS, resolve_required_headers_from_source
from src.ruleresolver.api import resolve_ruleset, validate_rules_integrity
from src.ruleresolver.ruleresolver import RuleResolverError
from src.rulesuite.rulesuite import RuleSuiteError


def _setup_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "rules").mkdir(parents=True)

    index = {
        "assays": [
            {"assay_key": "(1111)", "ruleset_file": "AssayA.json"},
            {"assay_key": "(2222)", "ruleset_file": "AssayB.json"},
        ]
    }
    (root / "rules" / "index.json").write_text(json.dumps(index), encoding="utf-8")

    assay_a = {
        "assay_name": "Assay A",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Lot:\\s*(\\w+)"},
        "extract_rules": {
            "fields": [
                {"key": "test", "regex": r"Test:\\s*(\\w+)", "required": True},
                {"key": "date", "regex": r"Date:\\s*(\\d{4}-\\d{2}-\\d{2})", "required": False},
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

    assay_b = {
        "assay_name": "Assay B",
        "assay_key": "(2222)",
        "lot_rule": {"regex": r"Lot:\\s*(\\w+)"},
        "extract_rules": {"fields": [{"key": "x", "regex": r"X:(\\w+)", "required": False}]},
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {"x": "X"},
        },
    }
    (root / "rules" / "AssayB.json").write_text(json.dumps(assay_b), encoding="utf-8")
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
                {"key": "TEST", "regex": r"Test:\s*(\S+)", "required": False},
                {"key": "VALIDATION", "regex": r"(Validationskriterien\s+erf)", "required": False, "search_from": {"line": 0}},
                {"key": "Haltbarkeit", "regex": r"Haltbarkeit:\s*(\S+)", "required": False},
                {"key": "FILE_NAME", "regex": r"Datei:\s*(\S+)", "required": False},
                {"key": "PCQ1", "regex": r"PCQ1\s+(\d+)", "required": False},
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
                "TEST": "TEST",
                "VALIDATION": "VALIDATION",
                "Haltbarkeit": "Haltbarkeit",
                "FILE_NAME": "FILE_NAME",
                "PCQ1": "PCQ1",
            },
        },
    }
    (root / "rules" / "template.json").write_text(json.dumps(template), encoding="utf-8")


def test_rulesuite_draft_and_set_regex(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)

    draft_path = create_draft(str(root), "(1111)")
    fields = list_fields(str(root), "(1111)")
    assert fields == ["test", "date"]

    updated = set_field_regex(draft_path, "test", r"TEST:\\s*(\\w+)")
    data = json.loads(Path(updated).read_text(encoding="utf-8"))
    assert data["extract_rules"]["fields"][0]["regex"] == r"TEST:\\s*(\\w+)"


def test_create_blank_and_derive_draft(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)

    blank = create_blank_draft(str(root), "(9000)", "New Assay")
    blank_data = load_draft(blank)
    assert blank_data["assay_key"] == "(9000)"
    assert blank_data["assay_name"] == "New Assay"
    assert blank_data["extract_rules"]["fields"] == []

    derived = derive_draft(str(root), "(1111)", "(9001)", "Clone A")
    derived_data = load_draft(derived)
    assert derived_data["assay_key"] == "(9001)"
    assert derived_data["assay_name"] == "Clone A"
    assert derived_data["extract_rules"]["fields"][0]["key"] == "test"


def test_field_ops_sync_column_mapping_and_dedupe(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")

    add_field(draft, "time", r"Time:(\\d{2}:\\d{2}:\\d{2})", required=False)
    set_dedupe_fields(draft, ["test", "time"])
    set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {"test": "TEST", "time": "TIME"})

    rename_field(draft, "time", "clock")
    d1 = load_draft(draft)
    assert d1["extract_rules"]["dedupe_fields"] == ["test", "clock"]
    assert "clock" in d1["excel_rules"]["column_mapping"]
    assert "time" not in d1["excel_rules"]["column_mapping"]

    update_field(draft, "clock", regex=r"Clock:(\\d{2}:\\d{2}:\\d{2})", required=True, search_from={"line": 1})
    d2 = load_draft(draft)
    clock = [f for f in d2["extract_rules"]["fields"] if f["key"] == "clock"][0]
    assert clock["required"] is True
    assert clock["search_from"] == {"line": 1}

    remove_field(draft, "clock")
    d3 = load_draft(draft)
    assert "clock" not in [f["key"] for f in d3["extract_rules"]["fields"]]
    assert "clock" not in d3["excel_rules"]["column_mapping"]

    duplicate_field(draft, "test", "test_copy")
    d4 = load_draft(draft)
    keys = [f["key"] for f in d4["extract_rules"]["fields"]]
    assert "test_copy" in keys

    move_field(draft, "test_copy", "up")
    d5 = load_draft(draft)
    keys2 = [f["key"] for f in d5["extract_rules"]["fields"]]
    assert keys2.index("test_copy") < keys2.index("date")


def test_add_field_adds_default_column_mapping(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9000)", "Test Assay")

    add_field(draft, "C1_MINIMUM", r"C1:(\d+)", required=False)
    data = load_draft(draft)

    assert data["excel_rules"]["column_mapping"]["C1_MINIMUM"] == "C1_MINIMUM"


def test_add_field_does_not_overwrite_existing_column_mapping(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9000)", "Test Assay")
    add_field(draft, "test", r"T:(\w+)", required=False)
    set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {"test": "CUSTOM"})

    add_field(draft, "other", r"O:(\w+)", required=False)
    data = load_draft(draft)

    assert data["excel_rules"]["column_mapping"]["test"] == "CUSTOM"
    assert data["excel_rules"]["column_mapping"]["other"] == "other"


def test_update_field_adds_missing_column_mapping(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    data = load_draft(draft)
    data["excel_rules"]["column_mapping"] = {"test": "TEST"}
    save_draft(draft, data)

    update_field(draft, "date", regex=r"Date:(\d+)")
    updated = load_draft(draft)

    assert updated["excel_rules"]["column_mapping"]["test"] == "TEST"
    assert updated["excel_rules"]["column_mapping"]["date"] == "date"


def test_update_field_not_found_leaves_column_mapping(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9000)", "Test Assay")

    with pytest.raises(RuleSuiteError, match="field_not_found"):
        update_field(draft, "missing", regex=r"x")

    data = load_draft(draft)
    assert data["excel_rules"]["column_mapping"] == {}


def test_duplicate_field_uses_new_key_column_name(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    set_excel_rules(
        draft,
        "{assay_name}.xlsx",
        "{lot_id}",
        {"test": "TEST_COL", "date": "DATE_COL"},
    )

    duplicate_field(draft, "test", "test_copy")
    data = load_draft(draft)

    assert data["excel_rules"]["column_mapping"]["test"] == "TEST_COL"
    assert data["excel_rules"]["column_mapping"]["test_copy"] == "test_copy"


def test_rename_field_without_old_mapping_adds_new_key_default(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    data = load_draft(draft)
    data["excel_rules"]["column_mapping"] = {"test": "TEST"}
    save_draft(draft, data)

    rename_field(draft, "date", "datum")
    updated = load_draft(draft)

    assert updated["excel_rules"]["column_mapping"]["test"] == "TEST"
    assert updated["excel_rules"]["column_mapping"]["datum"] == "datum"
    assert "date" not in updated["excel_rules"]["column_mapping"]


def test_sync_column_mapping_from_fields_adds_missing_without_overwrite(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    data = load_draft(draft)
    data["excel_rules"]["column_mapping"] = {"test": "CustomTest", "orphan": "OrphanCol"}
    save_draft(draft, data)

    sync_column_mapping_from_fields(draft)
    updated = load_draft(draft)
    col = updated["excel_rules"]["column_mapping"]

    assert col["test"] == "CustomTest"
    assert col["date"] == "date"
    assert col["orphan"] == "OrphanCol"


def test_column_mapping_normalized_when_missing_or_invalid(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9000)", "Test Assay")
    data = load_draft(draft)
    data["excel_rules"]["column_mapping"] = "not-a-dict"
    save_draft(draft, data)

    add_field(draft, "alpha", r"A:(\w+)", required=False)
    updated = load_draft(draft)

    assert isinstance(updated["excel_rules"]["column_mapping"], dict)
    assert updated["excel_rules"]["column_mapping"]["alpha"] == "alpha"


def test_regex_and_validate_draft(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")

    hit = test_regex("Result: 123", r"Result:\s*(\d+)")
    assert hit["matched"] is True
    assert hit["value"] == "123"
    assert hit["span"] == [8, 11]

    miss = test_regex("Result: 123", r"Time:\s*(\d+)")
    assert miss["matched"] is False
    assert miss["error"] is None

    bad = test_regex("x", r"(")
    assert bad["matched"] is False
    assert str(bad["error"]).startswith("invalid_regex")

    full = test_regex("Result: 123", r"Result:\s*(\d+)", group=0)
    assert full["matched"] is True
    assert full["value"] == "Result: 123"
    assert full["span"] == [0, 11]

    out_of_range = test_regex("Result: 123", r"Result:\s*(\d+)", group=3)
    assert out_of_range["matched"] is False
    assert str(out_of_range["error"]).startswith("group_out_of_range")

    ok = validate_draft(draft)
    assert ok["ok"] is True
    assert ok["errors"] == []

    set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {"unknown": "U"})
    bad_draft = validate_draft(draft)
    assert bad_draft["ok"] is False
    assert any("column_mapping unknown keys" in err for err in bad_draft["errors"])


def test_regex_honors_search_from_line() -> None:
    text = "Header: alpha\nFooter: beta"
    regex = r"Footer:\s*(\w+)"

    full = test_regex(text, regex)
    assert full["matched"] is True
    assert full["value"] == "beta"
    assert full["span"] == [22, 26]

    after_start = test_regex(text, regex, search_from={"line": 1})
    assert after_start["matched"] is True
    assert after_start["value"] == "beta"
    assert after_start["span"] == [22, 26]

    before_start = test_regex(text, regex, search_from={"line": 2})
    assert before_start["matched"] is False
    assert before_start["error"] is None

    only_on_first_line = test_regex(text, r"Header:\s*(\w+)", search_from={"line": 1})
    assert only_on_first_line["matched"] is False
    assert only_on_first_line["error"] is None

    invalid = test_regex(text, regex, search_from={"line": -1})
    assert invalid["matched"] is False
    assert invalid["error"] == "search_from.line must be >= 0"


def test_activate_new_draft_updates_index_and_rejects_duplicates(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9000)", "Fresh Assay")

    set_lot_rule(draft, r"Lot:\\s*(\\w+)")
    add_field(draft, "test", r"Test:\\s*(\\w+)", required=True)
    set_dedupe_fields(draft, ["test"])
    set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {"test": "TEST"})

    out_path = activate_new_draft(str(root), "(9000)", "Fresh Assay", draft)
    assert Path(out_path).exists()

    index = json.loads((root / "rules" / "index.json").read_text(encoding="utf-8"))
    assert any(row["assay_key"] == "(9000)" for row in index["assays"])

    with pytest.raises(RuleSuiteError):
        activate_new_draft(str(root), "(9000)", "Another Name", draft)


def test_activate_new_draft_rejects_invalid_filename_and_case_collision(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9002)", "Bad Name")
    set_lot_rule(draft, r"Lot:\\s*(\\w+)")
    add_field(draft, "test", r"Test:\\s*(\\w+)", required=True)
    set_dedupe_fields(draft, ["test"])
    set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {"test": "TEST"})

    with pytest.raises(RuleSuiteError, match="invalid_assay_name_for_filename"):
        activate_new_draft(str(root), "(9002)", "////", draft)

    out_path = activate_new_draft(str(root), "(9002)", "Case Name", draft)
    assert Path(out_path).exists()

    draft2 = create_blank_draft(str(root), "(9003)", "Case Name")
    set_lot_rule(draft2, r"Lot:\\s*(\\w+)")
    add_field(draft2, "test", r"Test:\\s*(\\w+)", required=True)
    set_dedupe_fields(draft2, ["test"])
    set_excel_rules(draft2, "{assay_name}.xlsx", "{lot_id}", {"test": "TEST"})

    with pytest.raises(RuleSuiteError, match="ruleset_file_exists_case_insensitive"):
        activate_new_draft(str(root), "(9003)", "case name", draft2)


def test_batch_check_and_diff(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    set_field_regex(draft, "test", r"Result:\s*(\d+)")
    add_field(draft, "time", r"Time:\s*(\d{2}:\d{2})", required=False)

    batch = batch_check_fields(draft, "Result: 123")
    assert batch["total_fields"] >= 2
    assert any(r["key"] == "test" and r["matched"] for r in batch["results"])

    diff = diff_draft_vs_active(str(root), "(1111)", draft)
    assert diff["mode"] == "update"
    assert len(diff["changes"]) > 0


def test_locate_fields_honors_search_from(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    text = "Header\nMarker line\nTest: ABC123\nFooter"
    update_field(draft, "test", regex=r"Test:\s*(\w+)", search_from={"after": r"Marker line"})

    out = locate_fields(draft, text, group=1)
    test_row = next(r for r in out["results"] if r["key"] == "test")
    assert test_row["matched"] is True
    assert test_row["value"] == "ABC123"
    assert test_row["span"] == [text.index("ABC123"), text.index("ABC123") + len("ABC123")]


def test_validate_draft_handles_non_object_extract_rules(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    data = load_draft(draft)
    data["extract_rules"] = "broken"
    Path(draft).write_text(json.dumps(data), encoding="utf-8")

    out = validate_draft(draft)
    assert out["ok"] is False
    assert "extract_rules must be object" in out["errors"]


def test_validate_draft_rejects_empty_fields(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9004)", "Empty Fields")
    set_lot_rule(draft, r"Lot:\\s*(\\w+)")
    set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {})

    out = validate_draft(draft)
    assert out["ok"] is False
    assert "extract_rules.fields must be non-empty" in out["errors"]


def test_validate_draft_rejects_invalid_search_from_after_regex(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    update_field(draft, "test", search_from={"after": "("})

    out = validate_draft(draft)
    assert out["ok"] is False
    assert any("field[0].search_from.after invalid regex" in err for err in out["errors"])


def test_validate_draft_rejects_invalid_excel_templates(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    data = load_draft(draft)
    data["excel_rules"]["excel_filename_template"] = "{assay_name}_{missing}.xlsx"
    data["excel_rules"]["sheetname_template"] = "{unknown}"
    Path(draft).write_text(json.dumps(data), encoding="utf-8")

    out = validate_draft(draft)
    assert out["ok"] is False
    assert any("excel_rules.excel_filename_template invalid template" in err for err in out["errors"])
    assert any("excel_rules.sheetname_template invalid template" in err for err in out["errors"])


def test_activate_draft_rejects_invalid_draft(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    data = load_draft(draft)
    data["excel_rules"]["column_mapping"] = {"unknown": "X"}
    Path(draft).write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(RuleSuiteError, match="draft_invalid"):
        activate_draft(str(root), "(1111)", draft)


def test_integrity_report_includes_content_errors(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    bad_ruleset_path = root / "rules" / "AssayA.json"
    data = json.loads(bad_ruleset_path.read_text(encoding="utf-8"))
    data["excel_rules"]["column_mapping"] = {"unknown": "X"}
    bad_ruleset_path.write_text(json.dumps(data), encoding="utf-8")

    report = validate_rules_integrity(str(root / "rules"), str(root / "rules" / "index.json"))
    assert any(row["ruleset_file"] == "AssayA.json" for row in report["content_errors"])


def test_create_draft_from_template_takes_required_header_rules(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)

    draft = create_draft_from_template(str(root), "(9100)", "Templated Assay")
    data = load_draft(draft)

    assert data["assay_key"] == "(9100)"
    assert data["assay_name"] == "Templated Assay"
    assert data["lot_rule"]["regex"] == r"Kit\s+(\S+)\s+\d{6}"

    keys = [f["key"] for f in data["extract_rules"]["fields"]]
    assert keys == list(REQUIRED_HEADER_FIELD_KEYS)
    assert "Haltbarkeit" not in keys
    assert "HALTBARKEIT" in keys
    assert "FILE_NAME" not in keys
    assert "PCQ1" not in keys
    assert all(bool(f.get("required")) for f in data["extract_rules"]["fields"])

    by_key = {f["key"]: f for f in data["extract_rules"]["fields"]}
    assert by_key["HALTBARKEIT"]["regex"] == r"Haltbarkeit:\s*(\S+)"
    assert by_key["TEST"]["regex"] == r"Test:\s*(\S+)"

    validation = next(f for f in data["extract_rules"]["fields"] if f["key"] == "VALIDATION")
    assert validation["search_from"] == {"line": 0}
    assert not validation["regex"].startswith("^")
    assert validation["regex"] == r"(Validationskriterien\s+erf)"

    col_map = data["excel_rules"]["column_mapping"]
    assert set(col_map.keys()) == set(REQUIRED_HEADER_FIELD_KEYS)
    assert col_map["HALTBARKEIT"] == "Haltbarkeit"


def test_create_draft_from_template_strips_validation_line_anchor(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    template = {
        "assay_name": "Template",
        "assay_key": "(0000)",
        "lot_rule": {"regex": r"Lot:\s*(\S+)"},
        "extract_rules": {
            "fields": [
                {
                    "key": "VALIDATION",
                    "regex": r"^(Validationskriterien\s+(?:nicht\s+)?erfüllt)",
                    "required": False,
                    "search_from": {"line": 0},
                },
            ]
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {"VALIDATION": "VALIDATION"},
        },
    }
    (root / "rules" / "template.json").write_text(json.dumps(template), encoding="utf-8")

    draft = create_draft_from_template(str(root), "(9105)", "Anchor Strip Assay")
    data = load_draft(draft)
    validation = next(f for f in data["extract_rules"]["fields"] if f["key"] == "VALIDATION")

    assert validation["regex"] == r"(Validationskriterien\s+(?:nicht\s+)?erfüllt)"
    assert validation["search_from"] == {"line": 0}


def test_create_draft_from_template_fills_missing_required_fields_with_empty_regex(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    template = {
        "assay_name": "Template",
        "assay_key": "(0000)",
        "lot_rule": {"regex": r"Lot:\s*(\S+)"},
        "extract_rules": {
            "fields": [
                {"key": "ZEIT", "regex": r"Zeit:\s*(\d{2}:\d{2}:\d{2})", "required": False},
                {"key": "ANWENDER", "regex": r"Anwender:\s*(\S+)", "required": False},
            ]
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {"ZEIT": "ZEIT", "ANWENDER": "ANWENDER"},
        },
    }
    (root / "rules" / "template.json").write_text(json.dumps(template), encoding="utf-8")

    draft = create_draft_from_template(str(root), "(9101)", "Sparse Template")
    data = load_draft(draft)

    keys = [f["key"] for f in data["extract_rules"]["fields"]]
    assert keys == list(REQUIRED_HEADER_FIELD_KEYS)
    assert all(bool(f.get("required")) for f in data["extract_rules"]["fields"])

    by_key = {f["key"]: f for f in data["extract_rules"]["fields"]}
    assert by_key["ZEIT"]["regex"] == r"Zeit:\s*(\d{2}:\d{2}:\d{2})"
    assert by_key["DATUM"]["regex"] == ""
    assert by_key["PLATTE"]["regex"] == ""
    assert by_key["TEST"]["regex"] == r"Test:[^\n]*?[\\/]([^\\/]+\.asy)\s*\("
    assert by_key["HALTBARKEIT"]["regex"] == ""
    assert set(data["excel_rules"]["column_mapping"].keys()) == set(REQUIRED_HEADER_FIELD_KEYS)


def test_create_draft_from_template_maps_haltbarkeit_legacy_key(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    template = {
        "assay_name": "Template",
        "assay_key": "(0000)",
        "lot_rule": {"regex": r"Lot:\s*(\S+)"},
        "extract_rules": {
            "fields": [
                {"key": "Haltbarkeit", "regex": r"Kit\s+E[0-9A-Za-z]+\s+(\d{6})", "required": False},
            ]
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {"Haltbarkeit": "Haltbarkeit"},
        },
    }
    (root / "rules" / "template.json").write_text(json.dumps(template), encoding="utf-8")

    draft = create_draft_from_template(str(root), "(9102)", "Legacy Haltbarkeit")
    data = load_draft(draft)
    by_key = {f["key"]: f for f in data["extract_rules"]["fields"]}

    assert [f["key"] for f in data["extract_rules"]["fields"]] == list(REQUIRED_HEADER_FIELD_KEYS)
    assert by_key["HALTBARKEIT"]["regex"] == r"Kit\s+E[0-9A-Za-z]+\s+(\d{6})"
    assert by_key["TEST"]["regex"] == r"Test:[^\n]*?[\\/]([^\\/]+\.asy)\s*\("
    assert data["excel_rules"]["column_mapping"]["HALTBARKEIT"] == "Haltbarkeit"


def test_create_draft_from_template_default_test_regex_matches_analyzer_path(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    template = {
        "assay_name": "Template",
        "assay_key": "(0000)",
        "lot_rule": {"regex": r"Lot:\s*(\S+)"},
        "extract_rules": {"fields": []},
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {},
        },
    }
    (root / "rules" / "template.json").write_text(json.dumps(template), encoding="utf-8")

    draft = create_draft_from_template(str(root), "(9106)", "Default Test")
    data = load_draft(draft)
    by_key = {f["key"]: f for f in data["extract_rules"]["fields"]}
    regex = by_key["TEST"]["regex"]
    text = r"Test: C:\ProgramData\Euroimmun_Analyzer_I\Assays\ANA Screen IgG.asy (1c9e)"

    assert regex == r"Test:[^\n]*?[\\/]([^\\/]+\.asy)\s*\("
    assert test_regex(text, regex)["value"] == "ANA Screen IgG.asy"


def test_create_draft_from_template_requires_template_file(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)

    with pytest.raises(RuleSuiteError, match="template_not_found"):
        create_draft_from_template(str(root), "(9100)", "Templated Assay")


def test_check_required_fields_reports_confirmed_and_misses(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    draft = create_draft_from_template(str(root), "(9100)", "Templated Assay")

    text = "\n".join(
        [
            "Datum: 09.07.2026",
            "Zeit: 10:15:00",
            "Anwender: LAB01",
            "Platte: P-12",
            "Test: RUN01",
            "Charge: CH-99",
            "Haltbarkeit: 261208",
            "Validationskriterien erfuellt",
        ]
    )

    report = check_required_fields(draft, text, group=1)
    assert report["total"] == 8
    assert report["all_confirmed"] is True
    assert report["confirmed"] == 8
    by_key = {row["key"]: row for row in report["results"]}
    assert by_key["DATUM"]["status"] == "confirmed"
    assert by_key["DATUM"]["matched"] is True
    assert by_key["VALIDATION"]["search_from"] == {"line": 0}


def test_check_required_fields_confirms_default_test_regex(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    template = {
        "assay_name": "Template",
        "assay_key": "(0000)",
        "lot_rule": {"regex": r"Lot:\s*(\S+)"},
        "extract_rules": {"fields": []},
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {},
        },
    }
    (root / "rules" / "template.json").write_text(json.dumps(template), encoding="utf-8")

    draft = create_draft_from_template(str(root), "(9107)", "Default Test Check")
    text = r"Test: C:\ProgramData\Euroimmun_Analyzer_I\Assays\ANA Screen IgG.asy (1c9e)"

    report = check_required_fields(draft, text, group=1)
    by_key = {row["key"]: row for row in report["results"]}

    assert by_key["TEST"]["status"] == "confirmed"
    assert by_key["TEST"]["value"] == "ANA Screen IgG.asy"


def test_check_required_fields_reports_missing_regex_miss_error_and_missing_field(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    draft = create_draft_from_template(str(root), "(9100)", "Templated Assay")

    update_field(draft, "DATUM", regex="")
    update_field(draft, "ZEIT", regex=r"Zeit:\s*(\d{2}:\d{2}:\d{2})")
    update_field(draft, "ANWENDER", regex=r"(")
    update_field(draft, "PLATTE", regex=r"Platte:\s*(\S+)")
    data = load_draft(draft)
    data["extract_rules"]["fields"] = [
        f for f in data["extract_rules"]["fields"] if f.get("key") != "CHARGE"
    ]
    Path(draft).write_text(json.dumps(data), encoding="utf-8")

    text = "Platte: P-12"
    report = check_required_fields(draft, text, group=1)
    by_key = {row["key"]: row for row in report["results"]}

    assert by_key["DATUM"]["status"] == "missing_regex"
    assert by_key["ZEIT"]["status"] == "miss"
    assert by_key["ANWENDER"]["status"] == "error"
    assert by_key["PLATTE"]["status"] == "confirmed"
    assert by_key["CHARGE"]["status"] == "missing_field"
    assert report["all_confirmed"] is False


def test_check_required_fields_honors_search_from_line(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    draft = create_draft_from_template(str(root), "(9100)", "Templated Assay")
    update_field(draft, "VALIDATION", regex=r"Footer:\s*(\w+)", search_from={"line": 2})

    text = "Header\nMiddle\nFooter: OK"
    report = check_required_fields(draft, text, group=1)
    validation = next(row for row in report["results"] if row["key"] == "VALIDATION")
    assert validation["status"] == "confirmed"
    assert validation["value"] == "OK"


def test_list_rulesets_inventory(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)

    out = list_rulesets(str(root))
    assert [row["assay_key"] for row in out] == ["(1111)", "(2222)"]

    row_a = next(row for row in out if row["assay_key"] == "(1111)")
    assert row_a["ruleset_file"] == "AssayA.json"
    assert row_a["assay_name"] == "Assay A"
    assert row_a["field_count"] == 2
    assert row_a["valid"] is True
    assert row_a["error"] is None

    (root / "rules" / "AssayB.json").unlink()
    out2 = list_rulesets(str(root))
    row_b = next(row for row in out2 if row["assay_key"] == "(2222)")
    assert row_b["error"] == "file_missing"


def test_delete_ruleset_deactivates_to_inactive(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)

    result = delete_ruleset(str(root), "(1111)")
    assert result["ruleset_file"] == "AssayA.json"
    assert result["inactive_path"] is not None

    inactive_file = Path(result["inactive_path"])
    assert inactive_file.exists()
    assert inactive_file.parent == root / "rules" / "inactive"
    assert not (root / "rules" / "AssayA.json").exists()

    index = json.loads((root / "rules" / "index.json").read_text(encoding="utf-8"))
    assert all(row["assay_key"] != "(1111)" for row in index["assays"])
    assert any(row["assay_key"] == "(2222)" for row in index["assays"])

    moved = json.loads(inactive_file.read_text(encoding="utf-8"))
    assert moved["assay_key"] == "(1111)"


def test_deactivate_ruleset_rejects_unknown_and_protected(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)

    with pytest.raises(RuleSuiteError, match="assay_not_found"):
        deactivate_ruleset(str(root), "(9999)")

    index = {"assays": [{"assay_key": "(7777)", "ruleset_file": "template.json"}]}
    (root / "rules" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(RuleSuiteError, match="protected_or_invalid_ruleset_file"):
        deactivate_ruleset(str(root), "(7777)")


def test_resolve_ruleset_rejects_invalid_search_from_marker_regex(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    ruleset_path = root / "rules" / "AssayA.json"
    data = json.loads(ruleset_path.read_text(encoding="utf-8"))
    data["extract_rules"]["fields"][0]["search_from"] = {"after": "("}
    ruleset_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(RuleResolverError, match="search_from.after invalid"):
        resolve_ruleset("(1111)", str(root / "rules"), str(root / "rules" / "index.json"))


def _write_legacy_source_ruleset(root: Path) -> None:
    ruleset = {
        "assay_name": "Legacy Source",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Kit\s+(\S+)\s+\d{6}"},
        "extract_rules": {
            "fields": [
                {"key": "plate_name", "regex": r"Plattenname:\s*(.+?)\s+Zeit:", "required": True},
                {"key": "date", "regex": r"Datum:\s*(\d{2}\.\d{2}\.\d{4})", "required": True},
                {"key": "time", "regex": r"Zeit:\s*(\d{2}:\d{2}:\d{2})", "required": True},
                {"key": "user", "regex": r"Anwender:\s*([^\s]+)", "required": True},
                {"key": "lot_id", "regex": r"Kit\s+(E[0-9A-Za-z]+)\s+\d{6}", "required": True},
                {"key": "test", "regex": r"Test:\s*(.+)", "required": False},
                {"key": "lot_expiry_yymmdd", "regex": r"Kit\s+E[0-9A-Za-z]+\s+(\d{6})", "required": False},
            ],
            "dedupe_fields": ["test"],
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {
                "plate_name": "Plattenname",
                "date": "Datum",
                "time": "Zeit",
                "user": "Anwender",
                "lot_id": "CHARGE",
                "test": "TEST",
                "lot_expiry_yymmdd": "Haltbarkeit",
            },
        },
    }
    (root / "rules" / "AssayA.json").write_text(json.dumps(ruleset), encoding="utf-8")


def test_resolve_required_headers_maps_legacy_keys_to_canonical() -> None:
    fields = [
        {"key": "date", "regex": r"Datum:\s*(\d+)", "required": False},
        {"key": "time", "regex": r"Zeit:\s*(\d+)", "required": False},
        {"key": "test", "regex": r"Test:\s*(\w+)", "required": False},
        {"key": "lot_expiry_yymmdd", "regex": r"Kit\s+(\d{6})", "required": False},
        {"key": "Haltbarkeit", "regex": r"Haltbarkeit:\s*(\d+)", "required": False},
    ]
    col = {
        "date": "Datum",
        "time": "Zeit",
        "test": "TEST",
        "lot_expiry_yymmdd": "Haltbarkeit",
        "Haltbarkeit": "Haltbarkeit",
    }
    out = resolve_required_headers_from_source(fields, col)
    by_key = {f["key"]: f for f in out["fields"]}
    assert [f["key"] for f in out["fields"]] == list(REQUIRED_HEADER_FIELD_KEYS)
    assert by_key["DATUM"]["regex"] == r"Datum:\s*(\d+)"
    assert by_key["ZEIT"]["regex"] == r"Zeit:\s*(\d+)"
    assert by_key["TEST"]["regex"] == r"Test:\s*(\w+)"
    assert by_key["HALTBARKEIT"]["regex"] == r"Kit\s+(\d{6})"
    assert by_key["VALIDATION"]["regex"] == ""
    assert out["column_mapping"]["DATUM"] == "Datum"
    assert out["column_mapping"]["TEST"] == "TEST"
    assert out["column_mapping"]["HALTBARKEIT"] == "Haltbarkeit"


def test_resolve_required_headers_defaults_missing_test_regex() -> None:
    out = resolve_required_headers_from_source([], {})
    by_key = {f["key"]: f for f in out["fields"]}

    assert by_key["TEST"]["regex"] == r"Test:[^\n]*?[\\/]([^\\/]+\.asy)\s*\("
    assert by_key["TEST"]["required"] is True
    assert by_key["HALTBARKEIT"]["regex"] == ""


def test_create_draft_from_ruleset_normalizes_legacy_headers(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_legacy_source_ruleset(root)

    draft = create_draft_from_ruleset(str(root), "(1111)", "(9102)", "Similar Assay")
    data = load_draft(draft)

    keys = [f["key"] for f in data["extract_rules"]["fields"]]
    assert keys == list(REQUIRED_HEADER_FIELD_KEYS)
    assert "date" not in keys
    assert "plate_name" not in keys

    by_key = {f["key"]: f for f in data["extract_rules"]["fields"]}
    assert by_key["DATUM"]["regex"] == r"Datum:\s*(\d{2}\.\d{2}\.\d{4})"
    assert by_key["CHARGE"]["regex"] == r"Kit\s+(E[0-9A-Za-z]+)\s+\d{6}"
    assert by_key["PLATTE"]["regex"] == r"Plattenname:\s*(.+?)\s+Zeit:"
    assert by_key["TEST"]["regex"] == r"Test:\s*(.+)"
    assert by_key["HALTBARKEIT"]["regex"] == r"Kit\s+E[0-9A-Za-z]+\s+(\d{6})"
    assert data["excel_rules"]["column_mapping"]["DATUM"] == "Datum"
    assert data["excel_rules"]["column_mapping"]["CHARGE"] == "CHARGE"
    assert data["extract_rules"]["dedupe_fields"] == []


def test_read_candidate_fields_excludes_headers_and_legacy_aliases(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    _write_legacy_source_ruleset(root)

    template_cands = read_candidate_fields(str(root), source="template")
    template_keys = {f["key"] for f in template_cands["fields"]}
    assert "Haltbarkeit" not in template_keys
    assert "HALTBARKEIT" not in template_keys
    assert "TEST" not in template_keys
    assert "test" not in template_keys
    assert "PCQ1" in template_keys
    assert "DATUM" not in template_keys
    assert "FILE_NAME" in template_keys

    ruleset_cands = read_candidate_fields(str(root), source_assay_key="(1111)")
    ruleset_keys = {f["key"] for f in ruleset_cands["fields"]}
    assert "test" not in ruleset_keys
    assert "lot_expiry_yymmdd" not in ruleset_keys
    assert "date" not in ruleset_keys
    assert LEGACY_HEADER_ALIAS_KEYS.isdisjoint(ruleset_keys)


def test_check_and_adopt_candidate_field(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    draft = create_draft_from_template(str(root), "(9103)", "Blank Assay")
    source = {"source": "template"}

    report = check_candidates(str(root), "PCQ1 42", draft, source)
    by_key = {row["key"]: row for row in report["results"]}
    assert by_key["PCQ1"]["status"] == "confirmed"

    adopt_candidate_field(
        str(root),
        draft,
        "PCQ1",
        source,
        required=True,
        search_from_set=False,
    )
    data = load_draft(draft)
    keys = [f["key"] for f in data["extract_rules"]["fields"]]
    assert "PCQ1" in keys
    pcq = next(f for f in data["extract_rules"]["fields"] if f["key"] == "PCQ1")
    assert pcq["required"] is True
    assert pcq["regex"] == r"PCQ1\s+(\d+)"
    assert data["excel_rules"]["column_mapping"]["PCQ1"] == "PCQ1"

    report2 = check_candidates(str(root), "PCQ1 42", draft, source)
    assert all(row["key"] != "PCQ1" for row in report2["results"])

    with pytest.raises(RuleSuiteError, match="field_exists"):
        adopt_candidate_field(str(root), draft, "PCQ1", source)


def test_adopt_candidate_field_allows_form_overrides(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    draft = create_draft_from_template(str(root), "(9104)", "Override Assay")
    source = {"source": "template"}

    adopt_candidate_field(
        str(root),
        draft,
        "PCQ1",
        source,
        regex=r"PCQ1\s+(\d+)",
        required=True,
        search_from={"line": 3},
        search_from_set=True,
    )
    data = load_draft(draft)
    field = next(f for f in data["extract_rules"]["fields"] if f["key"] == "PCQ1")
    assert field["regex"] == r"PCQ1\s+(\d+)"
    assert field["required"] is True
    assert field["search_from"] == {"line": 3}


def test_check_authoring_readiness_structure_only(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")

    report = check_authoring_readiness(draft, assay_text=None)
    assert report["ok"] is True
    assert report["structural_errors"] == []
    assert report["required_field_status"] is None
    assert report["missing_required"] == []
    assert any("no_assay_text" in w for w in report["warnings"])


def test_check_authoring_readiness_with_assay_text_all_confirmed(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    draft = create_draft_from_template(str(root), "(9100)", "Templated Assay")
    text = "\n".join(
        [
            "Datum: 09.07.2026",
            "Zeit: 10:15:00",
            "Anwender: LAB01",
            "Platte: P-12",
            "Test: RUN01",
            "Charge: CH-99",
            "Haltbarkeit: 261208",
            "Validationskriterien erfuellt",
        ]
    )

    report = check_authoring_readiness(draft, text)
    assert report["ok"] is True
    assert report["structural_errors"] == []
    assert report["required_field_status"]["all_confirmed"] is True
    assert report["missing_required"] == []
    assert report["warnings"] == []


def test_check_authoring_readiness_with_assay_text_missing_required(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    draft = create_draft_from_template(str(root), "(9100)", "Templated Assay")
    text = "Datum: 09.07.2026"

    report = check_authoring_readiness(draft, text)
    assert report["ok"] is False
    assert report["structural_errors"] == []
    assert "DATUM" not in report["missing_required"]
    assert len(report["missing_required"]) >= 1


def test_preview_extract_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")

    class _Record:
        lot_id = "LOT1"
        dedupe_key = "(1111)|LOT1|ABC"
        data = {"test": "ABC"}

    def _fake_get_assay_text(self, project_root, pdf_path, assay_key, assay_name, draft_path=None):
        return {
            "detected_assays": [assay_key],
            "assay_block": "Test: ABC\nLot: LOT1",
        }

    monkeypatch.setattr("src.rulesuite.rulesuite.RuleSuite.get_assay_text", _fake_get_assay_text)
    monkeypatch.setattr(
        "src.rulesuite.rulesuite.extract_record",
        lambda assay_block, ruleset: _Record(),
    )

    out = preview_extract(str(root), "dummy.pdf", "(1111)", draft_path=draft)
    assert set(out.keys()) == {
        "pdf_path",
        "assay_key",
        "detected_assays",
        "used_ruleset",
        "lot_id",
        "dedupe_key",
        "device_id",
        "dedupe_version",
        "dedupe_basis",
        "data",
    }
    assert out["pdf_path"] == "dummy.pdf"
    assert out["assay_key"] == "(1111)"
    assert out["detected_assays"] == ["(1111)"]
    assert out["lot_id"] == "LOT1"
    assert out["dedupe_key"] == "(1111)|LOT1|ABC"
    assert out["data"] == {"test": "ABC"}
    assert Path(str(out["used_ruleset"])).exists() or str(out["used_ruleset"]).endswith(".json")


def test_activate_draft_overwrites_valid_draft(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    set_field_regex(draft, "test", r"Test:\s*(UPDATED)")

    target = activate_draft(str(root), "(1111)", draft)
    data = json.loads(Path(target).read_text(encoding="utf-8"))
    field = next(f for f in data["extract_rules"]["fields"] if f["key"] == "test")
    assert field["regex"] == r"Test:\s*(UPDATED)"


def test_draft_path_for_assay_returns_path_without_creating_file(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    path = draft_path_for_assay(str(root), "(abcd)")

    assert path.endswith("rules\\drafts\\abcd.draft.json") or path.endswith("rules/drafts/abcd.draft.json")
    assert not Path(path).exists()


def test_create_draft_from_template_if_missing_creates_header_draft(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)

    result = create_draft_from_template_if_missing(str(root), "(abcd)", "New Assay")

    assert result["status"] == "created"
    assert Path(result["draft_path"]).exists()
    data = load_draft(result["draft_path"])
    keys = [field["key"] for field in data["extract_rules"]["fields"]]
    assert keys == list(REQUIRED_HEADER_FIELD_KEYS)
    assert all(bool(field.get("required")) for field in data["extract_rules"]["fields"])


def test_create_draft_from_template_if_missing_does_not_overwrite_existing(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    first = create_draft_from_template_if_missing(str(root), "(abcd)", "First Name")
    Path(first["draft_path"]).write_text('{"marker": true}', encoding="utf-8")

    second = create_draft_from_template_if_missing(str(root), "(abcd)", "Second Name")

    assert first["draft_path"] == second["draft_path"]
    assert second["status"] == "exists"
    assert json.loads(Path(second["draft_path"]).read_text(encoding="utf-8")) == {"marker": True}


def _write_source_ruleset_with_extra_fields(root: Path) -> None:
    ruleset = {
        "assay_name": "Source Assay",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Lot:\s*(\S+)"},
        "extract_rules": {
            "fields": [
                {"key": "DATUM", "regex": r"Datum:\s*(\S+)", "required": True},
                {"key": "PCQ1", "regex": r"PCQ1\s+(\d+)", "required": True, "search_from": {"line": 3}},
                {"key": "S1", "regex": r"S1\s+(\d+)", "required": False},
            ],
            "dedupe_fields": [],
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {
                "DATUM": "DATUM",
                "PCQ1": "PCQ1 Column",
                "S1": "S1",
            },
        },
    }
    (root / "rules" / "AssayA.json").write_text(json.dumps(ruleset), encoding="utf-8")


def test_adopt_candidate_fields_copies_non_header_fields_and_skips_existing(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    _write_source_ruleset_with_extra_fields(root)
    draft = create_draft_from_template(str(root), "(9999)", "Target Draft")
    source = {"source_assay_key": "(1111)"}

    result = adopt_candidate_fields(str(root), draft, source)

    assert result["adopted"] == ["PCQ1", "S1"]
    assert result["skipped_existing"] == []
    assert result["missing"] == []
    assert result["source"] == {"source_assay_key": "(1111)"}

    data = load_draft(draft)
    keys = [field["key"] for field in data["extract_rules"]["fields"]]
    assert "DATUM" not in keys[8:]  # no extra DATUM from source
    pcq = next(field for field in data["extract_rules"]["fields"] if field["key"] == "PCQ1")
    assert pcq["regex"] == r"PCQ1\s+(\d+)"
    assert pcq["required"] is True
    assert pcq["search_from"] == {"line": 3}
    assert data["excel_rules"]["column_mapping"]["PCQ1"] == "PCQ1 Column"

    result2 = adopt_candidate_fields(str(root), draft, source)
    assert result2["adopted"] == []
    assert set(result2["skipped_existing"]) == {"PCQ1", "S1"}


def test_adopt_candidate_fields_honors_field_keys_and_missing(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    _write_source_ruleset_with_extra_fields(root)
    draft = create_draft_from_template(str(root), "(9998)", "Target Draft")
    source = {"source_assay_key": "(1111)"}

    result = adopt_candidate_fields(str(root), draft, source, field_keys=["S1", "MISSING"])

    assert result["adopted"] == ["S1"]
    assert result["missing"] == ["MISSING"]


def test_adopt_candidate_fields_skipped_existing_leaves_field_and_mapping_unchanged(
    tmp_path: Path,
) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    _write_source_ruleset_with_extra_fields(root)
    draft = create_draft_from_template(str(root), "(9997)", "Target Draft")
    source = {"source_assay_key": "(1111)"}

    data = load_draft(draft)
    data["extract_rules"]["fields"].append(
        {
            "key": "PCQ1",
            "regex": r"Custom\s+PCQ1\s+(\d+)",
            "required": False,
            "search_from": {"line": 9},
        }
    )
    data["excel_rules"]["column_mapping"]["PCQ1"] = "Custom PCQ1 Header"
    save_draft(draft, data)
    before = load_draft(draft)

    result = adopt_candidate_fields(str(root), draft, source)

    assert result["adopted"] == ["S1"]
    assert result["skipped_existing"] == ["PCQ1"]
    after = load_draft(draft)
    before_pcq = next(field for field in before["extract_rules"]["fields"] if field["key"] == "PCQ1")
    after_pcq = next(field for field in after["extract_rules"]["fields"] if field["key"] == "PCQ1")
    assert after_pcq == before_pcq
    assert after["excel_rules"]["column_mapping"]["PCQ1"] == "Custom PCQ1 Header"


def test_list_rulesuite_inventory_lists_active_and_drafts(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    draft = create_draft_from_template(str(root), "(9996)", "Draft Assay")
    save_draft(draft, load_draft(draft))

    rows = list_rulesuite_inventory(str(root), kind="all")
    kinds = {(row["kind"], row["assay_key"]) for row in rows}

    assert ("active", "(1111)") in kinds
    assert ("active", "(2222)") in kinds
    assert ("draft", "(9996)") in kinds


def test_list_rulesuite_inventory_filters_and_tolerates_broken_draft(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft_dir = root / "rules" / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "broken.draft.json").write_text("{not-json", encoding="utf-8")

    active_rows = list_rulesuite_inventory(str(root), kind="active")
    draft_rows = list_rulesuite_inventory(str(root), kind="draft")

    assert all(row["kind"] == "active" for row in active_rows)
    assert len(draft_rows) == 1
    assert draft_rows[0]["valid"] is False
    assert draft_rows[0]["error"]


def _write_clone_source_ruleset(root: Path) -> None:
    ruleset = {
        "assay_name": "Source Assay",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Lot:\s*(\S+)"},
        "extract_rules": {
            "fields": [
                {"key": "DATUM", "regex": r"Datum:\s*(\S+)", "required": True},
                {"key": "PCQ1", "regex": r"PCQ1\s+(\d+)", "required": True, "search_from": {"line": 2}},
            ],
            "dedupe_fields": [],
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {"DATUM": "DATUM", "PCQ1": "PCQ1 Column"},
        },
    }
    (root / "rules" / "AssayA.json").write_text(json.dumps(ruleset), encoding="utf-8")


def test_clone_ruleset_to_draft_created_and_exists_without_overwrite(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    _write_clone_source_ruleset(root)
    index_before = (root / "rules" / "index.json").read_text(encoding="utf-8")

    created = clone_ruleset_to_draft(str(root), "(1111)", "(abcd)", "Clone Target", include_fields=True)
    assert created["status"] == "created"
    assert Path(created["draft_path"]).exists()
    data = load_draft(created["draft_path"])
    assert data["assay_key"] == "(abcd)"
    assert data["assay_name"] == "Clone Target"
    assert "PCQ1" in {field["key"] for field in data["extract_rules"]["fields"]}
    assert data["excel_rules"]["column_mapping"]["PCQ1"] == "PCQ1 Column"
    assert (root / "rules" / "index.json").read_text(encoding="utf-8") == index_before

    Path(created["draft_path"]).write_text('{"marker": true}', encoding="utf-8")
    exists = clone_ruleset_to_draft(str(root), "(1111)", "(abcd)", "Clone Target", overwrite=False)
    assert exists["status"] == "exists"
    assert json.loads(Path(exists["draft_path"]).read_text(encoding="utf-8")) == {"marker": True}


def test_clone_ruleset_to_draft_overwrite_and_include_fields_toggle(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    _write_clone_source_ruleset(root)
    target = Path(draft_path_for_assay(str(root), "(abcd)"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"marker": true}', encoding="utf-8")

    overwritten = clone_ruleset_to_draft(
        str(root),
        "(1111)",
        "(abcd)",
        "Target Name",
        overwrite=True,
        include_fields=True,
    )
    assert overwritten["status"] == "overwritten"
    full = load_draft(overwritten["draft_path"])
    assert full["assay_name"] == "Target Name"
    assert "PCQ1" in {field["key"] for field in full["extract_rules"]["fields"]}

    headers_only = clone_ruleset_to_draft(
        str(root),
        "(1111)",
        "(abce)",
        "Headers Only",
        overwrite=False,
        include_fields=False,
    )
    assert headers_only["status"] == "created"
    header_data = load_draft(headers_only["draft_path"])
    extra_keys = {
        field["key"]
        for field in header_data["extract_rules"]["fields"]
        if field["key"] not in REQUIRED_HEADER_FIELD_KEYS
    }
    assert extra_keys == set()


def test_clone_ruleset_to_draft_overwrite_keeps_target_key_and_name(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    _write_clone_source_ruleset(root)

    target_path = Path(draft_path_for_assay(str(root), "(9999)"))
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(
            {
                "assay_name": "Old Draft Name",
                "assay_key": "(1111)",
                "lot_rule": {"regex": ""},
                "extract_rules": {"fields": [], "dedupe_fields": []},
                "excel_rules": {
                    "excel_filename_template": "{assay_name}.xlsx",
                    "sheetname_template": "{lot_id}",
                    "column_mapping": {},
                },
            }
        ),
        encoding="utf-8",
    )

    result = clone_ruleset_to_draft(
        str(root),
        "(1111)",
        "(9999)",
        "Distinct Target Name",
        overwrite=True,
        include_fields=False,
    )

    assert result["status"] == "overwritten"
    assert result["source_assay_key"] == "(1111)"
    assert result["target_assay_key"] == "(9999)"
    assert result["target_assay_name"] == "Distinct Target Name"

    data = load_draft(str(target_path))
    assert data["assay_key"] == "(9999)"
    assert data["assay_name"] == "Distinct Target Name"
    assert data["assay_key"] != "(1111)"
    assert data["assay_name"] != "Source Assay"


def test_list_rulesuite_inventory_includes_inactive_and_filter(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    inactive_dir = root / "rules" / "inactive"
    inactive_dir.mkdir(parents=True, exist_ok=True)
    inactive_path = inactive_dir / "AssayA.20260101.json"
    inactive_path.write_text((root / "rules" / "AssayA.json").read_text(encoding="utf-8"), encoding="utf-8")
    (inactive_dir / "broken.json").write_text("{bad", encoding="utf-8")

    rows = list_rulesuite_inventory(str(root), kind="inactive")
    assert len(rows) == 2
    assert all(row["kind"] == "inactive" for row in rows)
    assert all(row["display_type"] == "Inaktiv" for row in rows)
    broken = next(row for row in rows if row["path"].endswith("broken.json"))
    assert broken["valid"] is False
    assert broken["error"]


def test_delete_inventory_item_moves_draft_and_inactive_without_index_change(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft_dir = root / "rules" / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / "test.draft.json"
    draft_path.write_text('{"assay_key":"(d1)","assay_name":"D1"}', encoding="utf-8")
    inactive_dir = root / "rules" / "inactive"
    inactive_dir.mkdir(parents=True, exist_ok=True)
    inactive_path = inactive_dir / "old.json"
    inactive_path.write_text('{"assay_key":"(i1)","assay_name":"I1"}', encoding="utf-8")
    index_before = (root / "rules" / "index.json").read_text(encoding="utf-8")

    draft_result = delete_inventory_item(str(root), "draft", str(draft_path))
    inactive_result = delete_inventory_item(str(root), "inactive", str(inactive_path))

    assert Path(draft_result["trash_path"]).exists()
    assert Path(inactive_result["trash_path"]).exists()
    assert not draft_path.exists()
    assert not inactive_path.exists()
    assert (root / "rules" / "index.json").read_text(encoding="utf-8") == index_before

    with pytest.raises(RuleSuiteError, match="active_must_be_deactivated_first"):
        delete_inventory_item(str(root), "active", str(root / "rules" / "AssayA.json"))


def test_open_inactive_as_draft_copies_to_drafts_without_overwrite(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    inactive_dir = root / "rules" / "inactive"
    inactive_dir.mkdir(parents=True, exist_ok=True)
    inactive_path = inactive_dir / "AssayA.20260101.json"
    payload = json.loads((root / "rules" / "AssayA.json").read_text(encoding="utf-8"))
    inactive_path.write_text(json.dumps(payload), encoding="utf-8")

    created = open_inactive_as_draft(str(root), str(inactive_path))
    assert created["status"] == "created"
    draft_path = Path(created["draft_path"])
    assert draft_path.exists()
    assert json.loads(draft_path.read_text(encoding="utf-8"))["assay_key"] == "(1111)"

    draft_path.write_text('{"marker": true}', encoding="utf-8")
    exists = open_inactive_as_draft(str(root), str(inactive_path))
    assert exists["status"] == "exists"
    assert json.loads(draft_path.read_text(encoding="utf-8")) == {"marker": True}
