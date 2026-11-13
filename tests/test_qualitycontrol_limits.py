"""Independent P2 vectors for manufacturer and single-value percentage limits."""
from __future__ import annotations

import copy
import itertools
import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.qualitycontrol.api import QCAnalysis, analyze_lot
from src.qualitycontrol.model import content_hash
from test_qualitycontrol_analysis import manifest, analyzed, manual


def limit_manifest(values, *, percent="10", enabled=True, minimum="80", maximum="120", **kwargs):
    source = manifest(values, **kwargs)
    source["manifest_version"] = "qc-sources-v2"
    source["profile_snapshot"].update(single_value_limits_enabled=enabled, single_value_limit_percent=percent if enabled else None)
    for rows in (source["included"], source["population"]):
        for index, point in enumerate(rows):
            for key, value in (("MIN", minimum), ("MAX", maximum)):
                raw = str(value[index] if isinstance(value, list) else value)
                point["raw"][key] = point["parsed"][key] = raw
    retoken(source)
    return source


def retoken(source):
    source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})


def test_percentage_limits_need_no_sd_and_never_remove_the_112_from_qmma():
    source = limit_manifest(["100", "100", "100", "112"], targets="100")
    before = copy.deepcopy(source)
    result = analyze_lot(source, {}).to_dict()
    series = result["computed_series"][0]
    assert (result["analysis_model_version"], result["algorithm_id"], result["renderer_id"]) == (3, "arev2-qc-analysis-v4", "arev2-qc-pdf-v4")
    assert series["qmma"]["n"] == 4 and series["qmma"]["value"] == series["qmma"]["relative_percent"] == "6"
    assert series["limits"]["manufacturer"] == {"available": True, "reason": "", "lower": "80", "upper": "120"}
    assert series["limits"]["single_value"] == {"enabled": True, "available": True, "reason": "", "percent": "10", "lower": "90", "upper": "110"}
    assert result["points"][-1]["eligible"] and result["points"][-1]["limit_findings"]["single_value"] == {"status": "exceeded", "reason": "", "direction": "above"}
    assert result["points"][-1]["limit_findings"]["manufacturer"]["status"] == "within_limit"
    assert not series["sd"]["available"] and not series["bands"]
    assert [(line["kind"], line["value"]) for line in series["chart"]["reference_lines"]] == [
        ("target", "100"), ("mean", "103"), ("manufacturer", "80"), ("manufacturer", "120"), ("single_value", "90"), ("single_value", "110")]
    assert Decimal(series["chart"]["y_range"][0]) < 80 < 120 < Decimal(series["chart"]["y_range"][1])
    assert source == before == result["source_manifest"]


def test_each_level_uses_its_own_target_with_one_shared_profile_percent():
    source = limit_manifest(["100", "200", "111", "220"], targets=["100", "200", "100", "200"], controls=["c1", "c2", "c1", "c2"], minimum=["80", "160", "80", "160"], maximum=["120", "240", "120", "240"])
    result = analyze_lot(source, {}).to_dict()
    assert [(row["limits"]["single_value"]["lower"], row["limits"]["single_value"]["upper"]) for row in result["computed_series"]] == [("90", "110"), ("180", "220")]
    by_run = {point["run_id"]: point for point in result["points"]}
    assert by_run[3]["limit_findings"]["single_value"]["status"] == "exceeded"
    assert by_run[4]["limit_findings"]["single_value"]["status"] == "within_limit"


@pytest.mark.parametrize("actual,expected", [("90", "within_limit"), ("110", "within_limit"),
    ("89.999999999999999999999999999999999999999999999999", "exceeded"),
    ("110.000000000000000000000000000000000000000000000001", "exceeded")])
def test_percentage_boundary_equality_and_unrounded_decisions(actual, expected):
    result = analyze_lot(limit_manifest([actual], targets="100"), {}).to_dict()
    assert result["points"][0]["limit_findings"]["single_value"]["status"] == expected


@pytest.mark.parametrize("actual,manufacturer,single", [("90", "within_limit", "within_limit"),
    ("110", "within_limit", "within_limit"), ("111", "exceeded", "within_limit"),
    ("126", "exceeded", "exceeded")])
def test_manufacturer_equality_and_percentage_assessment_are_separate(actual, manufacturer, single):
    result = analyze_lot(limit_manifest([actual], targets="100", percent="25", minimum="90", maximum="110"), {}).to_dict()
    point = result["points"][0]
    assert point["limit_findings"]["manufacturer"]["status"] == manufacturer
    assert point["limit_findings"]["single_value"]["status"] == single
    assert point["eligible"] and result["computed_series"][0]["qmma"]["n"] == 1


def test_percentage_precision_budget_includes_the_full_configured_p():
    tail = "0" * 120 + "1"
    percent, upper = "10." + tail, "110." + tail
    result = analyze_lot(limit_manifest([upper], targets="100", percent=percent), {}).to_dict()
    assert result["computed_series"][0]["limits"]["single_value"]["upper"] == upper
    assert result["points"][0]["limit_findings"]["single_value"]["status"] == "within_limit"
    beyond = "110." + "0" * 120 + "2"
    result = analyze_lot(limit_manifest([beyond], targets="100", percent=percent), {}).to_dict()
    assert result["points"][0]["limit_findings"]["single_value"]["status"] == "exceeded"


