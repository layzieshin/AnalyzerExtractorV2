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
    assert first.assay_name == "Assay A"


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
    from src.contentsplitter.api import AssaySection

    rules = create_desktop_services(_setup_project(tmp_path)).rules
    seen: dict[str, object] = {}

    def _split(text: str, *, known_keys) -> list[AssaySection]:
        seen["text"] = text
        seen["keys"] = known_keys
        return [AssaySection("(7777)", "Document title", "(7777)", 0, 5, "BLOCK")]

    monkeypatch.setattr("src.application.rules_controller.split_assay_sections", _split)
    monkeypatch.setattr(
        "src.application.rules_controller.parse",
        lambda _path: (_ for _ in ()).throw(AssertionError("derive must not parse a pdf")),
    )
    monkeypatch.setattr("src.application.rules_controller.load_known_assay_keys",
                        lambda _path: pytest.fail("UI derivation must use its frozen worker context, not read files"))
    known = ("(1111)",)

    assert rules.derive_assay_block("FULL", "(7777)", "Neu", known_assay_keys=known) == "BLOCK"
    assert seen == {"text": "FULL", "keys": {"(1111)", "(7777)"}}

    def _miss(_text: str, *, known_keys) -> list[AssaySection]:
        raise RuntimeError("content_split_failed: empty block for (miss)")

    monkeypatch.setattr("src.application.rules_controller.split_assay_sections", _miss)
    with pytest.raises(RuntimeError, match="content_split_failed: empty block"):
        rules.derive_assay_block("FULL", "(miss)", "Fehlt", known_assay_keys=known)

    def _empty(_text: str, *, known_keys) -> list[AssaySection]:
        return []

    monkeypatch.setattr("src.application.rules_controller.split_assay_sections", _empty)
    with pytest.raises(ValueError, match="authoring_pdf_assay_header_missing"):
        rules.derive_assay_block("FULL", "(leer)", "Leer", known_assay_keys=known)

    def _unexpected(_text: str, *, known_keys) -> list[AssaySection]:
        raise RuntimeError("content_split_failed")

    monkeypatch.setattr("src.application.rules_controller.split_assay_sections", _unexpected)
    with pytest.raises(RuntimeError, match="content_split_failed$"):
        rules.derive_assay_block("FULL", "(boom)", "Unerwartet", known_assay_keys=known)


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


def _authoring_fixture(tmp_path):
    from src.application.api import DesktopSettings, RuleSuiteController
    from test_rulesuite import _setup_project as setup, _v2_draft

    root = setup(tmp_path)
    (root / "input").mkdir()
    draft = _v2_draft(root)
    settings = [DesktopSettings("sqlite", str(root / "selected.sqlite3"))]
    return root, draft, settings, RuleSuiteController(root, settings_provider=lambda: settings[0])


def _register_authoring_import(root, pdf, *, status="DONE"):
    from types import SimpleNamespace
    from src.ingestion.api import register_import

    return register_import(root, pdf, source_kind="manual",
        enqueue=lambda _path, _source, digest: SimpleNamespace(job_id=digest[:16], status=status, last_error="")).record


def _seed_authoring_run(root, database, pdf, *, assay_key="(1111)", identity="old", provenance=None):
    import hashlib
    from src.dbwriter.api import write_record_sqlite
    from src.extractor.api import AssayRecord
    from src.ruleresolver.api import RuleSet

    data = json.loads((root / "rules" / "AssayA.json").read_text(encoding="utf-8"))
    data["assay_key"] = assay_key
    return write_record_sqlite(AssayRecord(assay_key, "STORED_LOT", identity, {"test": "STORED_RAW", "date": "2020-01-01"}, "DEVICE"),
        RuleSet(assay_key, "Historical.json", data), str(database), job_id=identity, pdf_path=str(pdf),
        pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(), source_provenance=provenance or {"rule_sha256": "a" * 64}).run_id


