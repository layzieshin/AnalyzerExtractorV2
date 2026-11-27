import hashlib
import json
from pathlib import Path

import pytest

from src.contentsplitter.api import split_assay_sections
from src.jobcontroller.api import submit
from src.parser.model import ParsedDocument, ParsedPage
from src.resultstore.api import list_result_runs
from src.rulesuite.api import RuleSuiteError, list_assay_identity_cases, observe_assay_identity_changes


def _project(root, assays=(("(1111)", "Assay A"),)):
    (root / "rules").mkdir(parents=True)
    entries = []
    for index, (key, name) in enumerate(assays):
        filename = f"assay{index}.json"
        entries.append({"assay_key": key, "ruleset_file": filename})
        rule = {"assay_key": key, "assay_name": name, "lot_rule": {"regex": r"Lot: (\w+)"},
                "extract_rules": {"fields": [{"key": "value", "regex": r"Value: (\S+)"}], "dedupe_fields": ["value"]},
                "excel_rules": {"excel_filename_template": "{assay_name}.xlsx", "sheetname_template": "{lot_id}", "column_mapping": {}}}
        (root / "rules" / filename).write_text(json.dumps(rule), encoding="utf-8")
    (root / "rules" / "index.json").write_text(json.dumps({"assays": entries}), encoding="utf-8")
    return root / "results.sqlite3"


def _block(name="Assay A", key="(2222)", value="42"):
    return f"{name}\nLot: LOT-A\nTest: C:\\Assays\\{name}.asy {key}\nValue: {value}"


def _parser(monkeypatch, documents):
    def parse(path):
        text = documents[Path(path).read_bytes()]
        return ParsedDocument(source_path=path, pages=[ParsedPage(page_number=1, lines=text.splitlines())], meta={"page_count": 1})

    monkeypatch.setattr("src.parser.api.parse", parse)
    monkeypatch.setattr("src.rulesuite.rulesuite.parse", parse)


def _observe(root, store, text, *, payload=b"synthetic-new-id", filename="input.pdf"):
    pdf = root / filename
    pdf.write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    return observe_assay_identity_changes(str(root), store_path=str(store), pdf_path=str(pdf), pdf_sha256=sha,
        job_id=sha[:16], device_id="TEST", normalized_text=text, sections=split_assay_sections(text, known_keys=["(1111)"]))


