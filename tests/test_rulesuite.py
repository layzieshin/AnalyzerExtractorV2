import json
from pathlib import Path

import pytest

from src.rulesuite.api import (
    AuthoringReadinessError,
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
    create_authoring_proof,
    create_draft,
    create_draft_from_ruleset,
    create_draft_from_template,
    create_draft_from_template_if_missing,
    deactivate_ruleset,
    delete_inventory_item,
    delete_never_active_ruleset,
    delete_ruleset,
    diff_draft_vs_active,
    draft_content_revision,
    draft_path_for_assay,
    duplicate_field,
    derive_draft,
    get_assay_text,
    list_fields,
    list_rulesets,
    list_rulesuite_inventory,
    load_draft,
    locate_fields,
    open_active_as_draft,
    open_history_as_draft,
    open_inactive_as_draft,
    move_field,
    preview_extract,
    read_candidate_fields,
    remove_field,
    rename_field,
    replace_field,
    REQUIRED_HEADER_FIELD_KEYS,
    restore_draft_snapshot,
    save_draft,
    set_dedupe_fields,
    set_excel_rules,
    set_field_regex,
    set_lot_rule,
    sync_column_mapping_from_fields,
    test_regex,
    update_draft_meta,
    update_field,
    validate_draft,
    verify_authoring_proof,
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


def _fake_authoring_preview(
    _self,
    _project_root: str,
    pdf_path: str,
    _assay_key: str,
    draft_path: str | None = None,
) -> dict:
    if Path(pdf_path).name == "failing.pdf":
        assert draft_path is not None
        return {"lot_id": "LOT-NEW", "data": {"test": "NEW", "date": "2026-09-25", "added": "X"}}
    if draft_path is None:
        return {"lot_id": "LOT-REF", "data": {"test": "BASE", "date": "2026-09-20"}}
    return {
        "lot_id": "LOT-REF",
        "data": {"test": "BASE", "date": "2026-09-20", "added": "NONEMPTY"},
    }


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


def test_add_field_writes_mapping_and_dedupe_atomically(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9001)", "Add Atomic")
    before = json.loads(Path(draft).read_text(encoding="utf-8"))
    vendor = {"keep": True}
    before["vendor_extension"] = vendor
    Path(draft).write_text(json.dumps(before), encoding="utf-8")

    add_field(
        draft,
        "gamma",
        r"G:\s*(\w+)",
        required=False,
        search_from={"after": "HEAD"},
        excel_column="GAMMA",
        dedupe_member=True,
    )
    data = load_draft(draft)
    assert data["extract_rules"]["fields"][-1]["key"] == "gamma"
    assert data["extract_rules"]["fields"][-1]["search_from"] == {"after": "HEAD"}
    assert data["excel_rules"]["column_mapping"]["gamma"] == "GAMMA"
    assert data["extract_rules"]["dedupe_fields"] == ["gamma"]
    assert data["vendor_extension"] == vendor


def test_add_field_defaults_keep_mapping_key_and_skip_dedupe(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9002)", "Add Default")
    payload = load_draft(draft)
    payload["extract_rules"]["dedupe_fields"] = ["existing"]
    save_draft(draft, payload)

    add_field(draft, "delta", r"D:\s*(\w+)")
    data = load_draft(draft)
    assert data["excel_rules"]["column_mapping"]["delta"] == "delta"
    assert data["extract_rules"]["dedupe_fields"] == ["existing"]


def test_add_field_invalid_input_and_write_failure_keep_exact_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.rulesuite as rulesuite

    root = _setup_project(tmp_path)
    draft = Path(create_blank_draft(str(root), "(9003)", "Add Bytes"))
    original = draft.read_bytes()

    with pytest.raises(RuleSuiteError, match="invalid_regex"):
        add_field(str(draft), "bad", r"[", excel_column="BAD", dedupe_member=True)
    assert draft.read_bytes() == original

    with pytest.raises(RuleSuiteError, match="invalid_excel_column"):
        add_field(str(draft), "bad", r"B:\s*(\w+)", excel_column="  ")
    assert draft.read_bytes() == original

    with pytest.raises(RuleSuiteError, match="invalid_dedupe_member"):
        add_field(str(draft), "bad", r"B:\s*(\w+)", dedupe_member="yes")  # type: ignore[arg-type]
    assert draft.read_bytes() == original

    def _fail_before_replace(_target: Path, _data: dict) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(rulesuite, "_write_json_atomic", _fail_before_replace)
    with pytest.raises(RuleSuiteError, match="draft_add_failed"):
        add_field(str(draft), "bad", r"B:\s*(\w+)", excel_column="BAD", dedupe_member=False)
    assert draft.read_bytes() == original

    def _foreign_write(target: Path, _data: dict) -> None:
        target.write_bytes(b"foreign-bytes")
        raise OSError("uncooperative writer")

    monkeypatch.setattr(rulesuite, "_write_json_atomic", _foreign_write)
    with pytest.raises(RuleSuiteError, match="draft_add_failed"):
        add_field(str(draft), "bad", r"B:\s*(\w+)", excel_column="BAD", dedupe_member=False)
    assert draft.read_bytes() == b"foreign-bytes"


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
    draft = Path(create_blank_draft(str(root), "(9000)", "Test Assay"))

    missing = load_draft(str(draft))
    missing["excel_rules"].pop("column_mapping", None)
    save_draft(str(draft), missing)
    add_field(str(draft), "alpha", r"A:(\w+)", required=False)
    updated = load_draft(str(draft))
    assert updated["excel_rules"]["column_mapping"]["alpha"] == "alpha"

    none_mapping = load_draft(str(draft))
    none_mapping["excel_rules"]["column_mapping"] = None
    save_draft(str(draft), none_mapping)
    add_field(str(draft), "beta", r"B:(\w+)", required=False)
    updated = load_draft(str(draft))
    assert updated["excel_rules"]["column_mapping"]["beta"] == "beta"
    assert "alpha" not in updated["excel_rules"]["column_mapping"]

    invalid = load_draft(str(draft))
    invalid["excel_rules"]["column_mapping"] = "not-a-dict"
    save_draft(str(draft), invalid)
    original = draft.read_bytes()
    with pytest.raises(RuleSuiteError, match="column_mapping must be object"):
        add_field(str(draft), "gamma", r"G:(\w+)", required=False)
    assert draft.read_bytes() == original

    malformed_fields = load_draft(str(draft))
    malformed_fields["excel_rules"]["column_mapping"] = {"alpha": "alpha"}
    malformed_fields["extract_rules"]["fields"] = ["not-a-field"]
    save_draft(str(draft), malformed_fields)
    original = draft.read_bytes()
    with pytest.raises(RuleSuiteError, match="malformed_fields"):
        add_field(str(draft), "gamma", r"G:(\w+)", required=False)
    assert draft.read_bytes() == original

    malformed_dedupe = load_draft(str(draft))
    malformed_dedupe["extract_rules"]["fields"] = []
    malformed_dedupe["extract_rules"]["dedupe_fields"] = [{"bad": True}]
    save_draft(str(draft), malformed_dedupe)
    original = draft.read_bytes()
    with pytest.raises(RuleSuiteError, match="malformed_dedupe_fields"):
        add_field(str(draft), "gamma", r"G:(\w+)", required=False)
    assert draft.read_bytes() == original

    with pytest.raises(RuleSuiteError, match="invalid_required"):
        add_field(str(draft), "gamma", r"G:(\w+)", required="false")  # type: ignore[arg-type]
    assert draft.read_bytes() == original


def test_draft_lock_allows_one_writer_and_releases(tmp_path: Path) -> None:
    import threading

    from src.rulesuite.lifecycle import rulesuite_draft_lock

    root = _setup_project(tmp_path)
    draft = Path(create_blank_draft(str(root), "(9010)", "Lock"))
    started = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def _hold() -> None:
        try:
            with rulesuite_draft_lock(draft):
                started.set()
                release.wait(2)
        except BaseException as exc:
            errors.append(exc)

    holder = threading.Thread(target=_hold)
    holder.start()
    assert started.wait(2)
    with pytest.raises(RuleSuiteError, match="draft_lock_busy"):
        add_field(str(draft), "alpha", r"A:(\w+)", required=False)
    assert json.loads(draft.read_text(encoding="utf-8"))["extract_rules"]["fields"] == []
    release.set()
    holder.join(2)
    assert errors == []
    assert not list(draft.parent.glob("*.lock"))
    assert not list(draft.parent.glob("*.tmp"))
    add_field(str(draft), "alpha", r"A:(\w+)", required=False)
    assert load_draft(str(draft))["extract_rules"]["fields"][-1]["key"] == "alpha"


def test_update_draft_meta_preserves_unknowns_and_lock(tmp_path: Path) -> None:
    import threading

    from src.rulesuite.lifecycle import rulesuite_draft_lock

    root = _setup_project(tmp_path)
    draft = Path(create_blank_draft(str(root), "(9011)", "Meta"))
    payload = load_draft(str(draft))
    payload["vendor_extension"] = {"keep": True}
    payload["lot_rule"]["note"] = "keep-lot"
    payload["excel_rules"]["column_mapping"] = {"known": "KNOWN"}
    payload["excel_rules"]["extra_excel"] = "keep"
    payload["extract_rules"]["dedupe_fields"] = ["known"]
    payload["extract_rules"]["custom_rule"] = {"mode": "strict"}
    save_draft(str(draft), payload)
    original = draft.read_bytes()

    update_draft_meta(
        str(draft),
        assay_key="(9011)",
        assay_name="Neu",
        lot_regex="LOT-9",
        excel_filename_template="neu.xlsx",
        sheetname_template="blatt",
    )
    data = load_draft(str(draft))
    assert data["assay_name"] == "Neu"
    assert data["lot_rule"] == {"regex": "LOT-9", "note": "keep-lot"}
    assert data["excel_rules"]["column_mapping"] == {"known": "KNOWN"}
    assert data["excel_rules"]["extra_excel"] == "keep"
    assert data["extract_rules"]["dedupe_fields"] == ["known"]
    assert data["extract_rules"]["custom_rule"] == {"mode": "strict"}
    assert data["vendor_extension"] == {"keep": True}

    started = threading.Event()
    release = threading.Event()

    def _hold() -> None:
        with rulesuite_draft_lock(draft):
            started.set()
            release.wait(2)

    holder = threading.Thread(target=_hold)
    holder.start()
    assert started.wait(2)
    before = draft.read_bytes()
    with pytest.raises(RuleSuiteError, match="draft_lock_busy"):
        update_draft_meta(
            str(draft),
            assay_key="(9011)",
            assay_name="Blocked",
            lot_regex="LOT-X",
            excel_filename_template="x.xlsx",
            sheetname_template="x",
        )
    assert draft.read_bytes() == before
    release.set()
    holder.join(2)

    payload = load_draft(str(draft))
    payload["excel_rules"] = "bad"
    save_draft(str(draft), payload)
    blocked = draft.read_bytes()
    with pytest.raises(RuleSuiteError, match="excel_rules must be object"):
        update_draft_meta(
            str(draft),
            assay_key="(9011)",
            assay_name="Neu",
            lot_regex="LOT-9",
            excel_filename_template="neu.xlsx",
            sheetname_template="blatt",
        )
    assert draft.read_bytes() == blocked
    assert original != blocked


def test_restore_draft_snapshot_is_locked(tmp_path: Path) -> None:
    import threading

    from src.rulesuite.lifecycle import rulesuite_draft_lock

    root = _setup_project(tmp_path)
    draft = Path(create_blank_draft(str(root), "(9012)", "Restore"))
    snapshot = load_draft(str(draft))
    add_field(str(draft), "alpha", r"A:(\w+)", required=False)
    current_revision = draft_content_revision(str(draft))
    restore_draft_snapshot(str(draft), snapshot, expected_revision=current_revision)
    assert load_draft(str(draft))["extract_rules"]["fields"] == []

    started = threading.Event()
    release = threading.Event()

    def _hold() -> None:
        with rulesuite_draft_lock(draft):
            started.set()
            release.wait(2)

    holder = threading.Thread(target=_hold)
    holder.start()
    assert started.wait(2)
    before = draft.read_bytes()
    with pytest.raises(RuleSuiteError, match="draft_lock_busy"):
        restore_draft_snapshot(str(draft), snapshot, expected_revision="a" * 64)
    assert draft.read_bytes() == before
    release.set()
    holder.join(2)


def test_receipt_undo_keeps_foreign_commit_and_restore_is_revision_bound(tmp_path: Path) -> None:
    import hashlib

    root = _setup_project(tmp_path)
    draft = Path(create_blank_draft(str(root), "(9013)", "Receipt"))
    observed = load_draft(str(draft))
    add_field(str(draft), "beta", r"B:(\w+)", required=False)
    bytes_after_b = draft.read_bytes()
    revision_after_b = hashlib.sha256(bytes_after_b).hexdigest()

    receipt = add_field(str(draft), "alpha", r"A:(\w+)", required=False, return_receipt=True)
    assert isinstance(receipt, dict)
    assert [row["key"] for row in receipt["before"]["extract_rules"]["fields"]] == ["beta"]
    assert receipt["before"] != observed
    assert receipt["before_revision"] == revision_after_b
    assert receipt["after_revision"] == hashlib.sha256(draft.read_bytes()).hexdigest()
    assert receipt["after_revision"] == draft_content_revision(str(draft))
    path_only = Path(create_blank_draft(str(root), "(9017)", "Path"))
    assert isinstance(add_field(str(path_only), "gamma", r"G:(\w+)", required=False), str)

    undone = restore_draft_snapshot(
        str(draft),
        receipt["before"],
        expected_revision=receipt["after_revision"],
        return_receipt=True,
    )
    assert isinstance(undone, dict)
    assert [row["key"] for row in load_draft(str(draft))["extract_rules"]["fields"]] == ["beta"]
    assert load_draft(str(draft)) != observed

    conflict = Path(create_blank_draft(str(root), "(9014)", "Conflict"))
    added = add_field(str(conflict), "alpha", r"A:(\w+)", required=False, return_receipt=True)
    assert isinstance(added, dict)
    undo_stack = [{"snapshot": added["before"], "expected_revision": added["after_revision"]}]
    redo_stack: list[dict] = []
    foreign = load_draft(str(conflict))
    foreign["extract_rules"]["fields"].append({"key": "foreign", "regex": r"F:(\w+)", "required": False})
    save_draft(str(conflict), foreign)
    foreign_bytes = conflict.read_bytes()
    with pytest.raises(RuleSuiteError, match="draft_revision_conflict"):
        restore_draft_snapshot(
            str(conflict),
            undo_stack[-1]["snapshot"],
            expected_revision=undo_stack[-1]["expected_revision"],
            return_receipt=True,
        )
    assert conflict.read_bytes() == foreign_bytes
    assert undo_stack[0]["expected_revision"] == added["after_revision"]
    assert redo_stack == []

    blank = Path(create_blank_draft(str(root), "(9016)", "Roundtrip"))
    base = load_draft(str(blank))
    added_round = add_field(str(blank), "alpha", r"A:(\w+)", required=False, return_receipt=True)
    assert isinstance(added_round, dict)
    undone_round = restore_draft_snapshot(
        str(blank),
        added_round["before"],
        expected_revision=added_round["after_revision"],
        return_receipt=True,
    )
    assert isinstance(undone_round, dict)
    assert load_draft(str(blank))["extract_rules"]["fields"] == []
    assert undone_round["after_revision"] == hashlib.sha256(blank.read_bytes()).hexdigest()
    assert [row["key"] for row in undone_round["before"]["extract_rules"]["fields"]] == ["alpha"]
    redone = restore_draft_snapshot(
        str(blank),
        undone_round["before"],
        expected_revision=undone_round["after_revision"],
        return_receipt=True,
    )
    assert isinstance(redone, dict)
    assert [row["key"] for row in load_draft(str(blank))["extract_rules"]["fields"]] == ["alpha"]
    assert redone["after_revision"] == hashlib.sha256(blank.read_bytes()).hexdigest()
    assert redone["before_revision"] == undone_round["after_revision"]
    assert base["assay_key"] == "(9016)"

    untouched = blank.read_bytes()
    with pytest.raises(RuleSuiteError, match="draft_restore_revision_required"):
        restore_draft_snapshot(str(blank), base)
    assert blank.read_bytes() == untouched


def test_meta_receipt_is_locked_before_and_push_false_returns_path(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = Path(create_blank_draft(str(root), "(9015)", "MetaReceipt"))
    stale = load_draft(str(draft))
    add_field(str(draft), "beta", r"B:(\w+)", required=False)
    receipt = update_draft_meta(
        str(draft),
        assay_key="(9015)",
        assay_name="Nachher",
        lot_regex="LOT-9",
        excel_filename_template="neu.xlsx",
        sheetname_template="blatt",
        return_receipt=True,
    )
    assert isinstance(receipt, dict)
    assert any(row["key"] == "beta" for row in receipt["before"]["extract_rules"]["fields"])
    assert receipt["before"] != stale
    assert receipt["after_revision"] == draft_content_revision(str(draft))
    path = update_draft_meta(
        str(draft),
        assay_key="(9015)",
        assay_name="Still",
        lot_regex="LOT-9",
        excel_filename_template="neu.xlsx",
        sheetname_template="blatt",
    )
    assert path == str(draft)


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


def test_existing_rule_authoring_proof_binds_draft_and_two_distinct_pdfs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    failing_pdf = root / "failing.pdf"
    reference_pdf = root / "reference.pdf"
    failing_pdf.write_bytes(b"failing-pdf")
    reference_pdf.write_bytes(b"known-good-reference")
    monkeypatch.setattr("src.rulesuite.rulesuite.RuleSuite.preview_extract", _fake_authoring_preview)

    proof = create_authoring_proof(
        str(root),
        "(1111)",
        draft,
        str(failing_pdf),
        str(reference_pdf),
    )

    assert proof["mode"] == "update"
    assert proof["compared_fields"] == ["test", "date"]
    assert proof["draft_sha256"]
    assert proof["failing_pdf_sha256"]
    assert proof["reference_pdf_sha256"]
    assert proof["active_ruleset_sha256"]
    sidecar = Path(draft + ".readiness")
    assert sidecar.is_file()
    assert not sidecar.name.endswith(".draft.json")
    draft_inventory = list_rulesuite_inventory(str(root), kind="draft")
    assert [Path(row["path"]) for row in draft_inventory] == [Path(draft)]
    assert verify_authoring_proof(str(root), "(1111)", draft)["ok"] is True

    failing_pdf.write_bytes(b"changed-failing-pdf")
    changed_pdf = verify_authoring_proof(str(root), "(1111)", draft)
    assert "authoring_proof_failing_pdf_changed" in changed_pdf["errors"]

    create_authoring_proof(str(root), "(1111)", draft, str(failing_pdf), str(reference_pdf))
    Path(draft).write_bytes(Path(draft).read_bytes() + b"\n")
    changed_draft = verify_authoring_proof(str(root), "(1111)", draft)
    assert "authoring_proof_draft_changed" in changed_draft["errors"]

    Path(proof["active_ruleset_path"]).write_bytes(Path(proof["active_ruleset_path"]).read_bytes() + b"\n")
    changed_active = verify_authoring_proof(str(root), "(1111)", draft)
    assert "authoring_proof_active_ruleset_changed" in changed_active["errors"]


def test_existing_rule_authoring_proof_requires_distinct_reference_and_exact_baseline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    failing_pdf = root / "failing.pdf"
    reference_pdf = root / "reference.pdf"
    failing_pdf.write_bytes(b"same")
    reference_pdf.write_bytes(b"same")
    monkeypatch.setattr("src.rulesuite.rulesuite.RuleSuite.preview_extract", _fake_authoring_preview)

    with pytest.raises(AuthoringReadinessError, match="reference_must_differ"):
        create_authoring_proof(str(root), "(1111)", draft, str(failing_pdf), str(reference_pdf))

    reference_pdf.write_bytes(b"different")

    def _mismatching_preview(
        self,
        project_root: str,
        pdf_path: str,
        assay_key: str,
        draft_path: str | None = None,
    ) -> dict:
        result = _fake_authoring_preview(self, project_root, pdf_path, assay_key, draft_path)
        if Path(pdf_path).name == "reference.pdf" and draft_path is not None:
            result["data"]["date"] = "CHANGED"
            result["lot_id"] = "CHANGED-LOT"
        return result

    monkeypatch.setattr("src.rulesuite.rulesuite.RuleSuite.preview_extract", _mismatching_preview)
    with pytest.raises(AuthoringReadinessError, match=r"reference_mismatch: date,lot_id"):
        create_authoring_proof(str(root), "(1111)", draft, str(failing_pdf), str(reference_pdf))
    assert verify_authoring_proof(str(root), "(1111)", draft)["errors"] == [
        "authoring_proof_not_ready"
    ]


def test_new_rule_authoring_proof_needs_only_example_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9000)", "Fresh Assay")
    set_lot_rule(draft, r"Lot:\s*(\w+)")
    add_field(draft, "test", r"Test:\s*(\w+)", required=True)
    set_dedupe_fields(draft, ["test"])
    set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {"test": "TEST"})
    failing_pdf = root / "failing.pdf"
    failing_pdf.write_bytes(b"new-rule-example")
    monkeypatch.setattr("src.rulesuite.rulesuite.RuleSuite.preview_extract", _fake_authoring_preview)

    proof = create_authoring_proof(str(root), "(9000)", draft, str(failing_pdf))

    assert proof["mode"] == "create"
    assert proof["reference_pdf_path"] == ""
    assert proof["active_ruleset_path"] == ""
    assert verify_authoring_proof(str(root), "(9000)", draft)["ok"] is True


