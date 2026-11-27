import hashlib
import json
from pathlib import Path

import pytest

from src.application.models import DesktopSettings
from src.application.rules_controller import RuleSuiteController
from src.jobcontroller.api import submit
from src.rulesuite.api import (
    AuthoringReadinessError, RuleSuiteError, activate_draft, activate_new_draft,
    confirm_assay_identity_case, create_authoring_proof, create_blank_draft,
    list_assay_identity_cases, load_draft, verify_authoring_proof,
    save_draft,
)
from test_rulesuite_identity_cases import _block, _observe, _parser, _project


def _confirm(root, store, case, *, initialization="copy", selected=None, name=None):
    selected = selected or case["candidate_assays"][0]
    return confirm_assay_identity_case(str(root), case["case_id"], store_path=str(store),
        expected_identity_token=case["identity_token"], source_assay_key=selected["assay_key"],
        expected_rule_sha256=selected["rule_sha256"], initialization=initialization, assay_name=name)


def _ready(root, monkeypatch):
    store = _project(root)
    text = _block()
    case = _observe(root, store, text, payload=b"imported")[0]
    result = _confirm(root, store, case)
    pdf = root / "manually-selected.pdf"
    pdf.write_bytes(b"manual")
    # Different bytes and path from every imported occurrence are deliberate.
    _parser(monkeypatch, {b"imported": text, b"manual": _block(value="88"), b"second": _block(value="99")})
    draft = result["draft_path"]
    proof = create_authoring_proof(str(root), "(2222)", draft, str(pdf), automatic_sources=lambda: (), identity_store_path=str(store))
    assert proof["status"] == "ready", proof
    return store, case, draft, pdf, proof


@pytest.mark.parametrize("initialization", ["blank", "copy"])
def test_confirmation_explicitly_creates_own_id_and_never_changes_source_rule(tmp_path, initialization):
    store = _project(tmp_path)
    case = _observe(tmp_path, store, _block())[0]
    source = tmp_path / "rules" / "assay0.json"
    before_rule, before_index = source.read_bytes(), (tmp_path / "rules" / "index.json").read_bytes()
    result = _confirm(tmp_path, store, case, initialization=initialization)
    draft = load_draft(result["draft_path"])
    assert draft["assay_key"] == "(2222)" and draft["assay_name"] == "Assay A"
    assert draft["extract_rules"]["fields"] == ([] if initialization == "blank" else json.loads(before_rule)["extract_rules"]["fields"])
    assignment = result["assignment"]
    assert assignment["source_assay_key"] == "(1111)"
    assert assignment["source_rule_sha256"] == hashlib.sha256(before_rule).hexdigest()
    assert source.read_bytes() == before_rule and (tmp_path / "rules" / "index.json").read_bytes() == before_index
    assert not store.exists() and not (tmp_path / "rules" / "history").exists()


def test_same_confirmation_reopens_edited_draft_without_rewriting_or_revoking_proof(tmp_path, monkeypatch):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    path, receipt = Path(draft), Path(draft + ".readiness")
    edited = load_draft(draft)
    edited["extract_rules"]["fields"][0]["regex"] = r"Value:\s+(\S+)"
    save_draft(draft, edited)
    assert create_authoring_proof(str(tmp_path), "(2222)", draft, str(pdf), automatic_sources=lambda: ())["status"] == "ready"
    before = path.read_bytes(), receipt.read_bytes()
    result = _confirm(tmp_path, store, case)
    assert result["status"] == "exists"
    assert (path.read_bytes(), receipt.read_bytes()) == before
    assert verify_authoring_proof(str(tmp_path), "(2222)", draft)["ok"]


