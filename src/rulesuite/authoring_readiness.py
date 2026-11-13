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
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from .required_fields import check_required_fields
from .validation import _validate_draft_data
from .json_io import _read_json_object

_PROOF_VERSION = 2


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


def _capture_proof_inputs(root: Path, key: str, draft: Path, failing_path: str, reference_path: str | None):
    draft_bytes = draft.read_bytes()
    draft_data = json.loads(draft_bytes)
    if not isinstance(draft_data, dict) or str(draft_data.get("assay_key", "")).strip() != key:
        raise AuthoringReadinessError("authoring_proof_assay_key_mismatch")
    structural = _validate_draft_data(draft_data)
    if not structural.get("ok"):
        raise AuthoringReadinessError(f"authoring_proof_draft_invalid: {structural.get('errors', [])}")
    index_path = root / "rules" / "index.json"
    index_bytes = index_path.read_bytes()
    index = json.loads(index_bytes)
    rows = index.get("assays") if isinstance(index, dict) else None
    if not isinstance(rows, list):
        raise AuthoringReadinessError("authoring_proof_index_invalid")
    matches = [row for row in rows if isinstance(row, dict) and str(row.get("assay_key", "")).strip() == key]
    if len(matches) > 1:
        raise AuthoringReadinessError("authoring_proof_active_binding_ambiguous")
    active = _require_contained_active_ruleset(root, str(matches[0].get("ruleset_file") or "")) if matches else None
    failing = _require_pdf(failing_path, "failing_pdf")
    if active is not None and not str(reference_path or "").strip():
        raise AuthoringReadinessError("authoring_proof_reference_pdf_required")
    reference = _require_pdf(str(reference_path), "reference_pdf") if active is not None else None
    values = {"draft": (draft, draft_bytes), "index": (index_path, index_bytes),
              "failing_pdf": (failing, failing.read_bytes())}
    if active is not None:
        values["active_ruleset"] = (active, active.read_bytes())
        values["reference_pdf"] = (reference, reference.read_bytes())
        if reference == failing or values["reference_pdf"][1] == values["failing_pdf"][1]:
            raise AuthoringReadinessError("authoring_proof_reference_must_differ")
    return {"mode": "update" if active is not None else "create", "assay_name": draft_data.get("assay_name"),
        "files": values, "binding": {name: {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()} for name, (path, raw) in values.items()}}


def _attempt_is_current(proof_path, attempt):
    try:
        value = json.loads(proof_path.read_text(encoding="utf-8"))
        return isinstance(value, dict) and value.get("attempt_id") == attempt
    except (OSError, ValueError):
        return False