def _page_document(lines: list[str]):
    class _Page:
        def __init__(self) -> None:
            self.lines = lines

    class _Document:
        pages = [_Page()]

    return _Document()


def test_get_assay_text_empty_index_returns_explicit_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "empty-index"
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "index.json").write_text(json.dumps({"assays": []}), encoding="utf-8")
    draft = create_blank_draft(str(root), "(9000)", "Fresh Assay")
    monkeypatch.setattr(
        "src.rulesuite.rulesuite.parse",
        lambda _path: _page_document(["Fresh Assay", "(9000)", "Lot: LOT1", "Test: ABC"]),
    )

    out = get_assay_text(str(root), str(root / "missing.pdf"), "(9000)", "Ignored", draft_path=draft)

    assert out["detected_assays"] == []
    assert out["assay_name"] == "Fresh Assay"
    assert "Fresh Assay" in out["assay_block"]
    assert "(9000)" in out["assay_block"]
    assert "Lot: LOT1" in out["assay_block"]


def test_get_assay_text_valid_index_keeps_detected_assays(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9000)", "Fresh Assay")
    monkeypatch.setattr(
        "src.rulesuite.rulesuite.parse",
        lambda _path: _page_document(
            ["Assay A", "(1111)", "Fresh Assay", "(9000)", "Lot: LOT1", "Test: ABC"]
        ),
    )

    out = get_assay_text(str(root), "dummy.pdf", "(9000)", "Fresh Assay", draft_path=draft)

    assert out["detected_assays"] == ["(1111)"]
    assert out["assay_block"].startswith("Fresh Assay")
    assert "Assay A" not in out["assay_block"]


