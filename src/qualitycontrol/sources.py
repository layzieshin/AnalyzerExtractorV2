"""Read-only validated population capture; its manifest defines the exact input.

Result and validation owners provide independent read transactions. This module
does not describe those reads as one atomic latest database snapshot. Publication
rechecks the complete manifest while the QC writer holds BEGIN IMMEDIATE.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from collections.abc import Mapping
from typing import Any

from src.resultstore.api import list_result_runs
from src.resultvalidation.api import ResultValidationError, ValidationAmbiguousError, list_run_validations_readonly

from .model import QCConfigurationError, QCStoreError, content_hash
from .profiles import get_profile, list_profiles, parse_decimal, parse_measurement_date
from .store import get_inventory, resolve_store_path


def _validations(store_spec: Mapping[str, Any], ids: list[int]) -> tuple[dict[int, Any], dict[int, str]]:
    if not ids:
        return {}, {}
    try:
        return dict(list_run_validations_readonly(store_spec, ids).latest_by_run_id), {}
    except ValidationAmbiguousError:
        found, errors = {}, {}
        for run_id in ids:
            try:
                found.update(list_run_validations_readonly(store_spec, [run_id]).latest_by_run_id)
            except ValidationAmbiguousError:
                errors[run_id] = "validation_ambiguous"
            except ResultValidationError:
                errors[run_id] = "validation_unreadable"
        return found, errors
    except ResultValidationError as exc:
        raise QCStoreError(f"Die Validierungsnachweise sind unlesbar: {exc}") from exc


def _matches_validation(record: Any, row: dict[str, Any]) -> bool:
    if record.revision_id != int(row.get("revision_id") or 0) or record.selection_id != row.get("selection_id"):
        return False
    if record.selection_token:
        return record.selection_token == row.get("selection_token")
    return (record.revision_id == 0 and row.get("selection_id") is None
            and not row.get("result_revisions") and not row.get("pending_revision"))


def get_lot_sources(store_spec: Mapping[str, Any], *, profile_version_id: int, kit_lot: str) -> dict[str, Any]:
    profile = get_profile(store_spec, profile_version_id)
    inventory = get_inventory(store_spec)
    configuration = profile["snapshot"]
    separate_time = bool(configuration.get("measurement_time_field"))
    # Do not normalize kit-lot text: its exact extracted identity is the key.
    if not isinstance(kit_lot, str) or not kit_lot.strip():
        raise QCConfigurationError("Eine genaue extrahierte Kit-Charge ist erforderlich.")
    all_rows = list_result_runs(dict(store_spec), limit=None)["runs"]
    rows = [row for row in all_rows if row.get("device_id") == configuration["device_id"]
            and row.get("assay_key") == configuration["assay_key"] and row.get("lot_id") == kit_lot]
    records, errors = _validations(store_spec, [int(row["id"]) for row in rows if row.get("id") is not None])
    device = next((row for row in inventory["snapshot"]["devices"] if row["device_id"] == configuration["device_id"]), None)
    inventory_usable = bool(inventory["version_id"] and device and device["active"] and not device["incomplete"])
    head = next((item["version_id"] for item in list_profiles(store_spec) if item["profile_id"] == profile["profile_id"]), 0)
    population, included, excluded = [], [], []
    for row in sorted(rows, key=lambda item: int(item.get("id") or 0)):
        run_id = row.get("id")
        validation = records.get(run_id)
        reasons = []
        if not inventory_usable:
            reasons.append("device_incomplete_or_inactive")
        if row.get("id") is None or row.get("revision_error") or row.get("payload_parse_error"):
            reasons.append("result_unreadable")
        if row.get("pending_revision"):
            reasons.append("result_choice_pending")
        if row.get("missing_fields"):
            reasons.append("result_incomplete")
        if run_id in errors:
            reasons.append(errors[run_id])
        elif validation is None:
            reasons.append("validation_missing")
        elif not _matches_validation(validation, row):
            reasons.append("validation_binding_mismatch")
        payload = row.get("payload")
        if not isinstance(payload, dict):
            payload = {}
            reasons.append("result_unreadable")
        try:
            measured_at = parse_measurement_date(payload.get(configuration["measurement_date_field"]), configuration["measurement_date_format"])
        except QCConfigurationError:
            measured_at = None
            reasons.append("measurement_date_invalid")
        if separate_time:
            time_raw = payload.get(configuration["measurement_time_field"])
            if time_raw is None or (isinstance(time_raw, str) and not time_raw.strip()):
                measured_at = None
                reasons.append("measurement_time_missing")
            else:
                try:
                    parsed_time = datetime.fromisoformat(parse_measurement_date(time_raw, configuration["measurement_time_format"])).time()
                    if measured_at is not None:
                        measured_at = datetime.combine(datetime.fromisoformat(measured_at).date(), parsed_time).isoformat()
                except QCConfigurationError:
                    measured_at = None
                    reasons.append("measurement_time_invalid")
        grouping_field = configuration["run_grouping_field"]
        grouping_raw = payload.get(grouping_field) if grouping_field else None
        analytical_run = str(grouping_raw).strip() if grouping_raw is not None else ""
        if grouping_field and not analytical_run:
            reasons.append("analytical_run_group_missing")
        if not grouping_field:
            analytical_run = f"stored-run:{run_id}"
        source = {"run_id": run_id, "revision_id": int(row.get("revision_id") or 0), "selection_id": row.get("selection_id"),
                  "selection_token": row.get("selection_token"), "validation": asdict(validation) if validation else None,
                  "validation_error": errors.get(run_id, ""), "raw_payload": payload, "source_hash": content_hash(row),
                  "pdf_sha256": row.get("pdf_sha256"), "assay_block_hash": row.get("assay_block_hash"),
                  "ruleset_file": row.get("ruleset_file"), "job_id": row.get("job_id"), "report_id": row.get("report_id"),
                  "measurement_date_raw": payload.get(configuration["measurement_date_field"]), "measured_at": measured_at,
                  "analytical_run_id": analytical_run, "run_group_raw": grouping_raw, "reasons": list(reasons)}
        if separate_time:
            source["measurement_time_raw"] = time_raw
        population.append(source)
        for control in configuration["controls"]:
            point = {"run_id": run_id, "revision_id": source["revision_id"], "selection_id": source["selection_id"],
                     "selection_token": source["selection_token"], "validation_id": validation.validation_id if validation else None,
                     "source_hash": source["source_hash"], "control_id": control["control_id"], "control_name": control["name"],
                     "raw": {key: payload.get(field) for key, field in control["fields"].items()},
                     "unit_raw": payload.get(control["unit_field"]) if control["unit_field"] else control["unit"],
                     "unit": control["unit"], "measured_at": measured_at, "analytical_run_id": analytical_run,
                     "parsed": {}, "reasons": list(reasons)}
            for key, raw in point["raw"].items():
                try:
                    point["parsed"][key] = str(parse_decimal(raw, configuration["numeric_grammar"]))
                except QCConfigurationError:
                    point["reasons"].append(f"{key.lower()}_invalid")
            if control["unit_field"] and (not isinstance(point["unit_raw"], str) or not point["unit_raw"].strip()):
                point["reasons"].append("unit_missing")
            if point["reasons"]:
                excluded.append(point)
            else:
                included.append(point)
    # A whole stable control series needs one target and unit. Never silently
    # select the first manufacturer's target or collapse incompatible units.
    for control in configuration["controls"]:
        points = [point for point in included if point["control_id"] == control["control_id"]]
        targets = {point["parsed"]["SOLL"] for point in points}
        units = {str(point["unit_raw"]).strip() for point in points}
        conflicts = []
        if len(targets) > 1:
            # Decimal textual scale is not a scientific target difference.
            if len({parse_decimal(target, "decimal_dot") for target in targets}) > 1:
                conflicts.append("target_conflict")
        if len(units) > 1 or (units and units != {control["unit"]}):
            conflicts.append("unit_conflict")
        if conflicts:
            for point in points:
                included.remove(point)
                point["reasons"].extend(conflicts)
                excluded.append(point)
    manifest = {"manifest_version": "qc-sources-v1", "store_path": str(resolve_store_path(store_spec)),
                "device_id": configuration["device_id"], "assay_key": configuration["assay_key"], "kit_lot": kit_lot,
                "inventory_version_id": inventory["version_id"], "inventory_hash": content_hash(inventory["snapshot"]),
                "profile_version_id": profile["version_id"], "profile_head_version_id": head,
                "profile_hash": content_hash(configuration), "profile_snapshot": configuration,
                "inventory_snapshot": inventory["snapshot"], "population": population,
                "included": sorted(included, key=lambda point: (point["measured_at"], point["run_id"], point["control_id"])),
                "excluded": sorted(excluded, key=lambda point: (point["run_id"], point["control_id"])),
                "included_count": len(included), "excluded_count": len(excluded), "population_count": len(population),
                "start_date": min((point["measured_at"] for point in included), default=None)}
    manifest["order_is_explicit"] = bool(any(part in configuration["measurement_date_format"] for part in ("%H", "%M", "%S")))
    if separate_time:
        manifest["order_is_explicit"] = True
    manifest["equal_time_order_unavailable"] = len({(point["control_id"], point["measured_at"]) for point in included}) < len(included)
    manifest["source_token"] = content_hash(manifest)
    return manifest
