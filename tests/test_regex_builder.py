from __future__ import annotations

from src.rulesuite.api import build_regex_from_builder_spec, suggest_builder_spec_from_selection, test_regex


def test_builder_extracts_pcq_range_between_repeated_unit_markers() -> None:
    line = "25-OH Vitamin D PCQ2 0013230223 261126 38,6 ng/ml 27,0-50,2 ng/ml"
    spec = {
        "line_contains": "PCQ2",
        "left_marker": "ng/ml",
        "left_marker_occurrence": "1",
        "right_marker": "ng/ml",
        "right_marker_occurrence": "2",
        "value_type": "range",
        "expected_value": "27,0-50,2",
    }

    out = build_regex_from_builder_spec(spec)
    hit = test_regex(line, out["regex"])

    assert hit["matched"] is True
    assert hit["value"] == "27,0-50,2"
    assert "38,6" not in out["regex"]
    assert "0013230223" not in out["regex"]


def test_builder_suggests_pcq_range_spec_from_selection() -> None:
    line = "25-OH Vitamin D PCQ2 0013230223 261126 38,6 ng/ml 27,0-50,2 ng/ml"
    selected = "27,0-50,2"
    start = line.index(selected)

    out = suggest_builder_spec_from_selection(line, selected, selection_start=start, selection_end=start + len(selected), line_index=9)
    spec = out["spec"]

    assert spec["line_contains"] == "PCQ2"
    assert spec["left_marker"] == "ng/ml"
    assert spec["left_marker_occurrence"] == "1"
    assert spec["right_marker"] == "ng/ml"
    assert spec["right_marker_occurrence"] == "2"
    assert spec["value_type"] == "range"
    assert spec["line_index"] == "9"


def test_builder_same_line_decimal_does_not_capture_serial_or_expiry() -> None:
    line = "25-OH Vitamin D S5 0013200223 261126 0,722 O.D. >0,100 O.D."
    spec = {
        "line_contains": "S5",
        "right_marker": "O.D.",
        "right_marker_occurrence": "1",
        "value_type": "decimal",
    }

    out = build_regex_from_builder_spec(spec)
    hit = test_regex(line, out["regex"])

    assert hit["matched"] is True
    assert hit["value"] == "0,722"
    assert "0013200223" not in out["regex"]
    assert "261126" not in out["regex"]


def test_builder_line_index_is_search_from_not_regex_context() -> None:
    out = build_regex_from_builder_spec({"line_index": "12", "value_type": "decimal"})

    assert out["regex"] == r"(\d+(?:[\.,]\d+)?)"
    assert out["proposed_search_from"] == {"line": 12}
    assert "line_index_unstable_hint" in out["warnings"]
    assert "line_index_used_as_search_from_only" in out["warnings"]


def test_builder_search_anchor_after_literal_is_escaped() -> None:
    out = build_regex_from_builder_spec(
        {
            "search_anchor_mode": "after",
            "search_anchor": "O.D.",
            "search_anchor_is_regex": False,
            "value_type": "decimal",
        }
    )

    assert out["proposed_search_from"] == {"after": r"O\.D\."}


def test_builder_search_anchor_after_regex_is_raw() -> None:
    out = build_regex_from_builder_spec(
        {
            "search_anchor_mode": "after",
            "search_anchor": r"Validationskriterien|Validierungskriterien",
            "search_anchor_is_regex": True,
            "value_type": "decimal",
        }
    )

    assert out["proposed_search_from"] == {"after": r"Validationskriterien|Validierungskriterien"}


def test_builder_search_anchor_after_missing_warns() -> None:
    out = build_regex_from_builder_spec({"search_anchor_mode": "after", "value_type": "decimal"})

    assert out["proposed_search_from"] is None
    assert "search_anchor_missing" in out["warnings"]


def test_builder_search_anchor_line_uses_line_index_with_stability_warning() -> None:
    out = build_regex_from_builder_spec(
        {
            "search_anchor_mode": "line",
            "line_index": "4",
            "line_contains": "PCQ1",
            "value_type": "decimal",
        }
    )

    assert out["proposed_search_from"] == {"line": 4}
    assert "line_index_unstable_hint" in out["warnings"]