def test_authoring_controller_current_import_first_is_read_only_and_does_not_query_history(tmp_path, monkeypatch):
    from test_rulesuite import _v2_pdf
    import src.application.results_controller as owner

    root, draft, _settings, rules = _authoring_fixture(tmp_path)
    primary = _v2_pdf(root / "chosen.pdf")
    secondary = _v2_pdf(root / "input" / "known.pdf", value="OTHER")
    record = _register_authoring_import(root, secondary)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    monkeypatch.setattr(owner, "list_result_runs", lambda *_a, **_k: pytest.fail("known current eligible import must precede DB fallback"))
    proof = rules.create_authoring_proof("(1111)", draft, str(primary))
    assert proof["version"] == 2 and proof["status"] == "ready"
    assert proof["secondary"]["source"]["kind"] == "current_import"
    assert proof["secondary"]["source"]["ingestion_id"] == record.ingestion_id
    assert {path: path.read_bytes() for path in before} == before
    assert rules.verify_authoring_proof("(1111)", draft)["ok"]
    assert not (root / "selected.sqlite3").exists()


@pytest.mark.parametrize("reason", ["archived", "moving", "backup", "changed_hash", "missing", "ambiguous", "moved_only"])
def test_authoring_controller_rejects_nonlocal_or_unresolved_import_sources(tmp_path, reason):
    from dataclasses import replace
    from uuid import uuid4
    from src.ingestion.store import save_record
    from test_rulesuite import _v2_pdf

    root, draft, _settings, rules = _authoring_fixture(tmp_path)
    primary = _v2_pdf(root / "chosen.pdf")
    secondary = _v2_pdf(root / "input" / "known.pdf", value="OTHER")
    record = _register_authoring_import(root, secondary)
    if reason == "archived":
        save_record(root, replace(record, archive_status="ARCHIVED", archived_at_utc="2026-01-01T00:00:00Z"))
    elif reason == "moving":
        save_record(root, replace(record, archive_status="MOVING"))
    elif reason == "backup":
        save_record(root, replace(record, watch_backup_path=str(secondary.parent)))
    elif reason == "changed_hash":
        save_record(root, replace(record, content_sha256="0" * 64))
    elif reason == "missing":
        secondary.unlink()
    elif reason == "ambiguous":
        save_record(root, replace(record, ingestion_id=str(uuid4())))
    else:
        moved = root / "input" / "moved.pdf"
        secondary.rename(moved)
        save_record(root, replace(record, current_path=str(moved), archive_status="PENDING"))
    proof = rules.create_authoring_proof("(1111)", draft, str(primary))
    assert proof["status"] == "ready" and proof["secondary"]["status"] == "not_available"


@pytest.mark.parametrize("next_state", ["archived", "ambiguous"])
def test_authoring_controller_source_completion_is_allowed_but_archival_or_new_ambiguity_revokes(tmp_path, next_state):
    from dataclasses import replace
    from uuid import uuid4
    from src.ingestion.store import save_record
    from test_rulesuite import _v2_pdf

    root, draft, _settings, rules = _authoring_fixture(tmp_path)
    primary = _v2_pdf(root / "chosen.pdf")
    secondary = _v2_pdf(root / "input" / "known.pdf", value="OTHER")
    record = _register_authoring_import(root, secondary, status="PENDING")
    assert rules.create_authoring_proof("(1111)", draft, str(primary))["status"] == "ready"
    done = replace(record, processing_status="DONE", updated_at_utc="2026-11-26T23:59:59Z")
    save_record(root, done)
    assert rules.verify_authoring_proof("(1111)", draft)["ok"]
    save_record(root, replace(done, ingestion_id=str(uuid4())) if next_state == "ambiguous" else replace(done, archive_status="ARCHIVED"))
    assert "authoring_proof_source_changed" in rules.verify_authoring_proof("(1111)", draft)["errors"]


