import json
from pathlib import Path

import pytest

from src.ruleresolver.api import resolve_ruleset, validate_rules_integrity
from src.ruleresolver.ruleresolver import RuleResolverError


def test_ruleresolver_detects_missing_section(tmp_path: Path):
    rules = tmp_path / "rules"
    rules.mkdir()
    index = {"assays": [{"assay_key": "(1111)", "ruleset_file": "A.json"}]}
    (rules / "index.json").write_text(json.dumps(index), encoding="utf-8")
    bad = {"assay_key": "(1111)", "lot_rule": {}, "extract_rules": {}}
    (rules / "A.json").write_text(json.dumps(bad), encoding="utf-8")

    with pytest.raises(RuleResolverError):
        resolve_ruleset("(1111)", str(rules), str(rules / "index.json"))


def test_validate_rules_integrity_reports_orphan_and_duplicate_keys(tmp_path: Path):
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1111)", "ruleset_file": "A.json"}]}),
        encoding="utf-8",
    )
    # duplicate top-level key on purpose
    (rules / "A.json").write_text(
        '{"assay_key":"(1111)","lot_rule":{},"extract_rules":{"fields":[]},"extract_rules":{},"excel_rules":{}}',
        encoding="utf-8",
    )
    (rules / "Orphan.json").write_text(
        json.dumps({"assay_key": "(2222)", "lot_rule": {}, "extract_rules": {"fields": []}, "excel_rules": {}}),
        encoding="utf-8",
    )

    report = validate_rules_integrity(str(rules), str(rules / "index.json"))
    assert "A.json" in report["duplicate_json_key_files"]
    assert "Orphan.json" in report["orphan_rulesets"]


def test_validate_rules_integrity_ignores_template_json(tmp_path: Path):
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1111)", "ruleset_file": "A.json"}]}),
        encoding="utf-8",
    )
    (rules / "A.json").write_text(
        json.dumps(
            {"assay_key": "(1111)", "lot_rule": {}, "extract_rules": {"fields": []}, "excel_rules": {}}
        ),
        encoding="utf-8",
    )
    (rules / "template.json").write_text("{}", encoding="utf-8")

    report = validate_rules_integrity(str(rules), str(rules / "index.json"))
    assert "template.json" not in report["orphan_rulesets"]
