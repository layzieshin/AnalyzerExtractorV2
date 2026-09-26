from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.api import create_desktop_services
from src.rulesuite.api import AuthoringReadinessError, REQUIRED_HEADER_FIELD_KEYS
from src.rulesuite.rulesuite import RuleSuiteError


def _setup_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "rules" / "drafts").mkdir(parents=True)
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
            ],
            "dedupe_fields": ["test"],
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {"test": "TEST"},
        },
    }
    (root / "rules" / "AssayA.json").write_text(json.dumps(assay_a), encoding="utf-8")
    (root / "rules" / "drafts" / "broken.draft.json").write_text("{bad-json", encoding="utf-8")
    return root


def test_controller_open_history_as_draft_routes_and_keeps_bytes(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    history_dir = root / "rules" / "history"
    history_dir.mkdir()
    history_path = history_dir / "AssayA-stamp.json"
    history_path.write_bytes((root / "rules" / "AssayA.json").read_bytes())
    active_before = (root / "rules" / "AssayA.json").read_bytes()
    history_before = history_path.read_bytes()

    created = rules.open_history_as_draft(str(history_path))
    assert created["status"] == "created"
    assert history_path.read_bytes() == history_before
    assert (root / "rules" / "AssayA.json").read_bytes() == active_before

    Path(created["draft_path"]).write_text('{"marker": true}', encoding="utf-8")
    exists = rules.open_history_as_draft(str(history_path))
    assert exists["status"] == "exists"
    assert Path(created["draft_path"]).read_text(encoding="utf-8") == '{"marker": true}'

    listed = rules.list_inventory(kind="history")
    assert len(listed) == 1
    assert listed[0].read_only is True
    assert listed[0].sha256
    assert listed[0].modified_at
    assert listed[0].ruleset_file == history_path.name


def test_inventory_maps_defective_draft(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    items = create_desktop_services(root).rules.list_inventory()
    kinds = {item.kind for item in items}
    assert "active" in kinds
    assert "draft" in kinds
    broken = next(item for item in items if item.path.endswith("broken.draft.json"))
    assert broken.valid is False
    assert broken.error


def test_regex_hit_miss_and_search_from(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    hit = rules.test_regex("Line A\nLine B Test: value", r"Test:\s*(\w+)", search_from={"line": 1})
    miss = rules.test_regex("Line A", r"Test:\s*(\w+)")
    assert hit.get("matched") is True
    assert miss.get("matched") is False


def test_locate_fields_returns_absolute_spans(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    draft_path = rules.create_draft("(1111)")
    assay_text = "Lot: ABC\nTest: value"
    located = rules.locate_fields(draft_path, assay_text)
    results = located.get("results") or []
    assert located.get("hits", 0) >= 1
    first = results[0]
    assert first.get("matched") is True
    span = first.get("span")
    assert isinstance(span, (list, tuple))
    assert len(span) == 2
    assert span[0] >= 0


def test_lifecycle_write_in_tmp_path_only(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    draft_path = rules.create_draft("(1111)")
    data = rules.load_draft(draft_path)
    data["assay_name"] = "Assay A Draft"
    rules.save_draft(draft_path, data)

    inactive = rules.deactivate_ruleset("(1111)")
    assert inactive["inactive_path"]

    moved = rules.delete_inventory_item("inactive", inactive["inactive_path"])
    assert moved["trash_path"]
    assert Path(moved["trash_path"]).exists()


def test_validate_rules_integrity_delegates_to_ruleresolver(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    report = create_desktop_services(root).rules.validate_rules_integrity()
    assert "content_errors" in report
    assert "missing_files" in report


def test_discover_assay_candidates_returns_application_dtos(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    text = "Test: Example.asy (1111)\nLine B"
    candidates = rules.discover_assay_candidates(text)
    assert candidates
    first = candidates[0]
    assert first.assay_key == "(1111)"
    assert first.reason == "test_line"
    assert first.known_status == "known"


def test_discover_assay_candidates_for_job_reads_beyond_display_cap(tmp_path: Path) -> None:
    import json

    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    jobs = root / "jobs"
    jobs.mkdir(exist_ok=True)
    normalized = jobs / "job1_normalized.txt"
    normalized.write_text("x" * 33000 + "\nTest: Late.asy (2222)\n", encoding="utf-8")
    (root / "rules" / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1111)", "ruleset_file": "AssayA.json"}, {"assay_key": "(2222)", "ruleset_file": "AssayA.json"}]}),
        encoding="utf-8",
    )
    state = {
        "job_id": "job1",
        "pdf_path": str(root / "sample.pdf"),
        "status": "FAILED",
        "error": "no_assay_detected",
        "steps": [{"step": "debug", "normalized_dump": str(normalized)}],
    }
    (jobs / "job1.json").write_text(json.dumps(state), encoding="utf-8")

    candidates = rules.discover_assay_candidates_for_job("job1")
    assert any(item.assay_key == "(2222)" for item in candidates)


def test_controller_activate_draft_snapshots_previous_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    active = root / "rules" / "AssayA.json"
    active.write_bytes(active.read_bytes() + b"\n")
    before = active.read_bytes()
    draft = rules.create_draft("(1111)")
    rules.set_field_regex(draft, "test", r"Test:\s*(UPDATED)")
    monkeypatch.setattr(rules, "verify_authoring_proof", lambda _key, _draft: {"ok": True})

    target = rules.activate_draft("(1111)", draft)

    snapshots = list((root / "rules" / "history").glob("*.json"))
    assert len(snapshots) == 1
    assert snapshots[0].read_bytes() == before
    assert Path(target).read_bytes() != before


def test_controller_activate_new_draft_does_not_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    draft = rules.create_blank_draft("(9000)", "Fresh Assay")
    rules.set_lot_rule(draft, r"Lot:\\s*(\\w+)")
    rules.add_field(draft, "test", r"Test:\\s*(\\w+)", required=True)
    rules.set_dedupe_fields(draft, ["test"])
    rules.set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {"test": "TEST"})
    monkeypatch.setattr(rules, "verify_authoring_proof", lambda _key, _draft: {"ok": True})

    out_path = rules.activate_new_draft("(9000)", "Fresh Assay", draft)

    assert Path(out_path).is_file()
    assert not (root / "rules" / "history").exists()


def test_controller_activate_draft_is_fail_closed_when_snapshot_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    active = root / "rules" / "AssayA.json"
    before = active.read_bytes()
    draft = rules.create_draft("(1111)")
    rules.set_field_regex(draft, "test", r"Test:\s*(UPDATED)")
    draft_bytes = Path(draft).read_bytes()

    def _fail(_path: Path) -> Path:
        raise RuleSuiteError("snapshot_publish_failed")

    monkeypatch.setattr("src.rulesuite.rulesuite.snapshot_existing_active_ruleset", _fail)
    monkeypatch.setattr(rules, "verify_authoring_proof", lambda _key, _draft: {"ok": True})

    with pytest.raises(RuleSuiteError, match="snapshot_publish_failed"):
        rules.activate_draft("(1111)", draft)

    assert active.read_bytes() == before
    assert Path(draft).read_bytes() == draft_bytes
    assert not (root / "rules" / "history").exists()


def test_controller_activation_is_blocked_without_authoring_proof(tmp_path: Path) -> None:
    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    draft = rules.create_draft("(1111)")
    active = root / "rules" / "AssayA.json"
    active_before = active.read_bytes()

    with pytest.raises(AuthoringReadinessError, match="authoring_proof_missing"):
        rules.activate_draft("(1111)", draft)

    assert active.read_bytes() == active_before


def test_controller_exposes_required_header_contract_and_pdf_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rules = create_desktop_services(_setup_project(tmp_path)).rules
    assert rules.required_header_field_keys == REQUIRED_HEADER_FIELD_KEYS

    seen: dict[str, str] = {}

    class _Page:
        lines = [" raw "]

    class _Document:
        pages = [_Page()]

    def _parse(pdf_path: str) -> _Document:
        seen["path"] = pdf_path
        return _Document()

    monkeypatch.setattr("src.application.rules_controller.parse", _parse)
    monkeypatch.setattr("src.application.rules_controller.normalize_lines", lambda lines: ["normalized"])

    assert rules.load_normalized_pdf_text("sample.pdf") == "normalized"
    assert seen["path"] == "sample.pdf"


def test_derive_assay_block_uses_only_normalized_text_and_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from src.contentsplitter.api import AssayDescriptor

    rules = create_desktop_services(_setup_project(tmp_path)).rules
    seen: dict[str, object] = {}

    def _split(text: str, assays: list[AssayDescriptor]) -> dict[str, str]:
        seen["text"] = text
        seen["assays"] = [(item.assay_key, item.assay_name) for item in assays]
        return {"(7777)": "BLOCK"}

    monkeypatch.setattr("src.application.rules_controller.split_by_assay_name_and_key", _split)
    monkeypatch.setattr(
        "src.application.rules_controller.parse",
        lambda _path: (_ for _ in ()).throw(AssertionError("derive must not parse a pdf")),
    )

    assert rules.derive_assay_block("FULL", "(7777)", "Neu") == "BLOCK"
    assert seen == {"text": "FULL", "assays": [("(7777)", "Neu")]}

    def _miss(_text: str, _assays: list[AssayDescriptor]) -> dict[str, str]:
        raise RuntimeError("content_split_failed: empty block for (miss)")

    monkeypatch.setattr("src.application.rules_controller.split_by_assay_name_and_key", _miss)
    assert rules.derive_assay_block("FULL", "(miss)", "Fehlt") == ""

    def _empty(_text: str, _assays: list[AssayDescriptor]) -> dict[str, str]:
        return {"(leer)": "   "}

    monkeypatch.setattr("src.application.rules_controller.split_by_assay_name_and_key", _empty)
    assert rules.derive_assay_block("FULL", "(leer)", "Leer") == ""

    def _unexpected(_text: str, _assays: list[AssayDescriptor]) -> dict[str, str]:
        raise RuntimeError("content_split_failed")

    monkeypatch.setattr("src.application.rules_controller.split_by_assay_name_and_key", _unexpected)
    with pytest.raises(RuntimeError, match="content_split_failed$"):
        rules.derive_assay_block("FULL", "(boom)", "Unerwartet")


def test_controller_crud_routes_only_through_rulesuite_api(tmp_path: Path) -> None:
    import src.application.rules_controller as rules_controller_module
    import src.rulesuite.api as rulesuite_api

    assert rules_controller_module.open_active_as_draft is rulesuite_api.open_active_as_draft
    assert rules_controller_module.replace_field is rulesuite_api.replace_field
    assert rules_controller_module.add_field is rulesuite_api.add_field
    assert rules_controller_module.update_draft_meta is rulesuite_api.update_draft_meta
    assert rules_controller_module.restore_draft_snapshot is rulesuite_api.restore_draft_snapshot
    assert rules_controller_module.delete_never_active_ruleset is rulesuite_api.delete_never_active_ruleset
    assert rules_controller_module.create_draft_from_template_if_missing is rulesuite_api.create_draft_from_template_if_missing

    root = _setup_project(tmp_path)
    rules = create_desktop_services(root).rules
    active = root / "rules" / "AssayA.json"
    active_before = active.read_bytes()
    opened = rules.open_active_as_draft("(1111)")
    draft = Path(opened["draft_path"])
    assert opened["status"] == "created"
    assert draft.read_bytes() == active_before

    updated = rules.replace_field(
        str(draft),
        "test",
        key="sample",
        regex=r"Sample:\s*(\w+)",
        required=True,
        search_from=None,
        excel_column=None,
        dedupe_member=None,
    )
    assert Path(updated) == draft
    loaded = json.loads(draft.read_text(encoding="utf-8"))
    assert loaded["extract_rules"]["fields"][0]["key"] == "sample"
    assert loaded["excel_rules"]["column_mapping"]["sample"] == "TEST"
    assert "test" not in loaded["excel_rules"]["column_mapping"]
    assert loaded["extract_rules"]["dedupe_fields"] == ["sample"]

    added = rules.add_field(
        str(draft),
        "extra",
        r"Extra:\s*(\w+)",
        required=False,
        search_from=None,
        excel_column="EXTRA",
        dedupe_member=True,
    )
    assert Path(added) == draft
    loaded = json.loads(draft.read_text(encoding="utf-8"))
    assert loaded["extract_rules"]["fields"][-1]["key"] == "extra"
    assert loaded["excel_rules"]["column_mapping"]["extra"] == "EXTRA"
    assert loaded["extract_rules"]["dedupe_fields"] == ["sample", "extra"]

    fresh_path = root / "rules" / "drafts" / "FRESH.draft.json"
    fresh_path.write_text(
        json.dumps({"assay_key": "FRESH", "assay_name": "Fresh", "extract_rules": {"fields": []}}),
        encoding="utf-8",
    )
    readiness = fresh_path.with_name(fresh_path.name + ".readiness")
    readiness.write_text("{}", encoding="utf-8")
    deleted = rules.delete_never_active_ruleset(str(fresh_path))
    assert deleted["status"] == "deleted"
    assert not fresh_path.exists()
    assert not readiness.exists()
    assert active.read_bytes() == active_before
