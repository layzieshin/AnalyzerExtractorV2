import pytest

from src.extractor.api import extract_record
from src.extractor.extractor import ExtractionError
from src.ruleresolver.model import RuleSet


def test_extractor_builds_v2_dedupe_from_header_basis():
    ruleset = RuleSet(
        assay_key="(1111)",
        ruleset_file="A.json",
        data={
            "assay_name": "A",
            "assay_key": "(1111)",
            "lot_rule": {"regex": r"Lot:\s*(\w+)"},
            "extract_rules": {
                "fields": [
                    {"key": "plate_name", "regex": r"Plate:\s*(\w+)", "required": True},
                    {"key": "test", "regex": r"Test:\s*(.+)", "required": False},
                    {"key": "date", "regex": r"Date:\s*([0-9\.\-]+)", "required": True},
                    {"key": "time", "regex": r"Time:\s*([0-9:]+)", "required": True},
                ]
            },
            "excel_rules": {},
        },
    )
    text = "Lot: LOTA\nPlate: P1\nTest: C:\\Assays\\Assay A.asy\nDate: 01.01.2026\nTime: 10:10"
    rec = extract_record(text, ruleset, device_id="dev1")
    assert rec.lot_id == "LOTA"
    assert rec.device_id == "dev1"
    assert rec.dedupe_version == "v2"
    assert rec.dedupe_key == "v2|dev1|P1|2026-01-01|10:10:00|Assay A.asy"
    assert rec.dedupe_basis["PLATTE"] == "P1"
    assert rec.dedupe_basis["TEST"] == "Assay A.asy"


def test_extractor_supports_configured_dedupe_fields():
    ruleset = RuleSet(
        assay_key="(2222)",
        ruleset_file="B.json",
        data={
            "assay_name": "B",
            "assay_key": "(2222)",
            "lot_rule": {"regex": r"Lot:\s*(\w+)"},
            "extract_rules": {
                "dedupe_fields": ["date", "time"],
                "fields": [
                    {"key": "date", "regex": r"Date:\s*([0-9\-]+)", "required": True},
                    {"key": "time", "regex": r"Time:\s*([0-9:]+)", "required": True},
                ],
            },
            "excel_rules": {},
        },
    )
    text = "Lot: LOTB\nDate: 2026-01-01\nTime: 11:00:00"
    rec = extract_record(text, ruleset)
    assert rec.dedupe_key == "(2222)|LOTB|2026-01-01|11:00:00"
    assert rec.dedupe_version == "explicit_legacy"


def test_extractor_fails_if_v2_dedupe_basis_missing():
    ruleset = RuleSet(
        assay_key="(3333)",
        ruleset_file="C.json",
        data={
            "assay_name": "C",
            "assay_key": "(3333)",
            "lot_rule": {"regex": r"Lot:\s*(\w+)"},
            "extract_rules": {"fields": [{"key": "x", "regex": r"X:\s*(\w+)", "required": False}]},
            "excel_rules": {},
        },
    )
    text = "Lot: LOTC"
    with pytest.raises(ExtractionError, match="dedupe basis missing"):
        extract_record(text, ruleset)


def test_extractor_different_device_changes_v2_key():
    ruleset = RuleSet(
        assay_key="(4444)",
        ruleset_file="D.json",
        data={
            "assay_name": "D",
            "assay_key": "(4444)",
            "lot_rule": {"regex": r"Lot:\s*(\w+)"},
            "extract_rules": {
                "fields": [
                    {"key": "PLATTE", "regex": r"Platte:\s*(\w+)", "required": True},
                    {"key": "DATUM", "regex": r"Datum:\s*([0-9\.]+)", "required": True},
                    {"key": "ZEIT", "regex": r"Zeit:\s*([0-9:]+)", "required": True},
                    {"key": "TEST", "regex": r"Test:\s*(.+?\.asy)", "required": True},
                ]
            },
            "excel_rules": {},
        },
    )
    text = "Lot: LOTD\nPlatte: P1\nDatum: 01.01.2026\nZeit: 10:10:00\nTest: ANA Screen IgG.asy"
    rec1 = extract_record(text, ruleset, device_id="dev1")
    rec2 = extract_record(text, ruleset, device_id="dev2")
    assert rec1.dedupe_key != rec2.dedupe_key
