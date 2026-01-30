import json
from pathlib import Path
from src.assaychooser.api import detect_assays

def test_detect_assays_case_sensitive(tmp_path: Path):
    index = {"assays": [{"assay_key": "(6bd7)", "ruleset_file": "x.json"}]}
    p = tmp_path / "index.json"
    p.write_text(json.dumps(index), encoding="utf-8")

    matches = detect_assays("abc (6bd7) def", str(p))
    assert [m.assay_key for m in matches] == ["(6bd7)"]

    matches2 = detect_assays("abc (6BD7) def", str(p))
    assert matches2 == []