def test_ambiguous_name_requires_actual_candidate_id_and_wrong_store_cannot_confirm(tmp_path):
    store = _project(tmp_path, (("(1111)", "Assay A"), ("(3333)", "Assay A")))
    case = _observe(tmp_path, store, _block())[0]
    assert case["requires_selection"] and "selected_assay_key" not in case
    with pytest.raises(RuleSuiteError, match="explicit_candidate_required"):
        confirm_assay_identity_case(str(tmp_path), case["case_id"], store_path=str(store),
            expected_identity_token=case["identity_token"], source_assay_key="", expected_rule_sha256="", initialization="copy")
    with pytest.raises(RuleSuiteError, match="store_or_selection_changed"):
        _confirm(tmp_path, tmp_path / "other.sqlite3", case)
    selected = next(row for row in case["candidate_assays"] if row["assay_key"] == "(3333)")
    result = _confirm(tmp_path, store, case, selected=selected)
    assert result["assignment"]["source_assay_key"] == "(3333)"


def test_source_revision_or_identity_revision_change_prevents_copy_without_draft_write(tmp_path):
    store = _project(tmp_path)
    case = _observe(tmp_path, store, _block())[0]
    source = tmp_path / "rules" / "assay0.json"
    data = json.loads(source.read_bytes())
    data["extract_rules"]["fields"][0]["regex"] = "CHANGED"
    source.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuleSuiteError, match="source_rule_changed"):
        _confirm(tmp_path, store, case)
    assert not (tmp_path / "rules" / "drafts").exists()
    with pytest.raises(RuleSuiteError, match="selection_changed"):
        confirm_assay_identity_case(str(tmp_path), case["case_id"], store_path=str(store), expected_identity_token="stale",
            source_assay_key="(1111)", expected_rule_sha256=case["candidate_assays"][0]["rule_sha256"], initialization="copy")


def test_existing_unowned_draft_is_never_overwritten_or_adopted(tmp_path):
    store = _project(tmp_path)
    case = _observe(tmp_path, store, _block())[0]
    draft = Path(create_blank_draft(str(tmp_path), "(2222)", "My unsaved setup"))
    before = draft.read_bytes()
    with pytest.raises(RuleSuiteError, match="draft_already_exists"):
        _confirm(tmp_path, store, case)
    assert draft.read_bytes() == before
    assert "assignment" not in list_assay_identity_cases(str(tmp_path), store_path=str(store))[0]


def test_unconfirmed_case_blocks_direct_proof_and_activation_api_bypass(tmp_path, monkeypatch):
    store = _project(tmp_path)
    _observe(tmp_path, store, _block())
    draft = create_blank_draft(str(tmp_path), "(2222)", "Assay A")
    before = (tmp_path / "rules" / "index.json").read_bytes()
    with pytest.raises(RuleSuiteError, match="confirmation_required"):
        create_authoring_proof(str(tmp_path), "(2222)", draft, str(tmp_path / "input.pdf"), automatic_sources=lambda: ())
    with pytest.raises(RuleSuiteError, match="tested_confirmation_required"):
        activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft)
    with pytest.raises(RuleSuiteError, match="tested_confirmation_required"):
        create_authoring_proof(str(tmp_path), "(2222)", draft, str(tmp_path / "input.pdf"))
    assert (tmp_path / "rules" / "index.json").read_bytes() == before
    assert json.loads(Path(draft + ".readiness").read_bytes())["status"] == "pending"


def test_free_matching_test_pdf_uses_actual_bytes_and_more_sources_do_not_revoke_assignment(tmp_path, monkeypatch):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    assert proof["primary"]["data"] == {"value": "88"}
    assert proof["primary"]["sha256"] == hashlib.sha256(b"manual").hexdigest()
    before = proof["identity_case"]
    later = _observe(tmp_path, store, _block(value="7"), payload=b"later", filename="later.pdf")[0]
    assert later["identity_token"] == case["identity_token"] and len(later["sources"]) == 2
    checked = verify_authoring_proof(str(tmp_path), "(2222)", draft)
    assert checked["ok"] and checked["proof"]["identity_case"] == before
    assert checked["proof"]["secondary"]["status"] == "not_available"


