"""Synthetic P4 acceptance for profiles, complete populations and lot evidence."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.qualitycontrol.api import (
    MutationContext, QCConfigurationError, QCConflictError, close_lot, configure_lot,
    get_inventory, get_lot, get_lot_sources, get_report_evidence, list_lots, list_profiles,
    open_lot, reopen_lot, save_inventory, save_profile,
    analyze_lot, get_profile, get_sd_reference_context,
)
from src.resultvalidation.api import validate_run


def context(request: str, reason="") -> MutationContext:
    return MutationContext("RR", request, reason)


def profile_payload() -> dict:
    return {"profile_id": "p1", "name": "Assay A", "device_id": "dev", "assay_key": "A",
            "measurement_date_field": "DATE", "measurement_date_format": "%Y-%m-%d", "numeric_grammar": "decimal_dot",
            "unit": "U", "rili_applicable": True, "relative_enabled": True, "relative_limit_percent": "12.5",
            "qc_profile": "classic-six-v1", "enabled_rules": ["1_2s", "1_3s", "2_2s", "R_4s", "4_1s", "10x"],
            "run_grouping_field": "", "controls": [{"control_id": "c1", "name": "Kontrolle 1",
                "fields": {"IST": "I1", "SOLL": "S1", "MIN": "N1", "MAX": "X1"}, "unit_field": "UNIT"}]}


def payload(date="2026-01-01", **changes) -> dict:
    return {"DATE": date, "I1": "42.0", "S1": "40", "N1": "30", "X1": "50", "UNIT": "U", **changes}


def add_run(spec: dict, run_id: int, *, lot="L1", data=None, validated=True) -> None:
    with sqlite3.connect(spec["path"]) as conn:
        conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            run_id, "", f"synthetic-{run_id}.pdf", "A", lot, "dev", json.dumps(data or payload()), "2026-01-01T00:00:00+00:00"))
    if validated:
        validate_run(spec, run_id, "RR")


def fixture(tmp_path: Path, *, count=2) -> tuple[dict, dict]:
    spec = {"driver": "sqlite", "path": str(tmp_path / "synthetic.sqlite3")}
    with sqlite3.connect(spec["path"]) as conn:
        conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, job_id TEXT, pdf_path TEXT, assay_key TEXT, lot_id TEXT, device_id TEXT, payload_json TEXT, created_at TEXT)")
    inventory = save_inventory(spec, {"default_device_id": "dev", "devices": [
        {"device_id": "dev", "display_name": "Laborgerät", "serial_number": "SYNTHETIC-SN"}]}, expected_version_id=0, context=context("inventory"))
    profile = save_profile(spec, profile_payload(), expected_version_id=0, expected_inventory_version_id=inventory["version_id"], context=context("profile"))
    for run_id in range(1, count + 1):
        add_run(spec, run_id, data=payload(f"2026-01-{min(run_id, 28):02d}"))
    return spec, profile


def sd_origin_fixture(tmp_path: Path, kind: str):
    spec, initial = fixture(tmp_path, count=0)
    value = copy.deepcopy(initial["snapshot"])
    value["unit"] = value["controls"][0]["unit"] = "A"
    value["controls"][0]["unit_field"] = ""
    profile = save_profile(spec, value, expected_version_id=initial["version_id"], expected_inventory_version_id=1,
                           context=context("origin-profile"))
    for number, actual in enumerate(("90", "91", "92"), 1):
        add_run(spec, number, data=payload(f"2026-01-{number:02d}", I1=actual, S1="100", N1="50", X1="150",
            I2="94", S2="100", N2="40", X2="160", DATE2=f"{number:02d}/01/2026", GROUP=f"group-{number}"))
    captured = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1")
    reference = {"kind": "manual", "value": "1"} if kind == "manual" else {"kind": "confirmed_baseline", "confirmed": True}
    opened = open_lot(spec, profile_version_id=profile["version_id"], kit_lot="L1", expected_source_token=captured["source_token"],
                      sd_references={"c1": reference}, context=context("origin-open"))
    return spec, profile, opened


@pytest.mark.parametrize("kind", ["manual", "confirmed_baseline"])
@pytest.mark.parametrize("change,available", [("unit", False), ("IST", False), ("grammar", False),
    ("name", True), ("date", True), ("group", True), ("rules", True), ("relative", True), ("limits", True), ("target", True)])
def test_frozen_sd_origin_compatibility_uses_measured_variable_not_whole_profile(tmp_path: Path, kind, change, available):
    spec, old_profile, opened = sd_origin_fixture(tmp_path, kind)
    old_refs = copy.deepcopy(opened["snapshot"]["sd_references"])
    value = copy.deepcopy(old_profile["snapshot"])
    if change == "unit":
        value["unit"] = value["controls"][0]["unit"] = "B"
    elif change == "IST":
        value["controls"][0]["fields"]["IST"] = "I2"
    elif change == "grammar":
        value["numeric_grammar"] = "decimal_comma"
    elif change == "name":
        value["name"] = value["controls"][0]["name"] = "Renamed"
    elif change == "date":
        value.update(measurement_date_field="DATE2", measurement_date_format="%d/%m/%Y")
    elif change == "group":
        value["run_grouping_field"] = "GROUP"
    elif change == "rules":
        value["enabled_rules"] = ["1_3s"]
    elif change == "relative":
        value["relative_limit_percent"] = "20"
    elif change == "limits":
        value["controls"][0]["fields"].update(MIN="N2", MAX="X2")
    else:
        value["controls"][0]["fields"]["SOLL"] = "S2"
    revised = save_profile(spec, value, expected_version_id=old_profile["version_id"], expected_inventory_version_id=1,
                           context=context("origin-edit-profile"))
    captured = get_lot_sources(spec, profile_version_id=revised["version_id"], kit_lot="L1")
    assert captured["excluded_count"] == 0
    updated = configure_lot(spec, opened["lot_key"], expected_version_id=opened["version_id"], profile_version_id=revised["version_id"],
        expected_source_token=captured["source_token"], sd_references=old_refs, context=context("origin-edit-lot"))
    origin = get_sd_reference_context(spec, lot_key=updated["lot_key"], expected_version_id=updated["version_id"])
    analysis = analyze_lot(captured, old_refs, sd_reference_context=origin).to_dict()
    series = analysis["computed_series"][0]
    assert series["sd"]["available"] is available and series["qmma"]["available"]
    if not available:
        assert not series["bands"] and all(point["z"] is None for point in analysis["points"])
    assert get_profile(spec, old_profile["version_id"]) == old_profile
    assert list_lots(spec, include_history=True)[0]["snapshot"]["sd_references"] == old_refs == analysis["sd_references"]
    if change == "unit" and kind == "manual":
        fresh = configure_lot(spec, updated["lot_key"], expected_version_id=updated["version_id"], profile_version_id=revised["version_id"],
            expected_source_token=captured["source_token"], sd_references={"c1": {"kind": "manual", "value": "1"}}, context=context("origin-new-manual"))
        new_refs = fresh["snapshot"]["sd_references"]
        assert new_refs["c1"]["value"] == old_refs["c1"]["value"] == "1"
        assert new_refs["c1"]["profile_version_id"] == revised["version_id"]
        assert new_refs["c1"]["reference_id"] != old_refs["c1"]["reference_id"]
        fresh_context = get_sd_reference_context(spec, lot_key=fresh["lot_key"], expected_version_id=fresh["version_id"])
        assert analyze_lot(captured, new_refs, sd_reference_context=fresh_context).to_dict()["computed_series"][0]["sd"]["available"]


@pytest.mark.parametrize("missing", ["none", "history", "profile", "reference-hash"])
def test_legacy_manual_origin_requires_complete_history_and_profile_without_writes(tmp_path: Path, missing):
    spec, old_profile, opened = sd_origin_fixture(tmp_path, "manual")
    # Synthetic old P4 bytes: manual references did not yet bind profile_version_id.
    legacy = copy.deepcopy(opened["snapshot"])
    reference = legacy["sd_references"]["c1"]
    reference.pop("profile_version_id")
    reference.pop("reference_id")
    from src.qualitycontrol.model import content_hash
    reference["reference_id"] = content_hash({"control_id": "c1", "reference": reference})
    if missing == "reference-hash":
        reference["value"] = "2"  # The stored ID no longer proves these raw reference bytes.
    with sqlite3.connect(spec["path"]) as conn:
        conn.execute("UPDATE qc_lot_versions SET snapshot_json=? WHERE version_id=?", (json.dumps(legacy), opened["version_id"]))
    captured = get_lot_sources(spec, profile_version_id=old_profile["version_id"], kit_lot="L1")
    later = configure_lot(spec, opened["lot_key"], expected_version_id=opened["version_id"], profile_version_id=old_profile["version_id"],
        expected_source_token=captured["source_token"], sd_references=legacy["sd_references"], context=context("legacy-keep"))
    if missing in {"history", "profile"}:
        with sqlite3.connect(spec["path"]) as conn:
            if missing == "history":
                conn.execute("DELETE FROM qc_lot_versions WHERE version_id=?", (opened["version_id"],))
            else:
                conn.execute("DELETE FROM qc_profile_versions WHERE version_id=?", (old_profile["version_id"],))
    before = Path(spec["path"]).read_bytes(), Path(spec["path"]).stat().st_mtime_ns
    origin = get_sd_reference_context(spec, lot_key=later["lot_key"], expected_version_id=later["version_id"])
    result = analyze_lot(captured, legacy["sd_references"], sd_reference_context=origin).to_dict()
    assert result["computed_series"][0]["sd"]["available"] is (missing == "none")
    assert result["computed_series"][0]["qmma"]["available"]
    assert (Path(spec["path"]).read_bytes(), Path(spec["path"]).stat().st_mtime_ns) == before
    if missing == "none":
        assert origin["references"]["c1"]["provenance"] == "lot-history"
        assert origin["references"]["c1"]["origin_lot_version_id"] == opened["version_id"]


def test_sd_origin_capture_rechecks_lot_after_profile_read(tmp_path: Path, monkeypatch):
    import src.qualitycontrol.api as owner
    spec, profile, opened = sd_origin_fixture(tmp_path, "manual")
    captured = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1")
    original, changed = owner.get_profile, []
    def raced(*args):
        result = original(*args)
        if not changed:
            changed.append(True)
            configure_lot(spec, opened["lot_key"], expected_version_id=opened["version_id"], profile_version_id=profile["version_id"],
                expected_source_token=captured["source_token"], sd_references=opened["snapshot"]["sd_references"], context=context("origin-race"))
        return result
    monkeypatch.setattr(owner, "get_profile", raced)
    with pytest.raises(QCConflictError, match="während des Lesens geändert"):
        get_sd_reference_context(spec, lot_key=opened["lot_key"], expected_version_id=opened["version_id"])


def sources(spec, profile, lot="L1"):
    return get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot=lot)


def test_assaywide_actual_only_profile_keeps_independent_statistics_and_honest_source_time(tmp_path):
    """A first-use profile remains useful as optional context is added later."""
    from src.qualitycontrol.api import ConfigurationContext, get_lot_chronology
    from src.qualitycontrol.profiles import interpret_measurement, interpret_numeric, parse_decimal
    spec, old = fixture(tmp_path, count=0)
    value = {"profile_schema_version": 2, "profile_id": "neutral", "name": "Gemeinsames Assayprofil", "assay_key": "A",
        "unit": "U", "controls": [{"control_id": "c1", "name": "Level 1", "fields": {"IST": "I1"}}]}
    profile = save_profile(spec, value, expected_version_id=0, expected_inventory_version_id=1, context=ConfigurationContext("actual-only"))
    for run_id, raw in enumerate((
        {"DATUM": "14.11.2026", "ZEIT": "8:05", "I1": "42,5"},
        {"date": "2026-11-14", "time": "08:05:00", "I1": "43.5"},
        {"DATE": "2026-11-15", "TIME": "24:00", "I1": "44.5"},
        {"DATE": "03/04/2026", "I1": "45.5"}), 1):
        add_run(spec, run_id, data=raw)
    captured = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1", device_id="dev")
    assert len(captured["included"]) == 4 and not captured["excluded"]
    result = analyze_lot(captured, {}).to_dict()
    series = result["computed_series"][0]
    assert series["descriptive"]["n"] == 4 and series["descriptive"]["mean"]["value"] == "44"
    assert series["descriptive"]["sample_sd"]["available"] and not series["qmma"]["available"]
    assert not series["limits"]["manufacturer"]["available"] and series["findings_summary"]["westgard_status"] == "disabled"
    assert series["function_counts"]["descriptive"] == 4 and series["function_counts"]["qmma"] == 0
    by_id = {point["run_id"]: point for point in result["points"]}
    assert by_id[1]["measurement"]["time"] == "08:05" and by_id[1]["measurement"]["precision"] == "minutes"
    assert by_id[2]["measurement"]["time"] == "08:05:00" and by_id[2]["measurement"]["precision"] == "seconds"
    assert by_id[1]["order_ambiguous"] and by_id[2]["order_ambiguous"]
    assert by_id[3]["measurement"]["date"] == "2026-11-15" and by_id[3]["measurement"]["time"] is None
    assert by_id[3]["measurement"]["precision"] == "day" and by_id[4]["measurement"]["date"] is None
    usage = get_lot_chronology(spec, profile_version_id=profile["version_id"], device_id="dev").to_dict()
    assert usage["device_id"] == "dev" and not usage["lots"][0]["last_usage_reliable"]
    midnight = interpret_measurement({"DATE": "2026-11-14", "TIME": "00:00"}, profile["snapshot"])
    assert midnight["time"] == "00:00" and midnight["precision"] == "minutes"
    conflict = interpret_measurement({"DATE": "2026-11-14", "DATUM": "15.11.2026"}, profile["snapshot"])
    assert conflict["interval"] is None and "measurement_date_conflict" in conflict["reasons"]
    with pytest.raises(QCConfigurationError, match="mehrdeutig"):
        parse_decimal("1,234", "auto")
    original_text = (Path(__file__).parents[1] / "rules" / "Anti-MPO IgG.json").read_text(encoding="utf-8")
    original_rule = {"rule_source_text": original_text, "rule_sha256": hashlib.sha256(original_text.encode()).hexdigest(), "ruleset": json.loads(original_text)}
    actual = interpret_numeric("1,234", "auto", field_key="S1_IST", source=original_rule)
    assert actual["value"] == "1.234" and actual["method"] == "verified-original-decimal-export-v1"
    changed_rule = {**original_rule, "rule_source_text": original_text + " "}
    with pytest.raises(QCConfigurationError, match="mehrdeutig"):
        interpret_numeric("1,234", "auto", field_key="S1_IST", source=changed_rule)
    with pytest.raises(QCConfigurationError, match="genau ein"):
        get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1")
    dimensionless = save_profile(spec, {**value, "profile_id": "dimensionless", "unit": "", "dimensionless": True},
        expected_version_id=0, expected_inventory_version_id=1, context=ConfigurationContext("dimensionless"))
    own = get_lot_sources(spec, profile_version_id=dimensionless["version_id"], kit_lot="L1", device_id="dev")
    lot = open_lot(spec, profile_version_id=dimensionless["version_id"], kit_lot="L1", device_id="dev",
        expected_source_token=own["source_token"], sd_references={"c1": {"kind": "confirmed_baseline", "confirmed": True}}, context=context("dimensionless-baseline"))
    sd_context = get_sd_reference_context(spec, lot_key=lot["lot_key"], expected_version_id=lot["version_id"])
    evaluated = analyze_lot(own, lot["snapshot"]["sd_references"], sd_reference_context=sd_context).to_dict()
    assert evaluated["computed_series"][0]["unit"] == "1" and evaluated["computed_series"][0]["sd"]["available"]


@pytest.mark.parametrize("optional", [{}, {"measurement_time_field": "", "measurement_time_format": ""},
    {"measurement_time_field": None, "measurement_time_format": None},
    {"measurement_time_field": "  ", "measurement_time_format": "  "}])
def test_optional_time_empty_pair_preserves_exact_old_normalized_profile(optional):
    from src.qualitycontrol.profiles import normalize_profile
    old = normalize_profile(profile_payload())
    assert normalize_profile({**profile_payload(), **optional}) == old
    assert "measurement_time_field" not in old and "measurement_time_format" not in old


@pytest.mark.parametrize("field,fmt,datefmt", [("TIME", "", "%Y-%m-%d"), ("", "%H:%M", "%Y-%m-%d"),
    (17, "%H:%M", "%Y-%m-%d"), ("TIME", "%H", "%Y-%m-%d"), ("TIME", "%M", "%Y-%m-%d"),
    ("TIME", "%I:%M %p", "%Y-%m-%d"), ("TIME", "%H:%M %z", "%Y-%m-%d"),
    ("TIME", "%Y %H:%M", "%Y-%m-%d"), ("TIME", "%X", "%Y-%m-%d"),
    ("TIME", "%H:%M%", "%Y-%m-%d"), ("TIME", "%H:%M:%H", "%Y-%m-%d"),
    ("TIME", "%H:%M", "%Y-%m-%d %H:%M:%S")])
def test_optional_time_rejects_partial_or_ambiguous_format(field, fmt, datefmt):
    from src.qualitycontrol.profiles import normalize_profile
    with pytest.raises(QCConfigurationError, match="Messzeit|Zeitformat|Uhrzeit"):
        normalize_profile({**profile_payload(), "measurement_date_format": datefmt,
            "measurement_time_field": field, "measurement_time_format": fmt})


def time_profile(spec, old, *, date_key="DATE", time_key="TIME", fmt="%H:%M"):
    value = copy.deepcopy(old["snapshot"])
    value.update(measurement_date_field=date_key, measurement_time_field=time_key, measurement_time_format=fmt)
    return save_profile(spec, value, expected_version_id=old["version_id"], expected_inventory_version_id=1,
                        context=context("time-profile"))


def time_analysis(spec, profile):
    captured = sources(spec, profile)
    opened = open_lot(spec, profile_version_id=profile["version_id"], kit_lot="L1", expected_source_token=captured["source_token"],
        sd_references={"c1": {"kind": "manual", "value": "1"}}, context=context("time-open"))
    origin = get_sd_reference_context(spec, lot_key=opened["lot_key"], expected_version_id=opened["version_id"])
    return captured, analyze_lot(captured, opened["snapshot"]["sd_references"], sd_reference_context=origin).to_dict()


@pytest.mark.parametrize("date_key,time_key", [("date", "time"), ("DATUM", "ZEIT")])
@pytest.mark.parametrize("fmt,early,late", [("%H:%M", "08:00", "09:00"),
    ("%H:%M:%S", "08:00:00", "09:00:00"), ("%H%M", "0800", "0900")])
def test_optional_time_proves_same_day_order_independent_of_run_ids(tmp_path: Path, date_key, time_key, fmt, early, late):
    spec, old = fixture(tmp_path, count=0)
    profile = time_profile(spec, old, date_key=date_key, time_key=time_key, fmt=fmt)
    for run_id, clock, actual in ((1, late, "2.2"), (2, early, "2.1")):
        data = payload(I1=actual, S1="0", N1="-10", X1="10")
        data.update({date_key: "2026-01-01", time_key: clock})
        add_run(spec, run_id, data=data)
    captured, result = time_analysis(spec, profile)
    assert captured["order_is_explicit"] and not captured["excluded"]
    assert [point["run_id"] for point in captured["included"]] == [2, 1]
    assert captured["included"][0]["measured_at"] == ("2026-01-01T08:00:00" if "%S" in fmt else "2026-01-01T08:00")
    assert captured["population"][0]["measurement_time_raw"] == late
    latest = next(run for run in result["analytical_runs"] if run["analytical_run_id"] == "stored-run:1")
    assert next(item for item in latest["findings"] if item["rule"] == "2_2s")["status"] == "reject"
    assert get_profile(spec, old["version_id"]) == old


@pytest.mark.parametrize("raw,reason", [(None, "measurement_time_missing"), ("", "measurement_time_missing"),
    ("  ", "measurement_time_missing"), ("24:00", "measurement_time_invalid"), ("8:00", "measurement_time_invalid"),
    ("08:00:00", "measurement_time_invalid"), (800, "measurement_time_invalid")])
def test_optional_time_missing_or_invalid_has_no_midnight_fallback(tmp_path: Path, raw, reason):
    spec, old = fixture(tmp_path, count=0)
    profile = time_profile(spec, old)
    add_run(spec, 1, data=payload(TIME=raw))
    captured = sources(spec, profile)
    assert captured["included_count"] == 1 and not captured["excluded"]
    point = captured["included"][0]
    assert point["measured_at"] == "2026-01-01" and point["measurement"]["time"] is None
    assert point["feature_reasons"]["time"] == [reason]
    assert captured["population"][0]["measurement_time_raw"] == raw and captured["start_date"] == "2026-01-01"


def test_optional_time_four_point_rule_and_invalid_time_history_barrier(tmp_path: Path):
    spec, old = fixture(tmp_path, count=0)
    profile = time_profile(spec, old, date_key="DATUM", time_key="ZEIT")
    for run_id, clock, actual in ((1, "11:00", "2.1"), (2, "10:00", "1.3"), (3, "09:00", "1.2"), (4, "08:00", "1.1")):
        add_run(spec, run_id, data=payload(DATUM="2026-01-01", ZEIT=clock, I1=actual, S1="0", N1="-10", X1="10"))
    _, result = time_analysis(spec, profile)
    latest = next(run for run in result["analytical_runs"] if run["analytical_run_id"] == "stored-run:1")
    assert next(item for item in latest["findings"] if item["rule"] == "4_1s")["status"] == "reject"
    add_run(spec, 5, data=payload(DATUM="2026-01-01", ZEIT="unlesbar", I1="2.2", S1="0"))
    current = sources(spec, profile)
    lot = get_lot(spec, list_lots(spec)[0]["lot_key"])
    origin = get_sd_reference_context(spec, lot_key=lot["lot_key"], expected_version_id=lot["version_id"])
    result = analyze_lot(current, lot["snapshot"]["sd_references"], sd_reference_context=origin).to_dict()
    assert not current["excluded"] and result["computed_series"][0]["qmma"]["available"]
    assert next(point for point in current["included"] if point["run_id"] == 5)["measurement"]["time"] is None
    latest = next(run for run in result["analytical_runs"] if run["analytical_run_id"] == "stored-run:1")
    finding = next(item for item in latest["findings"] if item["rule"] == "4_1s")
    assert finding["status"] == "unavailable" and finding["reason"] == "measurement_order_ambiguous"


def test_optional_time_old_no_map_and_equal_times_remain_barriers(tmp_path: Path):
    spec, old = fixture(tmp_path, count=0)
    for run_id in (1, 2):
        add_run(spec, run_id, data=payload("2026-01-01", TIME="08:00", I1="2.1", S1="0", N1="-10", X1="10"))
    legacy = sources(spec, old)
    assert not legacy["order_is_explicit"] and legacy["equal_time_order_unavailable"]
    assert all("measurement_time_raw" not in row for row in legacy["population"])
    profile = time_profile(spec, old)
    captured, result = time_analysis(spec, profile)
    assert captured["order_is_explicit"] and captured["equal_time_order_unavailable"]
    assert all(next(item for item in run["findings"] if item["rule"] == "2_2s")["status"] == "unavailable" for run in result["analytical_runs"])
    assert captured["source_token"] != legacy["source_token"]  # Explicit new profile/head, not an old-branch golden.


def open_current(spec, profile, **kwargs):
    manifest = sources(spec, profile)
    return open_lot(spec, profile_version_id=profile["version_id"], kit_lot="L1", expected_source_token=manifest["source_token"], context=context("open"), **kwargs)


def evidence_arguments(spec, profile, lot):
    manifest, witness = sources(spec, profile), sources(spec, profile, "L2")
    pdf = b"%PDF-1.4\nsynthetic supplied renderer evidence\n%%EOF"
    model = analyze_lot(manifest, lot["snapshot"]["sd_references"]).to_dict()
    return {"expected_version_id": lot["version_id"], "expected_source_token": manifest["source_token"], "witness_kit_lot": "L2",
            "expected_witness_source_token": witness["source_token"], "analysis_model": model, "pdf_bytes": pdf,
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(), "algorithm_id": model["algorithm_id"], "renderer_id": model["renderer_id"], "context": context("close")}


def test_complete_profile_history_stable_controls_and_no_control_count_limit(tmp_path: Path):
    spec, first = fixture(tmp_path)
    value = copy.deepcopy(first["snapshot"])
    value["name"] = "Umbenannt"
    value["controls"][0]["name"] = "Neue Bezeichnung"
    for number in range(2, 31):
        value["controls"].append({"control_id": f"c{number}", "name": f"Kontrolle {number}", "fields": {
            "IST": f"I{number}", "SOLL": f"S{number}", "MIN": f"N{number}", "MAX": f"X{number}"}})
    second = save_profile(spec, value, expected_version_id=first["version_id"], expected_inventory_version_id=1, context=context("profile-edit"))
    history = list_profiles(spec, include_history=True)
    assert len(second["snapshot"]["controls"]) == 30
    assert history[0]["snapshot"]["controls"][0]["name"] == "Kontrolle 1"
    assert second["snapshot"]["controls"][0]["control_id"] == "c1"
    assert history[0]["snapshot"]["controls"][0]["fields"] == {"IST": "I1", "SOLL": "S1", "MIN": "N1", "MAX": "X1"}
    with pytest.raises(QCConflictError):
        save_profile(spec, value, expected_version_id=first["version_id"], expected_inventory_version_id=1, context=context("stale"))


@pytest.mark.parametrize("raw,expected", [("12,5", "12.5"), ("12.5", "12.5"), ("0", "0"), ("250", "250"), (".5", "0.5")])
def test_single_value_percent_is_additive_independent_of_measurement_grammar(tmp_path, raw, expected):
    spec, old = fixture(tmp_path, count=0)
    value = copy.deepcopy(old["snapshot"])
    value.update(single_value_limits_enabled=True, single_value_limit_percent=raw, numeric_grammar="decimal_comma")
    revised = save_profile(spec, value, expected_version_id=old["version_id"], expected_inventory_version_id=1,
                           context=context("single-value"), available_field_keys=["I1", "S1", "N1", "X1"])
    assert revised["snapshot"]["single_value_limit_percent"] == expected
    assert revised["snapshot"]["single_value_limits_enabled"] is True
    assert revised["snapshot"]["relative_limit_percent"] == "12.5"
    assert revised["snapshot"]["rili_applicable"] and revised["snapshot"]["relative_enabled"]
    assert get_profile(spec, old["version_id"]) == old


@pytest.mark.parametrize("raw", [None, "", "-1", "NaN", "Infinity", "inf", "1.000,5", "1,000.5", "1,2,3", "1e2", True])
def test_invalid_enabled_single_value_percent_does_not_write_revision(tmp_path, raw):
    spec, old = fixture(tmp_path, count=0)
    value = {**copy.deepcopy(old["snapshot"]), "single_value_limits_enabled": True, "single_value_limit_percent": raw}
    before = Path(spec["path"]).read_bytes()
    with pytest.raises(QCConfigurationError, match="Einzelwert"):
        save_profile(spec, value, expected_version_id=old["version_id"], expected_inventory_version_id=1, context=context("invalid-p"))
    assert Path(spec["path"]).read_bytes() == before


def test_current_field_membership_blocks_foreign_and_removed_keys_but_keeps_history(tmp_path):
    spec, old = fixture(tmp_path, count=0)
    value = copy.deepcopy(old["snapshot"])
    value["controls"][0]["fields"]["IST"] = "FOREIGN_IST"
    with pytest.raises(QCConfigurationError, match="FOREIGN_IST"):
        save_profile(spec, value, expected_version_id=old["version_id"], expected_inventory_version_id=1,
                     context=context("foreign-field"), available_field_keys=["I1", "S1", "N1", "X1"])
    with pytest.raises(QCConfigurationError, match="X1"):
        save_profile(spec, old["snapshot"], expected_version_id=old["version_id"], expected_inventory_version_id=1,
                     context=context("removed-field"), available_field_keys=["I1", "S1", "N1"])
    value["controls"][0]["fields"]["IST"] = "S1"
    with pytest.raises(QCConfigurationError, match="unterschiedliche"):
        save_profile(spec, value, expected_version_id=old["version_id"], expected_inventory_version_id=1,
                     context=context("duplicate-field"), available_field_keys=["I1", "S1", "N1", "X1"])
    assert list_profiles(spec, include_history=True) == [old]
    assert get_profile(spec, old["version_id"]) == old


def test_legacy_profile_read_stays_exact_and_empty_legacy_qmma_limit_remains_saveable(tmp_path):
    spec, old = fixture(tmp_path, count=0)
    legacy = copy.deepcopy(old["snapshot"])
    legacy.pop("single_value_limits_enabled")
    legacy.pop("single_value_limit_percent")
    legacy["relative_limit_percent"] = None
    with sqlite3.connect(spec["path"]) as conn:
        conn.execute("UPDATE qc_profile_versions SET snapshot_json=? WHERE version_id=?", (json.dumps(legacy), old["version_id"]))
    before = Path(spec["path"]).read_bytes()
    assert get_profile(spec, old["version_id"])["snapshot"] == legacy
    assert Path(spec["path"]).read_bytes() == before
    revised = save_profile(spec, {**legacy, "name": "Neue Bezeichnung", "single_value_limit_percent": "NaN"},
        expected_version_id=old["version_id"], expected_inventory_version_id=1, context=context("legacy-edit"),
        available_field_keys=["I1", "S1", "N1", "X1"])
    assert revised["snapshot"]["single_value_limits_enabled"] is False
    assert revised["snapshot"]["single_value_limit_percent"] is None
    assert revised["snapshot"]["relative_limit_percent"] is None
    assert revised["snapshot"]["relative_enabled"] and revised["snapshot"]["rili_applicable"]
    assert get_profile(spec, old["version_id"])["snapshot"] == legacy


@pytest.mark.parametrize("raw", ["", "NaN", "Infinity", "<3", ">42", "1,2", "1.234,5", "42 U"])
def test_malformed_or_qualified_values_are_excluded_with_raw_value(tmp_path: Path, raw):
    spec, profile = fixture(tmp_path, count=0)
    add_run(spec, 1, data=payload(I1=raw))
    captured = sources(spec, profile)
    assert captured["included_count"] == 0 and captured["excluded_count"] == 1
    assert captured["excluded"][0]["raw"]["IST"] == raw
    assert "ist_invalid" in captured["excluded"][0]["reasons"]
    assert "IST" not in captured["excluded"][0]["parsed"]


def test_measurement_dates_have_no_import_fallback_and_preserve_explicit_time(tmp_path: Path):
    spec, profile = fixture(tmp_path, count=0)
    add_run(spec, 1, data=payload("yesterday"))
    assert sources(spec, profile)["start_date"] is None
    value = profile["snapshot"]
    value["measurement_date_format"] = "%Y-%m-%d %H:%M:%S"
    revised = save_profile(spec, value, expected_version_id=profile["version_id"], expected_inventory_version_id=1, context=context("time-profile"))
    add_run(spec, 2, data=payload("2026-01-01 13:24:17"))
    captured = sources(spec, revised)
    assert captured["included"][0]["measured_at"] == "2026-01-01T13:24:17"
    assert captured["order_is_explicit"]
    unknown = next(point for point in captured["included"] if point["run_id"] == 1)
    assert unknown["measured_at"] is None and "measurement_date_invalid" in unknown["feature_reasons"]["time"]


def test_target_and_unit_conflicts_need_clarification(tmp_path: Path):
    spec, profile = fixture(tmp_path, count=0)
    add_run(spec, 1)
    add_run(spec, 2, data=payload(S1="41", UNIT="other"))
    captured = sources(spec, profile)
    assert captured["included"] == []
    assert all("unit_conflict" in point["reasons"] and "target_conflict" in point["feature_reasons"]["target"] for point in captured["excluded"])


def test_all_rows_over_500_and_validation_changes_affect_manifest(tmp_path: Path):
    spec, profile = fixture(tmp_path, count=1)
    with sqlite3.connect(spec["path"]) as conn:
        for run_id in range(2, 604):
            conn.execute("INSERT INTO runs VALUES (?, '', ?, 'A', 'L1', 'dev', ?, '2099-12-31')", (run_id, f"synthetic-{run_id}.pdf", json.dumps(payload())))
            conn.execute("INSERT INTO run_validations (run_id, operator_initials, validated_at_utc, comment) VALUES (?, 'RR', '2026-01-01T00:00:00+00:00', '')", (run_id,))
    captured = sources(spec, profile)
    assert captured["population_count"] == captured["included_count"] == 603
    assert len(captured["population"][-1]["source_hash"]) == 64
    assert captured["equal_time_order_unavailable"] and not captured["order_is_explicit"]
    with sqlite3.connect(spec["path"]) as conn:
        conn.execute("INSERT INTO run_validations (run_id, operator_initials, validated_at_utc, comment) VALUES (1, 'XX', '2026-01-02', '')")
    revised = sources(spec, profile)
    assert revised["included_count"] == 602 and revised["excluded"][0]["reasons"] == ["validation_ambiguous"]
    assert revised["source_token"] != captured["source_token"]


def test_missing_or_mismatched_validation_is_excluded_individually(tmp_path: Path):
    spec, profile = fixture(tmp_path, count=1)
    add_run(spec, 2, validated=False)
    with sqlite3.connect(spec["path"]) as conn:
        conn.execute("UPDATE run_validations SET revision_id=7 WHERE run_id=1")
    captured = sources(spec, profile)
    reasons = {point["run_id"]: point["reasons"] for point in captured["excluded"]}
    assert reasons == {1: ["validation_binding_mismatch"], 2: ["validation_missing"]}


def test_source_and_configuration_recheck_reject_stale_before_append(tmp_path: Path):
    spec, profile = fixture(tmp_path)
    captured = sources(spec, profile)
    value = profile["snapshot"]
    value["name"] = "new configuration"
    save_profile(spec, value, expected_version_id=profile["version_id"], expected_inventory_version_id=1, context=context("change"))
    with pytest.raises(QCConflictError):
        open_lot(spec, profile_version_id=profile["version_id"], kit_lot="L1", expected_source_token=captured["source_token"], context=context("open-stale"))
    assert list_lots(spec) == []


def test_source_change_between_capture_and_lock_rolls_back(tmp_path: Path, monkeypatch):
    import src.qualitycontrol.store as store

    spec, profile = fixture(tmp_path)
    captured = sources(spec, profile)
    original = store._capture
    changed = False

    def racing(*args):
        nonlocal changed
        result = original(*args)
        if not changed:
            changed = True
            with sqlite3.connect(spec["path"]) as conn:
                conn.execute("UPDATE runs SET payload_json=? WHERE id=1", (json.dumps(payload(I1="43")),))
        return result

    monkeypatch.setattr(store, "_capture", racing)
    with pytest.raises(QCConflictError, match="während"):
        open_lot(spec, profile_version_id=profile["version_id"], kit_lot="L1", expected_source_token=captured["source_token"], context=context("race"))
    assert list_lots(spec) == []


def test_optional_manual_and_confirmed_frozen_sd_without_calculation(tmp_path: Path):
    spec, profile = fixture(tmp_path)
    opened = open_current(spec, profile)
    assert opened["snapshot"]["sd_references"] == {} and opened["snapshot"]["sd_evaluation"] == "unavailable"
    current = sources(spec, profile)
    manual = configure_lot(spec, opened["lot_key"], expected_version_id=opened["version_id"], profile_version_id=profile["version_id"],
        expected_source_token=current["source_token"], sd_references={"c1": {"kind": "manual", "value": "1.2"}}, context=context("manual"))
    baseline = configure_lot(spec, opened["lot_key"], expected_version_id=manual["version_id"], profile_version_id=profile["version_id"],
        expected_source_token=current["source_token"], sd_references={"c1": {"kind": "confirmed_baseline", "confirmed": True}}, context=context("baseline"))
    reference = baseline["snapshot"]["sd_references"]["c1"]
    assert reference["measurements"] == current["included"]
    assert "value" not in reference and "deferred" in reference["calculation"]
    history = list_lots(spec, include_history=True)
    assert history[1]["snapshot"]["sd_references"]["c1"]["value"] == "1.2"
    assert history[0]["snapshot"]["sd_references"] == {}


def test_close_requires_newer_lot_and_commits_exact_evidence_late_data_needs_reopen(tmp_path: Path):
    spec, profile = fixture(tmp_path)
    opened = open_current(spec, profile)
    add_run(spec, 3, lot="L2", data=payload("2026-02-01"))
    arguments = evidence_arguments(spec, profile, opened)
    closed = close_lot(spec, opened["lot_key"], **arguments)
    evidence = get_report_evidence(spec, lot_version_id=closed["version_id"])
    assert closed["state"] == "closed" and evidence["pdf_bytes"] == arguments["pdf_bytes"]
    assert evidence["model"] == arguments["analysis_model"]
    add_run(spec, 4, data=payload("2026-01-03"))
    assert close_lot(spec, opened["lot_key"], **arguments) == closed
    current = sources(spec, profile)
    assert current["source_token"] != closed["snapshot"]["source_manifest"]["source_token"]
    with pytest.raises(QCConflictError, match="Wiederöffnung"):
        configure_lot(spec, opened["lot_key"], expected_version_id=closed["version_id"], profile_version_id=profile["version_id"],
                      expected_source_token=current["source_token"], sd_references={}, context=context("late-config"))
    with pytest.raises(QCConfigurationError, match="Grund"):
        reopen_lot(spec, opened["lot_key"], expected_version_id=closed["version_id"], expected_source_token=current["source_token"], context=context("missing-reason"))
    reopened = reopen_lot(spec, opened["lot_key"], expected_version_id=closed["version_id"], expected_source_token=current["source_token"], context=context("reopen", "Späte Messung prüfen"))
    assert reopened["state"] == "open" and reopened["predecessor_id"] == closed["version_id"]
    assert get_report_evidence(spec, lot_version_id=closed["version_id"])["pdf_bytes"] == evidence["pdf_bytes"]
    assert get_lot(spec, opened["lot_key"])["snapshot"]["source_manifest"]["population_count"] == 3


def test_evidence_insert_failure_leaves_lot_open_and_history_unchanged(tmp_path: Path, monkeypatch):
    import src.qualitycontrol.store as store

    spec, profile = fixture(tmp_path)
    opened = open_current(spec, profile)
    add_run(spec, 3, lot="L2", data=payload("2026-02-01"))
    arguments = evidence_arguments(spec, profile, opened)
    original = store._append_lot

    def interrupted(*args):
        original(*args)
        raise RuntimeError("synthetic publish interruption")

    monkeypatch.setattr(store, "_append_lot", interrupted)
    with pytest.raises(RuntimeError, match="interruption"):
        close_lot(spec, opened["lot_key"], **arguments)
    assert get_lot(spec, opened["lot_key"]) == opened
    assert len(list_lots(spec, include_history=True)) == 1
    with sqlite3.connect(spec["path"]) as conn:
        assert conn.execute("SELECT count(*) FROM qc_report_evidence").fetchone()[0] == 0


def test_no_write_source_and_lot_browsing(tmp_path: Path):
    spec, profile = fixture(tmp_path)
    path = Path(spec["path"])
    before = path.read_bytes(), path.stat().st_mtime_ns
    sources(spec, profile)
    list_lots(spec, include_history=True)
    get_inventory(spec, include_history=True)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize("minimum,maximum,reasons", [
    ("31", "49", {"manufacturer_min_conflict", "manufacturer_max_conflict"}),
    ("30.0", "50.00", set()),
    ("51", "50", {"manufacturer_limits_reversed"}),
])
def test_p2_source_manifest_checks_decimal_manufacturer_limits_without_losing_raw_evidence(tmp_path, minimum, maximum, reasons):
    spec, profile = fixture(tmp_path, count=0)
    add_run(spec, 1, data=payload("2026-01-01"))
    add_run(spec, 2, data=payload("2026-01-02", N1=minimum, X1=maximum))
    source = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1")
    assert source["manifest_version"] == "qc-sources-v3"
    assert source["population_count"] == 2
    assert {point["run_id"]: point["raw"]["MIN"] for point in source["included"] + source["excluded"]} == {1: "30", 2: minimum}
    actual = {reason for point in source["included"] for reason in point["feature_reasons"].get("manufacturer", [])}
    assert actual == reasons
    assert source["included_count"] == 2 and not source["excluded"]
    assert analyze_lot(source, {}).to_dict()["computed_series"][0]["descriptive"]["n"] == 2


def test_p2_conflict_is_local_to_its_level_and_keeps_existing_exclusion_reasons(tmp_path):
    spec, old = fixture(tmp_path, count=0)
    value = copy.deepcopy(old["snapshot"])
    second = copy.deepcopy(value["controls"][0])
    second.update(control_id="c2", name="Zweites Level", fields={"IST": "I2", "SOLL": "S2", "MIN": "N2", "MAX": "X2"})
    value["controls"].append(second)
    profile = save_profile(spec, value, expected_version_id=old["version_id"], expected_inventory_version_id=1, context=context("p2-second-level"))
    for index, minimum in ((1, "30"), (2, "31"), (3, "32")):
        add_run(spec, index, validated=index != 3, data=payload(f"2026-01-{index:02d}", N1=minimum, I2="200", S2="200", N2="160", X2="240"))
    source = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1")
    assert {point["control_id"] for point in source["included"]} == {"c1", "c2"}
    assert source["included_count"] == 4
    assert all("validation_missing" in point["reasons"] for point in source["excluded"] if point["run_id"] == 3)
    result = analyze_lot(source, {}).to_dict()
    assert [row["included_count"] for row in result["computed_series"]] == [2, 2]
    assert not result["computed_series"][0]["limits"]["manufacturer"]["available"]
    assert result["computed_series"][1]["limits"]["manufacturer"]["available"]
    assert result["computed_series"][1]["qmma"]["value"] == "0"


def usage_snapshot(spec, profile):
    from src.qualitycontrol.api import get_lot_chronology
    return get_lot_chronology(spec, profile_version_id=profile["version_id"])


def usage_lots(spec, profile):
    return {row["kit_lot"]: row for row in usage_snapshot(spec, profile).to_dict()["lots"]}


def test_usage_overlap_later_unvalidated_bad_qc_and_unknown_third_lot_are_independent(tmp_path):
    spec, profile = fixture(tmp_path, count=0)
    for index, lot, date, valid, actual in ((1, "A", "2026-01-02", True, "42"), (2, "A", "2026-01-03", True, "42"),
        (3, "B", "2026-01-01", True, "42"), (4, "B", "2026-01-04", False, "unlesbar"), (5, "C", "unlesbar", False, "42")):
        add_run(spec, index, lot=lot, data=payload(date, I1=actual), validated=valid)
    usage = usage_lots(spec, profile)
    assert usage["A"]["close_available"] and {row["run_id"] for row in usage["A"]["witnesses"]} == {4}
    assert usage["A"]["last_usage"]["display"] == "2026-01-03"
    assert not usage["C"]["last_usage_reliable"] and not usage["B"]["close_available"]
    source = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="B")
    assert source["excluded_count"] == 1 and source["included_count"] == 1
    assert {"validation_missing", "ist_invalid"}.issubset(source["excluded"][0]["reasons"])


@pytest.mark.parametrize("dated,expected", [(False, False), (True, False)])
def test_usage_equal_day_or_exact_timestamp_has_no_import_or_id_tiebreaker(tmp_path, dated, expected):
    spec, profile = fixture(tmp_path, count=0)
    if dated:
        value = copy.deepcopy(profile["snapshot"])
        value["measurement_date_format"] = "%Y-%m-%dT%H:%M:%S"
        profile = save_profile(spec, value, expected_version_id=profile["version_id"], expected_inventory_version_id=1, context=context("usage-seconds"))
    for index, lot in ((1, "A"), (2, "B")):
        add_run(spec, index, lot=lot, data=payload("2026-01-04T12:00:00" if dated else "2026-01-04"))
    usage = usage_lots(spec, profile)
    assert all(row["close_available"] is expected for row in usage.values())
    assert all(row["last_usage"]["precision"] == ("seconds" if dated else "day") for row in usage.values())
    if not dated:
        assert all("00:00" not in row["last_usage"]["display"] for row in usage.values())


def test_usage_partial_order_three_lots_old_import_and_reuse_change_only_read_only_offers(tmp_path):
    spec, profile = fixture(tmp_path, count=0)
    for index, lot, date in ((1, "A", "2026-01-03"), (2, "B", "2026-01-04"), (3, "C", "2026-01-04")):
        add_run(spec, index, lot=lot, data=payload(date))
    before = usage_snapshot(spec, profile)
    usage = usage_lots(spec, profile)
    assert {row["kit_lot"] for row in usage["A"]["witnesses"]} == {"B", "C"}
    assert not usage["B"]["close_available"] and not usage["C"]["close_available"]
    add_run(spec, 4, lot="A", data=payload("2026-01-01"))
    after = usage_snapshot(spec, profile)
    assert after.snapshot_sha256 != before.snapshot_sha256
    assert usage_lots(spec, profile)["A"]["last_usage"] == usage["A"]["last_usage"]
    add_run(spec, 5, lot="A", data=payload("2026-01-05"))
    latest = usage_lots(spec, profile)
    assert not latest["A"]["close_available"] and latest["B"]["close_available"] and latest["C"]["close_available"]
    assert list_lots(spec) == []


def test_existing_profile_live_capture_keeps_statistics_with_missing_clock_target_and_limits(tmp_path):
    spec, old = fixture(tmp_path, count=0)
    profile = time_profile(spec, old)
    add_run(spec, 1, lot="A", data=payload("2026-01-03", TIME="13:00"))
    add_run(spec, 2, lot="B", data=payload("2026-01-04", TIME="24:00", S1=None, N1=None, X1=None))
    add_run(spec, 3, lot="B", data=payload("2026-01-04", TIME="14:05", I1="44", S1=None))
    usage = usage_lots(spec, profile)
    assert usage["A"]["close_available"] and usage["B"]["last_usage"]["precision"] == "day"
    assert usage["B"]["last_usage"]["display"] == "2026-01-04"
    assert "measurement_time_invalid" in usage["B"]["reasons"]
    source = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="B")
    assert source["manifest_version"] == "qc-sources-v3" and source["included_count"] == 2 and not source["excluded"]
    point = next(point for point in source["included"] if point["run_id"] == 2)
    assert point["measurement"]["time"] is None and point["feature_reasons"]["time"] == ["measurement_time_invalid"]
    series = analyze_lot(source, {}).to_dict()["computed_series"][0]
    assert series["descriptive"]["n"] == 2 and series["descriptive"]["mean"]["value"] == "43"
    assert not series["qmma"]["available"] and series["function_counts"]["qmma"] == 0
    assert series["limits"]["manufacturer"]["available"] and series["function_counts"]["manufacturer"] == 1
    assert source["profile_snapshot"]["measurement_time_format"] == "%H:%M"
    assert get_profile(spec, profile["version_id"]) == profile


@pytest.mark.parametrize("change", ["qc_only", "lot", "time"])
def test_usage_pending_revisions_preserve_possible_identities_without_selecting_candidate(tmp_path, monkeypatch, change):
    import src.qualitycontrol.sources as owner
    spec, profile = fixture(tmp_path, count=0)
    data = payload("2026-01-04")
    candidate = copy.deepcopy(data)
    candidate["I1"] = "unlesbar"
    if change == "time":
        candidate["DATE"] = "2026-01-05"
    row = {"id": 1, "device_id": "dev", "assay_key": "A", "lot_id": "A", "payload": payload("2026-01-03"), "selection_token": "original:1"}
    pending = {"id": 2, "device_id": "dev", "assay_key": "A", "lot_id": "B", "payload": data, "selection_token": "original:2|pending:1",
        "pending_revision": {"revision_id": 1, "result": {"lot_id": "C" if change == "lot" else "B", "payload": candidate}}}
    monkeypatch.setattr(owner, "list_result_runs", lambda *args, **kwargs: {"runs": [row, pending]})
    usage = usage_lots(spec, profile)
    assert usage["A"]["close_available"] is (change == "qc_only")
    if change == "lot":
        assert set(usage) == {"A", "B", "C"}
        assert not usage["B"]["last_usage_reliable"] and not usage["C"]["last_usage_reliable"]
    snapshot = usage_snapshot(spec, profile).to_dict()
    assert snapshot["runs"][1]["selection_token"] == "original:2|pending:1"
    assert snapshot["runs"][1]["determinate"] is (change == "qc_only")


def test_usage_all_more_than_500_rows_exact_lot_and_stable_device_assay_scope(tmp_path):
    spec, profile = fixture(tmp_path, count=0)
    inventory = get_inventory(spec)
    registered = copy.deepcopy(inventory["snapshot"])
    registered["devices"].append({"device_id": "other-device", "display_name": "Anderer bestätigter Bestandsplatz"})
    save_inventory(spec, registered, expected_version_id=inventory["version_id"], context=context("register-other-scope"))
    with sqlite3.connect(spec["path"]) as conn:
        conn.executemany("INSERT INTO runs VALUES (?, '', ?, ?, ?, ?, ?, '2026-01-01')", [
            (index, f"synthetic-{index}.pdf", "OTHER" if index == 504 else "A", " A " if index == 503 else ("B" if index == 502 else "A"),
             "other-device" if index == 505 else "dev", json.dumps(payload("2026-01-04" if index == 502 else "2026-01-03"))) for index in range(1, 506)])
    snapshot = usage_snapshot(spec, profile)
    assert len(snapshot.to_dict()["runs"]) == 503
    assert set(usage_lots(spec, profile)) == {"A", "B", " A "}
    assert usage_lots(spec, profile)["A"]["close_available"]


def test_usage_unknown_target_date_prevents_false_oldest_and_conflicting_profile_times_are_visible(tmp_path):
    spec, profile = fixture(tmp_path, count=0)
    add_run(spec, 1, lot="A", data=payload("unlesbar"))
    add_run(spec, 2, lot="B", data=payload("2026-01-04"))
    assert not usage_lots(spec, profile)["A"]["close_available"]
    assert not usage_lots(spec, profile)["A"]["last_usage_reliable"]
    value = copy.deepcopy(profile["snapshot"])
    value.update(profile_id="p2", measurement_date_field="OTHER_DATE")
    save_profile(spec, value, expected_version_id=0, expected_inventory_version_id=1, context=context("usage-other-mapping"))
    add_run(spec, 3, lot="C", data=payload("2026-01-05", OTHER_DATE="2026-01-06"))
    assert "profile_time_conflict" in usage_lots(spec, profile)["C"]["reasons"]


@pytest.mark.parametrize("format_string,raw,precision,expected", [
    ("%Y-%m-%d %S", "2026-01-03 45", "day", "2026-01-03"),
    ("%Y-%m-%d %H:%S", "2026-01-03 14:45", "hours", "2026-01-03 14"),
    ("%Y-%m-%d %H:%M", "2026-01-03 14:35", "minutes", "2026-01-03 14:35"),
])
def test_usage_only_contiguous_explicit_clock_components_define_precision(tmp_path, format_string, raw, precision, expected):
    spec, old = fixture(tmp_path, count=0)
    value = copy.deepcopy(old["snapshot"])
    value["measurement_date_format"] = format_string
    profile = save_profile(spec, value, expected_version_id=old["version_id"], expected_inventory_version_id=1, context=context("usage-unusual-format"))
    add_run(spec, 1, lot="A", data=payload(raw))
    interval = usage_lots(spec, profile)["A"]["last_usage"]
    assert interval["precision"] == precision and interval["display"] == expected
    width = {"day": 86_400_000_000, "hours": 3_600_000_000, "minutes": 60_000_000}[precision]
    assert interval["upper_exclusive"] - interval["lower"] == width
    assert interval["lower"] % width == 0


def test_usage_unreadable_revision_identity_prevents_other_lots_false_closure(tmp_path, monkeypatch):
    import src.qualitycontrol.sources as owner
    spec, profile = fixture(tmp_path, count=0)
    rows = [{"id": index, "device_id": "dev", "assay_key": "A", "lot_id": lot,
        "payload": payload(date), "selection_token": f"original:{index}"} for index, lot, date in
        ((1, "A", "2026-01-03"), (2, "B", "2026-01-04"), (3, "C", "2026-01-01"))]
    rows[2]["revision_error"] = "Unlesbare Ergebnishistorie"
    monkeypatch.setattr(owner, "list_result_runs", lambda *args, **kwargs: {"runs": rows})
    snapshot = usage_snapshot(spec, profile).to_dict()
    assert snapshot["unassigned_run_ids"] == [3]
    assert all(not row["close_available"] for row in snapshot["lots"])
    assert "usage_identity_unassigned" in next(row for row in snapshot["lots"] if row["kit_lot"] == "A")["reasons"]
