import json
from pathlib import Path
from src.assaychooser.api import detect_assays
from src.contentsplitter.api import split_assay_sections
import pytest

def test_detect_assays_case_sensitive(tmp_path: Path):
    index = {"assays": [{"assay_key": "(6bd7)", "ruleset_file": "x.json"}]}
    p = tmp_path / "index.json"
    p.write_text(json.dumps(index), encoding="utf-8")

    matches = detect_assays("abc (6bd7) def", str(p))
    assert [m.assay_key for m in matches] == ["(6bd7)"]

    matches2 = detect_assays("abc (6BD7) def", str(p))
    assert matches2 == []


def test_proven_sections_match_document_id_case_to_exact_configured_key(tmp_path):
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"assays": [{"assay_key": "(6bd7)", "ruleset_file": "x.json"}]}), encoding="utf-8")
    text = "Not a header: (6bd7)\nInstrument assay (6BD7)\nValue: 1\nUnknown (FADE)\nValue: 2"
    matches = detect_assays(text, str(index), sections=split_assay_sections(text))
    assert [row.assay_key for row in matches] == ["(6bd7)"]
    assert detect_assays("Notes about (6bd7)", str(index), sections=[]) == []


def test_proven_sections_reject_case_aliases_in_index(tmp_path):
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"assays": [{"assay_key": key, "ruleset_file": key + ".json"} for key in ("(6bd7)", "(6BD7)")]}), encoding="utf-8")
    text = "Instrument (6BD7)\nValue: 1"
    with pytest.raises(RuntimeError, match="assay_key_ambiguous_in_index"):
        detect_assays(text, str(index), sections=split_assay_sections(text))