@pytest.mark.parametrize("store_kind", ["absent", "empty", "corrupt", "incompatible"])
def test_authoring_controller_empty_history_is_yellow_but_invalid_existing_store_blocks(tmp_path, store_kind):
    import sqlite3
    from test_rulesuite import _v2_pdf

    root, draft, settings, rules = _authoring_fixture(tmp_path)
    database = Path(settings[0].sqlite_path)
    if store_kind == "corrupt":
        database.write_bytes(b"not a sqlite database")
    elif store_kind in {"empty", "incompatible"}:
        with sqlite3.connect(database) as conn:
            if store_kind == "incompatible":
                conn.execute("CREATE TABLE runs (id INTEGER, incompatible TEXT)")
    before = database.read_bytes() if database.exists() else None
    primary = _v2_pdf(root / "chosen.pdf")
    proof = rules.create_authoring_proof("(1111)", draft, str(primary))
    assert proof["status"] == ("blocked" if store_kind in {"corrupt", "incompatible"} else "ready")
    assert proof["secondary"]["status"] == ("failed" if proof["status"] == "blocked" else "not_available")
    assert (database.read_bytes() if database.exists() else None) == before


def test_authoring_controller_finds_older_exact_assay_past_fifty_other_reports_and_freezes_selected_rule(tmp_path):
    from src.dbwriter.api import append_result_revision, select_result_revision
    from src.resultstore.api import get_result_run
    from test_rulesuite import _v2_pdf

    root, draft, settings, rules = _authoring_fixture(tmp_path)
    database = Path(settings[0].sqlite_path)
    primary = _v2_pdf(root / "chosen.pdf")
    secondary = _v2_pdf(root / "input" / "older.pdf", value="OLDER")
    run_id = _seed_authoring_run(root, database, secondary)
    state = get_result_run({"path": str(database)}, run_id)
    snapshot = {"assay_key": "(1111)", "device_id": "DEVICE", "payload": {"test": "SELECTED_RAW", "date": "2020-01-02"},
        "lot_id": "SELECTED_LOT", "dedupe_key": "selected-key", "dedupe_version": "v2", "dedupe_basis": {},
        "ruleset_file": "Selected.json", "ruleset": state["source_provenance"]["ruleset"], "rule_sha256": "b" * 64,
        "source_verified": True, "source_provenance": state["source_provenance"], "error": ""}
    revision = append_result_revision(str(database), run_id, expected_selection_token=state["selection_token"], request_id="selected", snapshot=snapshot, created_by="RR")
    pending = get_result_run({"path": str(database)}, run_id)
    select_result_revision(str(database), run_id, revision["revision_id"], expected_selection_token=pending["selection_token"], action="accept_new", request_id="choose", decided_by="RR")
    selected = get_result_run({"path": str(database)}, run_id)
    append_result_revision(str(database), run_id, expected_selection_token=selected["selection_token"], request_id="later-pending", snapshot={**snapshot, "rule_sha256": "d" * 64}, created_by="RR")
    foreign = _v2_pdf(root / "input" / "foreign.pdf", header="Other Assay (2222)")
    for index in range(55):
        _seed_authoring_run(root, database, foreign, assay_key="(2222)", identity=f"newer-unrelated-{index}")
    before = database.read_bytes()
    proof = rules.create_authoring_proof("(1111)", draft, str(primary))
    source = proof["secondary"]["source"]
    assert proof["status"] == "ready" and source["kind"] == "result_history"
    assert source["run_id"] == run_id and source["path"] == str(secondary.resolve())
    assert source["ruleset_sha256"] == "b" * 64 and source["source_rule_sha256"] == "a" * 64
    assert source["ruleset_file"] == "Selected.json" and source["revision_id"] == revision["revision_id"]
    assert "pending" in source["selection_token"]
    assert rules.verify_authoring_proof("(1111)", draft)["ok"] and database.read_bytes() == before