@pytest.mark.parametrize("name,key", [("Other document", "(2222)"), ("Assay A", "(3333)")])
def test_free_test_pdf_with_wrong_confirmed_title_or_id_is_blocked(tmp_path, monkeypatch, name, key):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    _parser(monkeypatch, {b"manual": _block(name, key)})
    blocked = create_authoring_proof(str(tmp_path), "(2222)", draft, str(pdf), automatic_sources=lambda: (), identity_store_path=str(store))
    assert blocked["status"] == "blocked"
    assert not verify_authoring_proof(str(tmp_path), "(2222)", draft)["ok"]
    with pytest.raises(AuthoringReadinessError):
        activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=json.loads(Path(draft + ".readiness").read_bytes()))


def test_one_test_pdf_keeps_automatic_second_outcome_and_first_eligible_failure_blocks(tmp_path, monkeypatch):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    second = tmp_path / "known-second.pdf"
    second.write_bytes(b"second")
    source = {"local": True, "path": str(second), "sha256": hashlib.sha256(b"second").hexdigest(), "kind": "test"}
    tested = create_authoring_proof(str(tmp_path), "(2222)", draft, str(pdf), automatic_sources=lambda: (source,), identity_store_path=str(store))
    assert tested["primary"]["data"] == {"value": "88"} and tested["secondary"]["data"] == {"value": "99"}
    _parser(monkeypatch, {b"manual": _block(value="88"), b"second": _block().replace("Value: 42", "Missing")})
    blocked = create_authoring_proof(str(tmp_path), "(2222)", draft, str(pdf), automatic_sources=lambda: (source,), identity_store_path=str(store))
    assert blocked["status"] == "blocked" and blocked["secondary"]["status"] == "failed"


def test_activation_publishes_exact_own_rule_and_finishes_transition_without_touching_old_results(tmp_path, monkeypatch):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    old = tmp_path / "rules" / "assay0.json"
    before = old.read_bytes()
    receipt = verify_authoring_proof(str(tmp_path), "(2222)", draft)["proof"]
    target = Path(activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=receipt))
    assert target.name == "Assay A.2222.json" and target.read_bytes() == Path(draft).read_bytes()
    assert old.read_bytes() == before and not (tmp_path / "rules" / "history").exists() and not store.exists()
    saved = list_assay_identity_cases(str(tmp_path), store_path=str(store))[0]
    assert saved["status"] == "activated" and saved["activation"]["rule_sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert saved["assignment"]["source_rule_sha256"] == hashlib.sha256(before).hexdigest()
    processed = submit(str(pdf), str(tmp_path), sqlite_path=str(store))
    assert processed.status == "DONE", processed.details
    assert processed.details["writes"][0]["assay_key"] == "(2222)" and processed.details["writes"][0]["data"] == {"value": "88"}
    assert old.read_bytes() == before


@pytest.mark.parametrize("remove_source", [False, True])
def test_new_id_is_independent_of_old_rule_after_its_first_explicit_activation(tmp_path, monkeypatch, remove_source):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    first = verify_authoring_proof(str(tmp_path), "(2222)", draft)["proof"]
    target = Path(activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=first))
    old = tmp_path / "rules" / "assay0.json"
    if remove_source:
        index = json.loads((tmp_path / "rules" / "index.json").read_bytes())
        index["assays"] = [row for row in index["assays"] if row["assay_key"] != "(1111)"]
        (tmp_path / "rules" / "index.json").write_text(json.dumps(index), encoding="utf-8")
        old.unlink()
    else:
        old.write_text('{"changed original": true}', encoding="utf-8")
    second = create_authoring_proof(str(tmp_path), "(2222)", draft, str(pdf), automatic_sources=lambda: (), identity_store_path=str(store))
    assert second["status"] == "ready" and "identity_case" not in second
    checked = verify_authoring_proof(str(tmp_path), "(2222)", draft)
    assert checked["ok"]
    assert Path(activate_draft(str(tmp_path), "(2222)", draft, authoring_proof=checked["proof"])) == target
    assert list_assay_identity_cases(str(tmp_path), store_path=str(store))[0]["assignment"]["source_assay_key"] == "(1111)"


