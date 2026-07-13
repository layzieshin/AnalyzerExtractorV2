import json
from pathlib import Path

from src.assaycandidate.api import (
    annotate_assay_candidates,
    find_assay_candidates,
    load_known_assay_keys,
)


def test_find_assay_candidates_recognizes_path_variant_with_lowercase_key():
    text = r"Test: C:\ProgramData\Euroimmun_Analyzer_I\Assays\ANA Screen IgG.asy (1c9e)"

    candidates = find_assay_candidates(text)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["assay_key"] == "(1c9e)"
    assert candidate["raw_assay_key"] == "(1c9e)"
    assert candidate["test_file"] == "ANA Screen IgG.asy"
    assert candidate["assay_name_hint"] == "ANA Screen IgG"
    assert candidate["line_no"] == "1"
    assert candidate["line_text"] == text
    assert candidate["reason"] == "test_line"
    assert candidate["confidence"] == "high"
    assert candidate["candidate_id"] == "(1c9e)"


def test_find_assay_candidates_recognizes_no_path_variant_and_normalizes_key():
    text = "Test: ANA Screen IgG.asy (1C9E)"

    candidates = find_assay_candidates(text)

    assert len(candidates) == 1
    assert candidates[0]["assay_key"] == "(1c9e)"
    assert candidates[0]["raw_assay_key"] == "(1C9E)"
    assert candidates[0]["test_file"] == "ANA Screen IgG.asy"


def test_find_assay_candidates_deduplicates_same_key():
    text = "\n".join(
        [
            r"Test: C:\Assays\ANA Screen IgG.asy (1c9e)",
            "Test: ANA Screen IgG.asy (1C9E)",
        ]
    )

    candidates = find_assay_candidates(text)

    assert len(candidates) == 1
    assert candidates[0]["line_no"] == "1"


def test_find_assay_candidates_keeps_same_name_with_different_keys():
    text = "\n".join(
        [
            "Test: Shared Name.asy (1c9e)",
            "Test: Shared Name.asy (2abc)",
        ]
    )

    candidates = find_assay_candidates(text)

    assert len(candidates) == 2
    assert [candidate["assay_key"] for candidate in candidates] == ["(1c9e)", "(2abc)"]
    assert all(candidate["assay_name_hint"] == "Shared Name" for candidate in candidates)


def test_find_assay_candidates_uses_validation_fallback_only_without_test_lines():
    text = "\n".join(
        [
            "Reagenz: Anti-TPO Kit",
            "Validationskriterien nicht erfüllt",
            "Validationskriterien erfüllt",
        ]
    )

    candidates = find_assay_candidates(text)

    assert len(candidates) == 2
    assert candidates[0]["candidate_id"] == "2:validation_context"
    assert candidates[0]["assay_key"] == ""
    assert candidates[0]["assay_name_hint"] == ""
    assert candidates[0]["reason"] == "validation_context"
    assert candidates[0]["confidence"] == "medium"
    assert candidates[1]["candidate_id"] == "3:validation_context"


def test_find_assay_candidates_ignores_validation_when_test_line_exists():
    text = "\n".join(
        [
            "Validationskriterien nicht erfüllt",
            "Test: ANA Screen IgG.asy (1c9e)",
        ]
    )

    candidates = find_assay_candidates(text)

    assert len(candidates) == 1
    assert candidates[0]["reason"] == "test_line"


def test_find_assay_candidates_ignores_reagent_lines_without_test_prefix():
    text = "\n".join(
        [
            "Reagenz: Anti-TPO Kit",
            "Produkt: Euroimmun Analyzer",
            "Kit: XYZ",
        ]
    )

    assert find_assay_candidates(text) == []


def test_annotate_assay_candidates_marks_known_unknown_and_unchecked():
    candidates = [
        {"candidate_id": "(1c9e)", "assay_key": "(1c9e)"},
        {"candidate_id": "(abcd)", "assay_key": "(abcd)"},
        {"candidate_id": "2:validation_context", "assay_key": ""},
    ]

    annotated = annotate_assay_candidates(candidates, {"(1c9e)"})

    assert annotated[0]["known_status"] == "known"
    assert annotated[1]["known_status"] == "unknown"
    assert annotated[2]["known_status"] == "unchecked"


def test_annotate_assay_candidates_marks_all_unchecked_when_known_keys_missing():
    candidates = [{"candidate_id": "(1c9e)", "assay_key": "(1c9e)"}]

    annotated = annotate_assay_candidates(candidates, None)

    assert annotated[0]["known_status"] == "unchecked"


def test_load_known_assay_keys_reads_index_and_normalizes(tmp_path: Path):
    index = {
        "assays": [
            {"assay_key": "(1C9E)", "ruleset_file": "ANA Screen IgG.json"},
            {"assay_key": "(6bd7)", "ruleset_file": "25-OH Vitamin D.json"},
        ]
    }
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")

    keys = load_known_assay_keys(str(index_path))

    assert keys == {"(1c9e)", "(6bd7)"}


def test_load_known_assay_keys_returns_none_for_missing_or_invalid_file(tmp_path: Path):
    missing = tmp_path / "missing.json"
    broken = tmp_path / "broken.json"
    broken.write_text("{not-json", encoding="utf-8")

    assert load_known_assay_keys(str(missing)) is None
    assert load_known_assay_keys(str(broken)) is None