def test_new_authoring_proof_with_empty_index_uses_real_extract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Der Parser ist isoliert, weil die vorhandene .pdf kein gerendertes Berichtslayout ist.
    # preview_extract, get_assay_text und der Extractor laufen real.
    root = tmp_path / "first-assay"
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "index.json").write_text(json.dumps({"assays": []}), encoding="utf-8")
    draft = create_blank_draft(str(root), "(9000)", "Fresh Assay")
    set_lot_rule(draft, r"Lot:\s*(\w+)")
    add_field(draft, "test", r"Test:\s*(\w+)", required=True)
    set_dedupe_fields(draft, ["test"])
    set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {"test": "TEST"})
    failing_pdf = root / "problem.pdf"
    failing_pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        "src.rulesuite.rulesuite.parse",
        lambda _path: _page_document(["Fresh Assay", "(9000)", "Lot: LOT1", "Test: ABC"]),
    )

    proof = create_authoring_proof(str(root), "(9000)", draft, str(failing_pdf))

    assert proof["mode"] == "create"
    assert proof["reference_pdf_path"] == ""
    assert proof["status"] == "ready"
    assert verify_authoring_proof(str(root), "(9000)", draft)["ok"] is True


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


def test_clone_ruleset_full_copy_keeps_dedupe_excel_and_unknown_properties(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    _write_template(root)
    source = {
        "assay_name": "Source Assay",
        "assay_key": "(1111)",
        "vendor_extension": {"keep": True, "n": 1},
        "lot_rule": {"regex": r"Lot:\s*(\w+)", "note": "keep-lot"},
        "extract_rules": {
            "fields": [
                {"key": "DATUM", "regex": r"Datum:\s*(\S+)", "required": True, "hint": "keep-datum"},
                {"key": "PCQ1", "regex": r"PCQ1\s+(\d+)", "required": True, "note": "keep-pcq"},
            ],
            "dedupe_fields": ["PCQ1", "PCQ1"],
            "custom_rule": {"mode": "strict"},
        },
        "excel_rules": {
            "excel_filename_template": "Custom-{assay_name}.xlsx",
            "sheetname_template": "Sheet-{lot_id}",
            "column_mapping": {"DATUM": "Datumsspalte", "PCQ1": "PCQ1 Column"},
            "extra_excel": "keep",
        },
    }
    source_path = root / "rules" / "AssayA.json"
    source_before = json.dumps(source, indent=2, ensure_ascii=False)
    source_path.write_text(source_before, encoding="utf-8")

    created = clone_ruleset_to_draft(str(root), "(1111)", "(abcd)", "Clone Target", include_fields=True)
    assert created["status"] == "created"
    copied = load_draft(created["draft_path"])
    assert copied["assay_key"] == "(abcd)"
    assert copied["assay_name"] == "Clone Target"
    assert copied["vendor_extension"] == {"keep": True, "n": 1}
    assert copied["lot_rule"] == {"regex": r"Lot:\s*(\w+)", "note": "keep-lot"}
    assert copied["extract_rules"]["dedupe_fields"] == ["PCQ1", "PCQ1"]
    assert copied["extract_rules"]["custom_rule"] == {"mode": "strict"}
    assert copied["extract_rules"]["fields"][0]["hint"] == "keep-datum"
    assert copied["extract_rules"]["fields"][1]["note"] == "keep-pcq"
    assert copied["excel_rules"]["excel_filename_template"] == "Custom-{assay_name}.xlsx"
    assert copied["excel_rules"]["sheetname_template"] == "Sheet-{lot_id}"
    assert copied["excel_rules"]["column_mapping"]["PCQ1"] == "PCQ1 Column"
    assert copied["excel_rules"]["extra_excel"] == "keep"
    assert source_path.read_text(encoding="utf-8") == source_before


def test_clone_ruleset_overwrite_false_race_keeps_foreign_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    _write_template(root)
    _write_clone_source_ruleset(root)
    foreign = b'{"marker":"foreign-race"}'
    draft_path = Path(draft_path_for_assay(str(root), "(abcd)"))
    real_publish = lifecycle._publish_bytes_exclusive

    def _plant(path: Path, payload: bytes) -> bytes | None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(foreign)
        return real_publish(path, payload)

    monkeypatch.setattr(lifecycle, "_publish_bytes_exclusive", _plant)
    result = clone_ruleset_to_draft(str(root), "(1111)", "(abcd)", "Clone Target", overwrite=False, include_fields=True)
    assert result["status"] == "exists"
    assert draft_path.read_bytes() == foreign


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


def test_list_rulesuite_inventory_filters_history_and_trash_and_includes_both_in_all(tmp_path: Path) -> None:
    import hashlib
    from datetime import datetime, timezone

    root = _setup_project(tmp_path)
    history_dir = root / "rules" / "history"
    trash_dir = root / "rules" / "trash"
    history_dir.mkdir()
    trash_dir.mkdir()
    history_path = history_dir / "AssayA-20260924T070000000000Z.json"
    history_path.write_bytes((root / "rules" / "AssayA.json").read_bytes())
    trash_path = trash_dir / "old.json"
    trash_path.write_text("{not-json", encoding="utf-8")

    history_rows = list_rulesuite_inventory(str(root), kind="history")
    trash_rows = list_rulesuite_inventory(str(root), kind="trash")
    all_rows = list_rulesuite_inventory(str(root), kind="all")

    assert [row["kind"] for row in history_rows] == ["history"]
    assert [row["kind"] for row in trash_rows] == ["trash"]
    assert {row["kind"] for row in all_rows} >= {"active", "history", "trash"}
    history = history_rows[0]
    assert history["display_type"] == "Historie"
    assert history["ruleset_file"] == history_path.name
    assert history["read_only"] is True
    assert history["sha256"] == hashlib.sha256(history_path.read_bytes()).hexdigest()
    assert len(history["sha256"]) == 64
    assert history["modified_at"] == datetime.fromtimestamp(history_path.stat().st_mtime, tz=timezone.utc).isoformat()
    again = list_rulesuite_inventory(str(root), kind="history")[0]
    assert again["modified_at"] == history["modified_at"]
    assert again["sha256"] == history["sha256"]
    trash = trash_rows[0]
    assert trash["read_only"] is True
    assert trash["display_type"] == "Trash"
    assert trash["valid"] is False
    assert trash["error"]
    assert trash["sha256"] == hashlib.sha256(trash_path.read_bytes()).hexdigest()


def test_open_history_as_draft_copies_without_touching_source_or_active(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    history_dir = root / "rules" / "history"
    history_dir.mkdir()
    history_path = history_dir / "AssayA-stamp.json"
    history_path.write_bytes((root / "rules" / "AssayA.json").read_bytes())
    active_before = (root / "rules" / "AssayA.json").read_bytes()
    other_active_before = (root / "rules" / "AssayB.json").read_bytes()
    history_before = history_path.read_bytes()
    index_before = (root / "rules" / "index.json").read_bytes()

    created = open_history_as_draft(str(root), str(history_path))
    assert created["status"] == "created"
    draft_path = Path(created["draft_path"])
    assert draft_path.is_file()
    assert json.loads(draft_path.read_text(encoding="utf-8"))["assay_key"] == "(1111)"
    assert history_path.read_bytes() == history_before
    assert (root / "rules" / "AssayA.json").read_bytes() == active_before
    assert (root / "rules" / "AssayB.json").read_bytes() == other_active_before
    assert (root / "rules" / "index.json").read_bytes() == index_before

    draft_path.write_text('{"marker": true}', encoding="utf-8")
    exists = open_history_as_draft(str(root), history_path.name)
    assert exists["status"] == "exists"
    assert json.loads(draft_path.read_text(encoding="utf-8")) == {"marker": True}
    assert history_path.read_bytes() == history_before
    assert (root / "rules" / "AssayA.json").read_bytes() == active_before


def test_open_history_as_draft_rejects_foreign_and_traversal_paths(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    history_dir = root / "rules" / "history"
    history_dir.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"assay_key":"(1111)","assay_name":"X"}', encoding="utf-8")
    active = root / "rules" / "AssayA.json"
    active_before = active.read_bytes()

    for candidate in (
        str(outside),
        str(active),
        "../AssayA.json",
        str(history_dir / ".." / "AssayA.json"),
        str(history_dir),
    ):
        with pytest.raises(RuleSuiteError, match="path_outside_allowed_directory"):
            open_history_as_draft(str(root), candidate)

    assert active.read_bytes() == active_before
    assert not (root / "rules" / "drafts").exists() or not list((root / "rules" / "drafts").glob("*.draft.json"))


def test_open_history_as_draft_contains_manipulated_assay_key(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    history_dir = root / "rules" / "history"
    history_dir.mkdir()
    history_path = history_dir / "bad-key.json"
    history_path.write_text(
        json.dumps({"assay_key": "..\\..\\outside", "assay_name": "Bad"}),
        encoding="utf-8",
    )
    history_before = history_path.read_bytes()
    active_before = (root / "rules" / "AssayA.json").read_bytes()
    other_before = (root / "rules" / "AssayB.json").read_bytes()
    index_before = (root / "rules" / "index.json").read_bytes()
    drafts = (root / "rules" / "drafts").resolve()

    with pytest.raises(RuleSuiteError, match="path_outside_allowed_directory"):
        open_history_as_draft(str(root), str(history_path))

    assert history_path.read_bytes() == history_before
    assert (root / "rules" / "AssayA.json").read_bytes() == active_before
    assert (root / "rules" / "AssayB.json").read_bytes() == other_before
    assert (root / "rules" / "index.json").read_bytes() == index_before
    outside = [path for path in root.rglob("*.draft.json") if drafts not in path.resolve().parents]
    assert outside == []


def test_open_history_as_draft_race_keeps_foreign_draft_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    history_dir = root / "rules" / "history"
    history_dir.mkdir()
    history_path = history_dir / "AssayA-stamp.json"
    history_path.write_bytes((root / "rules" / "AssayA.json").read_bytes())
    foreign = b'{"marker":"foreign"}'
    real_publish = lifecycle._publish_new_draft_exclusive

    def _plant_then_publish(path: Path, data: dict) -> bytes | None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(foreign)
        return real_publish(path, data)

    monkeypatch.setattr(lifecycle, "_publish_new_draft_exclusive", _plant_then_publish)

    result = open_history_as_draft(str(root), str(history_path))

    assert result["status"] == "exists"
    assert Path(result["draft_path"]).read_bytes() == foreign


def test_open_history_as_draft_source_change_after_publish_keeps_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    history_dir = root / "rules" / "history"
    history_dir.mkdir()
    history_path = history_dir / "AssayA-stamp.json"
    history_path.write_bytes((root / "rules" / "AssayA.json").read_bytes())
    snapshot = json.loads(history_path.read_text(encoding="utf-8"))
    active_before = (root / "rules" / "AssayA.json").read_bytes()
    index_before = (root / "rules" / "index.json").read_bytes()
    real_publish = lifecycle._publish_new_draft_exclusive

    def _mutate_source_after_publish(path: Path, data: dict) -> bytes | None:
        written = real_publish(path, data)
        history_path.write_bytes(history_path.read_bytes() + b"\n")
        return written

    monkeypatch.setattr(lifecycle, "_publish_new_draft_exclusive", _mutate_source_after_publish)

    created = open_history_as_draft(str(root), str(history_path))

    assert created["status"] == "created_with_source_change"
    assert created["warning"] == "history_source_changed_during_copy"
    draft_path = Path(created["draft_path"])
    assert json.loads(draft_path.read_text(encoding="utf-8")) == snapshot
    assert history_path.read_bytes().endswith(b"\n")
    assert (root / "rules" / "AssayA.json").read_bytes() == active_before
    assert (root / "rules" / "index.json").read_bytes() == index_before


def test_open_history_as_draft_keeps_byte_identical_foreign_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    history_dir = root / "rules" / "history"
    history_dir.mkdir()
    history_path = history_dir / "AssayA-stamp.json"
    history_path.write_bytes((root / "rules" / "AssayA.json").read_bytes())
    active_before = (root / "rules" / "AssayA.json").read_bytes()
    other_active_before = (root / "rules" / "AssayB.json").read_bytes()
    index_before = (root / "rules" / "index.json").read_bytes()
    history_before = history_path.read_bytes()
    real_publish = lifecycle._publish_new_draft_exclusive
    observed: dict[str, object] = {}

    def _replace_with_identical_bytes(path: Path, data: dict) -> bytes | None:
        written = real_publish(path, data)
        payload = path.read_bytes()
        path.unlink()
        path.write_bytes(payload)
        observed["ino"] = path.stat().st_ino
        observed["payload"] = payload
        history_path.write_bytes(history_before + b"\n")
        return written

    monkeypatch.setattr(lifecycle, "_publish_new_draft_exclusive", _replace_with_identical_bytes)

    created = open_history_as_draft(str(root), str(history_path))

    draft_path = Path(created["draft_path"])
    assert created["status"] == "created_with_source_change"
    assert created["warning"] == "history_source_changed_during_copy"
    assert draft_path.exists()
    assert draft_path.stat().st_ino == observed["ino"]
    assert draft_path.read_bytes() == observed["payload"]
    assert history_path.read_bytes() == history_before + b"\n"
    assert (root / "rules" / "AssayA.json").read_bytes() == active_before
    assert (root / "rules" / "AssayB.json").read_bytes() == other_active_before
    assert (root / "rules" / "index.json").read_bytes() == index_before


def test_open_history_as_draft_write_zero_raises_without_final_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    history_dir = root / "rules" / "history"
    history_dir.mkdir()
    history_path = history_dir / "AssayA-stamp.json"
    history_path.write_bytes((root / "rules" / "AssayA.json").read_bytes())
    calls = {"n": 0}

    def _write_zero(_fd: int, _data: object) -> int:
        calls["n"] += 1
        if calls["n"] > 1:
            raise AssertionError("os.write returned 0 more than once")
        return 0

    monkeypatch.setattr(lifecycle.os, "write", _write_zero)

    with pytest.raises(RuleSuiteError, match="draft_publish_failed"):
        open_history_as_draft(str(root), str(history_path))

    assert calls["n"] == 1
    drafts = root / "rules" / "drafts"
    assert list(drafts.glob("*.draft.json")) == []


def test_open_history_as_draft_close_error_raises_without_final_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    history_dir = root / "rules" / "history"
    history_dir.mkdir()
    history_path = history_dir / "AssayA-stamp.json"
    history_path.write_bytes((root / "rules" / "AssayA.json").read_bytes())
    real_close = lifecycle.os.close
    leaked: list[int] = []

    def _close_fails(fd: int) -> None:
        leaked.append(fd)
        raise OSError("simulated close failure")

    monkeypatch.setattr(lifecycle.os, "close", _close_fails)

    try:
        with pytest.raises(RuleSuiteError, match="draft_publish_failed"):
            open_history_as_draft(str(root), str(history_path))
        drafts = root / "rules" / "drafts"
        assert list(drafts.glob("*.draft.json")) == []
    finally:
        for fd in leaked:
            try:
                real_close(fd)
            except OSError:
                pass


def test_delete_inventory_item_rejects_history_and_trash(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    history_dir = root / "rules" / "history"
    trash_dir = root / "rules" / "trash"
    history_dir.mkdir()
    trash_dir.mkdir()
    history_path = history_dir / "AssayA-stamp.json"
    trash_path = trash_dir / "old.json"
    history_path.write_bytes((root / "rules" / "AssayA.json").read_bytes())
    trash_path.write_text('{"assay_key":"(t)"}', encoding="utf-8")
    history_before = history_path.read_bytes()
    trash_before = trash_path.read_bytes()

    with pytest.raises(RuleSuiteError, match="read_only_inventory_kind"):
        delete_inventory_item(str(root), "history", str(history_path))
    with pytest.raises(RuleSuiteError, match="read_only_inventory_kind"):
        delete_inventory_item(str(root), "trash", str(trash_path))

    assert history_path.read_bytes() == history_before
    assert trash_path.read_bytes() == trash_before


def _prepared_existing_activation(root: Path) -> tuple[Path, str, bytes, bytes]:
    active = root / "rules" / "AssayA.json"
    active.write_bytes(active.read_bytes() + b"\n")
    before = active.read_bytes()
    draft = create_draft(str(root), "(1111)")
    set_field_regex(draft, "test", r"Test:\s*(UPDATED)")
    draft_bytes = Path(draft).read_bytes()
    return active, draft, before, draft_bytes


def test_activate_draft_publishes_byte_exact_history_snapshot(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    active, draft, before, draft_bytes = _prepared_existing_activation(root)

    target = activate_draft(str(root), "(1111)", draft)

    snapshots = sorted((root / "rules" / "history").glob("*.json"))
    assert len(snapshots) == 1
    assert snapshots[0].read_bytes() == before
    assert active.read_bytes() != before
    assert Path(target).read_bytes() == active.read_bytes()
    assert Path(draft).read_bytes() == draft_bytes
    assert not list((root / "rules" / "history").glob("*.tmp"))


def test_repeated_activation_uses_collision_safe_history_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.history as history

    monkeypatch.setattr(history, "_utc_stamp", lambda: "20260923T120000000000Z")
    root = _setup_project(tmp_path)
    active, draft, first_before, _draft_bytes = _prepared_existing_activation(root)

    activate_draft(str(root), "(1111)", draft)
    after_first = active.read_bytes()
    set_field_regex(draft, "test", r"Test:\s*(TWICE)")
    activate_draft(str(root), "(1111)", draft)

    by_name = {path.name: path for path in (root / "rules" / "history").glob("*.json")}
    first_name = "AssayA-20260923T120000000000Z.json"
    second_name = "AssayA-20260923T120000000000Z-2.json"
    assert set(by_name) == {first_name, second_name}
    assert by_name[first_name].read_bytes() == first_before
    assert by_name[second_name].read_bytes() == after_first
    assert active.read_bytes() != after_first


def test_activate_new_draft_does_not_publish_history_snapshot(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = create_blank_draft(str(root), "(9000)", "Fresh Assay")
    set_lot_rule(draft, r"Lot:\\s*(\\w+)")
    add_field(draft, "test", r"Test:\\s*(\\w+)", required=True)
    set_dedupe_fields(draft, ["test"])
    set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {"test": "TEST"})

    out_path = activate_new_draft(str(root), "(9000)", "Fresh Assay", draft)

    assert Path(out_path).is_file()
    assert not (root / "rules" / "history").exists()


def test_invalid_draft_activation_does_not_snapshot_or_overwrite(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    active = root / "rules" / "AssayA.json"
    before = active.read_bytes()
    draft = create_draft(str(root), "(1111)")
    data = load_draft(draft)
    data["excel_rules"]["column_mapping"] = {"unknown": "X"}
    Path(draft).write_text(json.dumps(data), encoding="utf-8")
    draft_bytes = Path(draft).read_bytes()

    with pytest.raises(RuleSuiteError, match="draft_invalid"):
        activate_draft(str(root), "(1111)", draft)

    assert active.read_bytes() == before
    assert Path(draft).read_bytes() == draft_bytes
    assert not (root / "rules" / "history").exists()


@pytest.mark.parametrize("stage", ["read", "mkdir", "write", "publish", "verify"])
def test_snapshot_failure_blocks_activation_without_changing_active_or_draft(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stage: str,
) -> None:
    import src.rulesuite.history as history

    root = _setup_project(tmp_path)
    active, draft, before, draft_bytes = _prepared_existing_activation(root)
    if stage == "read":

        def _fail_read(_path: Path) -> bytes:
            raise RuleSuiteError("snapshot_read_failed")

        monkeypatch.setattr(history, "_read_source_bytes", _fail_read)
    elif stage == "mkdir":
        (root / "rules" / "history").write_text("blocked", encoding="utf-8")
    elif stage == "write":

        def _fail_write(path: Path, payload: bytes) -> None:
            path.write_bytes(b"partial")
            raise RuleSuiteError(f"snapshot_write_failed: {len(payload)}")

        monkeypatch.setattr(history, "_write_temp_bytes", _fail_write)
    elif stage == "publish":

        def _fail_publish(_tmp: Path, _final: Path) -> None:
            raise RuleSuiteError("snapshot_publish_failed")

        monkeypatch.setattr(history, "_publish_snapshot", _fail_publish)
    else:
        real_verify = history._verify_snapshot_bytes

        def _fail_publish_verify(path: Path, payload: bytes, *, stage: str) -> None:
            real_verify(path, payload, stage=stage)
            if stage == "publish_verify":
                raise RuleSuiteError("snapshot_publish_verify_failed")

        monkeypatch.setattr(history, "_verify_snapshot_bytes", _fail_publish_verify)

    with pytest.raises(RuleSuiteError):
        activate_draft(str(root), "(1111)", draft)

    assert active.read_bytes() == before
    assert Path(draft).read_bytes() == draft_bytes
    history_path = root / "rules" / "history"
    if stage == "mkdir":
        assert history_path.is_file()
        assert history_path.read_text(encoding="utf-8") == "blocked"
        return
    published = list(history_path.glob("*.json")) if history_path.exists() else []
    temps = list(history_path.glob("*.tmp")) if history_path.exists() else []
    assert published == []
    assert temps == []


def _rich_active_bytes() -> bytes:
    payload = {
        "assay_name": "Assay A",
        "assay_key": "(1111)",
        "vendor_extension": {"keep": True, "n": 1},
        "lot_rule": {"regex": r"Lot:\s*(\w+)"},
        "extract_rules": {
            "fields": [
                {
                    "key": "alpha",
                    "regex": r"A:\s*(\w+)",
                    "required": True,
                    "hint": "keep-alpha",
                    "search_from": {"after": "BEGIN"},
                },
                {"key": "beta", "regex": r"B:\s*(\w+)", "required": False, "note": "keep-beta"},
            ],
            "dedupe_fields": ["alpha", "alpha"],
            "custom_rule": {"mode": "strict"},
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {"alpha": "ALPHA", "beta": "BETA"},
            "extra_excel": "keep",
        },
    }
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def test_open_active_as_draft_copies_complete_bytes_and_keeps_existing_draft(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    active = root / "rules" / "AssayA.json"
    active.write_bytes(_rich_active_bytes())
    other_before = (root / "rules" / "AssayB.json").read_bytes()
    index_before = (root / "rules" / "index.json").read_bytes()

    created = open_active_as_draft(str(root), "(1111)")
    draft_path = Path(created["draft_path"])
    assert created["status"] == "created"
    assert draft_path.read_bytes() == active.read_bytes()
    loaded = json.loads(draft_path.read_text(encoding="utf-8"))
    assert loaded["vendor_extension"] == {"keep": True, "n": 1}
    assert loaded["extract_rules"]["dedupe_fields"] == ["alpha", "alpha"]
    assert loaded["extract_rules"]["custom_rule"] == {"mode": "strict"}
    assert loaded["excel_rules"]["extra_excel"] == "keep"
    assert loaded["extract_rules"]["fields"][0]["hint"] == "keep-alpha"

    kept = json.dumps({"assay_key": "(1111)", "marker": True}, separators=(",", ":")).encode("utf-8")
    draft_path.write_bytes(kept)
    exists = open_active_as_draft(str(root), "(1111)")
    assert exists["status"] == "exists"
    assert draft_path.read_bytes() == kept
    assert active.read_bytes() == _rich_active_bytes()
    assert (root / "rules" / "AssayB.json").read_bytes() == other_before
    assert (root / "rules" / "index.json").read_bytes() == index_before


def test_open_active_as_draft_fail_closed_on_containment_and_identity(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    active = root / "rules" / "AssayA.json"
    before = active.read_bytes()
    index_path = root / "rules" / "index.json"
    original_index = index_path.read_bytes()

    index_path.write_text(
        json.dumps({"assays": [{"assay_key": "(1111)", "ruleset_file": "../outside.json"}]}),
        encoding="utf-8",
    )
    with pytest.raises(RuleSuiteError, match="protected_or_invalid_ruleset_file"):
        open_active_as_draft(str(root), "(1111)")

    index_path.write_text(
        json.dumps(
            {
                "assays": [
                    {"assay_key": "(1111)", "ruleset_file": "AssayA.json"},
                    {"assay_key": "(1111)", "ruleset_file": "AssayB.json"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuleSuiteError, match="active_ruleset_identity_ambiguous"):
        open_active_as_draft(str(root), "(1111)")

    index_path.write_bytes(original_index)
    active.write_text(json.dumps({"assay_key": "(9999)"}), encoding="utf-8")
    with pytest.raises(RuleSuiteError, match="active_ruleset_identity_ambiguous"):
        open_active_as_draft(str(root), "(1111)")

    active.write_bytes(before)
    drafts = root / "rules" / "drafts"
    assert not drafts.exists() or list(drafts.glob("*.draft.json")) == []


def test_open_active_as_draft_race_keeps_foreign_draft_and_source_change_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    active = root / "rules" / "AssayA.json"
    active.write_bytes(_rich_active_bytes())
    foreign = b'{"marker":"foreign"}'
    real_publish = lifecycle._publish_bytes_exclusive

    def _plant(_path: Path, payload: bytes) -> bytes | None:
        _path.parent.mkdir(parents=True, exist_ok=True)
        _path.write_bytes(foreign)
        return real_publish(_path, payload)

    monkeypatch.setattr(lifecycle, "_publish_bytes_exclusive", _plant)
    draft_path = Path(draft_path_for_assay(str(root), "(1111)"))
    with pytest.raises(RuleSuiteError, match="draft_identity_conflict"):
        open_active_as_draft(str(root), "(1111)")
    assert draft_path.read_bytes() == foreign
    draft_path.unlink()

    def _mutate_source(path: Path, payload: bytes) -> bytes | None:
        written = real_publish(path, payload)
        active.write_bytes(active.read_bytes() + b"\n")
        return written

    monkeypatch.setattr(lifecycle, "_publish_bytes_exclusive", _mutate_source)
    with pytest.raises(RuleSuiteError, match="active_ruleset_changed_during_copy"):
        open_active_as_draft(str(root), "(1111)")
    assert list((root / "rules" / "drafts").glob("*.draft.json")) == []


def test_open_active_as_draft_rejects_foreign_and_unreadable_existing_draft(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    active = root / "rules" / "AssayA.json"
    active.write_bytes(_rich_active_bytes())
    draft_path = Path(draft_path_for_assay(str(root), "(1111)"))
    draft_path.parent.mkdir(parents=True)
    active_before = active.read_bytes()

    for payload in (b'{"marker":true}', b'{"assay_key":"(2222)"}', b"\xffnot-json", b"[]"):
        draft_path.write_bytes(payload)
        with pytest.raises(RuleSuiteError, match="draft_identity_conflict"):
            open_active_as_draft(str(root), "(1111)")
        assert draft_path.read_bytes() == payload
        assert active.read_bytes() == active_before


def test_open_active_as_draft_race_rejects_foreign_and_unreadable_winner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    active = root / "rules" / "AssayA.json"
    active.write_bytes(_rich_active_bytes())
    draft_path = Path(draft_path_for_assay(str(root), "(1111)"))
    real_publish = lifecycle._publish_bytes_exclusive
    planted = {"payload": b""}

    def _plant(path: Path, payload: bytes) -> bytes | None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(planted["payload"])
        return real_publish(path, payload)

    monkeypatch.setattr(lifecycle, "_publish_bytes_exclusive", _plant)
    for payload in (b'{"marker":"foreign"}', b"not-json", b'{"assay_key":"OTHER"}'):
        planted["payload"] = payload
        if draft_path.exists():
            draft_path.unlink()
        with pytest.raises(RuleSuiteError, match="draft_identity_conflict"):
            open_active_as_draft(str(root), "(1111)")
        assert draft_path.read_bytes() == payload


def test_open_active_as_draft_rollback_keeps_foreign_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    active = root / "rules" / "AssayA.json"
    active.write_bytes(_rich_active_bytes())
    draft_path = Path(draft_path_for_assay(str(root), "(1111)"))
    foreign = b'{"assay_key":"FOREIGN"}'
    real_publish = lifecycle._publish_bytes_exclusive

    def _mutate_and_replace(path: Path, payload: bytes) -> bytes | None:
        written = real_publish(path, payload)
        path.write_bytes(foreign)
        active.write_bytes(active.read_bytes() + b"\n")
        return written

    monkeypatch.setattr(lifecycle, "_publish_bytes_exclusive", _mutate_and_replace)
    with pytest.raises(RuleSuiteError, match="draft_target_conflict"):
        open_active_as_draft(str(root), "(1111)")
    assert draft_path.read_bytes() == foreign


def _field_draft(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "proj"
    drafts = root / "rules" / "drafts"
    drafts.mkdir(parents=True)
    payload = {
        "assay_key": "FRESH",
        "assay_name": "Fresh",
        "vendor_extension": {"keep": True},
        "extract_rules": {
            "fields": [
                {
                    "key": "alpha",
                    "regex": r"A:\s*(\w+)",
                    "required": True,
                    "hint": "keep-alpha",
                    "search_from": {"line": 2},
                },
                {"key": "beta", "regex": r"B:\s*(\w+)", "required": False, "note": "keep-beta"},
            ],
            "dedupe_fields": ["alpha", "alpha"],
            "custom_rule": {"mode": "strict"},
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {"alpha": "ALPHA", "beta": "BETA"},
            "extra_excel": "keep",
        },
    }
    path = drafts / "FRESH.draft.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return root, path


def test_replace_field_updates_renames_and_preserves_unknown_properties(tmp_path: Path) -> None:
    _root, path = _field_draft(tmp_path)
    replace_field(
        str(path),
        "alpha",
        key="alpha",
        regex=r"A:\s*(\d+)",
        required=False,
        search_from=None,
        excel_column=None,
        dedupe_member=None,
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    alpha = data["extract_rules"]["fields"][0]
    assert alpha["key"] == "alpha"
    assert alpha["regex"] == r"A:\s*(\d+)"
    assert alpha["required"] is False
    assert "search_from" not in alpha
    assert alpha["hint"] == "keep-alpha"
    assert data["extract_rules"]["fields"][1]["note"] == "keep-beta"
    assert data["excel_rules"]["column_mapping"]["alpha"] == "ALPHA"
    assert data["extract_rules"]["dedupe_fields"] == ["alpha"]
    assert data["vendor_extension"] == {"keep": True}
    assert data["extract_rules"]["custom_rule"] == {"mode": "strict"}

    replace_field(
        str(path),
        "alpha",
        key="gamma",
        regex=r"G:\s*(\w+)",
        required=True,
        search_from={"after": "HEAD"},
        excel_column=None,
        dedupe_member=None,
    )
    renamed = json.loads(path.read_text(encoding="utf-8"))
    fields = renamed["extract_rules"]["fields"]
    assert [field["key"] for field in fields] == ["gamma", "beta"]
    assert fields[0]["hint"] == "keep-alpha"
    assert fields[0]["search_from"] == {"after": "HEAD"}
    assert renamed["excel_rules"]["column_mapping"] == {"gamma": "ALPHA", "beta": "BETA"}
    assert renamed["extract_rules"]["dedupe_fields"] == ["gamma"]
    assert renamed["excel_rules"]["extra_excel"] == "keep"


def test_replace_field_mapping_default_dedupe_authority_and_failure_keep_bytes(tmp_path: Path) -> None:
    _root, path = _field_draft(tmp_path)
    original = path.read_bytes()
    payload = json.loads(original.decode("utf-8"))
    payload["extract_rules"]["fields"][0].pop("search_from")
    payload["excel_rules"]["column_mapping"] = {"beta": "BETA"}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    before_rename = path.read_bytes()

    replace_field(
        str(path),
        "alpha",
        key="gamma",
        regex=r"G:\s*(\w+)",
        required=True,
        search_from=None,
        excel_column=None,
        dedupe_member=False,
    )
    renamed = json.loads(path.read_text(encoding="utf-8"))
    assert renamed["excel_rules"]["column_mapping"]["gamma"] == "gamma"
    assert "alpha" not in renamed["excel_rules"]["column_mapping"]
    assert renamed["extract_rules"]["dedupe_fields"] == []

    path.write_bytes(before_rename)
    conflict_before = path.read_bytes()
    conflict = json.loads(conflict_before.decode("utf-8"))
    conflict["excel_rules"]["column_mapping"]["gamma"] = "FOREIGN"
    path.write_text(json.dumps(conflict, indent=2), encoding="utf-8")
    conflict_bytes = path.read_bytes()
    with pytest.raises(RuleSuiteError, match="column_mapping_conflict"):
        replace_field(
            str(path),
            "alpha",
            key="gamma",
            regex=r"G:\s*(\w+)",
            required=True,
            search_from=None,
            excel_column="GAMMA",
        )
    assert path.read_bytes() == conflict_bytes

    with pytest.raises(RuleSuiteError, match="field_exists"):
        replace_field(
            str(path),
            "alpha",
            key="beta",
            regex=r"B:\s*(\w+)",
            required=True,
            search_from=None,
        )
    assert path.read_bytes() == conflict_bytes

    with pytest.raises(RuleSuiteError, match="invalid_search_from"):
        replace_field(
            str(path),
            "alpha",
            key="alpha",
            regex=r"A:\s*(\w+)",
            required=True,
            search_from={"line": -1},
        )
    assert path.read_bytes() == conflict_bytes


def test_replace_field_write_failure_restores_original_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.rulesuite as rulesuite

    _root, path = _field_draft(tmp_path)
    original = path.read_bytes()

    def _fail_before_replace(_target: Path, _data: dict) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr(rulesuite, "_write_json_atomic", _fail_before_replace)
    with pytest.raises(RuleSuiteError, match="draft_replace_failed"):
        replace_field(
            str(path),
            "alpha",
            key="alpha",
            regex=r"A:\s*(\d+)",
            required=False,
            search_from=None,
        )
    assert path.read_bytes() == original

    def _foreign_write(target: Path, _data: dict) -> None:
        target.write_bytes(b"foreign-bytes")
        raise OSError("uncooperative writer")

    monkeypatch.setattr(rulesuite, "_write_json_atomic", _foreign_write)
    with pytest.raises(RuleSuiteError, match="draft_replace_failed"):
        replace_field(
            str(path),
            "alpha",
            key="alpha",
            regex=r"A:\s*(\d+)",
            required=False,
            search_from=None,
        )
    assert path.read_bytes() == b"foreign-bytes"


def _never_active_draft(root: Path, assay_key: str = "NEVER-1", **extra: object) -> Path:
    drafts = root / "rules" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    payload = {
        "assay_key": assay_key,
        "assay_name": "Never",
        "extract_rules": {"fields": [], "dedupe_fields": []},
    }
    payload.update(extra)
    path = Path(draft_path_for_assay(str(root), assay_key))
    path.write_text(json.dumps(payload), encoding="utf-8")
    readiness = path.with_name(path.name + ".readiness")
    readiness.write_text(json.dumps({"ok": True, "assay_key": assay_key}), encoding="utf-8")
    return path


def test_delete_never_active_ruleset_removes_draft_and_readiness_without_trash(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    draft = _never_active_draft(root)
    readiness = draft.with_name(draft.name + ".readiness")
    active_before = (root / "rules" / "AssayA.json").read_bytes()
    index_before = (root / "rules" / "index.json").read_bytes()

    result = delete_never_active_ruleset(str(root), str(draft))
    assert result["status"] == "deleted"
    assert result["readiness_removed"] is True
    assert not draft.exists()
    assert not readiness.exists()
    trash = root / "rules" / "trash"
    history = root / "rules" / "history"
    assert not trash.exists() or list(trash.rglob("*")) == []
    assert not history.exists() or list(history.glob("*.json")) == []
    assert (root / "rules" / "AssayA.json").read_bytes() == active_before
    assert (root / "rules" / "index.json").read_bytes() == index_before


@pytest.mark.parametrize(
    "kind",
    ["active-index", "active-file", "inactive", "history", "trash", "foreign", "unreadable", "ambiguous"],
)
def test_delete_never_active_ruleset_rejects_traced_and_foreign_files(tmp_path: Path, kind: str) -> None:
    root = _setup_project(tmp_path)
    if kind == "active-index":
        draft = _never_active_draft(root, "(1111)")
    elif kind == "active-file":
        draft = _never_active_draft(root, "ORPHAN")
        (root / "rules" / "index.json").write_text(json.dumps({"assays": []}), encoding="utf-8")
        (root / "rules" / "Orphan.json").write_text(json.dumps({"assay_key": "ORPHAN"}), encoding="utf-8")
    elif kind == "inactive":
        draft = _never_active_draft(root, "OLD")
        inactive = root / "rules" / "inactive"
        inactive.mkdir()
        (inactive / "OLD.json").write_text(json.dumps({"assay_key": "OLD"}), encoding="utf-8")
    elif kind == "history":
        draft = _never_active_draft(root, "HIST")
        history = root / "rules" / "history"
        history.mkdir()
        (history / "HIST.json").write_text(json.dumps({"assay_key": "HIST"}), encoding="utf-8")
    elif kind == "trash":
        draft = _never_active_draft(root, "GONE")
        trash = root / "rules" / "trash"
        trash.mkdir()
        (trash / "GONE.json").write_text(json.dumps({"assay_key": "GONE"}), encoding="utf-8")
    elif kind == "foreign":
        draft = _never_active_draft(root)
        outside = tmp_path / "outside.draft.json"
        outside.write_bytes(draft.read_bytes())
        before = outside.read_bytes()
        with pytest.raises(RuleSuiteError, match="path_outside_allowed_directory"):
            delete_never_active_ruleset(str(root), str(outside))
        assert outside.read_bytes() == before
        assert draft.exists()
        return
    elif kind == "unreadable":
        draft = _never_active_draft(root, "PLAIN")
        history = root / "rules" / "history"
        history.mkdir()
        (history / "broken.json").write_bytes(b"{not-json")
    else:
        draft = _never_active_draft(root, "MAYBE")
        draft.write_text(json.dumps({"assay_key": "OTHER"}), encoding="utf-8")

    before = draft.read_bytes()
    readiness = draft.with_name(draft.name + ".readiness")
    readiness_before = readiness.read_bytes() if readiness.exists() else None
    with pytest.raises(RuleSuiteError):
        delete_never_active_ruleset(str(root), str(draft))
    assert draft.read_bytes() == before
    if readiness_before is not None:
        assert readiness.read_bytes() == readiness_before


def test_delete_never_active_ruleset_rolls_back_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    draft = _never_active_draft(root)
    readiness = draft.with_name(draft.name + ".readiness")
    draft_before = draft.read_bytes()
    readiness_before = readiness.read_bytes()
    real_replace = lifecycle.os.replace
    calls = {"n": 0}

    def _fail_second(src: Path, dst: Path) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated partial delete")
        real_replace(src, dst)

    monkeypatch.setattr(lifecycle.os, "replace", _fail_second)
    with pytest.raises(RuleSuiteError, match="delete_never_active_failed"):
        delete_never_active_ruleset(str(root), str(draft))

    assert draft.read_bytes() == draft_before
    assert readiness.read_bytes() == readiness_before
    assert list((root / "rules" / "drafts").glob(".*.deleting")) == []
    trash = root / "rules" / "trash"
    assert not trash.exists() or list(trash.rglob("*")) == []


def test_delete_never_active_ruleset_ignores_non_json_and_blocks_broken_json(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    (root / "rules" / "README.md").write_text("project notes", encoding="utf-8")
    history = root / "rules" / "history"
    history.mkdir()
    (history / "notes.txt").write_text("independent", encoding="utf-8")
    draft = _never_active_draft(root)
    readiness = draft.with_name(draft.name + ".readiness")

    result = delete_never_active_ruleset(str(root), str(draft))
    assert result["status"] == "deleted"
    assert not draft.exists()
    assert not readiness.exists()
    assert (root / "rules" / "README.md").read_text(encoding="utf-8") == "project notes"
    assert (history / "notes.txt").read_text(encoding="utf-8") == "independent"

    blocked = _never_active_draft(root, "STILL")
    blocked_readiness = blocked.with_name(blocked.name + ".readiness")
    draft_before = blocked.read_bytes()
    readiness_before = blocked_readiness.read_bytes()
    (history / "broken.json").write_bytes(b"{not-json")
    with pytest.raises(RuleSuiteError, match="lifecycle_artifact_unreadable"):
        delete_never_active_ruleset(str(root), str(blocked))
    assert blocked.read_bytes() == draft_before
    assert blocked_readiness.read_bytes() == readiness_before
    assert (history / "broken.json").read_bytes() == b"{not-json"


def test_delete_never_active_ruleset_discard_failure_restores_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import src.rulesuite.lifecycle as lifecycle

    root = _setup_project(tmp_path)
    draft = _never_active_draft(root)
    readiness = draft.with_name(draft.name + ".readiness")
    draft_before = draft.read_bytes()
    readiness_before = readiness.read_bytes()
    real_discard = lifecycle._discard_quarantine
    calls = {"n": 0}

    def _fail_final_discard(path: Path) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            path.unlink()
            raise OSError("simulated discard failure")
        real_discard(path)

    monkeypatch.setattr(lifecycle, "_discard_quarantine", _fail_final_discard)
    with pytest.raises(RuleSuiteError, match="delete_never_active_failed"):
        delete_never_active_ruleset(str(root), str(draft))

    assert draft.read_bytes() == draft_before
    assert readiness.read_bytes() == readiness_before
    assert list((root / "rules" / "drafts").glob(".*.deleting")) == []


def test_lifecycle_lock_blocks_activate_and_permanent_delete_without_file_changes(tmp_path: Path) -> None:
    from src.runtime.api import release_exclusive, try_acquire_exclusive

    root = _setup_project(tmp_path)
    draft = create_draft(str(root), "(1111)")
    never = _never_active_draft(root, "NEVER-LOCK")
    readiness = never.with_name(never.name + ".readiness")
    active = root / "rules" / "AssayA.json"
    index = root / "rules" / "index.json"
    before = {
        "draft": Path(draft).read_bytes(),
        "never": never.read_bytes(),
        "readiness": readiness.read_bytes(),
        "active": active.read_bytes(),
        "index": index.read_bytes(),
    }
    lock_path = root / "rules" / ".lifecycle.lock"
    assert try_acquire_exclusive(lock_path, 120.0) is True
    try:
        with pytest.raises(RuleSuiteError, match="lifecycle_lock_busy"):
            activate_draft(str(root), "(1111)", draft)
        with pytest.raises(RuleSuiteError, match="lifecycle_lock_busy"):
            activate_new_draft(str(root), "(lock)", "Lock Assay", draft)
        with pytest.raises(RuleSuiteError, match="lifecycle_lock_busy"):
            deactivate_ruleset(str(root), "(1111)")
        with pytest.raises(RuleSuiteError, match="lifecycle_lock_busy"):
            delete_never_active_ruleset(str(root), str(never))
        assert Path(draft).read_bytes() == before["draft"]
        assert never.read_bytes() == before["never"]
        assert readiness.read_bytes() == before["readiness"]
        assert active.read_bytes() == before["active"]
        assert index.read_bytes() == before["index"]
        assert lock_path.is_file()
    finally:
        release_exclusive(lock_path)
    assert not lock_path.exists()

    activate_draft(str(root), "(1111)", draft)
    assert not lock_path.exists()
    with pytest.raises(RuleSuiteError):
        delete_never_active_ruleset(str(root), str(never.with_name("missing.draft.json")))
    assert not lock_path.exists()
    delete_never_active_ruleset(str(root), str(never))
    assert not never.exists()
    assert not lock_path.exists()
