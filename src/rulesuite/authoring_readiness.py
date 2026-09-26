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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from .required_fields import check_required_fields
from .validation import _validate_draft_data
from .json_io import _read_json_object

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
) -> Dict[str, Any]:
    """Create a hash-bound proof for the current draft and its acceptance PDFs."""
    from .rulesuite import RuleSuite

    root = Path(project_root).resolve()
    draft = _require_contained_draft(root, draft_path)
    proof_path = _proof_path(draft)
    # Starting a new check revokes an older proof immediately. Otherwise a
    # failed attempt with a newly selected problem PDF could leave a previous
    # proof usable for activation.
    _write_json_atomic(
        proof_path,
        {
            "version": _PROOF_VERSION,
            "status": "pending",
            "draft_path": str(draft),
            "started_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        },
    )
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
    _write_json_atomic(proof_path, proof)
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
    if not isinstance(proof, dict) or proof.get("version") != _PROOF_VERSION:
        return {"ok": False, "errors": ["authoring_proof_version_invalid"]}
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