def test_changed_assignment_or_source_under_activation_guard_cannot_publish(tmp_path, monkeypatch):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    receipt = verify_authoring_proof(str(tmp_path), "(2222)", draft)["proof"]
    old = tmp_path / "rules" / "assay0.json"
    old.write_bytes(old.read_bytes() + b"\n")
    before = (tmp_path / "rules" / "index.json").read_bytes()
    with pytest.raises(AuthoringReadinessError, match="source_rule_changed"):
        activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=receipt)
    assert (tmp_path / "rules" / "index.json").read_bytes() == before and not (tmp_path / "rules" / "Assay A.2222.json").exists()


def test_failed_confirmation_or_activation_receipt_write_rolls_back_only_own_new_files(tmp_path, monkeypatch):
    store = _project(tmp_path)
    case = _observe(tmp_path, store, _block())[0]
    from src.rulesuite import identity_authoring

    def fail(path, data):
        raise OSError("synthetic private receipt write failure")

    with monkeypatch.context() as failure:
        failure.setattr(identity_authoring, "_write_json_atomic", fail)
        with pytest.raises(OSError, match="synthetic private"):
            _confirm(tmp_path, store, case)
    assert not (tmp_path / "rules" / "drafts" / "2222.draft.json").exists()
    result = _confirm(tmp_path, store, case)
    pdf = tmp_path / "chosen.pdf"
    pdf.write_bytes(b"chosen")
    _parser(monkeypatch, {b"chosen": _block()})
    create_authoring_proof(str(tmp_path), "(2222)", result["draft_path"], str(pdf), automatic_sources=lambda: ())
    checked = verify_authoring_proof(str(tmp_path), "(2222)", result["draft_path"])
    index = tmp_path / "rules" / "index.json"
    catalogue = tmp_path / "storage" / "rulesuite" / "identity_cases.json"
    before = index.read_bytes(), catalogue.read_bytes()
    monkeypatch.setattr(identity_authoring, "_write_json_atomic", fail)
    with pytest.raises(OSError, match="synthetic private"):
        activate_new_draft(str(tmp_path), "(2222)", "Assay A", result["draft_path"], authoring_proof=checked["proof"])
    assert (index.read_bytes(), catalogue.read_bytes()) == before
    assert not (tmp_path / "rules" / "Assay A.2222.json").exists()


def test_product_controller_binds_confirmation_test_and_activation_to_selected_store(tmp_path, monkeypatch):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    selected = [DesktopSettings(output_mode="sqlite", sqlite_path=str(store))]
    controller = RuleSuiteController(tmp_path, settings_provider=lambda: selected[0], authoring_source_reader=lambda *, matches_assay: iter(()))
    assert controller.list_identity_cases()[0]["case_id"] == case["case_id"]
    assert controller.create_authoring_proof("(2222)", draft, str(pdf))["status"] == "ready"
    selected[0] = DesktopSettings(output_mode="sqlite", sqlite_path=str(tmp_path / "other.sqlite3"))
    assert not controller.verify_authoring_proof("(2222)", draft)["ok"]
    with pytest.raises(AuthoringReadinessError, match="store_changed"):
        controller.activate_draft("(2222)", draft, assay_name="Assay A")
    with pytest.raises(RuleSuiteError, match="store_changed"):
        controller.confirm_identity_case(case["case_id"], store_path=str(store), expected_identity_token=case["identity_token"],
            source_assay_key="(1111)", expected_rule_sha256=case["candidate_assays"][0]["rule_sha256"], initialization="copy")
    with pytest.raises(RuleSuiteError, match="confirmation_required"):
        controller.create_authoring_proof("(2222)", draft, str(pdf))


