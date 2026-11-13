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
    assert captured["included"][0]["measured_at"] == "2026-01-01T08:00:00"
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
    assert not captured["included"] and captured["excluded"][0]["measured_at"] is None
    assert captured["excluded"][0]["reasons"] == [reason]
    assert captured["population"][0]["measurement_time_raw"] == raw and captured["start_date"] is None


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
    assert current["excluded"][0]["measured_at"] is None and result["computed_series"][0]["qmma"]["available"]
    latest = next(run for run in result["analytical_runs"] if run["analytical_run_id"] == "stored-run:1")
    finding = next(item for item in latest["findings"] if item["rule"] == "4_1s")
    assert finding["status"] == "unavailable" and finding["reason"] == "measurement_order_unavailable"


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
    model = {"source_manifest": manifest, "sd_references": lot["snapshot"]["sd_references"], "algorithm_id": "synthetic-algorithm-v1", "renderer_id": "synthetic-renderer-v1"}
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
    assert "measurement_date_invalid" in captured["excluded"][0]["reasons"]


def test_target_and_unit_conflicts_need_clarification(tmp_path: Path):
    spec, profile = fixture(tmp_path, count=0)
    add_run(spec, 1)
    add_run(spec, 2, data=payload(S1="41", UNIT="other"))
    captured = sources(spec, profile)
    assert captured["included"] == []
    assert all({"target_conflict", "unit_conflict"}.issubset(point["reasons"]) for point in captured["excluded"])


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
