"""Pure, versioned Decimal QC analysis; no database, UI, runtime or PDF I/O.

Classic-six-v1 keeps the current-run 2-SD trigger independent of the 1_2s
warning display. A deterministic row order is never a measurement-order proof.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from .model import CURRENT_ANALYSIS_ID, QCAnalysis, QCConfigurationError, canonical_json, content_hash, sd_parameter_definition

ALGORITHM_ID = CURRENT_ANALYSIS_ID
RENDERER_ID = "arev2-qc-pdf-v5"
RULES = ("1_2s", "1_3s", "2_2s", "R_4s", "4_1s", "10x")
MAX_MODEL_BYTES = 16 * 1024 * 1024
MAX_POINTS = 50_000
MAX_DECIMAL_DIGITS = 4096
REFERENCES = {
    "qmma": {"version": "Rili-BAEK-2023-definition-p2", "url": "https://www.bundesaerztekammer.de/fileadmin/user_upload/BAEK/Themen/Qualitaetssicherung/_Bek_BAEK_RiLi_BAEK_ONLINE_FINAL_VERS_26_05_2023.pdf"},
    "westgard": {"version": "classic-six-v1", "url": "https://www.westgard.com/westgard-rules.html",
                 "r4s_reference": "https://www.westgard.com/lessons/westgard-rules/westgard-rules/quest7.html"},
    "report_scope": "Validierte Kit-Chargen-Auswertung; kein Nachweis vollständiger Richtlinienkonformität.",
}


def _decimal(raw: object) -> Decimal:
    if not isinstance(raw, str) or len(raw) > MAX_DECIMAL_DIGITS:
        raise QCConfigurationError("Ein endlicher Dezimalwert als Text ist erforderlich.")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise QCConfigurationError("Ein Dezimalwert ist ungültig.") from exc
    if not value.is_finite() or len(value.as_tuple().digits) + abs(value.as_tuple().exponent) > MAX_DECIMAL_DIGITS:
        raise QCConfigurationError("Ein Dezimalwert ist nicht endlich oder überschreitet die Rechengrenze.")
    return value


def _text(value: Decimal) -> str:
    if not value:
        return "0"
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def _point_key(point: dict[str, Any]) -> str:
    return f"{point.get('run_id')}:{point.get('revision_id')}:{point.get('control_id')}:{point.get('selection_token')}"


def _date(raw: object) -> datetime | None:
    try:
        return datetime.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        return None


def _precision(model: dict[str, Any], references: dict[str, Any]) -> int:
    # Finite source decimals have a bounded lexical size. This budget keeps
    # sums/products exact; only displayed division/square roots are rounded.
    longest = 1
    points = model["included"] + model["excluded"]
    values = [raw for point in points for raw in point.get("parsed", {}).values()]
    values.extend(model["profile_snapshot"].get(key) for key in ("single_value_limit_percent", "relative_limit_percent"))
    for reference in references.values():
        if isinstance(reference, Mapping):
            values.append(reference.get("value"))
            values.extend(point.get("parsed", {}).get("IST") for point in reference.get("measurements", []) if isinstance(point, Mapping))
    for raw in values:
        try:
            value = _decimal(raw)
            longest = max(longest, len(value.as_tuple().digits) + abs(value.as_tuple().exponent))
        except QCConfigurationError:
            pass
    return max(80, 8 * longest + 40)


def _sd_origin_reason(reference: Mapping[str, Any], control_id: str, source: dict[str, Any], context: object) -> str:
    if not isinstance(context, Mapping) or context.get("context_version") != "qc-sd-origin-v1":
        return "sd_origin_unavailable"
    if any(context.get(key) != source.get(key) for key in ("store_path", "device_id", "assay_key", "kit_lot")):
        return "sd_origin_unavailable"
    entries = context.get("references")
    origin = entries.get(control_id) if isinstance(entries, Mapping) else None
    if not isinstance(origin, Mapping) or origin.get("reason"):
        return "sd_origin_unavailable"
    profile = origin.get("origin_profile_snapshot")
    version_id = origin.get("origin_profile_version_id")
    if (not isinstance(version_id, int) or isinstance(version_id, bool) or version_id <= 0
            or origin.get("reference_hash") != content_hash(reference)
            or not isinstance(profile, Mapping) or origin.get("origin_profile_hash") != content_hash(profile)
            or (reference.get("profile_version_id") is not None and reference["profile_version_id"] != version_id)):
        return "sd_origin_unavailable"
    old = sd_parameter_definition(profile, control_id, device_id=context.get("device_id"))
    current = sd_parameter_definition(source["profile_snapshot"], control_id, device_id=source.get("device_id"))
    if old is None or current is None:
        return "sd_origin_unavailable"
    if old["unit"] != current["unit"] or old["unit_field"] != current["unit_field"]:
        return "sd_unit_incompatible"
    if old != current:
        return "sd_parameter_incompatible"
    if reference.get("kind") == "confirmed_baseline":
        # Units belong to the frozen observations, not today's interpretation.
        measurements = reference.get("measurements")
        if not isinstance(measurements, list):
            return "sd_origin_unavailable"
        for point in measurements:
            if (not isinstance(point, Mapping) or point.get("unit") != old["unit"]
                    or str(point.get("unit_raw") or "").strip() != old["unit"]):
                return "sd_origin_unavailable"
    return ""


def _sd_reference(reference: object, control_id: str, target: Decimal | None, source: dict[str, Any], context: object) -> dict[str, Any]:
    unavailable = {"available": False, "reason": "sd_reference_missing"}
    if not isinstance(reference, Mapping):
        return unavailable
    origin_reason = _sd_origin_reason(reference, control_id, source, context)
    if origin_reason:
        return {"available": False, "reason": origin_reason}
    try:
        if reference.get("kind") == "manual":
            sd = _decimal(reference.get("value"))
            if sd <= 0 or target is None:
                return {"available": False, "reason": "sd_nonpositive_or_target_unavailable"}
            return {"available": True, "kind": "manual", "center": _text(target), "sd": _text(sd),
                    "reference_id": reference.get("reference_id", ""), "n": None,
                    "center_sum": target, "center_n": Decimal(1),
                    "variance_numerator": sd * sd, "variance_denominator": Decimal(1)}
        if reference.get("kind") != "confirmed_baseline" or reference.get("confirmed") is not True:
            return {"available": False, "reason": "sd_reference_unconfirmed"}
        baseline = reference.get("measurements")
        if not isinstance(baseline, list) or len(baseline) < 2:
            return {"available": False, "reason": "baseline_insufficient"}
        values = []
        for point in baseline:
            if point.get("control_id") != control_id or point.get("validation_id") is None or point.get("reasons"):
                return {"available": False, "reason": "baseline_not_validated_or_control_mismatch"}
            values.append(_decimal(point.get("parsed", {}).get("IST")))
        n = Decimal(len(values))
        total = sum(values, Decimal(0))
        numerator = n * sum((value * value for value in values), Decimal(0)) - total * total
        denominator = n * (n - 1)
        if numerator <= 0:
            return {"available": False, "reason": "baseline_sd_zero"}
        return {"available": True, "kind": "confirmed_baseline", "center": _text(total / n),
                "sd": _text((numerator / denominator).sqrt()), "n": int(n),
                "reference_id": reference.get("reference_id", ""), "center_sum": total, "center_n": n,
                "variance_numerator": numerator, "variance_denominator": denominator,
                "baseline_source_token": reference.get("source_token", ""),
                "baseline_profile_version_id": reference.get("profile_version_id")}
    except QCConfigurationError:
        return {"available": False, "reason": "sd_reference_invalid"}


def _normalization(value: Decimal, reference: dict[str, Any]) -> dict[str, Any]:
    # Compare squared rational quantities before any square-root/division
    # rounding. This also preserves exact equality to baseline SD thresholds.
    n = reference["center_n"]
    difference = value * n - reference["center_sum"]
    left = difference * difference * reference["variance_denominator"]
    unit = reference["variance_numerator"] * n * n
    direction = 1 if difference > 0 else (-1 if difference < 0 else 0)
    z = (left / unit).sqrt() * direction
    return {"z": _text(z), "side": direction,
            "above_1s": left > unit, "above_2s": left > 4 * unit, "above_3s": left > 9 * unit}


def _window(point: dict[str, Any], buckets: dict[datetime, list[dict[str, Any]]], count: int,
            unknown_dates: bool) -> tuple[list[dict[str, Any]], str]:
    if unknown_dates:
        return [], "measurement_order_unavailable"
    date = point["_date"]
    if date is None or len(buckets[date]) != 1 or point.get("order_ambiguous"):
        return [], "measurement_order_ambiguous"
    dates = [value for value in sorted(buckets) if value <= date]
    if len(dates) < count:
        return [], "history_insufficient"
    result = []
    for key in dates[-count:]:
        if len(buckets[key]) != 1 or buckets[key][0].get("order_ambiguous"):
            return [], "measurement_order_ambiguous"
        candidate = buckets[key][0]
        if not candidate["eligible"] or candidate.get("z") is None:
            return [], "history_value_unavailable"
        result.append(candidate)
    return result, ""


def _same_side(points: list[dict[str, Any]], threshold: int) -> bool:
    if not points or points[0].get("side") not in {-1, 1}:
        return False
    side = points[0]["side"]
    return all(point.get("side") == side and (point.get(f"above_{threshold}s") if threshold else True) for point in points)


def _finding(rule: str, enabled: bool, gate: bool, witnesses: list[dict[str, Any]], available: bool,
             reason: str = "", *, warning=False) -> dict[str, Any]:
    if not enabled:
        status = "disabled"
    elif witnesses and gate:
        status = "warning" if warning else "reject"
    elif not available:
        status = "unavailable"
    elif not gate:
        status = "not_triggered"
    else:
        status = "pass"
    return {"rule": rule, "status": status, "classic_trigger": gate, "point_keys": [point["point_key"] for point in witnesses],
            "reason": reason if not available else ("classic_2sd_trigger_absent" if not gate else "")}


def _evaluate_runs(points: list[dict[str, Any]], controls: list[dict[str, Any]], enabled: list[str]) -> list[dict[str, Any]]:
    groups, timelines, unknown_dates = defaultdict(list), defaultdict(lambda: defaultdict(list)), defaultdict(bool)
    for point in points:
        groups[point["analytical_run_id"] or f"missing-group:{point['point_key']}"] .append(point)
        if point["_date"] is None:
            unknown_dates[point["control_id"]] = True
        else:
            timelines[point["control_id"]][point["_date"]].append(point)
    configured_ids = {control["control_id"] for control in controls}
    result = []
    for group, current in groups.items():
        valid = [point for point in current if point["eligible"] and point.get("z") is not None]
        complete = len(valid) == len(current) and {point["control_id"] for point in current} == configured_ids
        grouped = all(point["analytical_run_id"] for point in current)
        gate = any(point["above_2s"] for point in valid)
        findings = [
            _finding("1_2s", "1_2s" in enabled, gate, [point for point in valid if point["above_2s"]], complete, "sd_or_group_incomplete", warning=True),
            _finding("1_3s", "1_3s" in enabled, gate, [point for point in valid if point["above_3s"]], complete, "sd_or_group_incomplete"),
        ]
        positive = [point for point in valid if point["side"] > 0 and point["above_2s"]]
        negative = [point for point in valid if point["side"] < 0 and point["above_2s"]]
        r4 = positive[:1] + negative[:1] if grouped and positive and negative else []
        findings.append(_finding("R_4s", "R_4s" in enabled, gate, r4, complete and grouped and len(current) >= 2,
                                 "within_run_controls_or_sd_unavailable"))
        for rule, length, threshold in (("2_2s", 2, 2), ("4_1s", 4, 1), ("10x", 10, 0)):
            witnesses, available, reasons = [], False, []
            # Within an analytical run, 2_2s compares control materials by their
            # own centers/SD. R_4s above is likewise a qualitative within-run rule.
            if rule == "2_2s" and grouped and (len(positive) >= 2 or len(negative) >= 2):
                witnesses = (positive if len(positive) >= 2 else negative)[:2]
                available = True
            elif rule == "2_2s" and complete and grouped and len(current) >= 2:
                available = True
            # Do not construct a favorable cross-control order/subset for 4/10.
            # A whole complete group on one qualifying side is order-invariant.
            if length >= 4 and complete and grouped and len(current) >= length:
                available = True
                if _same_side(current, threshold):
                    witnesses = current
            for point in current:
                window, reason = _window(point, timelines[point["control_id"]], length, unknown_dates[point["control_id"]])
                if window:
                    available = True
                    if _same_side(window, threshold) and not witnesses:
                        witnesses = window
                else:
                    reasons.append(reason)
            findings.append(_finding(rule, rule in enabled, gate, witnesses, available,
                                     sorted(set(reasons))[0] if reasons else "history_insufficient"))
        statuses = {finding["status"] for finding in findings}
        state = "reject" if "reject" in statuses else ("warning" if "warning" in statuses else ("unavailable" if "unavailable" in statuses else "no_rejection"))
        result.append({"analytical_run_id": group, "classic_trigger": gate, "findings": findings, "status": state,
                       "point_keys": [point["point_key"] for point in current], "measurement_dates": sorted({point["measured_at"] for point in current if point["measured_at"]})})
    return result


def _series_limits(configuration, prepared, target, minima, maxima, *, modern=False):
    reasons = {reason for point in prepared for reason in point.get("reasons", [])}
    manufacturer_reason = next((reason for reason in ("manufacturer_min_conflict", "manufacturer_max_conflict",
        "manufacturer_limits_reversed", "min_invalid", "max_invalid") if reason in reasons), "eligible_values_missing")
    manufacturer = {"available": len(minima) == len(maxima) == 1 and (target is not None or modern),
                    "reason": manufacturer_reason, "lower": None, "upper": None}
    if manufacturer["available"]:
        manufacturer.update(reason="", lower=_text(next(iter(minima))), upper=_text(next(iter(maxima))))
    enabled = configuration.get("single_value_limits_enabled", False)
    single = {"enabled": enabled, "available": False, "reason": "not_configured", "percent": None, "lower": None, "upper": None}
    if enabled:
        percent = _decimal(configuration.get("single_value_limit_percent"))
        if percent < 0:
            raise QCConfigurationError("Die Einzelwert-Prozentgrenze darf nicht negativ sein.")
        single.update(percent=_text(percent), reason="eligible_values_missing")
        if target is not None:
            lower, upper = target * (1 - percent / 100), target * (1 + percent / 100)
            if lower > upper:
                single["reason"] = "percentage_limits_reversed"
            else:
                single.update(available=True, reason="", lower=_text(lower), upper=_text(upper))
    return {"manufacturer": manufacturer, "single_value": single}


def _limit_finding(point, limit):
    if not point["eligible"]:
        return {"status": "unavailable", "reason": "point_ineligible", "direction": ""}
    if not limit["available"]:
        return {"status": "unavailable", "reason": limit["reason"], "direction": ""}
    actual = point["_actual"]
    direction = "below" if actual < _decimal(limit["lower"]) else ("above" if actual > _decimal(limit["upper"]) else "")
    return {"status": "exceeded" if direction else "within_limit", "reason": "", "direction": direction}


def _reference_lines(item):
    # Frozen drawing order keeps the SOLL visible above the reference SD grid.
    lines = [{"kind": "sd", "boundary": str(band["sd_multiple"]), "value": band["value"],
              "label": f"{band['sd_multiple']:+d} SD"} for band in item["bands"]]
    if item["qmma"].get("target") is not None:
        lines.append({"kind": "target", "boundary": "target", "value": item["qmma"]["target"], "label": "SOLL"})
    if item["descriptive"]["mean"]["available"]:
        lines.append({"kind": "mean", "boundary": "mean", "value": item["descriptive"]["mean"]["value"], "label": "Mittelwert"})
    for kind, label in (("manufacturer", "Hersteller"), ("single_value", "Einzelwert")):
        limit = item["limits"][kind]
        if limit["available"]:
            for boundary, caption in (("lower", "MIN"), ("upper", "MAX")):
                suffix = f" ({limit['percent']} %)" if kind == "single_value" else ""
                lines.append({"kind": kind, "boundary": boundary, "value": limit[boundary], "label": f"{label} {caption}{suffix}"})
    return lines


def _metric(value=None, reason=""):
    return {"available": value is not None, "value": _text(value) if value is not None else None, "reason": reason}


def _descriptive(eligible):
    n = len(eligible)
    result = {"version": "qc-descriptive-v1", "n": n, "mean": _metric(reason="eligible_values_missing"),
        "sample_sd": _metric(reason="sample_sd_requires_two_values"), "cv_percent": _metric(reason="sample_sd_requires_two_values")}
    if not n:
        return result
    count = Decimal(n)
    total = sum((point["_actual"] for point in eligible), Decimal(0))
    mean = total / count
    result["mean"] = _metric(mean)
    if n >= 2:
        squares = sum((point["_actual"] * point["_actual"] for point in eligible), Decimal(0))
        sd = ((count * squares - total * total) / (count * (count - 1))).sqrt()
        result["sample_sd"] = _metric(sd)
        result["cv_percent"] = _metric(100 * sd / mean) if mean > 0 else _metric(reason="positive_mean_required")
    return result


def _observation_identity(point):
    return tuple(point.get(key) for key in ("run_id", "revision_id", "selection_id", "selection_token", "source_hash"))


def _measurement(point, configuration, original):
    if isinstance(point.get("measurement"), dict):
        return dict(point["measurement"])
    date_raw = original.get("measurement_date_raw", (original.get("raw_payload") or {}).get(configuration["measurement_date_field"]))
    time_raw = original.get("measurement_time_raw")
    measured = _date(point.get("measured_at"))
    precision, date, time = "unknown", None, None
    if measured is not None:
        format_string = configuration.get("measurement_time_format") if configuration.get("measurement_time_field") else configuration["measurement_date_format"]
        precision = "day"
        for token, name in (("%H", "hours"), ("%M", "minutes"), ("%S", "seconds")):
            if token not in format_string:
                break
            precision = name
        date = measured.date().isoformat()
        if precision != "day":
            time = measured.time().isoformat(timespec=precision)
    elif isinstance(date_raw, str):
        try:
            parsed = datetime.strptime(date_raw.strip(), configuration["measurement_date_format"])
            if parsed.strftime(configuration["measurement_date_format"]) == date_raw.strip():
                date, precision = parsed.date().isoformat(), "day"
        except ValueError:
            pass
    return {"date": date, "time": time, "precision": precision, "date_raw": date_raw, "time_raw": time_raw}


def _analyze(manifest: dict[str, Any], references: dict[str, Any], sd_context: dict[str, Any]) -> dict[str, Any]:
    configuration = manifest["profile_snapshot"]
    modern = manifest.get("manifest_version") == "qc-sources-v3"
    controls = configuration["controls"]
    originals = defaultdict(list)
    for source in manifest["population"]:
        originals[_observation_identity(source)].append(source)
    all_points, series = [], []
    for control in controls:
        identifier = control["control_id"]
        source_points = [point for point in manifest["included"] + manifest["excluded"] if point["control_id"] == identifier]
        prepared, targets, units, minima, maxima = [], set(), set(), set(), set()
        for source in source_points:
            point = json.loads(canonical_json(source))
            point.update(point_key=_point_key(point), eligible=not bool(point.get("reasons")), z=None,
                         _date=_date(point.get("measured_at")), order_ambiguous=False)
            if modern:
                parsed = point.get("parsed", {})
                numbers = {}
                for role in ("IST", "SOLL", "MIN", "MAX"):
                    try:
                        numbers[role] = _decimal(parsed.get(role))
                    except QCConfigurationError:
                        numbers[role] = None
                if numbers["IST"] is None:
                    point["eligible"] = False
                    point["reasons"] = list(dict.fromkeys([*point.get("reasons", []), "ist_invalid"]))
                point["_actual"], point["_target"] = numbers["IST"], numbers["SOLL"]
                if point["eligible"]:
                    units.add(str(point.get("unit_raw") or point.get("unit") or "").strip())
                    if numbers["SOLL"] is not None and not point.get("feature_reasons", {}).get("target"):
                        targets.add(numbers["SOLL"])
                    if numbers["MIN"] is not None and numbers["MAX"] is not None and not point.get("feature_reasons", {}).get("manufacturer"):
                        if numbers["MIN"] <= numbers["MAX"]:
                            minima.add(numbers["MIN"])
                            maxima.add(numbers["MAX"])
                prepared.append(point)
                continue
            try:
                actual = _decimal(point.get("parsed", {}).get("IST"))
                target = _decimal(point.get("parsed", {}).get("SOLL"))
                minimum = _decimal(point.get("parsed", {}).get("MIN"))
                maximum = _decimal(point.get("parsed", {}).get("MAX"))
                if minimum > maximum:
                    point["eligible"] = False
                    point["reasons"] = list(dict.fromkeys([*point.get("reasons", []), "manufacturer_limits_reversed"]))
                if point["eligible"]:
                    targets.add(target)
                    minima.add(minimum)
                    maxima.add(maximum)
                    units.add(str(point.get("unit_raw") or point.get("unit") or "").strip())
                point["_actual"], point["_target"] = actual, target
            except QCConfigurationError:
                point["eligible"] = False
                point["reasons"] = list(point.get("reasons", [])) + ["numeric_value_invalid"]
            prepared.append(point)
        expected_unit = "1" if modern and configuration.get("dimensionless") else control["unit"]
        unit_conflict = len(units) > 1 or bool(units and expected_unit and units != {expected_unit})
        conflict = len(targets) > 1 or unit_conflict
        conflicts = (["target_or_unit_conflict"] if conflict else [])
        conflicts += [reason for values, reason in ((minima, "manufacturer_min_conflict"), (maxima, "manufacturer_max_conflict")) if len(values) > 1]
        if conflicts and not modern:
            for point in prepared:
                point["eligible"] = False
                point["reasons"] = list(dict.fromkeys([*point.get("reasons", []), *conflicts]))
        eligible = [point for point in prepared if point["eligible"]]
        if modern and unit_conflict:
            for point in prepared:
                point["eligible"] = False
                point["reasons"] = list(dict.fromkeys([*point.get("reasons", []), "unit_conflict"]))
            eligible = []
        target = next(iter(targets)) if len(targets) == 1 and (not conflicts or modern and not unit_conflict) else None
        limits = _series_limits(configuration, prepared, target, minima, maxima, modern=modern)
        for point in prepared:
            point["limit_findings"] = {kind: _limit_finding(point, limit) if not modern or not point.get("feature_reasons", {}).get("manufacturer" if kind == "manufacturer" else "target")
                else {"status": "unavailable", "reason": point["feature_reasons"]["manufacturer" if kind == "manufacturer" else "target"][0], "direction": ""} for kind, limit in limits.items()}
            has_target = point["eligible"] and point.get("_target") is not None
            absolute = abs(point["_actual"] - point["_target"]) if has_target else None
            point["deviation"] = {"absolute": _metric(absolute, "" if has_target else "target_unavailable" if point["eligible"] else "point_ineligible"),
                "relative_percent": _metric(100 * absolute / point["_target"]) if has_target and point["_target"] > 0 else
                    _metric(reason="positive_target_required" if point["eligible"] else "point_ineligible")}
            matches = originals[_observation_identity(point)]
            point["measurement"] = _measurement(point, configuration, matches[0] if len(matches) == 1 else {})
        display_order = sorted(prepared, key=lambda point: (point["measurement"]["date"] or "~", point.get("measured_at") or "~", point["point_key"]))
        for position, point in enumerate(display_order, 1):
            point["position"] = position
        dates = [point["measurement"]["date"] for point in prepared if point["measurement"]["date"]]
        period = {"start_date": min(dates, default=None), "end_date": max(dates, default=None), "unknown_date_count": len(prepared) - len(dates)}
        target_points = [point for point in eligible if point.get("_target") is not None and not point.get("feature_reasons", {}).get("target")] if modern else eligible
        qmma = {"available": False, "reason": "target_or_unit_conflict" if conflict else "target_unavailable" if modern and not target_points else "eligible_values_missing", "value": None,
                "relative_percent": None, "relative_reason": "positive_target_required", "limit_status": "unavailable", "n": len(target_points)}
        if target_points and target is not None:
            count = Decimal(len(target_points))
            sum_squares = sum(((point["_actual"] - target) ** 2 for point in target_points), Decimal(0))
            value = (sum_squares / count).sqrt()
            relative = 100 * value / target if target > 0 else None
            limit = configuration.get("relative_limit_percent")
            limit_status = "not_configured"
            if not configuration.get("relative_enabled") or not configuration.get("rili_applicable"):
                limit_status = "not_applicable"
            elif target > 0 and limit is not None:
                limit_value = _decimal(limit)
                limit_status = "exceeded" if 10_000 * sum_squares > count * target * target * limit_value * limit_value else "within_limit"
            elif target <= 0:
                limit_status = "unavailable"
            qmma.update(available=True, reason="", value=_text(value), target=_text(target), sum_squared_deviations=_text(sum_squares),
                        relative_percent=_text(relative) if relative is not None else None,
                        relative_reason="" if target > 0 else "positive_target_required", limit_status=limit_status,
                        relative_limit_percent=limit)
        reference = _sd_reference(references.get(identifier), identifier, target, manifest, sd_context)
        if modern:
            # A single observation needs a qualified value/reference, not a
            # timestamp. Chronology still gates windows and sequence rules.
            for point in prepared:
                if point["eligible"] and reference["available"]:
                    point.update(_normalization(point["_actual"], reference))
        buckets = defaultdict(list)
        for point in prepared:
            if point["_date"] is not None:
                buckets[point["_date"]].append(point)
        if modern:
            intervals = sorted((point["measurement"]["interval"]["lower"], point["measurement"]["interval"]["upper_exclusive"], point["point_key"], point)
                for point in prepared if point["measurement"].get("interval"))
            cluster, upper = [], None
            for lower, end, _key, point in intervals:
                if upper is not None and lower < upper:
                    cluster[0]["order_ambiguous"] = True
                    point["order_ambiguous"] = True
                    upper = max(upper, end)
                else:
                    cluster, upper = [point], end
        segments, segment = [], []
        for measured_at in sorted(buckets):
            bucket = buckets[measured_at]
            ambiguous = len(bucket) != 1 or any(point["order_ambiguous"] for point in bucket)
            for point in bucket:
                point["order_ambiguous"] = ambiguous
                if not modern and point["eligible"] and reference["available"]:
                    point.update(_normalization(point["_actual"], reference))
                seconds = Decimal(measured_at.hour * 3600 + measured_at.minute * 60 + measured_at.second)
                point["chart_x"] = _text(Decimal(measured_at.toordinal()) + seconds / 86400)
            if ambiguous or not bucket[0]["eligible"]:
                if segment:
                    segments.append(segment)
                    segment = []
                continue
            segment.append(bucket[0]["point_key"])
        if segment:
            segments.append(segment)
        computed_reference = {key: value for key, value in reference.items() if key not in {"center_sum", "center_n", "variance_numerator", "variance_denominator"}}
        bands = []
        if reference["available"]:
            center, sd = _decimal(reference["center"]), _decimal(reference["sd"])
            bands = [{"sd_multiple": multiple, "value": _text(center + multiple * sd)} for multiple in range(-3, 4)]
        series.append({"control_id": identifier, "control_name": control["name"], "unit": expected_unit or (next(iter(units)) if len(units) == 1 else "ungeklärt"), "qmma": qmma,
                       "descriptive": _descriptive(eligible), "period": period,
                       "sd": computed_reference, "bands": bands, "segments": segments, "limits": limits,
                       "point_keys": [point["point_key"] for point in prepared],
                       "included_count": len(eligible), "excluded_count": len(prepared) - len(eligible)})
        series[-1]["function_counts"] = {"descriptive": len(eligible), "qmma": len(target_points),
            "manufacturer": sum(point["limit_findings"]["manufacturer"]["status"] in {"within_limit", "exceeded"} for point in prepared),
            "single_value": sum(point["limit_findings"]["single_value"]["status"] in {"within_limit", "exceeded"} for point in prepared),
            "dated": sum(point["measurement"]["date"] is not None for point in prepared)}
        all_points.extend(prepared)
    runs = _evaluate_runs(all_points, controls, configuration["enabled_rules"])
    run_by_point = {key: run for run in runs for key in run["point_keys"]}
    for item in series:
        own_points = [point for point in all_points if point["control_id"] == item["control_id"]]
        own_keys = set(item["point_keys"])
        own_runs = [run for run in runs if own_keys.intersection(run["point_keys"])]
        item["findings_summary"] = {kind + "_exceeded_count": sum(point["limit_findings"][kind]["status"] == "exceeded" for point in own_points)
            for kind in ("manufacturer", "single_value")}
        item["findings_summary"].update(westgard_reject_count=sum(run["status"] == "reject" for run in own_runs),
            westgard_warning_count=sum(run["status"] == "warning" for run in own_runs),
            westgard_status="disabled" if not configuration["enabled_rules"] else ("reject" if any(run["status"] == "reject" for run in own_runs) else
                ("warning" if any(run["status"] == "warning" for run in own_runs) else
                ("unavailable" if not own_runs or any(run["status"] == "unavailable" for run in own_runs) else "no_rejection"))),
            westgard_unavailable_reasons=sorted({finding["reason"] for run in own_runs for finding in run["findings"] if finding["status"] == "unavailable"}))
        selected = [point for point in all_points if point["control_id"] == item["control_id"] and point["eligible"] and point["_date"] is not None]
        chart_points = [{"point_key": point["point_key"], "x": point["chart_x"], "y": _text(point["_actual"]),
            "measured_at": point["measured_at"], "run_id": point["run_id"], "revision_id": point["revision_id"],
            "selection_id": point.get("selection_id"), "validation_id": point.get("validation_id"),
            "raw": point["raw"], "parsed": point["parsed"], "z": point["z"], "order_ambiguous": point["order_ambiguous"],
            "run_status": run_by_point[point["point_key"]]["status"], "findings": run_by_point[point["point_key"]]["findings"],
            "limit_findings": point["limit_findings"]} for point in selected]
        for point, frozen in zip(selected, chart_points):
            frozen.update(position=point["position"], measurement=point["measurement"], deviation=point["deviation"])
        reference_lines = _reference_lines(item)
        ys = [point["_actual"] for point in selected] + [_decimal(line["value"]) for line in reference_lines]
        xs = [_decimal(point["chart_x"]) for point in selected]
        xlo, xhi = (min(xs), max(xs)) if xs else (Decimal(0), Decimal(1))
        ylo, yhi = (min(ys), max(ys)) if ys else (Decimal(0), Decimal(1))
        xpad = (xhi - xlo) / 20 if xhi != xlo else Decimal("0.5")
        ypad = (yhi - ylo) / 10 if yhi != ylo else max(abs(ylo) / 20, Decimal(1))
        item["chart"] = {"points": chart_points, "segments": item["segments"], "bands": item["bands"], "unit": item["unit"],
                         "reference_lines": reference_lines,
                         "target": item["qmma"].get("target"), "x_range": [_text(xlo - xpad), _text(xhi + xpad)],
                         "y_range": [_text(ylo - ypad), _text(yhi + ypad)],
                         "x_label": "Extrahiertes Messdatum / Messzeit", "y_label": f"Messwert ({item['unit']})"}
    for point in all_points:
        point.pop("_actual", None)
        point.pop("_target", None)
        point.pop("_date", None)
    return {"algorithm_id": ALGORITHM_ID, "renderer_id": RENDERER_ID, "analysis_model_version": 4,
            "source_manifest": manifest, "sd_references": references, "sd_reference_context": sd_context, "references": REFERENCES,
            "profile_reference": configuration.get("guideline_reference", ""),
            "human_validation": "captured_separately_in_source_manifest", "computed_series": series,
            "points": all_points, "analytical_runs": runs,
            "counts": {"source_population": manifest["population_count"], "source_included": manifest["included_count"],
                       "source_excluded": manifest["excluded_count"], "analysis_included": sum(item["included_count"] for item in series),
                       "analysis_excluded": sum(item["excluded_count"] for item in series)}}


def analyze_lot(manifest: Mapping[str, Any], sd_references: Mapping[str, Any], *, sd_reference_context: Mapping[str, Any] | None = None) -> QCAnalysis:
    """Freeze one explicitly captured population without changing any raw refs."""
    raw = canonical_json({"manifest": manifest, "sd_references": sd_references, "sd_reference_context": sd_reference_context or {}})
    if len(raw.encode("utf-8")) > MAX_MODEL_BYTES:
        raise QCConfigurationError("Die Analysepopulation überschreitet die Rechengrenze (16 MB).")
    value = json.loads(raw)
    source = value["manifest"]
    try:
        token = source["source_token"]
        if source.get("manifest_version") not in {"qc-sources-v1", "qc-sources-v2", "qc-sources-v3"}:
            raise QCConfigurationError("Die Quellenmanifest-Fassung wird nicht unterstützt.")
        if content_hash({key: item for key, item in source.items() if key != "source_token"}) != token:
            raise QCConfigurationError("Die Prüfsumme des Quellenmanifests stimmt nicht.")
        if len(source["included"]) + len(source["excluded"]) > MAX_POINTS:
            raise QCConfigurationError("Die Analyse enthält zu viele Kontrollwerte.")
        if source["profile_snapshot"]["qc_profile"] != "classic-six-v1":
            raise QCConfigurationError("Das QC-Verfahren wird nicht unterstützt.")
        with localcontext() as context:
            context.prec = _precision(source, value["sd_references"])
            analysis = QCAnalysis.freeze(_analyze(source, value["sd_references"], value["sd_reference_context"]))
        if len(analysis.model_json.encode("utf-8")) > MAX_MODEL_BYTES:
            raise QCConfigurationError("Das eingefrorene Analysemodell überschreitet 16 MB.")
        return analysis
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise QCConfigurationError("Das Quellenmanifest enthält unvollständige oder unlesbare Analysedaten.") from exc
