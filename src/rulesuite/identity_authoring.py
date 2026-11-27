"""Explicit assignment and proof binding for observed manufacturer-ID changes."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.assaycandidate.api import canonical_assay_key

from .errors import RuleSuiteError
from .identity_cases import _catalogue_path, _digest, _load_catalogue, _name_key, _path_key
from .json_io import _write_json_atomic
from .lifecycle import _active_ruleset_path, _publish_new_draft_exclusive, rulesuite_draft_lock, rulesuite_lifecycle_lock
from .templates import blank_draft_data, draft_path_for_assay


def _cases_for_key(root: Path, key: str) -> list[dict[str, Any]]:
    cases = _load_catalogue(_catalogue_path(root))["cases"].values()
    selected = [case for case in cases if case.get("assay_key") == canonical_assay_key(key)]
    if any(case.get("project_root") != str(root) for case in selected):
        raise RuleSuiteError("identity_case_workspace_changed")
    # Once this new ID was explicitly tested and activated it is an independent
    # rule, not a permanent alias/dependency on the original source rule.
    if any(identity_activation_committed(root, case) for case in selected):
        return []
    return selected


def identity_activation_committed(root: Path, case: dict[str, Any]) -> bool:
    activation = case.get("activation") or {}
    if (activation.get("assay_key") != case.get("assay_key")
            or activation.get("assignment_sha256") != _digest(case.get("assignment"))):
        return False
    if activation.get("publication") == "committed":
        return True
    # A preparation alone is not a completed transition. The atomic public
    # index must actually expose the exact prepared new rule first.
    try:
        index = json.loads((root / "rules" / "index.json").read_bytes())
        matches = [row for row in index.get("assays", [])
                   if canonical_assay_key(str(row.get("assay_key") or "")) == case["assay_key"]]
        if len(matches) != 1 or matches[0].get("ruleset_file") != activation.get("ruleset_file"):
            return False
        target = root / "rules" / str(activation["ruleset_file"])
        return hashlib.sha256(target.read_bytes()).hexdigest() == activation.get("rule_sha256")
    except (OSError, ValueError, TypeError, KeyError):
        return False


def has_identity_transition(root: Path, key: str) -> bool:
    return any(case.get("assay_key") == canonical_assay_key(key)
               for case in _load_catalogue(_catalogue_path(root))["cases"].values())


def owns_prepared_target(root: Path, target: Path, proof: dict[str, Any] | None, payload: bytes | None) -> bool:
    """Resume only an exact interrupted publication, never adopt another file."""
    if proof is None or payload is None or not target.is_file():
        return False
    binding = proof.get("identity_case") or {}
    case = _load_catalogue(_catalogue_path(root))["cases"].get(binding.get("case_id")) or {}
    activation = case.get("activation") or {}
    sha = hashlib.sha256(payload).hexdigest()
    return (activation.get("publication") == "prepared" and activation.get("ruleset_file") == target.name
            and activation.get("assignment_sha256") == binding.get("assignment_sha256")
            and activation.get("proof_sha256") == proof.get("proof_sha256")
            and activation.get("rule_sha256") == sha == hashlib.sha256(target.read_bytes()).hexdigest())


def finalize_identity_publication(root: Path, key: str) -> None:
    """Persist past publication before a later update/deactivation changes it.

    Called inside the lifecycle lock. After the first index switch this is
    only bookkeeping: failure cannot roll back the now-visible activation.
    """
    path = _catalogue_path(root)
    catalogue = _load_catalogue(path)
    changed = False
    for case in catalogue["cases"].values():
        activation = case.get("activation") or {}
        if (case.get("assay_key") == canonical_assay_key(key) and activation.get("publication") != "committed"
                and identity_activation_committed(root, case)):
            activation["publication"], case["status"] = "committed", "activated"
            changed = True
    if changed:
        _write_json_atomic(path, catalogue)


def require_identity_activation_proof(root: Path, key: str, proof: dict[str, Any] | None) -> None:
    """Also guard lower-level/CLI activation; ordinary legacy rules stay compatible."""
    finalize_identity_publication(root, key)
    if _cases_for_key(root, key) and (not isinstance(proof, dict) or proof.get("version") != 2 or not proof.get("identity_case")):
        raise RuleSuiteError("identity_case_tested_confirmation_required")


def _new_case_draft_path(root: Path, key: str) -> Path:
    parent = root
    for part in ("rules", "drafts"):
        expected = parent / part
        if expected.resolve() != expected:
            raise RuleSuiteError("identity_case_draft_directory_redirected")
        parent = expected
    path = Path(draft_path_for_assay(str(root), key))
    if path.resolve() != path or path.parent != parent:
        raise RuleSuiteError("identity_case_draft_path_invalid")
    return path


def confirm_assay_identity_case(
    project_root: str, case_id: str, *, store_path: str, expected_identity_token: str,
    source_assay_key: str, expected_rule_sha256: str, initialization: str,
    assay_name: str | None = None,
) -> dict[str, Any]:
    """Create one explicitly assigned empty/copied draft, never overwrite a draft.

    The selected old ID is evidence for a user decision, not an alias. Reopening
    the identical decision keeps edited draft bytes and an existing proof intact.
    """
    if not str(store_path).strip():
        raise RuleSuiteError("identity_case_store_required")
    if initialization not in {"blank", "copy"}:
        raise RuleSuiteError("identity_case_initialization_required")
    root, store = Path(project_root).resolve(), _path_key(store_path)
    with rulesuite_lifecycle_lock(str(root)):
        catalogue = _load_catalogue(_catalogue_path(root))
        case = catalogue["cases"].get(case_id)
        if case is None or case.get("project_root") != str(root) or case.get("store_path") != store:
            raise RuleSuiteError("identity_case_store_or_selection_changed")
        if case.get("identity_token") != expected_identity_token:
            raise RuleSuiteError("identity_case_selection_changed")
        candidate = next((row for row in case["candidate_assays"] if row["assay_key"] == source_assay_key), None)
        if candidate is None:
            raise RuleSuiteError("identity_case_explicit_candidate_required")
        key = str(case["assay_key"])
        index = json.loads((root / "rules" / "index.json").read_bytes())
        if any(canonical_assay_key(str(row.get("assay_key") or "")) == key for row in index.get("assays", [])):
            raise RuleSuiteError("identity_case_new_id_already_active")
        _source, filename, source_bytes = _active_ruleset_path(str(root), source_assay_key)
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        if not expected_rule_sha256 or source_hash != expected_rule_sha256 or source_hash != candidate["rule_sha256"]:
            raise RuleSuiteError("identity_case_source_rule_changed")
        name = (case["observed_names"][0] if assay_name is None else assay_name).strip()
        if not name:
            raise RuleSuiteError("identity_case_assay_name_required")
        draft = _new_case_draft_path(root, key)
        with rulesuite_draft_lock(draft):
            existing = case.get("assignment") or {}
            if draft.exists():
                same = (existing.get("draft_path") == str(draft) and existing.get("identity_token") == expected_identity_token
                        and existing.get("source_assay_key") == source_assay_key and existing.get("source_rule_sha256") == source_hash
                        and existing.get("initialization") == initialization)
                if not same or json.loads(draft.read_bytes()).get("assay_key") != key:
                    raise RuleSuiteError("identity_case_draft_already_exists")
                return {"status": "exists", "case_id": case_id, "draft_path": str(draft), "assignment": copy.deepcopy(existing)}
            if Path(str(draft) + ".readiness").exists():
                raise RuleSuiteError("identity_case_draft_already_exists")
            if initialization == "copy":
                data = json.loads(source_bytes)
                data["assay_key"], data["assay_name"] = key, name
            else:
                data = blank_draft_data(key, name)
            written = _publish_new_draft_exclusive(draft, data)
            if written is None:
                raise RuleSuiteError("identity_case_draft_already_exists")
            assignment = {"assignment_id": uuid4().hex, "identity_token": expected_identity_token,
                          "source_assay_key": source_assay_key, "source_ruleset_file": filename,
                          "source_rule_sha256": source_hash, "initialization": initialization,
                          "draft_path": str(draft), "initial_draft_sha256": hashlib.sha256(written).hexdigest(),
                          "confirmed_at_utc": datetime.now(timezone.utc).isoformat()}
            case["assignment"], case["status"] = assignment, "draft"
            try:
                _write_json_atomic(_catalogue_path(root), catalogue)
            except Exception:
                # Roll back only this call's freshly published bytes, never an
                # existing or concurrently replaced user draft.
                if draft.read_bytes() == written:
                    draft.unlink()
                raise
            return {"status": "created", "case_id": case_id, "draft_path": str(draft), "assignment": copy.deepcopy(assignment)}


def identity_proof_context(root: Path, key: str, draft: Path, *, store_path: str | None = None) -> dict[str, Any] | None:
    cases = _cases_for_key(root, key)
    if not cases:
        return None
    if store_path is not None:
        cases = [case for case in cases if case.get("store_path") == _path_key(store_path)]
    assigned = [case for case in cases if (case.get("assignment") or {}).get("draft_path") == str(draft)]
    if len(assigned) != 1:
        raise RuleSuiteError("identity_case_confirmation_required")
    case, assignment = assigned[0], assigned[0]["assignment"]
    if assignment.get("identity_token") != case.get("identity_token"):
        raise RuleSuiteError("identity_case_assignment_changed")
    _path, filename, payload = _active_ruleset_path(str(root), assignment["source_assay_key"])
    if filename != assignment["source_ruleset_file"] or hashlib.sha256(payload).hexdigest() != assignment["source_rule_sha256"]:
        raise RuleSuiteError("identity_case_source_rule_changed")
    return {"case_id": case["case_id"], "store_path": case["store_path"], "assay_key": case["assay_key"],
            "identity_token": case["identity_token"], "assignment_sha256": _digest(assignment),
            "document_name_sha256": sorted({_digest(_name_key(name)) for name in case["observed_names"]})}


def bind_identity_test(context: dict[str, Any], header: dict[str, Any]) -> dict[str, Any]:
    name_hash = _digest(_name_key(str(header.get("assay_name") or "")))
    if canonical_assay_key(str(header.get("assay_key") or "")) != context["assay_key"] or name_hash not in context["document_name_sha256"]:
        raise RuleSuiteError("identity_case_test_pdf_identity_mismatch")
    header_hash = hashlib.sha256(json.dumps(header, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {**context, "tested_name_sha256": name_hash, "tested_header_sha256": header_hash}


def verify_identity_proof(root: Path, key: str, draft: Path, proof: dict[str, Any]) -> list[str]:
    recorded = proof.get("identity_case")
    try:
        context = identity_proof_context(root, key, draft, store_path=recorded.get("store_path") if isinstance(recorded, dict) else None)
        if context is None:
            return ["identity_case_assignment_changed"] if recorded else []
        if not isinstance(recorded, dict) or {name: recorded.get(name) for name in context} != context:
            return ["identity_case_assignment_changed"]
        header = proof.get("primary", {}).get("assay_header") or {}
        header_hash = (hashlib.sha256(json.dumps(header, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
                       if "assay_name" in header else header.get("header_sha256"))
        if recorded.get("tested_name_sha256") not in context["document_name_sha256"] or recorded.get("tested_header_sha256") != header_hash:
            return ["identity_case_test_pdf_identity_mismatch"]
        secondary_store = proof.get("secondary", {}).get("source", {}).get("store_path")
        if secondary_store and _path_key(secondary_store) != context["store_path"]:
            return ["identity_case_store_changed"]
        return []
    except (RuleSuiteError, OSError, ValueError, KeyError) as exc:
        return [str(exc) if isinstance(exc, RuleSuiteError) else "identity_case_assignment_unreadable"]


def record_identity_activation(root: Path, key: str, target: Path, proof: dict[str, Any]) -> bytes:
    """Prepare the first transition before the final atomic index publication."""
    recorded = proof["identity_case"]
    path = _catalogue_path(root)
    catalogue = _load_catalogue(path)
    case = catalogue["cases"].get(recorded["case_id"])
    if case is None or _digest(case.get("assignment")) != recorded["assignment_sha256"] or case.get("identity_token") != recorded["identity_token"]:
        raise RuleSuiteError("identity_case_assignment_changed")
    case["activation"] = {"assay_key": canonical_assay_key(key), "ruleset_file": target.name,
                          "rule_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                          "draft_sha256": proof["draft_sha256"], "attempt_id": proof["attempt_id"],
                          "proof_sha256": proof["proof_sha256"], "assignment_sha256": recorded["assignment_sha256"],
                          "prepared_at_utc": datetime.now(timezone.utc).isoformat(), "publication": "prepared"}
    case["status"] = "activation_pending"
    _write_json_atomic(path, catalogue)
    return json.dumps(catalogue, indent=2, ensure_ascii=False).encode("utf-8")
