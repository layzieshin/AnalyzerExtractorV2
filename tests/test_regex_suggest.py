from __future__ import annotations

from src.rulesuite.api import suggest_regex_from_selection


def test_suggest_regex_generalizes_analyzer_s5_measurement() -> None:
    line = "25-OH Vitamin D S5 0013200223 261126 0,722 O.D. >0,100 O.D."

    out = suggest_regex_from_selection(line, "0,722")

    assert out["regex"] == r"\bS5\s+\S+\s+\d{6}\s+(\d+(?:[\.,]\d+)?)\s+O\.D\."
    assert "0013200223" not in out["regex"]
    assert "261126" not in out["regex"]
    assert ">0,100" not in out["regex"]
    assert out["capture"] == r"(\d+(?:[\.,]\d+)?)"


def test_suggest_regex_uses_asy_filename_capture() -> None:
    line = r"Test: C:\ProgramData\Euroimmun_Analyzer_I\Assays\25-OH Vitamin D.asy (6bd7)"

    out = suggest_regex_from_selection(line, "25-OH Vitamin D.asy")

    assert out["regex"] == r"Test:.*[\\/]([^\\/]+\.asy)"
    assert "25\\-OH" not in out["regex"]
    assert out["capture"] == r"([^\\/]+\.asy)"


def test_suggest_regex_header_date() -> None:
    line = "Anwender: Fischer Datum: 14.01.2026 Wellenlaengen: 450nm/620nm"

    out = suggest_regex_from_selection(line, "14.01.2026")

    assert out["regex"] == r"Datum:\s+(\d{1,2}\.\d{1,2}\.\d{4})"
    assert out["capture"] == r"(\d{1,2}\.\d{1,2}\.\d{4})"


def test_suggest_regex_threshold_and_range() -> None:
    threshold = suggest_regex_from_selection("S5 S5>0,100 0,785>0,1", ">0,100")
    value_range = suggest_regex_from_selection("PCQ1 17,3 ng/ml 8,7-26,0 ng/ml", "8,7-26,0")

    assert threshold["capture"] == r"([<>]=?\s*\d+(?:[\.,]\d+)?)"
    assert value_range["capture"] == r"(\d+(?:[\.,]\d+)?\s*-\s*\d+(?:[\.,]\d+)?)"
