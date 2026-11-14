"""Independent numeric/classical reference vectors for pure P5 analysis."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from dataclasses import FrozenInstanceError
from datetime import datetime
from decimal import Decimal

import pytest

from src.qualitycontrol.api import QCAnalysis, QCConfigurationError, analyze_lot
from src.qualitycontrol.model import content_hash

RULES = ["1_2s", "1_3s", "2_2s", "R_4s", "4_1s", "10x"]


def manifest(values, *, targets="0", controls=None, dates=None, groups=None, units=None, enabled=None):
    controls = controls or ["c1"] * len(values)
    stable = list(dict.fromkeys(controls)) or ["c1"]
    if not isinstance(targets, list):
        targets = [targets] * len(values)
    points = []
    for index, (value, target, control) in enumerate(zip(values, targets, controls)):
        group = groups[index] if groups is not None else f"run:{index + 1}"
        point = {"run_id": index + 1, "revision_id": 0, "selection_id": None, "selection_token": f"original:{index + 1}",
            "validation_id": index + 100, "source_hash": f"synthetic-{index}", "control_id": control, "control_name": control,
            "raw": {"IST": str(value), "SOLL": str(target), "MIN": "-100", "MAX": "100"},
            "parsed": {"IST": str(value), "SOLL": str(target), "MIN": "-100", "MAX": "100"},
            "unit": "U", "unit_raw": units[index] if units else "U", "reasons": [],
            "measured_at": dates[index] if dates else f"2026-01-{index + 1:02d}T00:00:00", "analytical_run_id": group}
        points.append(point)
    profile = {"profile_id": "p1", "name": "Synthetisches Prüfprofil", "device_id": "dev", "assay_key": "A",
        "measurement_date_field": "DATE", "measurement_date_format": "%Y-%m-%d", "numeric_grammar": "decimal_dot",
        "qc_profile": "classic-six-v1", "enabled_rules": RULES if enabled is None else enabled,
        "controls": [{"control_id": value, "name": value, "unit": "U", "fields": {"IST": "IST", "SOLL": "SOLL", "MIN": "MIN", "MAX": "MAX"}} for value in stable],
        "unit": "U", "relative_enabled": True, "rili_applicable": True, "relative_limit_percent": "10", "guideline_reference": "2023-formula-reference"}
    result = {"manifest_version": "qc-sources-v1", "device_id": "dev", "assay_key": "A", "kit_lot": "L1",
        "store_path": "synthetic.sqlite3", "inventory_version_id": 1, "profile_version_id": 1, "profile_head_version_id": 1,
        "inventory_snapshot": {"devices": [{"device_id": "dev", "display_name": "Laborgerät", "serial_number": "SYNTHETIC-SN"}]},
        "profile_snapshot": profile, "included": points, "excluded": [], "population": copy.deepcopy(points),
        "included_count": len(points), "excluded_count": 0, "population_count": len(points),
        "start_date": min((point["measured_at"] for point in points), default=None), "order_is_explicit": False,
        "equal_time_order_unavailable": False}
    result["source_token"] = content_hash(result)
    return result


def manual(controls=("c1",), value="1"):
    return {control: {"kind": "manual", "value": value, "reference_id": f"sd-{control}"} for control in controls}


def reference_context(source, refs, *, origin=None):
    origin = origin or source
    profile = copy.deepcopy(origin["profile_snapshot"])
    return {"context_version": "qc-sd-origin-v1", **{key: source[key] for key in ("store_path", "device_id", "assay_key", "kit_lot")},
        "references": {identifier: {"reference_hash": content_hash(reference), "origin_profile_version_id": origin["profile_version_id"],
            "origin_profile_snapshot": profile, "origin_profile_hash": content_hash(profile)} for identifier, reference in refs.items()}}


def analyzed(source, refs, *, origin=None):
    return analyze_lot(source, refs, sd_reference_context=reference_context(source, refs, origin=origin))


def model(values, *, sd=True, **kwargs):
    source = manifest(values, **kwargs)
    refs = manual({point["control_id"] for point in source["included"]}) if sd else {}
    return analyzed(source, refs).to_dict()


def last_rule(result, rule):
    return next(value for value in result["analytical_runs"][-1]["findings"] if value["rule"] == rule)


@pytest.mark.parametrize("values,target,qmma,relative,n", [
    (["90", "110"], "100", "10", "10", 2), (["110"], "100", "10", "10", 1),
    (["-1", "1"], "0", "1", None, 2), ([], "100", None, None, 0),
])
def test_qmma_independent_of_sd_reference(values, target, qmma, relative, n):
    result = model(values, targets=target, sd=False)
    series = result["computed_series"][0]
    assert series["qmma"]["value"] == qmma and series["qmma"]["relative_percent"] == relative
    assert series["qmma"]["n"] == n
    assert series["sd"]["available"] is False and series["bands"] == []
    assert series["qmma"]["available"] == bool(values)


def test_qmma_and_sample_sd_use_different_denominators():
    source = manifest(["90", "100", "110"], targets="100")
    baseline = {"c1": {"kind": "confirmed_baseline", "confirmed": True, "measurements": copy.deepcopy(source["included"]),
        "reference_id": "frozen-baseline", "source_token": source["source_token"], "profile_version_id": 1,
        "calculation": "sample-sd-and-mean-deferred-to-p5"}}
    result = analyzed(source, baseline).to_dict()["computed_series"][0]
    assert abs(Decimal(result["qmma"]["value"]) ** 2 - Decimal(200) / 3) < Decimal("1e-24")
    assert result["sd"]["sd"] == "10" and result["sd"]["center"] == "100"


@pytest.mark.parametrize("values,expected", [(["90", "110"], "within_limit"), (["89.999", "110.001"], "exceeded"),
    (["110.000000000000000000000000000000000001"], "exceeded")])
def test_qmma_limit_is_strict_and_decided_before_display_rounding(values, expected):
    assert model(values, targets="100", sd=False)["computed_series"][0]["qmma"]["limit_status"] == expected


@pytest.mark.parametrize("values,targets,units", [(["90", "110"], ["100", "101"], None),
    (["90", "110"], "100", ["U", "other"]), (["negativ"], "100", None)])
def test_conflicting_or_qualitative_series_never_become_zero(values, targets, units):
    result = model(values, targets=targets, units=units, sd=False)["computed_series"][0]
    assert result["qmma"]["available"] is False and result["qmma"]["value"] is None


@pytest.mark.parametrize("z,warning,reject", [("2", False, False), ("2.0001", True, False), ("3", True, False), ("3.0001", True, True)])
@pytest.mark.parametrize("sign", [1, -1])
def test_classic_strict_threshold_equalities(z, warning, reject, sign):
    result = model([str(Decimal(z) * sign)])
    assert (last_rule(result, "1_2s")["status"] == "warning") is warning
    assert (last_rule(result, "1_3s")["status"] == "reject") is reject


def test_warning_checkbox_never_disables_structural_classic_trigger():
    result = model(["3.1"], enabled=["1_3s"])
    assert last_rule(result, "1_2s")["status"] == "disabled"
    assert last_rule(result, "1_3s")["status"] == "reject"
    assert last_rule(model(["3"], enabled=["1_3s"]), "1_3s")["status"] == "pass"


@pytest.mark.parametrize("rule,values,reject", [
    ("2_2s", ["2.1", "2.2"], True), ("2_2s", ["2.0", "2.2"], False),
    ("4_1s", ["1.1", "1.2", "1.3", "2.1"], True), ("4_1s", ["1.1", "1.0", "1.3", "2.1"], False),
    ("4_1s", ["1.1"] * 4, False), ("4_1s", ["2.1", "1.1", "1.2", "1.3"], False),
    ("10x", ["0.5"] * 9 + ["2.1"], True), ("10x", ["0.5"] * 10, False),
    ("10x", ["0.5"] * 4 + ["0"] + ["0.5"] * 4 + ["2.1"], False),
])
@pytest.mark.parametrize("sign", [1, -1])
def test_longitudinal_classic_reference_vectors_and_no_latched_trigger(rule, values, reject, sign):
    result = model([str(Decimal(value) * sign) for value in values])
    assert (last_rule(result, rule)["status"] == "reject") is reject


def test_nine_points_are_insufficient_for_10x():
    assert last_rule(model(["0.5"] * 8 + ["2.1"]), "10x")["status"] == "unavailable"


@pytest.mark.parametrize("values,reject", [(["2.1", "-2.1"], True), (["2.4", "-1.8"], False), (["2", "-2.1"], False)])
def test_r4_is_qualitative_inside_same_analytical_run(values, reject):
    result = model(values, controls=["c1", "c2"], groups=["same-run", "same-run"], dates=["2026-01-01T00:00:00"] * 2)
    assert (last_rule(result, "R_4s")["status"] == "reject") is reject


def test_r4_never_crosses_runs_even_on_same_calendar_date():
    for dates in (["2026-01-01T00:00:00"] * 2, ["2026-01-01T00:00:00", "2026-01-02T00:00:00"]):
        result = model(["2.1", "-2.2"], controls=["c1", "c2"], groups=["run-a", "run-b"], dates=dates)
        assert not any(finding["status"] == "reject" for run in result["analytical_runs"] for finding in run["findings"] if finding["rule"] == "R_4s")


def test_cross_control_normalization_uses_own_center_and_sd():
    source = manifest(["104.2", "979"], targets=["100", "1000"], controls=["c1", "c2"], groups=["same", "same"])
    result = analyzed(source, {"c1": {"kind": "manual", "value": "2"}, "c2": {"kind": "manual", "value": "10"}}).to_dict()
    assert [point["z"] for point in result["points"]] == ["2.1", "-2.1"]
    assert last_rule(result, "R_4s")["status"] == "reject"
    same_side = model(["2.1", "2.2"], controls=["c1", "c2"], groups=["same", "same"])
    assert last_rule(same_side, "2_2s")["status"] == "reject"


def test_whole_unordered_group_proof_does_not_choose_favorable_control_subset():
    controls = [f"c{number}" for number in range(5)]
    result = model(["2.1", "1.1", "1.1", "-0.1", "1.1"], controls=controls, groups=["same"] * 5)
    assert last_rule(result, "4_1s")["status"] != "reject"
    proven = model(["2.1", "1.1", "1.1", "1.1"], controls=controls[:4], groups=["same"] * 4)
    assert last_rule(proven, "4_1s")["status"] == "reject"
    pooled = model(["0.5"] * 9 + ["2.1"], controls=controls * 2, groups=["run-a"] * 5 + ["run-b"] * 5)
    assert last_rule(pooled, "10x")["status"] == "unavailable"


@pytest.mark.parametrize("timestamp", ["2026-01-02T00:00:00", "2026-01-02T13:24:17"])
def test_equal_time_measurements_are_history_barriers_and_chart_has_no_fake_connection(timestamp):
    result = model(["2.1", "0.1", "0.2", "2.2"], dates=["2026-01-01T00:00:00", timestamp, timestamp, "2026-01-03T00:00:00"])
    assert last_rule(result, "2_2s")["status"] == "unavailable"
    assert last_rule(result, "2_2s")["reason"] == "measurement_order_ambiguous"
    points = result["points"]
    assert points[1]["order_ambiguous"] and points[2]["order_ambiguous"]
    assert result["computed_series"][0]["segments"] == [[points[0]["point_key"]], [points[3]["point_key"]]]


def test_baseline_stays_frozen_and_exact_3sd_equality_is_not_13s():
    baseline = manifest(["90", "91", "92"], targets="100")
    reference = {"c1": {"kind": "confirmed_baseline", "confirmed": True, "measurements": baseline["included"], "reference_id": "frozen",
        "source_token": baseline["source_token"], "profile_version_id": 1, "calculation": "sample-sd-and-mean-deferred-to-p5"}}
    before = copy.deepcopy(reference)
    result = analyzed(manifest(["94"], targets="100"), reference).to_dict()
    series = result["computed_series"][0]
    assert series["sd"]["center"] == "91" and series["sd"]["sd"] == "1" and series["qmma"]["value"] == "6"
    assert result["points"][0]["z"] == "3" and last_rule(result, "1_3s")["status"] == "pass"
    grown = analyzed(manifest(["94", "1000"], targets="100"), reference).to_dict()
    assert grown["computed_series"][0]["sd"]["center"] == "91"
    assert reference == before == result["sd_references"]


@pytest.mark.parametrize("reference", [{"kind": "manual", "value": "0"}, {"kind": "manual", "value": "NaN"},
    {"kind": "confirmed_baseline", "confirmed": True, "measurements": []}])
def test_unusable_sd_is_unavailable_and_does_not_disable_qmma(reference):
    result = analyzed(manifest(["90", "110"], targets="100"), {"c1": reference}).to_dict()
    assert result["computed_series"][0]["qmma"]["value"] == "10"
    assert not result["computed_series"][0]["sd"]["available"]
    assert result["computed_series"][0]["bands"] == []
    assert last_rule(result, "1_3s")["status"] == "unavailable"


def test_analysis_is_immutable_and_preserves_exact_population_provenance():
    source = manifest(["1", "2"])
    original = copy.deepcopy(source)
    analysis = analyzed(source, manual())
    assert isinstance(analysis, QCAnalysis)
    with pytest.raises(FrozenInstanceError):
        analysis.model_json = "changed"
    first = analysis.to_dict()
    first["source_manifest"]["included"][0]["raw"]["IST"] = "999"
    assert analysis.to_dict()["source_manifest"] == original == source
    assert analysis.model_sha256 == content_hash(analysis.to_dict())
    source["included"][0]["parsed"]["IST"] = "999"
    with pytest.raises(QCConfigurationError, match="Prüfsumme"):
        analyzed(source, manual())


def test_known_unusable_observation_is_not_skipped_to_join_history():
    source = manifest(["2.1", "unlesbar", "2.2"])
    excluded = source["included"].pop(1)
    excluded["reasons"] = ["ist_invalid"]
    excluded["parsed"].pop("IST")
    source["excluded"] = [excluded]
    source["included_count"], source["excluded_count"] = 2, 1
    source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
    result = analyzed(source, manual()).to_dict()
    assert result["computed_series"][0]["qmma"]["n"] == 2
    assert last_rule(result, "2_2s")["status"] == "unavailable"
    assert last_rule(result, "2_2s")["reason"] == "history_value_unavailable"


@pytest.mark.parametrize("kind", ["manual", "confirmed_baseline"])
@pytest.mark.parametrize("change,reason", [("unit", "sd_unit_incompatible"), ("IST", "sd_parameter_incompatible"),
                                         ("numeric_grammar", "sd_parameter_incompatible")])
def test_sd_origin_defines_unit_and_measured_parameter_without_disabling_qmma(kind, change, reason):
    origin = manifest(["90", "91", "92"], targets="100")
    source = manifest(["94"], targets="100")
    source["profile_version_id"] = source["profile_head_version_id"] = 2
    if change == "unit":
        source["profile_snapshot"]["unit"] = source["profile_snapshot"]["controls"][0]["unit"] = "B"
        source["included"][0]["unit"] = source["included"][0]["unit_raw"] = "B"
    elif change == "IST":
        source["profile_snapshot"]["controls"][0]["fields"]["IST"] = "ANOTHER_MEASUREMENT"
    else:
        source["profile_snapshot"]["numeric_grammar"] = "decimal_comma"
    source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
    refs = manual()
    if kind == "confirmed_baseline":
        refs = {"c1": {"kind": kind, "confirmed": True, "measurements": origin["included"], "profile_version_id": 1}}
    before = copy.deepcopy(refs)
    result = analyzed(source, refs, origin=origin).to_dict()
    series = result["computed_series"][0]
    assert series["qmma"]["value"] == "6" and series["qmma"]["available"]
    assert series["sd"] == {"available": False, "reason": reason} and not series["bands"]
    assert result["points"][0]["z"] is None and last_rule(result, "1_3s")["status"] == "unavailable"
    assert refs == before == result["sd_references"] and result["source_manifest"] == source
    assert result["algorithm_id"] == "arev2-qc-analysis-v5"
    assert result["sd_reference_context"]["references"]["c1"]["origin_profile_snapshot"] == origin["profile_snapshot"]


@pytest.mark.parametrize("kind", ["manual", "confirmed_baseline"])
def test_compatible_profile_edits_and_manufacturer_limits_do_not_define_sd(kind):
    origin, source = manifest(["90", "91", "92"], targets="100"), manifest(["94"], targets="100")
    source["profile_version_id"] = source["profile_head_version_id"] = 2
    source["profile_snapshot"].update(name="Renamed", measurement_date_format="%d.%m.%Y", run_grouping_field="GROUP",
                                      relative_limit_percent="12", enabled_rules=["1_3s"])
    source["profile_snapshot"]["controls"][0]["fields"].update(SOLL="OTHER_TARGET", MIN="NEW_MIN", MAX="NEW_MAX")
    source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
    refs = manual() if kind == "manual" else {"c1": {"kind": kind, "confirmed": True,
        "measurements": origin["included"], "profile_version_id": 1}}
    result = analyzed(source, refs, origin=origin).to_dict()
    assert result["computed_series"][0]["sd"]["available"]
    assert result["computed_series"][0]["sd"]["center"] == ("100" if kind == "manual" else "91")


@pytest.mark.parametrize("context_problem", ["missing", "other-store", "tampered-profile", "different-reference"])
def test_unproven_sd_context_is_unavailable_not_a_guess(context_problem):
    source, refs = manifest(["94"], targets="100"), manual()
    context = reference_context(source, refs)
    if context_problem == "missing":
        context = None
    elif context_problem == "other-store":
        context["store_path"] = "other.sqlite3"
    elif context_problem == "tampered-profile":
        context["references"]["c1"]["origin_profile_snapshot"]["unit"] = "B"
    else:
        context["references"]["c1"]["reference_hash"] = "different"
    result = analyze_lot(source, refs, sd_reference_context=context).to_dict()
    assert result["computed_series"][0]["sd"] == {"available": False, "reason": "sd_origin_unavailable"}
    assert result["computed_series"][0]["qmma"]["value"] == "6"


@pytest.mark.parametrize("renderer", ["arev2-qc-pdf-v1", "arev2-qc-pdf-v2"])
def test_legacy_model_reader_never_adds_context_or_reinterprets_v1(renderer):
    # Synthetic compatibility variation of a genuine pre-P2 frozen model.
    fixture = json.loads((Path(__file__).parent / "fixtures" / "qc_pre_p2_schema1_v2.json").read_text(encoding="utf-8"))
    old = json.loads(fixture["model_json"])
    old["algorithm_id"] = "arev2-qc-analysis-v1"
    old["renderer_id"] = renderer
    old.pop("sd_reference_context")
    frozen = QCAnalysis.freeze(old)
    assert frozen.is_supported and frozen.to_dict() == old and "sd_reference_context" not in frozen.to_dict()
    assert frozen.model_sha256 == content_hash(old)
    unsupported = copy.deepcopy(old)
    unsupported["algorithm_id"] = "unknown-algorithm"
    assert not QCAnalysis.freeze(unsupported).is_supported


@pytest.mark.parametrize('values,target,mean,sd,cv', [
    (['100', '100', '100', '112'], '100', '103', '6', Decimal(600) / 103),
    (['60','63','63','62','63','61','62','62','57','58','60'], '63', '61', None, None),
    (['5', '5'], '5', '5', '0', Decimal(0)),
    (['-1', '1'], '0', '0', None, None),
    (['-3', '-1'], '-2', '-2', None, None),
    (['7'], '7', '7', None, None),
    ([], '7', None, None, None),
])
def test_p4_frozen_descriptive_uses_eligible_sample_not_reference_sd(values, target, mean, sd, cv):
    result = model(values, targets=target, sd=False)
    series = result['computed_series'][0]
    summary = series['descriptive']
    assert summary['version'] == 'qc-descriptive-v1' and summary['n'] == len(values)
    assert summary['mean']['value'] == mean
    assert summary['mean']['available'] is bool(values)
    assert summary['sample_sd']['available'] is (len(values) >= 2)
    if sd is not None:
        assert summary['sample_sd']['value'] == sd
    if cv is not None:
        assert abs(Decimal(summary['cv_percent']['value']) - cv) < Decimal('1e-24')
    assert summary['cv_percent']['available'] is (len(values) >= 2 and Decimal(mean) > 0)
    assert not series['sd']['available'] and series['bands'] == []
    assert any(line['kind'] == 'mean' and line['value'] == mean for line in series['chart']['reference_lines']) is bool(values)
    for point in result['points']:
        absolute = abs(Decimal(point['parsed']['IST']) - Decimal(target))
        assert Decimal(point['deviation']['absolute']['value']) == absolute
        assert point['deviation']['relative_percent']['available'] is (Decimal(target) > 0)
    if target == '63':
        assert abs(Decimal(summary['sample_sd']['value']) - Decimal('2.0493901531919196766')) < Decimal('1e-18')
        assert abs(Decimal(summary['cv_percent']['value']) - Decimal('3.3596559888392125846')) < Decimal('1e-18')


def test_p4_descriptive_cancellation_budget_and_excluded_outlier():
    offset = 10 ** 120
    source = manifest([str(offset), str(offset + 2), '99999999999999999999999999999999999'], targets=str(offset))
    excluded = source['included'].pop()
    excluded['reasons'] = ['validation_missing']
    source['excluded'].append(excluded)
    source['population'][-1]['reasons'] = ['validation_missing']
    source.update(included_count=2, excluded_count=1)
    source['source_token'] = content_hash({key: value for key, value in source.items() if key != 'source_token'})
    result = analyze_lot(source, {}).to_dict()
    summary = result['computed_series'][0]['descriptive']
    assert summary['n'] == 2 and summary['mean']['value'] == str(offset + 1)
    assert abs(Decimal(summary['sample_sd']['value']) - Decimal(2).sqrt()) < Decimal('1e-27')
    point = result['points'][-1]
    assert not point['eligible'] and not point['deviation']['absolute']['available']
    assert point['deviation']['relative_percent']['reason'] == 'point_ineligible'


@pytest.mark.parametrize('format_string,measured,precision,time', [
    ('%Y-%m-%d', '2026-11-13T00:00:00', 'day', None),
    ('%Y-%m-%d %H', '2026-11-13T12:00:00', 'hours', '12'),
    ('%Y-%m-%d %H:%M', '2026-11-13T12:34:00', 'minutes', '12:34'),
    ('%Y-%m-%d %H:%M:%S', '2026-11-13T12:34:56', 'seconds', '12:34:56'),
    ('%Y-%m-%d %S', '2026-11-13T00:00:56', 'day', None),
    ('%Y-%m-%d %H:%S', '2026-11-13T12:00:56', 'hours', '12'),
])
def test_p4_display_precision_is_frozen_contiguous_and_position_is_stable(format_string, measured, precision, time):
    source = manifest(['100'], targets='100', dates=[measured])
    source['profile_snapshot']['measurement_date_format'] = format_string
    source['population'][0]['measurement_date_raw'] = datetime.fromisoformat(measured).strftime(format_string)
    source['source_token'] = content_hash({key: value for key, value in source.items() if key != 'source_token'})
    result = analyze_lot(source, {}).to_dict()
    point = result['points'][0]
    assert point['position'] == 1
    assert point['measurement']['date'] == '2026-11-13'
    assert (point['measurement']['precision'], point['measurement']['time']) == (precision, time)
    assert result['computed_series'][0]['period'] == {'start_date':'2026-11-13','end_date':'2026-11-13','unknown_date_count':0}
    frozen = result['computed_series'][0]['chart']['points'][0]
    assert frozen['measurement'] == point['measurement'] and frozen['deviation'] == point['deviation']
