"""Read-only validated population capture; its manifest defines the exact input.

Result and validation owners provide independent read transactions. This module
does not describe those reads as one atomic latest database snapshot. Publication
rechecks the complete manifest while the QC writer holds BEGIN IMMEDIATE.
"""
from __future__ import annotations

from dataclasses import asdict
from collections.abc import Mapping
from typing import Any

from src.resultstore.api import list_result_runs, list_pending_report_candidates, get_report_device_context
from src.resultvalidation.api import ResultValidationError, ValidationAmbiguousError, list_run_validations_readonly

from .model import QCConfigurationError, QCStoreError, QCUsageSnapshot, content_hash
from .profiles import get_profile, list_profiles, parse_decimal, interpret_measurement, interpret_numeric
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
    if getattr(record, "device_assignment_id", 0) != int(row.get("device_assignment_id") or 0):
        return False
    if record.revision_id != int(row.get("revision_id") or 0) or record.selection_id != row.get("selection_id"):
        return False
    if record.selection_token:
        return record.selection_token == row.get("selection_token")
    return (record.revision_id == 0 and row.get("selection_id") is None
            and not row.get("result_revisions") and not row.get("pending_revision"))


def get_lot_sources(store_spec: Mapping[str, Any], *, profile_version_id: int, kit_lot: str, device_id: str | None = None) -> dict[str, Any]:
    profile = get_profile(store_spec, profile_version_id)
    inventory = get_inventory(store_spec)
    configuration = profile["snapshot"]
    # Every fresh capture uses feature-specific eligibility. Profile versions
    # still govern their explicit parsing choices, never current eligibility.
    effective_device = device_id or configuration["device_id"]
    if not effective_device or (configuration["device_id"] and configuration["device_id"] != effective_device):
        raise QCConfigurationError("Für diese Auswertung bitte genau ein passendes Gerät wählen.")
    separate_time = bool(configuration.get("measurement_time_field"))
    # Do not normalize kit-lot text: its exact extracted identity is the key.
    if not isinstance(kit_lot, str) or not kit_lot.strip():
        raise QCConfigurationError("Eine genaue extrahierte Kit-Charge ist erforderlich.")
    all_rows = list_result_runs(dict(store_spec), limit=None)["runs"]
    rows = [row for row in all_rows if row.get("effective_device_id", row.get("device_id")) == effective_device
            and row.get("assay_key") == configuration["assay_key"] and row.get("lot_id") == kit_lot]
    records, errors = _validations(store_spec, [int(row["id"]) for row in rows if row.get("id") is not None])
    device = next((row for row in inventory["snapshot"]["devices"] if row["device_id"] == effective_device), None)
    inventory_usable = bool(inventory["version_id"] and device and device["active"] and device.get("display_name"))
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
        measurement = interpret_measurement(payload, configuration)
        time_raw = measurement["time_raw"]
        temporal_reasons = list(measurement["reasons"])
        measured_at = (measurement["date"] + ("T" + measurement["time"] if measurement["time"] else "")) if measurement["date"] else None
        grouping_field = configuration["run_grouping_field"]
        grouping_raw = payload.get(grouping_field) if grouping_field else None
        analytical_run = str(grouping_raw).strip() if grouping_raw is not None else ""
        if not grouping_field:
            analytical_run = f"stored-run:{run_id}"
        source = {"run_id": run_id, "revision_id": int(row.get("revision_id") or 0), "selection_id": row.get("selection_id"),
                  "selection_token": row.get("selection_token"), "validation": asdict(validation) if validation else None,
                  "validation_error": errors.get(run_id, ""), "raw_payload": payload, "source_hash": content_hash(row),
                  "pdf_sha256": row.get("pdf_sha256"), "assay_block_hash": row.get("assay_block_hash"),
                  "ruleset_file": row.get("ruleset_file"), "job_id": row.get("job_id"), "report_id": row.get("report_id"),
                  "measurement_date_raw": measurement["date_raw"], "measured_at": measured_at,
                  "analytical_run_id": analytical_run, "run_group_raw": grouping_raw, "reasons": list(reasons)}
        source["measurement"] = measurement
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
            point["numeric_interpretations"] = {}
            point["measurement"] = measurement
            point["feature_reasons"] = {"time": temporal_reasons, "grouping": ["analytical_run_group_missing"] if grouping_field and not analytical_run else []}
            if configuration.get("dimensionless"):
                point["unit"] = point["unit_raw"] = "1"
            elif not str(point["unit_raw"] or "").strip():
                point["reasons"].append("unit_unconfirmed")
            elif not point["unit"]:
                point["unit"] = str(point["unit_raw"]).strip()
            for key, raw in point["raw"].items():
                try:
                    numeric_source = row.get("source_provenance", {})
                    if row.get("revision_id"):
                        revision = next((item["result"] for item in row.get("result_revisions", []) if item["revision_id"] == row["revision_id"]), {})
                        numeric_source = {**numeric_source, **{name: revision.get(name) for name in ("ruleset", "rule_source_text", "rule_sha256")}}
                    interpreted = interpret_numeric(raw, configuration["numeric_grammar"], field_key=control["fields"][key], source=numeric_source)
                    point["numeric_interpretations"][key] = interpreted
                    point["parsed"][key] = interpreted["value"]
                except QCConfigurationError:
                    if key != "IST":
                        point["feature_reasons"].setdefault("target" if key == "SOLL" else "manufacturer", []).append(f"{key.lower()}_invalid")
                    else:
                        point["reasons"].append(f"{key.lower()}_invalid")
            if "MIN" in point["parsed"] and "MAX" in point["parsed"]:
                if parse_decimal(point["parsed"]["MIN"], "decimal_dot") > parse_decimal(point["parsed"]["MAX"], "decimal_dot"):
                    point["feature_reasons"].setdefault("manufacturer", []).append("manufacturer_limits_reversed")
            if control["unit_field"] and (not isinstance(point["unit_raw"], str) or not point["unit_raw"].strip()):
                point["reasons"].append("unit_missing")
            if point["reasons"]:
                excluded.append(point)
            else:
                included.append(point)
    # One stable control series needs constant target, manufacturer limits and
    # unit. Decimal textual scale is not a scientific difference.
    for control in configuration["controls"]:
        points = [point for point in included if point["control_id"] == control["control_id"]]
        units = {str(point["unit_raw"]).strip() for point in points}
        conflicts = []
        for key, reason in (("SOLL", "target_conflict"), ("MIN", "manufacturer_min_conflict"), ("MAX", "manufacturer_max_conflict")):
            if len({parse_decimal(point["parsed"][key], "decimal_dot") for point in points if key in point["parsed"]
                    and (key == "SOLL" or not point["feature_reasons"].get("manufacturer"))}) > 1:
                conflicts.append(reason)
        expected_unit = "1" if configuration.get("dimensionless") else control["unit"]
        if len(units) > 1 or (units and expected_unit and units != {expected_unit}):
            conflicts.append("unit_conflict")
        if conflicts:
            for point in points:
                blocking = [reason for reason in conflicts if reason == "unit_conflict"]
                if blocking:
                    included.remove(point)
                    point["reasons"].extend(blocking)
                    excluded.append(point)
                for reason in conflicts:
                    if reason != "unit_conflict":
                        point["feature_reasons"].setdefault("target" if reason == "target_conflict" else "manufacturer", []).append(reason)
    manifest = {"manifest_version": "qc-sources-v3", "store_path": str(resolve_store_path(store_spec)),
                "device_id": effective_device, "assay_key": configuration["assay_key"], "kit_lot": kit_lot,
                "inventory_version_id": inventory["version_id"], "inventory_hash": content_hash(inventory["snapshot"]),
                "profile_version_id": profile["version_id"], "profile_head_version_id": head,
                "profile_hash": content_hash(configuration), "profile_snapshot": configuration,
                "inventory_snapshot": inventory["snapshot"], "population": population,
                "included": sorted(included, key=lambda point: (point["measured_at"] or "~", point["run_id"], point["control_id"])),
                "excluded": sorted(excluded, key=lambda point: (point["run_id"], point["control_id"])),
                "included_count": len(included), "excluded_count": len(excluded), "population_count": len(population),
                "start_date": min((point["measured_at"] for point in included if point["measured_at"]), default=None)}
    manifest["order_is_explicit"] = any(point["measurement"]["time"] is not None for point in included)
    manifest["equal_time_order_unavailable"] = len({(point["control_id"], point["measured_at"]) for point in included}) < len(included)
    manifest["source_token"] = content_hash(manifest)
    return manifest