@pytest.mark.parametrize("replace_target", [False, True])
def test_index_publish_failure_removes_only_own_unmodified_new_rule(tmp_path, monkeypatch, replace_target):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    checked = verify_authoring_proof(str(tmp_path), "(2222)", draft)["proof"]
    from src.rulesuite import rulesuite

    index = tmp_path / "rules" / "index.json"
    target = tmp_path / "rules" / "Assay A.2222.json"
    before = index.read_bytes()
    original = rulesuite._write_json_atomic

    def fail_only_index(path, data):
        if path == index:
            assert target.read_bytes() == Path(draft).read_bytes()
            if replace_target:
                target.write_bytes(b"foreign replacement; do not remove")
            raise OSError("synthetic index publish failure")
        return original(path, data)

    monkeypatch.setattr(rulesuite, "_write_json_atomic", fail_only_index)
    with pytest.raises(OSError, match="index publish"):
        activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=checked)
    assert index.read_bytes() == before
    if replace_target:
        assert target.read_bytes() == b"foreign replacement; do not remove"
    else:
        assert not target.exists()
        monkeypatch.setattr(rulesuite, "_write_json_atomic", original)
        assert Path(activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=checked)) == target


@pytest.mark.parametrize("index_fails", [False, True])
def test_worker_cannot_import_new_id_before_last_index_switch(tmp_path, monkeypatch, index_fails):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    checked = verify_authoring_proof(str(tmp_path), "(2222)", draft)["proof"]
    from src.rulesuite import rulesuite

    original = rulesuite._write_json_atomic
    index = tmp_path / "rules" / "index.json"
    target = tmp_path / "rules" / "Assay A.2222.json"
    before = index.read_bytes()
    interrupted = []

    def worker_before_index(path, data):
        if path == index:
            assert target.read_bytes() == Path(draft).read_bytes()
            pending = list_assay_identity_cases(str(tmp_path), store_path=str(store))[0]
            assert pending["status"] == "activation_pending"
            assert pending["activation"]["publication"] == "prepared"
            assert index.read_bytes() == before
            interrupted.append(submit(str(pdf), str(tmp_path), sqlite_path=str(store)))
            assert interrupted[-1].status == "FAILED" and not store.exists()
            if index_fails:
                raise OSError("index publication deliberately stopped after worker")
        original(path, data)

    monkeypatch.setattr(rulesuite, "_write_json_atomic", worker_before_index)
    if index_fails:
        with pytest.raises(OSError, match="deliberately stopped"):
            activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=checked)
        assert index.read_bytes() == before and not target.exists() and not store.exists()
        saved = list_assay_identity_cases(str(tmp_path), store_path=str(store))[0]
        assert saved["status"] == "draft" and "activation" not in saved
    else:
        assert Path(activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=checked)) == target
        assert submit(str(pdf), str(tmp_path), sqlite_path=str(store)).status == "DONE"
        assert submit(str(pdf), str(tmp_path), sqlite_path=str(store)).status == "SKIPPED"
    assert len(interrupted) == 1


def test_post_index_bookkeeping_failure_never_revokes_committed_rule(tmp_path, monkeypatch):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    checked = verify_authoring_proof(str(tmp_path), "(2222)", draft)["proof"]
    from src.rulesuite import identity_authoring

    actual = identity_authoring._write_json_atomic
    calls = []

    def fail_only_finalization(path, data):
        calls.append(data["cases"][case["case_id"]]["activation"]["publication"])
        if calls[-1] == "committed":
            raise OSError("non-authoritative bookkeeping failure")
        actual(path, data)

    monkeypatch.setattr(identity_authoring, "_write_json_atomic", fail_only_finalization)
    target = Path(activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=checked))
    assert target.is_file() and calls == ["prepared", "committed"]
    saved = list_assay_identity_cases(str(tmp_path), store_path=str(store))[0]
    assert saved["status"] == "activated" and saved["activation"]["publication"] == "prepared"
    assert submit(str(pdf), str(tmp_path), sqlite_path=str(store)).status == "DONE"


