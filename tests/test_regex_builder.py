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
    assert "line_index_used_as_search_from_only" in out["warnings"]


def test_builder_literal_marker_is_escaped_and_regex_marker_can_be_raw() -> None:
    literal = build_regex_from_builder_spec({"line_contains": "S5", "right_marker": "O.D.", "value_type": "decimal"})
    raw = build_regex_from_builder_spec(
        {"line_contains": "PCQ2", "right_marker": r"(?:ng/ml|IU/ml)", "right_marker_is_regex": True, "value_type": "range"}
    )

    assert r"O\.D\." in literal["regex"]
    assert r"(?:ng/ml|IU/ml)" in raw["regex"]