def _usage_interval(payload, configuration):
    """Usage shares source parsing, precision and explicit legacy overrides."""
    return interpret_measurement(payload, configuration)


def get_lot_chronology(store_spec: Mapping[str, Any], *, profile_version_id: int, device_id: str | None = None) -> QCUsageSnapshot:
    """Capture all usage, including excluded/QC-pending observations, read-only.

    Pairwise witnesses prove later usage, not a globally newest charge. Unknown
    or conflicting target usage cannot silently become the oldest observation.
    """
    from .store import list_lots

    profile = get_profile(store_spec, profile_version_id)
    configuration = profile["snapshot"]
    effective_device = device_id or configuration["device_id"]
    if not effective_device or (configuration["device_id"] and configuration["device_id"] != effective_device):
        raise QCConfigurationError("Für diesen Nutzungsnachweis bitte genau ein passendes Gerät wählen.")
    inventory = get_inventory(store_spec)
    profiles = [row for row in list_profiles(store_spec) if
        row["snapshot"]["device_id"] in ("", effective_device) and row["snapshot"]["assay_key"] == configuration["assay_key"]]
    bindings = [row for row in list_lots(store_spec) if
        (row["device_id"], row["assay_key"]) == (effective_device, configuration["assay_key"])]
    temporal_profiles = {row["version_id"]: row["snapshot"] for row in profiles}
    temporal_profiles[profile_version_id] = configuration
    for binding in bindings:
        identifier = binding["snapshot"]["profile_version_id"]
        if identifier not in temporal_profiles:
            temporal_profiles[identifier] = get_profile(store_spec, identifier)["snapshot"]
    all_rows = list_result_runs(dict(store_spec), limit=None)["runs"]
    rows = [row for row in all_rows if
        (row.get("effective_device_id", row.get("device_id")), row.get("assay_key")) == (effective_device, configuration["assay_key"])]
    records, validation_errors = _validations(store_spec, [int(row["id"]) for row in rows if row.get("id") is not None])
    runs, observations, unassigned = [], [], []
    temporal_keys = ("measurement_date_field", "measurement_date_format", "measurement_time_field", "measurement_time_format")
    for row in sorted(rows, key=lambda item: int(item.get("id") or 0)):
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        selected = {"kit_lot": row.get("lot_id"), **_usage_interval(payload, configuration)}
        source = {"run_id": row.get("id"), "revision_id": int(row.get("revision_id") or 0),
            "selection_id": row.get("selection_id"), "selection_token": row.get("selection_token"), "source_hash": content_hash(row),
            "validation": asdict(records[row["id"]]) if row.get("id") in records else None,
            "validation_error": validation_errors.get(row.get("id"), ""), "variants": [selected], "determinate": True, "reasons": []}
        if row.get("revision_error") or row.get("payload_parse_error") or row.get("id") is None:
            source["determinate"] = False
            source["reasons"].append("usage_source_unreadable")
        if row.get("revision_error"):
            # An unreadable history may conceal another candidate lot identity.
            # The selected projection alone cannot bound that uncertainty.
            unassigned.append(source["run_id"])
        for alternate in temporal_profiles.values():
            if any(alternate.get(key) != configuration.get(key) for key in temporal_keys):
                interval = _usage_interval(payload, alternate)["interval"]
                if interval is not None and selected["interval"] is not None and interval != selected["interval"]:
                    source["determinate"] = False
                    source["reasons"].append("profile_time_conflict")
                    break
        pending = row.get("pending_revision")
        if pending:
            candidate = pending.get("result") if isinstance(pending, Mapping) else None
            candidate = candidate if isinstance(candidate, Mapping) else {}
            candidate_payload = candidate.get("payload") if isinstance(candidate.get("payload"), Mapping) else {}
            variant = {"kit_lot": candidate.get("lot_id"), **_usage_interval(candidate_payload, configuration)}
            same = (variant["kit_lot"] == selected["kit_lot"] and variant["interval"] is not None and variant["interval"] == selected["interval"])
            if not same:
                source["variants"].append(variant)
                source["determinate"] = False
                source["reasons"].append("pending_usage_conflict")
            else:
                source["reasons"].append("result_choice_pending_qc_only")
        runs.append(source)
        for variant in source["variants"]:
            lot = variant["kit_lot"]
            if not isinstance(lot, str) or not lot.strip():
                unassigned.append(source["run_id"])
                continue
            observations.append({"kit_lot": lot, "run_id": source["run_id"], "source_hash": source["source_hash"],
                "determinate": source["determinate"], "interval": variant["interval"], "date_raw": variant["date_raw"], "time_raw": variant["time_raw"],
                "reasons": list(dict.fromkeys(source["reasons"] + variant["reasons"]))})
    identities = {row["kit_lot"] for row in observations} | {row["kit_lot"] for row in bindings}
    lots = []
    for lot in sorted(identities):
        own = [row for row in observations if row["kit_lot"] == lot]
        reliable = bool(own) and not unassigned and all(row["determinate"] and row["interval"] is not None for row in own)
        last = max((row["interval"] for row in own if row["interval"] is not None), key=lambda value: value["upper_exclusive"], default=None)
        witnesses = [row for row in observations if reliable and row["kit_lot"] != lot and row["determinate"]
            and row["interval"] is not None and row["interval"]["lower"] >= last["upper_exclusive"]]
        reasons = list(dict.fromkeys(reason for row in own for reason in row["reasons"]))
        if unassigned:
            reasons.append("usage_identity_unassigned")
        if not own:
            reasons.append("usage_missing")
        if reliable and not witnesses:
            reasons.append("no_proven_later_usage")
        lots.append({"kit_lot": lot, "run_ids": list(dict.fromkeys(row["run_id"] for row in own)), "last_usage": last,
            "last_usage_reliable": reliable, "close_available": bool(witnesses), "reasons": reasons, "witnesses": witnesses})
    uncertainty = []
    for row in all_rows:
        if row.get("assay_key") != configuration["assay_key"] or row.get("effective_device_id", row.get("device_id")):
            continue
        possible_lots = [row.get("lot_id")]
        pending = row.get("pending_revision")
        if pending:
            possible_lots.append((pending.get("result") or {}).get("lot_id"))
        if row.get("revision_error"):
            possible_lots.append(None)
        for possible in dict.fromkeys(possible_lots):
            known = isinstance(possible, str) and bool(possible.strip())
            uncertainty.append({"kind": "run", "id": row["id"], "kit_lot": possible if known else None,
                "reason": "report_device_unconfirmed", "source_hash": content_hash(row)})
    candidate_devices = {}
    for candidate in list_pending_report_candidates(dict(store_spec)):
        if candidate["assay_key"] == configuration["assay_key"]:
            report = candidate["report_id"]
            if report not in candidate_devices:
                context = get_report_device_context(dict(store_spec), report)
                candidate_devices[report] = context.get("device_id", "") if context else ""
            confirmed = candidate_devices[report]
            if not confirmed or confirmed == effective_device:
                uncertainty.append({"kind": "candidate", "id": candidate["candidate_id"], "kit_lot": candidate["meta"].get("lot_id"),
                    "reason": "duplicate_source_unresolved", "source_hash": content_hash(candidate), "confirmed_device_id": confirmed})
    for lot in lots:
        relevant = [item for item in uncertainty if not item["kit_lot"] or item["kit_lot"] == lot["kit_lot"]]
        if relevant:
            lot["close_available"] = False
            lot["last_usage_reliable"] = False
            lot["witnesses"] = []
            lot["reasons"].extend(sorted({item["reason"] for item in relevant}))
    snapshot = {"chronology_version": "qc-usage-v1", "store_path": str(resolve_store_path(store_spec)),
        "device_id": effective_device, "assay_key": configuration["assay_key"], "profile_version_id": profile_version_id,
        "profile_hash": content_hash(configuration), "profile_snapshot": configuration,
        "profile_heads": [{"version_id": row["version_id"], "profile_hash": content_hash(row["snapshot"])} for row in profiles],
        "temporal_profiles": {str(key): value for key, value in temporal_profiles.items()},
        "inventory_version_id": inventory["version_id"], "inventory_hash": content_hash(inventory["snapshot"]),
        "lot_bindings": [{"lot_key": row["lot_key"], "version_id": row["version_id"], "snapshot_hash": content_hash(row["snapshot"])} for row in bindings],
        "runs": runs, "unassigned_run_ids": sorted(set(unassigned), key=str), "lots": lots,
        **({"unresolved_device_sources": uncertainty} if uncertainty else {})}
    return QCUsageSnapshot.freeze(snapshot)
