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

from .model import QCConfigurationError, QCStoreError, QCUsageSnapshot, content_hash
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
            if "MIN" in point["parsed"] and "MAX" in point["parsed"]:
                if parse_decimal(point["parsed"]["MIN"], "decimal_dot") > parse_decimal(point["parsed"]["MAX"], "decimal_dot"):
                    point["reasons"].append("manufacturer_limits_reversed")
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
            if len({parse_decimal(point["parsed"][key], "decimal_dot") for point in points}) > 1:
                conflicts.append(reason)
        if len(units) > 1 or (units and units != {control["unit"]}):
            conflicts.append("unit_conflict")
        if conflicts:
            for point in points:
                included.remove(point)
                point["reasons"].extend(conflicts)
                excluded.append(point)
    manifest = {"manifest_version": "qc-sources-v2", "store_path": str(resolve_store_path(store_spec)),
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


def _usage_interval(payload, configuration):
    """A stated date/time denotes its whole precision interval, never an import order."""
    date_raw = payload.get(configuration["measurement_date_field"])
    clock_field = configuration.get("measurement_time_field")
    clock_raw = payload.get(clock_field) if clock_field else None
    result = {"date_raw": date_raw, "time_raw": clock_raw, "interval": None, "reasons": []}
    try:
        measured = datetime.fromisoformat(parse_measurement_date(date_raw, configuration["measurement_date_format"]))
    except QCConfigurationError:
        result["reasons"].append("measurement_date_invalid")
        return result
    date_format = configuration["measurement_date_format"]
    def explicit_precision(format_string):
        precision = "day"
        for token, name in (("%H", "hours"), ("%M", "minutes"), ("%S", "seconds")):
            if token not in format_string:
                break
            precision = name
        return precision
    precision = explicit_precision(date_format)
    if clock_field:
        try:
            clock = datetime.fromisoformat(parse_measurement_date(clock_raw, configuration["measurement_time_format"])).time()
            measured = datetime.combine(measured.date(), clock)
            precision = explicit_precision(configuration["measurement_time_format"])
        except QCConfigurationError:
            measured = datetime.combine(measured.date(), datetime.min.time())
            precision = "day"
            result["reasons"].append("measurement_time_missing" if clock_raw is None or not str(clock_raw).strip() else "measurement_time_invalid")
    # Missing higher clock components are unknown, even if strptime defaulted
    # them or a lower component was explicitly present in an unusual format.
    if precision == "day":
        measured = measured.replace(hour=0, minute=0, second=0, microsecond=0)
    elif precision == "hours":
        measured = measured.replace(minute=0, second=0, microsecond=0)
    elif precision == "minutes":
        measured = measured.replace(second=0, microsecond=0)
    widths = {"day": 86_400_000_000, "hours": 3_600_000_000, "minutes": 60_000_000, "seconds": 1_000_000, "microseconds": 1}
    lower = ((measured.toordinal() * 86400 + measured.hour * 3600 + measured.minute * 60 + measured.second) * 1_000_000 + measured.microsecond)
    result["interval"] = {"lower": lower, "upper_exclusive": lower + widths[precision], "precision": precision,
        "display": measured.date().isoformat() if precision == "day" else measured.isoformat(sep=" ", timespec=precision)}
    return result


def get_lot_chronology(store_spec: Mapping[str, Any], *, profile_version_id: int) -> QCUsageSnapshot:
    """Capture all usage, including excluded/QC-pending observations, read-only.

    Pairwise witnesses prove later usage, not a globally newest charge. Unknown
    or conflicting target usage cannot silently become the oldest observation.
    """
    from .store import list_lots

    profile = get_profile(store_spec, profile_version_id)
    configuration = profile["snapshot"]
    inventory = get_inventory(store_spec)
    profiles = [row for row in list_profiles(store_spec) if
        (row["snapshot"]["device_id"], row["snapshot"]["assay_key"]) == (configuration["device_id"], configuration["assay_key"])]
    bindings = [row for row in list_lots(store_spec) if
        (row["device_id"], row["assay_key"]) == (configuration["device_id"], configuration["assay_key"])]
    temporal_profiles = {row["version_id"]: row["snapshot"] for row in profiles}
    temporal_profiles[profile_version_id] = configuration
    for binding in bindings:
        identifier = binding["snapshot"]["profile_version_id"]
        if identifier not in temporal_profiles:
            temporal_profiles[identifier] = get_profile(store_spec, identifier)["snapshot"]
    rows = [row for row in list_result_runs(dict(store_spec), limit=None)["runs"] if
        (row.get("device_id"), row.get("assay_key")) == (configuration["device_id"], configuration["assay_key"])]
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
    snapshot = {"chronology_version": "qc-usage-v1", "store_path": str(resolve_store_path(store_spec)),
        "device_id": configuration["device_id"], "assay_key": configuration["assay_key"], "profile_version_id": profile_version_id,
        "profile_hash": content_hash(configuration), "profile_snapshot": configuration,
        "profile_heads": [{"version_id": row["version_id"], "profile_hash": content_hash(row["snapshot"])} for row in profiles],
        "temporal_profiles": {str(key): value for key, value in temporal_profiles.items()},
        "inventory_version_id": inventory["version_id"], "inventory_hash": content_hash(inventory["snapshot"]),
        "lot_bindings": [{"lot_key": row["lot_key"], "version_id": row["version_id"], "snapshot_hash": content_hash(row["snapshot"])} for row in bindings],
        "runs": runs, "unassigned_run_ids": sorted(set(unassigned), key=str), "lots": lots}
    return QCUsageSnapshot.freeze(snapshot)
