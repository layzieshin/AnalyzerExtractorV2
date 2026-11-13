"""Public API for the single versioned QC/device authority."""
from .model import MutationContext, QCAnalysis, QCPdfReport, QCConfigurationError, QCConflictError, QCReportError, QCStoreError, QualityControlError, content_hash
from .store import (
    close_lot, configure_lot, get_inventory, get_lot, get_report_evidence, get_status,
    legacy_device_source, list_lots, lot_identity, migrate_legacy_devices, open_lot, reopen_lot, save_inventory,
    resolve_store_path as validate_store_spec,
)
from .profiles import get_profile, list_profiles, save_profile
from .sources import get_lot_sources
from .analysis import analyze_lot
from .pdf_report import export_report_evidence, render_analysis_pdf

__all__ = [
    "MutationContext", "QCConfigurationError", "QCConflictError", "QCStoreError", "QualityControlError",
    "get_inventory", "get_status", "legacy_device_source", "migrate_legacy_devices", "save_inventory",
    "close_lot", "configure_lot", "get_lot", "get_lot_sources", "get_profile", "get_report_evidence",
    "list_lots", "list_profiles", "open_lot", "reopen_lot", "save_profile",
    "lot_identity",
    "validate_store_spec",
    "QCAnalysis", "QCReportError", "analyze_lot",
    "QCPdfReport", "export_report_evidence", "render_analysis_pdf",
    "get_sd_reference_context",
]


def _reference_birth(history, current, control_id, reference):
    """Prove the complete immutable chain, then locate this continuous binding."""
    records = {row["version_id"]: row for row in history if row["lot_key"] == current["lot_key"]}
    chain, seen, row = [], set(), current
    while row is not None:
        identifier = row["version_id"]
        if identifier in seen or row["lot_key"] != current["lot_key"]:
            return None
        seen.add(identifier)
        chain.append(row)
        previous = row["predecessor_id"]
        if previous == 0:
            break
        if not isinstance(previous, int) or previous >= identifier or previous not in records:
            return None
        row = records[previous]
    if not chain or chain[-1]["predecessor_id"] != 0:
        return None
    origin = chain[0]
    for previous in chain[1:]:
        if previous["snapshot"].get("sd_references", {}).get(control_id) != reference:
            break
        origin = previous
    return origin


def get_sd_reference_context(store_spec, *, lot_key: str, expected_version_id: int):
    """Read-only origin evidence for the exact stored lot/reference binding.

    Direct profile bindings cover baseline and newly declared manual references.
    Older manual references require an unbroken lot chain and its frozen source
    profile. No old reference, profile, schema or evidence is rewritten.
    """
    current = get_lot(store_spec, lot_key)
    if current["version_id"] != expected_version_id:
        raise QCConflictError("Die Charge wurde geändert. Bitte die SD-Referenzen neu laden.")
    snapshot = current["snapshot"]
    context = {"context_version": "qc-sd-origin-v1", "store_path": str(validate_store_spec(store_spec)),
               "lot_key": lot_key, "lot_version_id": current["version_id"],
               "lot_snapshot_hash": content_hash(snapshot),
               **{key: snapshot[key] for key in ("device_id", "assay_key", "kit_lot")}, "references": {}}
    history = list_lots(store_spec, include_history=True)
    for identifier, reference in snapshot["sd_references"].items():
        entry = {"reference_hash": content_hash(reference), "reason": "sd_origin_unavailable"}
        context["references"][identifier] = entry
        if not isinstance(reference, dict):
            continue
        reference_payload = {key: value for key, value in reference.items() if key != "reference_id"}
        expected_id = content_hash({"control_id": identifier, "reference": reference_payload})
        if reference.get("reference_id") != expected_id:
            continue
        origin = _reference_birth(history, current, identifier, reference)
        version_id = reference.get("profile_version_id")
        legacy_manual = version_id is None and reference.get("kind") == "manual"
        if legacy_manual and origin is not None:
            version_id = origin["snapshot"].get("profile_version_id")
        if not isinstance(version_id, int) or isinstance(version_id, bool) or version_id <= 0:
            continue
        try:
            profile = get_profile(store_spec, version_id)
        except QCConfigurationError:
            continue
        if legacy_manual:
            source = origin["snapshot"].get("source_manifest", {}) if origin else {}
            if (source.get("profile_version_id") != version_id
                    or source.get("profile_snapshot") != profile["snapshot"]
                    or source.get("device_id") != snapshot["device_id"]
                    or source.get("assay_key") != snapshot["assay_key"]
                    or source.get("kit_lot") != snapshot["kit_lot"]):
                continue
        entry.update(reason="", origin_profile_version_id=version_id,
                     origin_profile_snapshot=profile["snapshot"], origin_profile_hash=content_hash(profile["snapshot"]),
                     origin_lot_version_id=origin["version_id"] if origin else None,
                     origin_lot_snapshot_hash=content_hash(origin["snapshot"]) if origin else None,
                     provenance="lot-history" if legacy_manual else "frozen-profile-version")
    if get_lot(store_spec, lot_key) != current:
        raise QCConflictError("Die Charge oder ihre SD-Referenzen wurden während des Lesens geändert. Bitte neu laden.")
    return context