@pytest.mark.parametrize("mixed", [False, True])
def test_import_persists_known_name_new_id_before_any_assay_sink(tmp_path, monkeypatch, mixed):
    store = _project(tmp_path)
    text = (_block(key="(1111)") + "\n" if mixed else "") + _block()
    pdf = tmp_path / "incoming.pdf"
    pdf.write_bytes(b"new-mixed" if mixed else b"new-single")
    _parser(monkeypatch, {pdf.read_bytes(): text})
    original_rules = {path.name: path.read_bytes() for path in (tmp_path / "rules").glob("*.json")}

    def forbid(*args, **kwargs):
        raise AssertionError("neither extraction nor an output sink may run")

    monkeypatch.setattr("src.extractor.api.extract_record", forbid)
    monkeypatch.setattr("src.dbwriter.api.write_record_sqlite", forbid)
    result = submit(str(pdf), str(tmp_path), sqlite_path=str(store))
    assert result.status == "FAILED"
    assert result.details["error"] == "assay_identity_change_pending"
    cases = list_assay_identity_cases(str(tmp_path), store_path=str(store))
    assert len(cases) == 1 and cases[0]["case_id"] in result.details["identity_case_ids"]
    case = cases[0]
    assert case["status"] == "open" and case["assay_key"] == "(2222)"
    assert "selected_assay_key" not in case
    assert [row["assay_key"] for row in case["candidate_assays"]] == ["(1111)"]
    source = case["sources"][0]
    assert source["pdf_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert source["assay_block_sha256"] == hashlib.sha256(_block().encode()).hexdigest()
    normalized = (tmp_path / "jobs" / f"{result.job_id}_normalized.txt").read_text(encoding="utf-8")
    assert normalized[source["block_start"]:source["block_end"]] == _block()
    state = json.loads((tmp_path / "jobs" / f"{result.job_id}.json").read_text(encoding="utf-8"))
    assert state["identity_case_ids"] == result.details["identity_case_ids"]
    assert "output_plan" not in state and "writes" not in state
    assert not store.exists()
    assert {path.name: path.read_bytes() for path in (tmp_path / "rules").glob("*.json")} == original_rules
    assert not (tmp_path / "rules" / "changes").exists()
    receipt = (tmp_path / "storage" / "rulesuite" / "identity_cases.json").read_text(encoding="utf-8")
    assert "Value:" not in receipt and "LOT-A" not in receipt and "normalized_text" not in receipt


@pytest.mark.parametrize("evidence_kind", ["provenance", "job_step"])
def test_actual_historical_report_name_is_known_despite_different_display_and_done_stays_exact(tmp_path, monkeypatch, evidence_kind):
    store = _project(tmp_path, (("(1111)", "Internal display, not manufacturer spelling"),))
    old_pdf, new_pdf = tmp_path / "old.pdf", tmp_path / "new.pdf"
    old_pdf.write_bytes(b"old-complete")
    new_pdf.write_bytes(b"new-identity")
    _parser(monkeypatch, {b"old-complete": _block("Manufacturer Report", "(1111)"),
                          b"new-identity": _block("Manufacturer Report", "(2222)")})
    with monkeypatch.context() as legacy:
        if evidence_kind == "job_step":
            # Build the legacy shape at insertion, never rewrite immutable
            # evidence after the completed result has been persisted.
            legacy.setattr("src.jobcontroller.jobcontroller.JobController._source_provenance", lambda *args: {})
        old_result = submit(str(old_pdf), str(tmp_path), sqlite_path=str(store))
    assert old_result.status == "DONE", old_result.details
    state = tmp_path / "jobs" / f"{old_result.job_id}.json"
    old_state, old_db = state.read_bytes(), store.read_bytes()
    new_result = submit(str(new_pdf), str(tmp_path), sqlite_path=str(store))
    assert new_result.status == "FAILED" and new_result.details["error"] == "assay_identity_change_pending"
    case = list_assay_identity_cases(str(tmp_path), store_path=str(store))[0]
    candidate = case["candidate_assays"][0]
    assert candidate["assay_name"] == "Internal display, not manufacturer spelling"
    assert any(row["kind"] == "report_history" and row["name"] == "Manufacturer Report" for row in candidate["name_evidence"])
    assert state.read_bytes() == old_state and store.read_bytes() == old_db
    assert submit(str(old_pdf), str(tmp_path), sqlite_path=str(store)).status == "SKIPPED"
    assert state.read_bytes() == old_state and store.read_bytes() == old_db
    assert len(list_result_runs({"driver": "sqlite", "path": str(store)}, limit=None)["runs"]) == 1


def test_current_known_section_supplies_exact_document_name_without_history(tmp_path):
    store = _project(tmp_path, (("(1111)", "Internal Alias"),))
    cases = _observe(tmp_path, store, _block("Manufacturer", "(1111)") + "\n" + _block("Manufacturer"))
    assert len(cases) == 1
    assert cases[0]["candidate_assays"][0]["name_evidence"][0]["kind"] == "current_report"


@pytest.mark.parametrize("mixed", [False, True])
def test_unrelated_unknown_report_is_not_reclassified_as_known_family(tmp_path, monkeypatch, mixed):
    store = _project(tmp_path)
    text = (_block(key="(1111)") + "\n" if mixed else "") + _block("Entirely Different")
    pdf = tmp_path / "unknown.pdf"
    pdf.write_bytes(b"unrelated")
    _parser(monkeypatch, {b"unrelated": text})
    result = submit(str(pdf), str(tmp_path), sqlite_path=str(store))
    assert result.status == ("DONE" if mixed else "FAILED")
    if not mixed:
        assert result.details["error"] == "no_assay_detected"
    assert list_assay_identity_cases(str(tmp_path), store_path=str(store)) == []
    assert not (tmp_path / "storage" / "rulesuite").exists()


def test_multiple_pdf_sources_are_idempotent_and_do_not_revise_identity_decision(tmp_path):
    store = _project(tmp_path)
    first = _observe(tmp_path, store, _block(), payload=b"first", filename="same-one.pdf")[0]
    path = tmp_path / "storage" / "rulesuite" / "identity_cases.json"
    previous = path.read_bytes()
    repeated = _observe(tmp_path, store, _block(), payload=b"first", filename="same-one.pdf")[0]
    assert path.read_bytes() == previous and repeated == first
    second = _observe(tmp_path, store, _block(value="99"), payload=b"second", filename="same-two.pdf")[0]
    assert second["case_id"] == first["case_id"] and second["identity_token"] == first["identity_token"]
    assert second["source_revision"] == 2 and len(second["sources"]) == 2
    assert {row["pdf_sha256"] for row in second["sources"]} == {hashlib.sha256(raw).hexdigest() for raw in (b"first", b"second")}
    assert {row["assay_block_sha256"] for row in second["sources"]} == {hashlib.sha256(text.encode()).hexdigest() for text in (_block(), _block(value="99"))}


def test_ambiguous_exact_name_is_only_a_choice_not_an_assignment(tmp_path):
    store = _project(tmp_path, (("(1111)", "Assay A"), ("(ABCD)", "Assay A")))
    case = _observe(tmp_path, store, _block())[0]
    assert case["requires_selection"] is True
    assert {row["assay_key"] for row in case["candidate_assays"]} == {"(1111)", "(ABCD)"}
    assert "selected_assay_key" not in case


def test_store_and_id_case_normalization_are_precise_not_aliases(tmp_path):
    store = _project(tmp_path)
    first = _observe(tmp_path, store, _block(key="(ABCD)"))[0]
    same = _observe(tmp_path, store, _block(key="(abcd)"), payload=b"case")[0]
    other = _observe(tmp_path, tmp_path / "other.sqlite3", _block(key="(ABCD)"), payload=b"other")[0]
    assert first["case_id"] == same["case_id"] != other["case_id"]
    assert len(list_assay_identity_cases(str(tmp_path), store_path=str(store))) == 1
    assert len(list_assay_identity_cases(str(tmp_path), store_path=str(tmp_path / "other.sqlite3"))) == 1
    assert {row["raw_assay_key"] for row in same["sources"]} == {"(ABCD)", "(abcd)"}


def test_case_read_is_nonmutating_on_fresh_root_and_requires_store(tmp_path):
    assert list_assay_identity_cases(str(tmp_path), store_path=str(tmp_path / "store.sqlite3")) == []
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(RuleSuiteError, match="store_required"):
        list_assay_identity_cases(str(tmp_path), store_path="")


def test_multi_unknown_known_names_publish_one_atomic_batch(tmp_path, monkeypatch):
    store = _project(tmp_path, (("(1111)", "Assay A"), ("(3333)", "Assay B")))
    from src.rulesuite import identity_cases

    actual, writes = identity_cases._write_json_atomic, []

    def record(path, payload):
        writes.append(set(payload["cases"]))
        actual(path, payload)

    monkeypatch.setattr(identity_cases, "_write_json_atomic", record)
    cases = _observe(tmp_path, store, _block() + "\n" + _block("Assay B", "(4444)"))
    assert len(cases) == 2 and len(writes) == 1 and writes[0] == {case["case_id"] for case in cases}


def test_failed_persistence_or_changed_active_catalogue_prevents_import_output(tmp_path, monkeypatch):
    store = _project(tmp_path)
    pdf = tmp_path / "new.pdf"
    pdf.write_bytes(b"failure")
    _parser(monkeypatch, {b"failure": _block()})
    from src.rulesuite import identity_cases

    def fail(path, payload):
        raise OSError("synthetic persistence failure")

    monkeypatch.setattr(identity_cases, "_write_json_atomic", fail)
    result = submit(str(pdf), str(tmp_path), sqlite_path=str(store))
    assert result.status == "FAILED" and "synthetic persistence failure" in result.details["error"]
    assert not store.exists() and list_assay_identity_cases(str(tmp_path), store_path=str(store)) == []
    original = identity_cases._active_catalogue
    calls = []

    def changed(root, *, expected_index_sha256=None):
        active, signature = original(root, expected_index_sha256=expected_index_sha256)
        calls.append(None)
        return active, signature if len(calls) == 1 else "changed"

    monkeypatch.setattr(identity_cases, "_active_catalogue", changed)
    result = submit(str(pdf), str(tmp_path), sqlite_path=str(store))
    assert result.status == "FAILED" and "active_rules_changed" in result.details["error"]
    assert not store.exists()


def test_existing_corrupt_history_is_not_silently_no_known_report_names(tmp_path):
    store = _project(tmp_path)
    store.write_bytes(b"corrupt SQLite")
    with pytest.raises(RuleSuiteError, match="history_unreadable"):
        _observe(tmp_path, store, _block())
    assert not (tmp_path / "storage" / "rulesuite").exists()


def test_redirected_private_storage_is_rejected_without_foreign_write(tmp_path, monkeypatch):
    store = _project(tmp_path)
    redirected = tmp_path / "storage"
    target = tmp_path / "foreign"
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        return target if path == redirected else original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(RuleSuiteError, match="storage_redirected"):
        _observe(tmp_path, store, _block())
    assert not target.exists() and not redirected.exists()


def test_known_import_does_not_read_history_or_scan_other_rules(tmp_path, monkeypatch):
    store = _project(tmp_path)
    pdf = tmp_path / "known.pdf"
    pdf.write_bytes(b"known")
    _parser(monkeypatch, {b"known": _block(key="(1111)")})

    def forbid(*args, **kwargs):
        raise AssertionError("ordinary known import needs no identity discovery")

    monkeypatch.setattr("src.rulesuite.api.observe_assay_identity_changes", forbid)
    result = submit(str(pdf), str(tmp_path), sqlite_path=str(store))
    assert result.status == "DONE", result.details


def test_history_keeps_one_witness_per_name_and_never_projects_revisions(tmp_path, monkeypatch):
    store = _project(tmp_path, (("(1111)", "Internal"),))
    pdf = tmp_path / "old.pdf"
    documents = {}
    for index in range(3):
        payload = f"old-{index}".encode()
        documents[payload] = _block("Manufacturer", "(1111)", value=str(index))
    _parser(monkeypatch, documents)
    for payload in documents:
        pdf.write_bytes(payload)
        assert submit(str(pdf), str(tmp_path), sqlite_path=str(store)).status == "DONE"

    def forbid(*args, **kwargs):
        raise AssertionError("identity discovery must not project result revisions")

    monkeypatch.setattr("src.resultstore.sqlite_store.project_run", forbid)
    case = _observe(tmp_path, store, _block("Manufacturer"))[0]
    witnesses = case["candidate_assays"][0]["name_evidence"]
    assert len(witnesses) == 1 and witnesses[0]["kind"] == "report_history"
    assert witnesses[0]["run_id"] == 3
    assert "payload" not in witnesses[0] and "ruleset" not in witnesses[0]


def test_legacy_name_evidence_must_match_original_full_hash_and_path(tmp_path, monkeypatch):
    from src.jobcontroller.api import get_job_evidence

    store = _project(tmp_path)
    pdf = tmp_path / "known.pdf"
    pdf.write_bytes(b"known")
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    _parser(monkeypatch, {b"known": _block(key="(1111)")})
    result = submit(str(pdf), str(tmp_path), sqlite_path=str(store))
    assert result.status == "DONE"
    assert get_job_evidence(tmp_path, result.job_id, expected_pdf_sha256=sha, expected_pdf_path=str(pdf)).status == "DONE"
    assert get_job_evidence(tmp_path, result.job_id, expected_pdf_sha256=sha[:16] + "0" * 48) is None
    assert get_job_evidence(tmp_path, result.job_id, expected_pdf_path=str(tmp_path / "unrelated.pdf")) is None


@pytest.mark.parametrize("invalid", [None, []])
def test_unrelated_nonobject_rule_does_not_break_known_name_change_discovery(tmp_path, invalid):
    store = _project(tmp_path, (("(1111)", "Assay A"), ("(3333)", "Unrelated")))
    (tmp_path / "rules" / "assay1.json").write_text(json.dumps(invalid), encoding="utf-8")
    case = _observe(tmp_path, store, _block())[0]
    assert case["assay_key"] == "(2222)"
    assert [item["assay_key"] for item in case["candidate_assays"]] == ["(1111)"]


def test_activation_between_frozen_detection_and_observation_never_produces_partial_done(tmp_path, monkeypatch):
    store = _project(tmp_path)
    pdf = tmp_path / "mixed.pdf"
    pdf.write_bytes(b"activation-race")
    _parser(monkeypatch, {b"activation-race": _block(key="(1111)") + "\n" + _block()})
    from src.assaychooser.api import detect_assays

    index_path = tmp_path / "rules" / "index.json"
    original_index = index_path.read_bytes()
    frozen = []

    def detect_and_activate(text, path, *, sections=None, index_bytes=None):
        frozen.append(index_bytes)
        matches = detect_assays(text, path, sections=sections, index_bytes=index_bytes)
        new_rule = json.loads((tmp_path / "rules" / "assay0.json").read_text(encoding="utf-8"))
        new_rule["assay_key"] = "(2222)"
        (tmp_path / "rules" / "new.json").write_text(json.dumps(new_rule), encoding="utf-8")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["assays"].append({"assay_key": "(2222)", "ruleset_file": "new.json"})
        index_path.write_text(json.dumps(index), encoding="utf-8")
        return matches

    def forbid(*args, **kwargs):
        raise AssertionError("index race must fail before extraction/output")

    monkeypatch.setattr("src.assaychooser.api.detect_assays", detect_and_activate)
    monkeypatch.setattr("src.extractor.api.extract_record", forbid)
    result = submit(str(pdf), str(tmp_path), sqlite_path=str(store))
    assert frozen == [original_index]
    assert result.status == "FAILED" and "active_rules_changed" in result.details["error"]
    assert not store.exists()
    state = json.loads((tmp_path / "jobs" / f"{result.job_id}.json").read_text(encoding="utf-8"))
    assert state["status"] == "FAILED" and "output_plan" not in state


def test_detection_uses_snapshot_even_if_index_changes_before_chooser_reads_it(tmp_path, monkeypatch):
    store = _project(tmp_path)
    pdf = tmp_path / "known.pdf"
    pdf.write_bytes(b"snapshot-race")
    _parser(monkeypatch, {b"snapshot-race": _block(key="(1111)")})
    from src.assaycandidate.api import load_known_assay_keys

    index_path = tmp_path / "rules" / "index.json"
    original = index_path.read_bytes()

    def keys_and_change(path, *, index_bytes=None):
        assert index_bytes == original
        index_path.write_text(json.dumps({"assays": [{"assay_key": "(2222)", "ruleset_file": "irrelevant.json"}]}), encoding="utf-8")
        return load_known_assay_keys(path, index_bytes=index_bytes)

    monkeypatch.setattr("src.assaycandidate.api.load_known_assay_keys", keys_and_change)
    result = submit(str(pdf), str(tmp_path), sqlite_path=str(store))
    assert result.status == "FAILED" and result.details["error"] == "rules_index_changed_during_processing"
    state = json.loads((tmp_path / "jobs" / f"{result.job_id}.json").read_text(encoding="utf-8"))
    assert next(step["assay_keys"] for step in state["steps"] if step["step"] == "assaychooser") == ["(1111)"]
    assert not store.exists()