def test_interrupted_preparation_is_not_activated_and_resumes_only_exact_owned_target(tmp_path, monkeypatch):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    checked = verify_authoring_proof(str(tmp_path), "(2222)", draft)["proof"]
    from src.rulesuite.identity_authoring import record_identity_activation
    from src.rulesuite.lifecycle import rulesuite_lifecycle_lock

    target = tmp_path / "rules" / "Assay A.2222.json"
    before = (tmp_path / "rules" / "index.json").read_bytes()
    with rulesuite_lifecycle_lock(str(tmp_path)):
        target.write_bytes(Path(draft).read_bytes())
        record_identity_activation(tmp_path, "(2222)", target, checked)
    assert list_assay_identity_cases(str(tmp_path), store_path=str(store))[0]["status"] == "activation_pending"
    with pytest.raises(RuleSuiteError, match="tested_confirmation_required"):
        activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft)
    assert (tmp_path / "rules" / "index.json").read_bytes() == before
    assert Path(activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=checked)) == target
    assert list_assay_identity_cases(str(tmp_path), store_path=str(store))[0]["status"] == "activated"


def test_later_deactivation_and_reactivation_keep_new_id_independent_and_own_filename(tmp_path, monkeypatch):
    from src.rulesuite.api import deactivate_ruleset

    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    first = verify_authoring_proof(str(tmp_path), "(2222)", draft)["proof"]
    target = Path(activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=first))
    deactivate_ruleset(str(tmp_path), "(2222)")
    old = tmp_path / "rules" / "assay0.json"
    old.write_text('{"old rule changed":true}', encoding="utf-8")
    assert create_authoring_proof(str(tmp_path), "(2222)", draft, str(pdf), automatic_sources=lambda: ())["status"] == "ready"
    checked = verify_authoring_proof(str(tmp_path), "(2222)", draft)
    assert "identity_case" not in checked["proof"] and checked["ok"]
    assert Path(activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=checked["proof"])) == target


@pytest.mark.parametrize("references_target", [False, True])
def test_failed_index_switch_preserves_foreign_index_and_catalogue_bytes(tmp_path, monkeypatch, references_target):
    store, case, draft, pdf, proof = _ready(tmp_path, monkeypatch)
    checked = verify_authoring_proof(str(tmp_path), "(2222)", draft)["proof"]
    from src.rulesuite import rulesuite

    index = tmp_path / "rules" / "index.json"
    catalogue = tmp_path / "storage" / "rulesuite" / "identity_cases.json"
    target = tmp_path / "rules" / "Assay A.2222.json"
    foreign = {}
    original = rulesuite._write_json_atomic

    def foreign_change_then_fail(path, data):
        if path == index:
            other_index = json.loads(index.read_bytes())
            other_index["foreign_change"] = "preserve byte for byte"
            if references_target:
                other_index["assays"].append({"assay_key": "(9999)", "ruleset_file": target.name})
            other_catalogue = json.loads(catalogue.read_bytes())
            other_catalogue["foreign_change"] = "preserve this too"
            foreign["index"] = json.dumps(other_index).encode()
            foreign["catalogue"] = json.dumps(other_catalogue).encode()
            index.write_bytes(foreign["index"])
            catalogue.write_bytes(foreign["catalogue"])
            raise OSError("foreign edits during index failure")
        original(path, data)

    monkeypatch.setattr(rulesuite, "_write_json_atomic", foreign_change_then_fail)
    with pytest.raises(OSError, match="foreign edits"):
        activate_new_draft(str(tmp_path), "(2222)", "Assay A", draft, authoring_proof=checked)
    assert index.read_bytes() == foreign["index"] and catalogue.read_bytes() == foreign["catalogue"]
    assert target.exists() is references_target
    assert list_assay_identity_cases(str(tmp_path), store_path=str(store))[0]["status"] == "activation_pending"