def test_builder_literal_marker_is_escaped_and_regex_marker_can_be_raw() -> None:
    literal = build_regex_from_builder_spec({"line_contains": "S5", "right_marker": "O.D.", "value_type": "decimal"})
    raw = build_regex_from_builder_spec(
        {"line_contains": "PCQ2", "right_marker": r"(?:ng/ml|IU/ml)", "right_marker_is_regex": True, "value_type": "range"}
    )

    assert r"O\.D\." in literal["regex"]
    assert r"(?:ng/ml|IU/ml)" in raw["regex"]


def test_builder_decimal_value_max_len_skips_long_numeric_candidates() -> None:
    line = "Anti-MPO IgG PCQ1 0013290324 261208 112 RU/ml 78-146 RU/ml"
    spec = {
        "line_contains": "PCQ1",
        "value_type": "decimal",
        "value_max_len": "5",
    }

    out = build_regex_from_builder_spec(spec)
    hit = test_regex(line, out["regex"])

    assert hit["matched"] is True
    assert hit["value"] == "112"


def test_builder_decimal_value_length_does_not_match_suffix_of_long_number() -> None:
    line = "Marker 123456 78"
    out = build_regex_from_builder_spec({"line_contains": "Marker", "value_type": "decimal", "value_max_len": "5"})
    hit = test_regex(line, out["regex"])

    assert hit["matched"] is True
    assert hit["value"] == "78"


def test_builder_decimal_value_length_with_right_marker() -> None:
    line = "Anti-MPO IgG PCQ1 0013290324 261208 112 RU/ml 78-146 RU/ml"
    spec = {
        "line_contains": "PCQ1",
        "right_marker": "RU/ml",
        "right_marker_occurrence": "1",
        "value_type": "decimal",
        "value_max_len": "5",
    }

    out = build_regex_from_builder_spec(spec)
    hit = test_regex(line, out["regex"])

    assert hit["matched"] is True
    assert hit["value"] == "112"


def test_builder_token_value_length_limits_complete_token() -> None:
    line = "Marker abcdef good xx"
    out = build_regex_from_builder_spec(
        {"line_contains": "Marker", "value_type": "token", "value_min_len": "3", "value_max_len": "4"}
    )
    hit = test_regex(line, out["regex"])

    assert hit["matched"] is True
    assert hit["value"] == "good"


def test_builder_value_length_supports_only_min_and_only_max() -> None:
    min_only = build_regex_from_builder_spec({"value_type": "decimal", "value_min_len": "2"})
    min_hit = test_regex("A 1 12", min_only["regex"])
    assert min_hit["matched"] is True
    assert min_hit["value"] == "12"

    max_only = build_regex_from_builder_spec({"value_type": "decimal", "value_max_len": "2"})
    max_hit = test_regex("A 123 45", max_only["regex"])
    assert max_hit["matched"] is True
    assert max_hit["value"] == "45"


def test_builder_value_length_invalid_range_keeps_default_capture() -> None:
    out = build_regex_from_builder_spec({"value_type": "decimal", "value_min_len": "6", "value_max_len": "2"})

    assert out["capture"] == r"(\d+(?:[\.,]\d+)?)"
    assert "value_length_range_invalid" in out["warnings"]


def test_builder_value_length_ignored_for_range() -> None:
    out = build_regex_from_builder_spec({"value_type": "range", "value_min_len": "2", "value_max_len": "5"})

    assert out["capture"] == r"(\d+(?:[\.,]\d+)?\s*-\s*\d+(?:[\.,]\d+)?)"
    assert "length_ignored_for_value_type" in out["warnings"]


def test_builder_suggests_ru_per_ml_as_right_marker() -> None:
    line = "Anti-MPO IgG PCQ1 0013290324 261208 112 RU/ml 78-146 RU/ml"
    selected = "112"
    start = line.index(selected)

    out = suggest_builder_spec_from_selection(line, selected, selection_start=start, selection_end=start + len(selected), line_index=4)
    spec = out["spec"]

    assert spec["line_contains"] == "PCQ1"
    assert spec["right_marker"] == "RU/ml"
    assert spec["right_marker_occurrence"] == "1"