def test_authoring_controller_history_lookup_and_existing_proof_remain_bound_to_selected_store(tmp_path, monkeypatch):
    from dataclasses import replace
    from test_rulesuite import _v2_pdf
    import src.application.results_controller as owner

    root, draft, settings, rules = _authoring_fixture(tmp_path)
    first, second = Path(settings[0].sqlite_path), root / "other.sqlite3"
    primary = _v2_pdf(root / "chosen.pdf")
    known = _v2_pdf(root / "input" / "known.pdf", value="KNOWN")
    other = _v2_pdf(root / "input" / "other.pdf", value="OTHER")
    _seed_authoring_run(root, first, known)
    _seed_authoring_run(root, second, other)
    before = first.read_bytes(), second.read_bytes()
    original = owner.list_result_runs

    def switch(*args, **kwargs):
        rows = original(*args, **kwargs)
        settings[0] = replace(settings[0], sqlite_path=str(second))
        return rows

    monkeypatch.setattr(owner, "list_result_runs", switch)
    blocked = rules.create_authoring_proof("(1111)", draft, str(primary))
    assert blocked["status"] == "blocked"
    settings[0] = replace(settings[0], sqlite_path=str(first))
    monkeypatch.setattr(owner, "list_result_runs", original)
    assert rules.create_authoring_proof("(1111)", draft, str(primary))["status"] == "ready"
    settings[0] = replace(settings[0], sqlite_path=str(second))
    assert rules.verify_authoring_proof("(1111)", draft)["errors"] == ["authoring_proof_source_store_changed"]
    assert (first.read_bytes(), second.read_bytes()) == before


def test_authoring_controller_old_v1_precheck_cannot_bypass_new_v2_attempt(tmp_path, monkeypatch):
    from src.rulesuite.api import create_authoring_proof
    from test_rulesuite import _fake_authoring_preview, _v2_pdf

    root, draft, _settings, rules = _authoring_fixture(tmp_path)
    primary = _v2_pdf(root / "failing.pdf")
    reference = _v2_pdf(root / "reference.pdf", value="OTHER")
    monkeypatch.setattr("src.rulesuite.rulesuite.RuleSuite.preview_extract", _fake_authoring_preview)
    create_authoring_proof(str(root), "(1111)", draft, str(primary), str(reference))
    checked = rules.verify_authoring_proof("(1111)", draft)
    assert checked["ok"] and checked["proof"]["version"] == 1
    active = root / "rules" / "AssayA.json"
    before = active.read_bytes()

    def old_precheck(*_args):
        create_authoring_proof(str(root), "(1111)", draft, str(root / "missing.pdf"), automatic_sources=lambda: ())
        return checked

    monkeypatch.setattr(rules, "verify_authoring_proof", old_precheck)
    with pytest.raises(AuthoringReadinessError, match="not_ready"):
        rules.activate_draft("(1111)", draft)
    assert active.read_bytes() == before and not (root / "rules" / "history").exists()


@pytest.mark.parametrize("mode", ["create", "update"])
def test_authoring_commit_chooses_current_mode_in_controller_and_keeps_exact_bytes(tmp_path, mode):
    from test_rulesuite import _v2_pdf

    root, draft, _settings, rules = _authoring_fixture(tmp_path)
    key, name = "(1111)", "Assay A"
    if mode == "create":
        key, name = "(7777)", "New Assay"
        data = json.loads(Path(draft).read_text(encoding="utf-8"))
        data.update(assay_key=key, assay_name=name)
        Path(draft).write_text(json.dumps(data), encoding="utf-8")
    pdf = _v2_pdf(root / "chosen.pdf", header=f"Instrument Alpha {key}")
    outcome = rules.create_authoring_proof(key, draft, str(pdf))
    assert outcome["status"] == "ready"
    receipt = rules.verify_authoring_proof(key, draft)["proof"]
    before = Path(draft).read_bytes()
    target = rules.activate_draft(key, draft, assay_name=name, authoring_proof=receipt, expected_mode=mode)
    assert Path(target).read_bytes() == before


def test_authoring_commit_rechecks_confirmed_receipt_under_existing_lock(tmp_path, monkeypatch):
    import src.application.rules_controller as owner
    from test_rulesuite import _v2_pdf

    root, draft, _settings, rules = _authoring_fixture(tmp_path)
    pdf = _v2_pdf(root / "chosen.pdf")
    rules.create_authoring_proof("(1111)", draft, str(pdf))
    receipt = rules.verify_authoring_proof("(1111)", draft)["proof"]
    active, commit = root / "rules" / "AssayA.json", owner.activate_draft
    before = active.read_bytes()

    def replace_after_controller_check(*args, **kwargs):
        assert kwargs["authoring_proof"] == receipt
        newer = rules.create_authoring_proof("(1111)", draft, str(pdf))
        assert newer["status"] == "ready" and newer["attempt_id"] != receipt["attempt_id"]
        return commit(*args, **kwargs)

    monkeypatch.setattr(owner, "activate_draft", replace_after_controller_check)
    with pytest.raises(AuthoringReadinessError, match="attempt_changed"):
        rules.activate_draft("(1111)", draft, assay_name="Assay A", authoring_proof=receipt, expected_mode="update")
    assert active.read_bytes() == before and not (root / "rules" / "history").exists()


