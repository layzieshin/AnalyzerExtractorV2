"""Authoring-Readiness and hash-bound PDF proof for product activation.

Semantik (AP-6.1):
- ``check_authoring_readiness`` ohne *assay_text*: nur Strukturcheck via ``_validate_draft_data``.
  ``ok=true`` ist möglich, enthält aber immer Warning ``no_assay_text`` — **keine** fachliche Freigabe.
- Mit *assay_text* (oder CLI ``--pdf``): zusätzlich ``check_required_fields`` für die acht Pflicht-Header.
  ``ok=true`` bedeutet Struktur + alle Pflichtfelder confirmed → fachliche Readiness für Testbetrieb.
- ``check_required`` / ``readiness --assay-text`` sind die fachlichen Vorab-Checks mit Beispieltext/PDF.
- Die unteren ``activate_draft`` / ``activate_new_draft`` APIs bleiben kompatibel.
  Produktaktivierungen ueber den Application-Controller und Rule Editor verlangen
  zusaetzlich einen gueltigen, hashgebundenen PDF-Nachweis.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from src.assaycandidate.api import canonical_assay_key

from .required_fields import check_required_fields
from .validation import _validate_draft_data
from .json_io import _read_json_object
from .lifecycle import rulesuite_draft_lock, rulesuite_lifecycle_lock
from .errors import RuleSuiteError

_PROOF_VERSION = 1


class AuthoringReadinessError(RuntimeError):
    pass


def check_authoring_readiness(
    draft_path: str,
    assay_text: str | None = None,
    *,
    group: int = 1,
) -> Dict[str, Any]:
    """Prüft Draft-Struktur und optional die acht Pflicht-Header gegen *assay_text*.

  Ohne Text: ``ok`` nur strukturell; ``warnings`` enthält ``no_assay_text``.
  Mit Text: ``ok`` nur wenn Struktur ok und ``required_field_status.all_confirmed``.
  ``activate_draft`` / ``activate_new_draft`` rufen diese Funktion nicht auf.
    """
    data = _read_json_object(Path(draft_path))
    structural = _validate_draft_data(data)
    structural_errors: List[str] = [] if structural.get("ok") else list(structural.get("errors", []))

    warnings: List[str] = []
    required_field_status: Dict[str, Any] | None = None
    missing_required: List[str] = []

    text = (assay_text or "").strip()
    if text:
        required_field_status = check_required_fields(draft_path, text, group=group)
        missing_required = [
            str(row["key"])
            for row in required_field_status.get("results", [])
            if isinstance(row, dict) and row.get("status") != "confirmed"
        ]
    else:
        warnings.append("no_assay_text: Pflichtfelder gegen PDF/Beispieltext nicht geprüft")

    ok = not structural_errors
    if text:
        ok = ok and bool(required_field_status and required_field_status.get("all_confirmed"))

    return {
        "ok": ok,
        "structural_errors": structural_errors,
        "required_field_status": required_field_status,
        "missing_required": missing_required,
        "warnings": warnings,
    }


def create_authoring_proof(
    project_root: str,
    assay_key: str,
    draft_path: str,
    failing_pdf_path: str,
    reference_pdf_path: str | None = None,
    *,
    automatic_sources: Callable[[], Iterable[Dict[str, Any]]] | None = None,
    identity_store_path: str | None = None,
) -> Dict[str, Any]:
    """Create a hash-bound proof for the current draft and its acceptance PDFs."""
    if automatic_sources is not None:
        return _create_authoring_proof_v2(project_root, assay_key, draft_path, failing_pdf_path, automatic_sources,
                                          identity_store_path=identity_store_path)
    from .rulesuite import RuleSuite

    root = Path(project_root).resolve()
    draft = _require_contained_draft(root, draft_path)
    proof_path = _proof_path(draft)
    attempt = uuid4().hex
    # Starting a new check revokes an older proof immediately. Otherwise a
    # failed attempt with a newly selected problem PDF could leave a previous
    # proof usable for activation.
    with rulesuite_lifecycle_lock(str(root)), rulesuite_draft_lock(draft):
        _require_contained_draft(root, str(draft))
        _write_json_atomic(
            proof_path,
            {
                "version": _PROOF_VERSION, "attempt_id": attempt,
                "status": "pending",
                "draft_path": str(draft),
                "started_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
        )
        from .identity_authoring import require_identity_activation_proof
        require_identity_activation_proof(root, assay_key, None)
    failing_pdf = _require_pdf(failing_pdf_path, "failing_pdf")
    key = str(assay_key or "").strip()
    if not key:
        raise AuthoringReadinessError("authoring_proof_assay_key_missing")

    service = RuleSuite()
    draft_data = service.load_draft(str(draft))
    if str(draft_data.get("assay_key", "")).strip() != key:
        raise AuthoringReadinessError("authoring_proof_assay_key_mismatch")
    structural = _validate_draft_data(draft_data)
    if not structural.get("ok"):
        raise AuthoringReadinessError(f"authoring_proof_draft_invalid: {structural.get('errors', [])}")

    # The former failing/example PDF must now pass the real extractor completely.
    failing_result = service.preview_extract(str(root), str(failing_pdf), key, draft_path=str(draft))
    diff = service.diff_draft_vs_active(str(root), key, str(draft))
    mode = str(diff.get("mode") or "create")

    reference_pdf: Path | None = None
    reference_hash = ""
    active_ruleset: Path | None = None
    active_ruleset_hash = ""
    compared_fields: list[str] = []
    if mode == "update":
        active_ruleset = _require_contained_active_ruleset(root, str(diff.get("ruleset_file") or ""))
        active_ruleset_hash = _sha256_file(active_ruleset)
        if not str(reference_pdf_path or "").strip():
            raise AuthoringReadinessError("authoring_proof_reference_pdf_required")
        reference_pdf = _require_pdf(str(reference_pdf_path), "reference_pdf")
        failing_hash = _sha256_file(failing_pdf)
        reference_hash = _sha256_file(reference_pdf)
        if failing_pdf == reference_pdf or failing_hash == reference_hash:
            raise AuthoringReadinessError("authoring_proof_reference_must_differ")
        active_reference = service.preview_extract(str(root), str(reference_pdf), key, draft_path=None)
        draft_reference = service.preview_extract(str(root), str(reference_pdf), key, draft_path=str(draft))
        expected = dict(active_reference.get("data") or {})
        actual = dict(draft_reference.get("data") or {})
        compared_fields = list(expected.keys())
        mismatches = [field for field in compared_fields if actual.get(field) != expected.get(field)]
        if str(draft_reference.get("lot_id") or "") != str(active_reference.get("lot_id") or ""):
            mismatches.append("lot_id")
        if mismatches:
            raise AuthoringReadinessError(
                "authoring_proof_reference_mismatch: " + ",".join(dict.fromkeys(mismatches))
            )
    else:
        failing_hash = _sha256_file(failing_pdf)

    proof = {
        "version": _PROOF_VERSION,
        "attempt_id": attempt,
        "status": "ready",
        "assay_key": key,
        "mode": mode,
        "draft_path": str(draft),
        "draft_sha256": _sha256_file(draft),
        "failing_pdf_path": str(failing_pdf),
        "failing_pdf_sha256": failing_hash,
        "reference_pdf_path": str(reference_pdf) if reference_pdf is not None else "",
        "reference_pdf_sha256": reference_hash,
        "active_ruleset_path": str(active_ruleset) if active_ruleset is not None else "",
        "active_ruleset_sha256": active_ruleset_hash,
        "compared_fields": compared_fields,
        "checked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "failing_result_fields": list(dict(failing_result.get("data") or {}).keys()),
    }
    _publish_attempt(root, proof_path, attempt, proof)
    return proof


def verify_authoring_proof(project_root: str, assay_key: str, draft_path: str) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    try:
        draft = _require_contained_draft(root, draft_path)
    except AuthoringReadinessError as exc:
        return {"ok": False, "errors": [str(exc)]}
    proof_path = _proof_path(draft)
    if not proof_path.is_file():
        return {"ok": False, "errors": ["authoring_proof_missing"]}
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "errors": ["authoring_proof_unreadable"]}
    if isinstance(proof, dict) and proof.get("version") == 2:
        return _verify_authoring_proof_v2(root, str(assay_key or "").strip(), draft, proof)
    if not isinstance(proof, dict) or proof.get("version") != _PROOF_VERSION:
        return {"ok": False, "errors": ["authoring_proof_version_invalid"]}
    from .identity_authoring import require_identity_activation_proof
    try:
        require_identity_activation_proof(root, assay_key, proof)
    except RuleSuiteError as exc:
        return {"ok": False, "errors": [str(exc)], "proof": proof}
    if proof.get("status") != "ready":
        return {"ok": False, "errors": ["authoring_proof_not_ready"]}

    errors: list[str] = []
    key = str(assay_key or "").strip()
    if str(proof.get("assay_key") or "") != key:
        errors.append("authoring_proof_assay_key_mismatch")
    if str(proof.get("draft_path") or "") != str(draft):
        errors.append("authoring_proof_draft_path_mismatch")
    if str(proof.get("draft_sha256") or "") != _sha256_file(draft):
        errors.append("authoring_proof_draft_changed")
    for label in ("failing_pdf", "reference_pdf"):
        raw_path = str(proof.get(f"{label}_path") or "").strip()
        expected_hash = str(proof.get(f"{label}_sha256") or "").strip()
        if not raw_path and label == "reference_pdf" and proof.get("mode") != "update":
            continue
        path = Path(raw_path).resolve() if raw_path else None
        if path is None or not path.is_file():
            errors.append(f"authoring_proof_{label}_missing")
        elif _sha256_file(path) != expected_hash:
            errors.append(f"authoring_proof_{label}_changed")
    if proof.get("mode") == "update" and not proof.get("reference_pdf_sha256"):
        errors.append("authoring_proof_reference_pdf_required")
    if proof.get("mode") == "update":
        active_path_raw = str(proof.get("active_ruleset_path") or "").strip()
        expected_active_hash = str(proof.get("active_ruleset_sha256") or "").strip()
        try:
            active_path = _require_contained_active_ruleset(root, active_path_raw)
        except AuthoringReadinessError:
            errors.append("authoring_proof_active_ruleset_missing")
        else:
            if _sha256_file(active_path) != expected_active_hash:
                errors.append("authoring_proof_active_ruleset_changed")
    return {"ok": not errors, "errors": errors, "proof": proof}


def _activation_baseline(root: Path, key: str) -> Dict[str, Any]:
    """Freeze the exact index mapping and active source; never infer a new identity."""
    index_path = root / "rules" / "index.json"
    index_bytes = index_path.read_bytes()
    index = json.loads(index_bytes.decode("utf-8"))
    if not isinstance(index, dict) or not isinstance(index.get("assays"), list):
        raise AuthoringReadinessError("authoring_proof_active_mapping_invalid")
    rows = [row for row in index.get("assays", []) if isinstance(row, dict) and canonical_assay_key(str(row.get("assay_key", ""))) == canonical_assay_key(key)]
    if len(rows) > 1:
        raise AuthoringReadinessError("authoring_proof_active_mapping_ambiguous")
    if rows and str(rows[0].get("assay_key", "")).strip() != key:
        raise AuthoringReadinessError("authoring_proof_assay_key_case_conflict")
    file_name = str(rows[0].get("ruleset_file") or "") if rows else ""
    active = _require_contained_active_ruleset(root, file_name) if rows else None
    if active is not None and (Path(file_name).name != file_name or active.parent != (root / "rules").resolve()):
        raise AuthoringReadinessError("authoring_proof_active_mapping_invalid")
    known_keys = {canonical_assay_key(str(row.get("assay_key", ""))) for row in index["assays"] if isinstance(row, dict) and row.get("assay_key")}
    known_keys.add(canonical_assay_key(key))
    return {"index_path": str(index_path), "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
            "known_assay_keys": sorted(known_keys), "section_keys": sorted(item for item in known_keys if not re.fullmatch(r"\([0-9a-f]{4}\)", item)),
            "mode": "update" if rows else "create", "ruleset_file": file_name,
            "active_ruleset_path": str(active) if active else "",
            "active_ruleset_sha256": _sha256_file(active) if active else ""}


def _proof_record(proof: Dict[str, Any]) -> Dict[str, Any]:
    """Extraction values exist only in the transient UI result, never in the sidecar."""
    record = {key: value for key, value in proof.items() if key != "test_error"}
    for label in ("primary", "secondary"):
        if isinstance(record.get(label), dict):
            record[label] = {key: value for key, value in record[label].items() if key not in {"data", "lot_id", "error"}}
            header = record[label].get("assay_header")
            if isinstance(header, dict) and "assay_name" in header:
                # Actual source header text is also transient. Its exact
                # identity remains verifiable without storing PDF text.
                record[label]["assay_header"] = {
                    "assay_key": header.get("assay_key", ""),
                    "header_sha256": hashlib.sha256(json.dumps(header, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
                }
    return record


def _proof_digest(proof: Dict[str, Any]) -> str:
    data = {key: value for key, value in _proof_record(proof).items() if key != "proof_sha256"}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _publish_attempt(root: Path, proof_path: Path, attempt: str, proof: Dict[str, Any]) -> None:
    # V1 and V2 use the same short lifecycle critical section and sidecar CAS.
    with rulesuite_lifecycle_lock(str(root)):
        try:
            current = json.loads(proof_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AuthoringReadinessError("authoring_proof_attempt_superseded") from exc
        if current.get("attempt_id") != attempt:
            raise AuthoringReadinessError("authoring_proof_attempt_superseded")
        _write_json_atomic(proof_path, proof)


def _create_authoring_proof_v2(root_path: str, key: str, draft_path: str, pdf_path: str,
                               sources: Callable[[], Iterable[Dict[str, Any]]], *,
                               identity_store_path: str | None = None) -> Dict[str, Any]:
    from .rulesuite import RuleSuite
    from .identity_authoring import bind_identity_test, identity_proof_context

    root = Path(root_path).resolve()
    draft = _require_contained_draft(root, draft_path)
    proof_path = _proof_path(draft)
    attempt = uuid4().hex
    with rulesuite_lifecycle_lock(str(root)), rulesuite_draft_lock(draft):
        _require_contained_draft(root, str(draft))
        draft_bytes = draft.read_bytes()
        _write_json_atomic(proof_path, {"version": 2, "status": "pending", "attempt_id": attempt})
        identity_context = identity_proof_context(root, key, draft, store_path=identity_store_path)
    data = json.loads(draft_bytes.decode("utf-8"))
    key = str(key or "").strip()
    if not key or not isinstance(data, dict) or str(data.get("assay_key") or "").strip() != key:
        raise AuthoringReadinessError("authoring_proof_assay_key_mismatch")
    structural = _validate_draft_data(data)
    if not structural.get("ok"):
        raise AuthoringReadinessError(f"authoring_proof_draft_invalid: {structural.get('errors', [])}")
    proof: Dict[str, Any] = {
        "version": 2, "status": "blocked", "attempt_id": attempt, "project_root": str(root), "assay_key": key,
        "assay_name": str(data.get("assay_name") or ""), "draft_path": str(draft),
        "draft_sha256": hashlib.sha256(draft_bytes).hexdigest(),
        "activation_baseline": _activation_baseline(root, key), "errors": [],
        "primary": {"status": "failed", "data": {}},
        "secondary": {"status": "not_available", "message": "Einmal geprüft – Zweitprüfung noch offen", "data": {}},
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if identity_context is not None:
        proof["identity_case"] = identity_context
    service = RuleSuite()
    with tempfile.TemporaryDirectory(prefix="are-rule-proof-") as temporary:
        frozen_draft = Path(temporary) / "tested.draft.json"
        frozen_draft.write_bytes(draft_bytes)

        def evaluate(path: Path, payload: bytes, label: str, expected_header=None) -> Dict[str, Any]:
            frozen_pdf = Path(temporary) / f"{label}.pdf"
            frozen_pdf.write_bytes(payload)
            result = {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest(), "status": "failed", "data": {}}
            try:
                preview = service.preview_extract(str(root), str(frozen_pdf), key, draft_path=str(frozen_draft),
                                                  strict=True, expected_header=expected_header,
                                                  known_assay_keys=proof["activation_baseline"]["known_assay_keys"])
                result.update(status="passed", data=preview["data"], lot_id=preview["lot_id"], assay_header=preview["assay_header"])
            except Exception as exc:
                result.update(error=str(exc), data=dict(getattr(exc, "partial_data", {}) or {}),
                              missing_fields=list(getattr(exc, "missing_fields", ()) or ()))
                # Eligibility is established by the strict header before extraction.
                result["eligible"] = bool(getattr(exc, "authoring_header", None))
                result["incompatible"] = isinstance(exc, RuleSuiteError) and str(exc) in {
                    "authoring_pdf_assay_header_missing_or_ambiguous", "authoring_pdf_assay_header_ambiguous",
                    "authoring_pdf_assay_header_incompatible"}
                result["error_code"] = "configured_fields_empty" if result["missing_fields"] else "assay_header_incompatible" if result["incompatible"] else "extraction_failed"
            result["field_keys"] = list(result["data"])
            result["field_states"] = {field: "missing" if value is None or value == "" else "extracted"
                                      for field, value in result["data"].items()}
            return result

        try:
            primary = _require_pdf(pdf_path, "test_pdf")
            primary_bytes = primary.read_bytes()
            proof["primary"] = evaluate(primary, primary_bytes, "primary")
            if proof["primary"]["status"] == "passed":
                if identity_context is not None:
                    proof["identity_case"] = bind_identity_test(identity_context, proof["primary"]["assay_header"])
                for source in sources():
                    if source.get("local") is not True:
                        continue
                    try:
                        candidate = _require_pdf(str(source.get("path") or ""), "secondary_pdf")
                        candidate_bytes = candidate.read_bytes()
                    except (OSError, AuthoringReadinessError):
                        continue
                    candidate_hash = hashlib.sha256(candidate_bytes).hexdigest()
                    if candidate_hash == proof["primary"]["sha256"] or candidate_hash != source.get("sha256"):
                        continue
                    outcome = evaluate(candidate, candidate_bytes, "secondary", proof["primary"]["assay_header"])
                    if outcome.get("incompatible"):
                        continue
                    allowed_source_fields = ("kind", "path", "original_path", "sha256", "ingestion_id", "job_id", "report_id", "run_id",
                                             "store_path", "selection_token", "revision_id", "ruleset_file", "ruleset_sha256",
                                             "source_rule_sha256", "source_project_root", "source_provenance_sha256", "ledger_record_sha256")
                    outcome["source"] = {field: source[field] for field in allowed_source_fields
                                         if field in source and isinstance(source[field], (str, int)) and not isinstance(source[field], bool)}
                    proof["secondary"] = outcome
                    break  # First eligible failure is final; never search for a greener PDF.
            else:
                proof["errors"].append("authoring_proof_primary_failed")
        except Exception as exc:
            proof["errors"].append(f"authoring_proof_test_failed: {type(exc).__name__}")
            proof["test_error"] = str(exc)
            if proof["primary"]["status"] == "passed":
                proof["secondary"] = {"status": "failed", "error_code": "source_discovery_failed", "data": {}}
    if proof["secondary"]["status"] == "failed":
        proof["errors"].append("authoring_proof_secondary_failed")
    proof["status"] = "ready" if not proof["errors"] else "blocked"
    proof["proof_sha256"] = _proof_digest(proof)
    checked = _verify_authoring_proof_v2(root, key, draft, proof)
    if proof["status"] == "ready" and not checked["ok"]:
        proof["status"] = "blocked"
        proof["errors"].extend(checked["errors"])
        proof["proof_sha256"] = _proof_digest(proof)
    # Another attempt may have revoked this one while extraction ran.
    _publish_attempt(root, proof_path, attempt, _proof_record(proof))
    return proof


def _verify_authoring_proof_v2(root: Path, key: str, draft: Path, proof: Dict[str, Any]) -> Dict[str, Any]:
    from .identity_authoring import verify_identity_proof

    errors = []
    if not all(isinstance(proof.get(label), dict) for label in ("primary", "secondary")):
        return {"ok": False, "errors": ["authoring_proof_not_ready"], "proof": proof}
    if proof.get("status") != "ready":
        errors.append("authoring_proof_not_ready")
    if proof.get("proof_sha256") != _proof_digest(proof):
        errors.append("authoring_proof_content_changed")
    if proof.get("project_root") != str(root) or proof.get("draft_path") != str(draft):
        errors.append("authoring_proof_draft_path_mismatch")
    if proof.get("assay_key") != key:
        errors.append("authoring_proof_assay_key_mismatch")
    errors.extend(verify_identity_proof(root, key, draft, proof))
    fields: list[str] = []
    try:
        payload = draft.read_bytes()
        if hashlib.sha256(payload).hexdigest() != proof.get("draft_sha256"):
            errors.append("authoring_proof_draft_changed")
        data = json.loads(payload.decode("utf-8"))
        if not isinstance(data, dict) or data.get("assay_key") != key or data.get("assay_name") != proof.get("assay_name"):
            errors.append("authoring_proof_assay_key_mismatch")
        else:
            fields = [str(field["key"]) for field in data.get("extract_rules", {}).get("fields", []) if isinstance(field, dict) and field.get("key")]
        baseline = _activation_baseline(root, key)
        recorded = proof.get("activation_baseline", {})
        binding_keys = ("mode", "ruleset_file", "active_ruleset_path", "active_ruleset_sha256")
        if not isinstance(recorded, dict) or any(baseline.get(field) != recorded.get(field) for field in binding_keys):
            errors.append("authoring_proof_active_mapping_changed")
        if not isinstance(recorded, dict) or recorded.get("section_keys") != baseline["section_keys"]:
            errors.append("authoring_proof_section_context_changed")
    except (OSError, ValueError, AuthoringReadinessError):
        errors.append("authoring_proof_source_unreadable")
    for label in ("primary", "secondary"):
        outcome = proof.get(label, {})
        if label == "secondary" and outcome.get("status") == "not_available":
            continue
        if outcome.get("status") != "passed":
            errors.append(f"authoring_proof_{label}_failed")
        if outcome.get("field_keys") != fields or outcome.get("field_states") != {field: "extracted" for field in fields}:
            errors.append(f"authoring_proof_{label}_fields_incomplete")
        try:
            from src.ingestion.api import verified_pdf_location
            original = str(outcome.get("path") or "")
            source = outcome.get("source", {}) if label == "secondary" else {}
            if source.get("kind") in {"current_import", "result_history"} and source.get("original_path"):
                if source.get("sha256") != outcome.get("sha256"):
                    errors.append("authoring_proof_source_changed")
                else:
                    original = source["original_path"]
            path = Path(verified_pdf_location(root, original, str(outcome.get("sha256") or "")))
            if _sha256_file(path) != outcome.get("sha256"):
                errors.append(f"authoring_proof_{label}_changed")
        except (OSError, RuntimeError, ValueError):
            errors.append(f"authoring_proof_{label}_missing")
    if proof.get("secondary", {}).get("status") == "passed":
        if proof["secondary"].get("sha256") == proof.get("primary", {}).get("sha256"):
            errors.append("authoring_proof_secondary_must_differ")
        if proof["secondary"].get("assay_header") != proof.get("primary", {}).get("assay_header"):
            errors.append("authoring_proof_secondary_header_mismatch")
        errors.extend(_verify_source_state(root, proof["secondary"].get("source", {})))
    return {"ok": not errors, "errors": list(dict.fromkeys(errors)), "proof": proof}


def _verify_source_state(root: Path, source: Dict[str, Any]) -> list[str]:
    """Recheck frozen public ledger/history pointers, without source discovery or writes."""
    if not isinstance(source, dict):
        return ["authoring_proof_source_invalid"]
    if source.get("kind") not in {"current_import", "result_history"}:
        return []
    from src.ingestion.api import get_import_record, resolve_current_path
    from src.resultstore.api import get_report_runs, get_result_run

    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()

    try:
        from src.ingestion.api import verified_pdf_location
        if source.get("ingestion_id"):
            known_record = get_import_record(root, source["ingestion_id"])
            if known_record is not None and resolve_current_path(root, known_record.processing_job_id, known_record.original_path).path_status == "ambiguous":
                return ["authoring_proof_source_changed"]
        effective_path = Path(verified_pdf_location(root, source.get("original_path") or source["path"], source["sha256"])).resolve()
        relocated = effective_path != Path(source["path"]).resolve()
        if source["kind"] == "current_import" and not source.get("ingestion_id"):
            return ["authoring_proof_source_invalid"]
        if source.get("ingestion_id"):
            record = get_import_record(root, source["ingestion_id"])
            if record is None or record.processing_job_id != source.get("job_id") or str(record.content_sha256).lower() != source.get("sha256"):
                return ["authoring_proof_source_changed"]
            path, original = Path(record.current_path).resolve(), Path(record.original_path).resolve()
            relocated = effective_path != path
            if (not relocated and path != Path(source["path"]).resolve()) or original != Path(source.get("original_path", "")).resolve():
                return ["authoring_proof_source_changed"]
            if not relocated and (record.archive_status not in {"NOT_REQUIRED", "PENDING"} or record.archived_at_utc or (path != original and record.archive_status != "NOT_REQUIRED")):
                return ["authoring_proof_source_changed"]
            if not relocated and any(raw and (path == Path(raw).resolve() or path.is_relative_to(Path(raw).resolve()))
                   for raw in (record.watch_backup_path, record.archive_target, record.planned_archive_path)):
                return ["authoring_proof_source_changed"]
            resolved = resolve_current_path(root, record.processing_job_id, record.original_path)
            if resolved.path_status != "resolved" or resolved.ingestion_id != source["ingestion_id"] or Path(resolved.current_pdf_path).resolve() != effective_path:
                return ["authoring_proof_source_changed"]
        if source["kind"] == "result_history":
            spec = {"driver": "sqlite", "path": source["store_path"]}
            row = get_result_run(spec, source["run_id"])
            report = get_report_runs(spec, source["report_id"])
            if row is None or report is None or row.get("revision_error") or not any(item.get("id") == source["run_id"] for item in report["runs"]):
                return ["authoring_proof_source_changed"]
            if any(row.get(field) != source.get(field) for field in ("selection_token", "revision_id", "ruleset_file")):
                return ["authoring_proof_source_changed"]
            original = row["original_result"]
            resolved = resolve_current_path(root, row["job_id"], original["pdf_path"])
            if resolved.path_status in {"ambiguous", "unavailable"} or resolved.ingestion_id != source.get("ingestion_id", "") or Path(resolved.current_pdf_path).resolve() != effective_path:
                return ["authoring_proof_source_changed"]
            if str(original.get("pdf_sha256") or "").lower() != source["sha256"]:
                return ["authoring_proof_source_changed"]
            selected = next((item["result"] for item in row.get("result_revisions", []) if item["revision_id"] == row.get("revision_id")), row.get("source_provenance") or {})
            provenance = selected.get("source_provenance", selected)
            if digest(provenance) != source.get("source_provenance_sha256") or str(selected.get("rule_sha256") or "") != source.get("ruleset_sha256"):
                return ["authoring_proof_source_changed"]
    except Exception:
        return ["authoring_proof_source_unreadable"]
    return []


def _verified_activation_bytes(root: Path, key: str, draft_path: str, expected_proof: Dict[str, Any]) -> bytes:
    """Called only inside the lifecycle lock. Hash/read only; no PDF parsing."""
    report = verify_authoring_proof(str(root), key, draft_path)
    if not report.get("ok") or report.get("proof") != expected_proof or expected_proof.get("version") not in {1, 2}:
        raise AuthoringReadinessError(",".join(report.get("errors", ())) or "authoring_proof_attempt_changed")
    payload = Path(draft_path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_proof.get("draft_sha256"):
        raise AuthoringReadinessError("authoring_proof_draft_changed")
    return payload


def _require_contained_draft(root: Path, draft_path: str) -> Path:
    draft = Path(draft_path).resolve()
    draft_root = (root / "rules" / "drafts").resolve()
    try:
        draft.relative_to(draft_root)
    except ValueError as exc:
        raise AuthoringReadinessError("authoring_proof_draft_outside_rules_drafts") from exc
    if not draft.is_file():
        raise AuthoringReadinessError("authoring_proof_draft_missing")
    return draft


def _require_pdf(path: str, label: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_file() or resolved.suffix.casefold() != ".pdf":
        raise AuthoringReadinessError(f"authoring_proof_{label}_missing")
    return resolved


def _require_contained_active_ruleset(root: Path, ruleset_file: str) -> Path:
    rules_root = (root / "rules").resolve()
    candidate = (rules_root / ruleset_file).resolve()
    try:
        candidate.relative_to(rules_root)
    except ValueError as exc:
        raise AuthoringReadinessError("authoring_proof_active_ruleset_missing") from exc
    if not ruleset_file.strip() or not candidate.is_file():
        raise AuthoringReadinessError("authoring_proof_active_ruleset_missing")
    return candidate


def _proof_path(draft: Path) -> Path:
    return draft.with_name(draft.name + ".readiness")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