def create_authoring_proof(project_root: str, assay_key: str, draft_path: str,
                           failing_pdf_path: str, reference_pdf_path: str | None = None) -> Dict[str, Any]:
    """Extract only privately frozen bytes; publish ready for this attempt only."""
    from .rulesuite import RuleSuite
    from .lifecycle import rulesuite_draft_lock, rulesuite_lifecycle_lock

    root, key = Path(project_root).resolve(), str(assay_key or "").strip()
    draft = _require_contained_draft(root, draft_path)
    proof_path, attempt = _proof_path(draft), uuid4().hex
    pending = {"version": _PROOF_VERSION, "status": "pending", "attempt_id": attempt, "draft_path": str(draft),
               "started_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        # Locks are short-lived: real PDF extraction may exceed the draft TTL.
        with rulesuite_lifecycle_lock(str(root)), rulesuite_draft_lock(draft):
            _write_json_atomic(proof_path, pending)
            if not key:
                raise AuthoringReadinessError("authoring_proof_assay_key_missing")
            captured = _capture_proof_inputs(root, key, draft, failing_pdf_path, reference_pdf_path)
        with tempfile.TemporaryDirectory(prefix="arev2-authoring-proof-") as temporary:
            frozen_root = Path(temporary)
            frozen_paths = {}
            for name, (original, raw) in captured["files"].items():
                if name == "index":
                    destination = frozen_root / "rules" / "index.json"
                elif name == "active_ruleset":
                    destination = frozen_root / "rules" / original.relative_to((root / "rules").resolve())
                elif name == "draft":
                    destination = frozen_root / "rules" / "drafts" / original.name
                else:
                    destination = frozen_root / name / original.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                frozen_paths[name] = str(destination)
            if captured["mode"] == "update":
                # Absolute in-root paths and symlink aliases in the real index
                # must resolve to captured bytes, never back to a live file.
                private_index = json.loads(captured["files"]["index"][1])
                private_active = Path(frozen_paths["active_ruleset"]).relative_to(frozen_root / "rules").as_posix()
                for row in private_index["assays"]:
                    if isinstance(row, dict) and str(row.get("assay_key", "")).strip() == key:
                        row["ruleset_file"] = private_active
                Path(frozen_paths["index"]).write_text(json.dumps(private_index), encoding="utf-8")
            service = RuleSuite()
            failing_result = service.preview_extract(str(frozen_root), frozen_paths["failing_pdf"], key, draft_path=frozen_paths["draft"])
            compared_fields = []
            if captured["mode"] == "update":
                active_reference = service.preview_extract(str(frozen_root), frozen_paths["reference_pdf"], key, draft_path=None)
                draft_reference = service.preview_extract(str(frozen_root), frozen_paths["reference_pdf"], key, draft_path=frozen_paths["draft"])
                expected, actual = dict(active_reference.get("data") or {}), dict(draft_reference.get("data") or {})
                compared_fields = list(expected)
                mismatches = [field for field in compared_fields if actual.get(field) != expected.get(field)]
                if str(draft_reference.get("lot_id") or "") != str(active_reference.get("lot_id") or ""):
                    mismatches.append("lot_id")
                if mismatches:
                    raise AuthoringReadinessError("authoring_proof_reference_mismatch: " + ",".join(dict.fromkeys(mismatches)))
        proof = {**pending, "status": "ready", "assay_key": key, "assay_name": captured["assay_name"], "mode": captured["mode"],
            "input_snapshot": "exact-bytes-v1", "input_bindings": captured["binding"],
            "compared_fields": compared_fields, "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "failing_result_fields": list(dict(failing_result.get("data") or {}))}
        for name in ("draft", "failing_pdf", "reference_pdf", "active_ruleset", "index"):
            binding = captured["binding"].get(name, {})
            proof[name + "_path"] = binding.get("path", "")
            proof[name + "_sha256"] = binding.get("sha256", "")
        with rulesuite_lifecycle_lock(str(root)), rulesuite_draft_lock(draft):
            if not _attempt_is_current(proof_path, attempt):
                raise AuthoringReadinessError("authoring_proof_superseded")
            current = _capture_proof_inputs(root, key, draft, failing_pdf_path, reference_pdf_path)
            if current["binding"] != captured["binding"] or current["mode"] != captured["mode"]:
                raise AuthoringReadinessError("authoring_proof_inputs_changed_during_check")
            _write_json_atomic(proof_path, proof)
        return proof
    except Exception as exc:
        # A superseded attempt must never overwrite a newer pending/failed one.
        try:
            with rulesuite_draft_lock(draft):
                if _attempt_is_current(proof_path, attempt):
                    _write_json_atomic(proof_path, {**pending, "status": "failed", "error": str(exc)})
        except Exception:
            pass  # Leaving pending is fail-closed as well.
        raise


def verify_authoring_proof(project_root: str, assay_key: str, draft_path: str) -> Dict[str, Any]:
    root = Path(project_root).resolve()
    try:
        draft = _require_contained_draft(root, draft_path)
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
            return {"ok": False, "errors": ["authoring_proof_not_ready"], "proof": proof}
        errors, key = [], str(assay_key or "").strip()
        if proof.get("assay_key") != key:
            errors.append("authoring_proof_assay_key_mismatch")
        if proof.get("draft_path") != str(draft):
            errors.append("authoring_proof_draft_path_mismatch")
        for name in ("draft", "failing_pdf", "reference_pdf", "active_ruleset", "index"):
            raw_path, expected = proof.get(name + "_path"), proof.get(name + "_sha256")
            if name in {"reference_pdf", "active_ruleset"} and proof.get("mode") == "create":
                continue
            path = Path(raw_path).resolve() if raw_path else None
            if path is None or not path.is_file():
                errors.append(f"authoring_proof_{name}_missing")
            elif _sha256_file(path) != expected:
                errors.append(f"authoring_proof_{name}_changed")
        from .rulesuite import RuleSuite
        diff = RuleSuite().diff_draft_vs_active(str(root), key, str(draft))
        if diff.get("mode") != proof.get("mode"):
            errors.append("authoring_proof_mode_changed")
        if diff.get("mode") == "update":
            current_active = _require_contained_active_ruleset(root, str(diff.get("ruleset_file") or ""))
            if str(current_active) != proof.get("active_ruleset_path"):
                errors.append("authoring_proof_active_binding_changed")
        if proof.get("input_snapshot") != "exact-bytes-v1":
            errors.append("authoring_proof_snapshot_required")
        return {"ok": not errors, "errors": errors, "proof": proof}
    except Exception as exc:
        return {"ok": False, "errors": [str(exc)]}


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