def test_authoring_commit_never_silently_changes_confirmed_create_update_intent(tmp_path):
    from test_rulesuite import _v2_pdf

    root, draft, _settings, rules = _authoring_fixture(tmp_path)
    pdf = _v2_pdf(root / "chosen.pdf")
    rules.create_authoring_proof("(1111)", draft, str(pdf))
    receipt = rules.verify_authoring_proof("(1111)", draft)["proof"]
    active = root / "rules" / "AssayA.json"
    before = active.read_bytes()
    with pytest.raises(AuthoringReadinessError, match="mapping_changed"):
        rules.activate_draft("(1111)", draft, assay_name="Assay A", authoring_proof=receipt, expected_mode="create")
    assert active.read_bytes() == before and not (root / "rules" / "history").exists()


@pytest.mark.parametrize("mixed,key,document_key", [(False, "(1C9E)", "(1c9e)"), (True, "(1c9e)", "(1C9E)")])
def test_authoring_same_pdf_bytes_activate_import_and_preview_share_exact_sections(tmp_path, mixed, key, document_key):
    import hashlib
    import fitz
    from src.application.api import DesktopSettings, RuleSuiteController
    from src.jobcontroller.api import submit
    from src.resultstore.api import get_result_run, list_result_runs
    from src.rulesuite.api import load_draft

    root = tmp_path / "synthetic"
    (root / "rules").mkdir(parents=True)
    database = root / "selected.sqlite"
    spec = {"driver": "sqlite", "path": str(database)}
    fields = {"PLATTE": r"Plate:\s*(\S+)", "DATUM": r"Date:\s*([0-9-]+)", "ZEIT": r"Time:\s*([0-9:]+)",
              "TEST": r"Test:\s*(.+\.asy\s+\([0-9a-fA-F]{4}\))", "PC_IST": r"Value:\s*([0-9.]+)"}
    other = {"assay_key": "(2f4a)", "assay_name": "Another internal display name", "lot_rule": {"regex": r"Lot:\s*(\S+)"},
             "extract_rules": {"fields": [{"key": field, "regex": regex, "required": True} for field, regex in fields.items()]},
             "excel_rules": {"excel_filename_template": "{assay_name}.xlsx", "sheetname_template": "{lot_id}", "column_mapping": {}}}
    other_path = root / "rules" / "other.json"
    other_path.write_text(json.dumps(other), encoding="utf-8")
    (root / "rules" / "index.json").write_text(json.dumps({"assays": [{"assay_key": "(2f4a)", "ruleset_file": "other.json"}]}), encoding="utf-8")
    other_before = other_path.read_bytes()
    rules = RuleSuiteController(root, settings_provider=lambda: DesktopSettings("sqlite", str(database)))
    name = "Internal profile different from manufacturer title"
    draft = rules.create_blank_draft(key, name)
    rules.set_lot_rule(draft, r"Lot:\s*(\S+)")
    for field, regex in fields.items():
        rules.add_field(draft, field, regex, required=True)
    rules.set_excel_rules(draft, "{assay_name}.xlsx", "{lot_id}", {field: field for field in fields})
    target = ["Earlier reference to Instrument Alpha", "Instrument Alpha", "Plate: P_A", "Lot: LOT_A", "Date: 2026-11-26", "Time: 09:15:00",
              rf"Test: C:\Assays\Instrument Alpha.asy {document_key}", "Referenzwerte (U/mL)", "Einheit (IU)", "Value: 106.4"]
    following = ["Unknown assay (FADE)", "Value: 999.9", "Date: 1999-01-01"]
    if mixed:
        following += ["Instrument Beta", "Plate: P_B", "Lot: LOT_B", "Date: 2026-11-25", "Time: 08:00:00",
                      r"Test: C:\Assays\Instrument Beta.asy (2F4A)", "Value: 105.2"]
    def write_pdf(path, lines):
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((35, 35), "\n".join(lines), fontsize=9)
            document.save(path)
        return path
    pdf = write_pdf(root / "chosen.pdf", target + following)
    source_bytes = pdf.read_bytes()
    preview = rules.get_assay_text(str(pdf), key, name, draft_path=draft)
    assert rules.derive_assay_block(preview["normalized_text"], key, name) == preview["assay_block"]
    assert "Referenzwerte (U/mL)" in preview["assay_block"] and "999.9" not in preview["assay_block"]
    proof = rules.create_authoring_proof(key, draft, str(pdf))
    assert proof["status"] == "ready" and proof["primary"]["data"]["PC_IST"] == "106.4"
    assert proof["primary"]["sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert proof["secondary"]["status"] == "not_available" and not database.exists()
    receipt = rules.verify_authoring_proof(key, draft)["proof"]
    published = rules.activate_draft(key, draft, assay_name=name, authoring_proof=receipt, expected_mode="create")
    assert Path(published).read_bytes() == Path(draft).read_bytes()
    imported = submit(str(pdf), str(root), sqlite_path=str(database), device_id="SYNTHETIC")
    assert imported.status == "DONE", imported.details
    assert pdf.read_bytes() == source_bytes and other_path.read_bytes() == other_before
    writes = {item["assay_key"]: item for item in imported.details["writes"]}
    assert set(writes) == ({key, "(2f4a)"} if mixed else {key})
    assert writes[key]["data"] == proof["primary"]["data"] and writes[key]["lot_id"] == proof["primary"]["lot_id"] == "LOT_A"
    row = get_result_run(spec, writes[key]["sqlite_run_id"])
    source = row["source_provenance"]
    normalized = preview["normalized_text"]
    assert normalized[source["block_start"]:source["block_end"]] == preview["assay_block"]
    assert source["pdf_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert row["payload"] == proof["primary"]["data"]
    # A later assay has a date, but neither preview/proof nor import may borrow it.
    incomplete = write_pdf(root / "missing-date.pdf", [line for line in target if not line.startswith("Date:")] + following)
    blocked = rules.create_authoring_proof(key, draft, str(incomplete))
    assert blocked["status"] == "blocked" and blocked["primary"]["missing_fields"] == ["DATUM"]
    failed = submit(str(incomplete), str(root), sqlite_path=str(database), device_id="SYNTHETIC")
    assert failed.status == "FAILED" and failed.details["error"] == "configured_fields_empty: DATUM"
    assert len(list_result_runs(spec)["runs"]) == len(writes)
    assert load_draft(draft)["assay_name"] == name


def test_authoring_rejects_case_alias_before_proof_and_under_activation_lock(tmp_path):
    from test_rulesuite import _v2_pdf
    from src.rulesuite.api import activate_new_draft
    root, draft, _settings, rules = _authoring_fixture(tmp_path)
    active = root / "rules" / "AssayA.json"
    data = json.loads(active.read_text(encoding="utf-8"))
    data["assay_key"] = "(ABCD)"
    active.write_text(json.dumps(data), encoding="utf-8")
    index = root / "rules" / "index.json"
    index.write_text(json.dumps({"assays": [{"assay_key": "(ABCD)", "ruleset_file": active.name}]}), encoding="utf-8")
    draft_data = json.loads(Path(draft).read_text(encoding="utf-8"))
    draft_data.update(assay_key="(abcd)", assay_name="Different display name")
    Path(draft).write_text(json.dumps(draft_data), encoding="utf-8")
    before = {path: path.read_bytes() for path in (index, active)}
    pdf = _v2_pdf(root / "chosen.pdf", header="Instrument Alpha (ABCD)")
    with pytest.raises(AuthoringReadinessError, match="case_conflict"):
        rules.create_authoring_proof("(abcd)", draft, str(pdf))
    assert not rules.verify_authoring_proof("(abcd)", draft)["ok"]
    # Legacy callers without a product receipt still cannot create a duplicate
    # canonical ID; the guard runs in the existing lifecycle commit lock.
    with pytest.raises(RuleSuiteError, match="assay_key_exists"):
        activate_new_draft(str(root), "(abcd)", "Different display name", draft)
    assert {path: path.read_bytes() for path in before} == before
    assert not (root / "rules" / "Different display name.json").exists()


def test_known_foreign_special_key_bounds_editor_wizard_proof_and_import(tmp_path):
    import fitz
    from src.jobcontroller.api import submit
    from src.rulesuite.api import activate_draft
    root, draft, settings, rules = _authoring_fixture(tmp_path)
    activate_draft(str(root), "(1111)", draft)
    index = root / "rules" / "index.json"
    configured = json.loads(index.read_text(encoding="utf-8"))
    configured["assays"].append({"assay_key": "(ZZ01)", "ruleset_file": "special.json"})
    index.write_text(json.dumps(configured), encoding="utf-8")
    (root / "rules" / "special.json").write_text(json.dumps({"assay_key": "(ZZ01)", "assay_name": "Other special profile",
        "lot_rule": {"regex": r"Lot:\s*(\w+)"}, "extract_rules": {"fields": [{"key": "test", "regex": r"Test:\s*(\w+)"}]},
        "excel_rules": {"excel_filename_template": "special.xlsx", "sheetname_template": "{lot_id}"}}), encoding="utf-8")
    pdf = root / "missing-before-special.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((35, 35), "\n".join(["Instrument Alpha (1111)", "Lot: TARGET", "Test: TARGET",
                         "Other manufacturer (ZZ01)", "Lot: OTHER", "Test: FOREIGN", "Date: 2099-01-01"]), fontsize=9)
        document.save(pdf)
    context = rules.load_authoring_pdf_context(str(pdf))
    assert "(zz01)" in context["known_assay_keys"]
    block = rules.derive_assay_block(context["normalized_text"], "(1111)", "Assay A", known_assay_keys=context["known_assay_keys"])
    preview = rules.get_assay_text(str(pdf), "(1111)", "Assay A", draft_path=draft)
    assert block == preview["assay_block"] and "2099" not in block and "FOREIGN" not in block
    assert preview["detected_assays"] == ["(1111)", "(zz01)"]
    proof = rules.create_authoring_proof("(1111)", draft, str(pdf))
    assert proof["status"] == "blocked" and proof["primary"]["missing_fields"] == ["date"]
    result = submit(str(pdf), str(root), sqlite_path=settings[0].sqlite_path)
    assert result.status == "FAILED" and result.details["error"] == "configured_fields_empty: date"
    assert not Path(settings[0].sqlite_path).exists()


