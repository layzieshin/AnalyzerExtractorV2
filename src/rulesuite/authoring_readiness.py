"""Authoring-Readiness: Strukturvalidierung und optional Pflichtfeld-Treffer gegen Assay-Text.

Semantik (AP-6.1):
- ``check_authoring_readiness`` ohne *assay_text*: nur Strukturcheck via ``_validate_draft_data``.
  ``ok=true`` ist möglich, enthält aber immer Warning ``no_assay_text`` — **keine** fachliche Freigabe.
- Mit *assay_text* (oder CLI ``--pdf``): zusätzlich ``check_required_fields`` für die sechs Pflicht-Header.
  ``ok=true`` bedeutet Struktur + alle Pflichtfelder confirmed → fachliche Readiness für Testbetrieb.
- ``check_required`` / ``readiness --assay-text`` sind die fachlichen Vorab-Checks mit Beispieltext/PDF.
- ``activate_draft`` / ``activate_new_draft`` bleiben strukturell (``validate_draft`` only); PDF-Treffer-Gate
  liegt bewusst hier, in CLI/GUI/PyQt — nicht in ``activate_*``.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .required_fields import check_required_fields
from .validation import _validate_draft_data
from .json_io import _read_json_object
from pathlib import Path


def check_authoring_readiness(
    draft_path: str,
    assay_text: str | None = None,
    *,
    group: int = 1,
) -> Dict[str, Any]:
    """Prüft Draft-Struktur und optional die sechs Pflicht-Header gegen *assay_text*.

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