@pytest.mark.parametrize("target,percent,lower,upper,reason", [
    ("100", "150", "-50", "250", ""), ("0", "10", "0", "0", ""),
    ("-100", "10", None, None, "percentage_limits_reversed"), ("-100", "0", "-100", "-100", ""),
    ("100", "0", "100", "100", "")])
def test_large_percent_zero_and_negative_targets_are_explicit(target, percent, lower, upper, reason):
    result = analyze_lot(limit_manifest([target], targets=target, percent=percent), {}).to_dict()
    series = result["computed_series"][0]
    limit = series["limits"]["single_value"]
    assert (limit["lower"], limit["upper"], limit["reason"]) == (lower, upper, reason)
    assert limit["available"] is (not reason)
    assert series["qmma"]["available"]
    if target == "0":
        assert series["qmma"]["relative_percent"] is None


def test_new_percentage_switch_does_not_reuse_qmma_threshold_or_change_westgard():
    source = limit_manifest(["100", "112"], targets="100", enabled=False)
    source["profile_snapshot"]["relative_limit_percent"] = "1"
    retoken(source)
    old = analyzed(source, manual(value="1")).to_dict()
    source["profile_snapshot"].update(single_value_limits_enabled=True, single_value_limit_percent="10")
    retoken(source)
    new = analyzed(source, manual(value="1")).to_dict()
    assert old["computed_series"][0]["limits"]["single_value"]["reason"] == "not_configured"
    assert old["analytical_runs"] == new["analytical_runs"]
    assert old["computed_series"][0]["qmma"] == new["computed_series"][0]["qmma"]
    assert [point["z"] for point in old["points"]] == [point["z"] for point in new["points"]]
    assert new["points"][-1]["limit_findings"]["single_value"]["status"] == "exceeded"


@pytest.mark.parametrize("minimum,maximum,reason", [(["30", "31"], ["50", "49"], "manufacturer_min_conflict"),
    (["30", "30"], ["50", "49"], "manufacturer_max_conflict")])
def test_defensive_analyzer_rejects_changing_manufacturer_limits_and_preserves_sources(minimum, maximum, reason):
    source = limit_manifest(["40", "40"], targets="40", minimum=minimum, maximum=maximum)
    result = analyze_lot(source, {}).to_dict()
    assert result["counts"]["analysis_included"] == 0
    assert all(reason in point["reasons"] for point in result["points"])
    assert not result["computed_series"][0]["limits"]["manufacturer"]["available"]
    assert result["source_manifest"] == source
    assert result["points"][1]["raw"]["MIN"] == minimum[1]


def test_defensive_analyzer_accepts_equivalent_scale_and_keeps_other_levels_usable():
    source = limit_manifest(["40", "40", "200"], targets=["40", "40", "200"], controls=["c1", "c1", "c2"],
        minimum=["30", "30.0", "160"], maximum=["50", "50.00", "240"])
    result = analyze_lot(source, {}).to_dict()
    assert [row["included_count"] for row in result["computed_series"]] == [2, 1]
    source["included"][1]["parsed"]["MIN"] = "31"
    retoken(source)
    result = analyze_lot(source, {}).to_dict()
    assert [row["included_count"] for row in result["computed_series"]] == [0, 1]
    assert result["computed_series"][1]["limits"]["single_value"]["lower"] == "180"


def test_defensive_analyzer_keeps_reversed_range_exclusion_and_other_reasons():
    source = limit_manifest(["40", "40"], targets="40", minimum=["51", "30"], maximum="50")
    source["included"][0]["reasons"] = ["validation_missing"]
    retoken(source)
    result = analyze_lot(source, {}).to_dict()
    assert result["points"][0]["reasons"] == ["validation_missing", "manufacturer_limits_reversed"]
    assert result["computed_series"][0]["qmma"]["n"] == 1


def test_only_explicit_model_version_tuples_are_supported_and_old_bytes_stay_frozen():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "qc_pre_p2_schema1_v2.json").read_text(encoding="utf-8"))
    old = QCAnalysis(fixture["model_json"], fixture["model_sha256"])
    assert old.is_supported and old.to_dict()["source_manifest"]["manifest_version"] == "qc-sources-v1"
    assert "reference_lines" not in old.to_dict()["computed_series"][0]["chart"]
    for version, algorithm, renderer in itertools.product((1, 2, 3), range(1, 5), range(1, 5)):
        synthetic = old.to_dict()
        synthetic.update(analysis_model_version=version, algorithm_id=f"arev2-qc-analysis-v{algorithm}", renderer_id=f"arev2-qc-pdf-v{renderer}")
        expected = (version == 1 and algorithm in (1, 2) and renderer in (1, 2)) or (version, algorithm, renderer) in {(2, 3, 3), (3, 4, 4)}
        assert QCAnalysis.freeze(synthetic).is_supported is expected
    assert (old.model_json, old.model_sha256) == (fixture["model_json"], fixture["model_sha256"])