@pytest.mark.parametrize("change", ["ordinary-hex", "special", "old-v2"])
def test_authoring_proof_binds_effective_special_key_context_only(tmp_path, change):
    from src.rulesuite.authoring_readiness import _proof_digest
    from test_rulesuite import _v2_pdf
    root, draft, _settings, rules = _authoring_fixture(tmp_path)
    pdf = _v2_pdf(root / "chosen.pdf")
    proof = rules.create_authoring_proof("(1111)", draft, str(pdf))
    assert proof["status"] == "ready"
    sidecar = Path(draft + ".readiness")
    if change == "old-v2":
        old = json.loads(sidecar.read_text(encoding="utf-8"))
        old["activation_baseline"].pop("section_keys")
        old["activation_baseline"].pop("known_assay_keys")
        old["proof_sha256"] = _proof_digest(old)
        sidecar.write_text(json.dumps(old), encoding="utf-8")
    else:
        index = root / "rules" / "index.json"
        data = json.loads(index.read_text(encoding="utf-8"))
        data["assays"].append({"assay_key": "(3333)" if change == "ordinary-hex" else "(ZZ01)", "ruleset_file": "other.json"})
        index.write_text(json.dumps(data), encoding="utf-8")
    before = sidecar.read_bytes()
    checked = rules.verify_authoring_proof("(1111)", draft)
    assert checked["ok"] is (change == "ordinary-hex")
    if change != "ordinary-hex":
        assert "authoring_proof_section_context_changed" in checked["errors"]
    assert sidecar.read_bytes() == before
