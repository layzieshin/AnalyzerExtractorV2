from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .model import RuleSet


class RuleResolverError(RuntimeError):
    pass


class RuleResolver:
    def resolve_ruleset(self, assay_key: str, rules_dir: str, rules_index_path: str) -> RuleSet:
        try:
            idx = json.loads(Path(rules_index_path).read_text(encoding="utf-8"))
        except Exception as e:
            raise RuleResolverError(f"Cannot read index.json: {e}") from e

        mapping: Dict[str, str] = {}
        for a in idx.get("assays", []):
            k = a.get("assay_key")
            f = a.get("ruleset_file")
            if k and f:
                mapping[k] = f

        if assay_key not in mapping:
            raise RuleResolverError(f"Unknown assay_key: {assay_key}")

        ruleset_file = mapping[assay_key]
        path = Path(rules_dir) / ruleset_file
        if not path.exists():
            raise RuleResolverError(f"RuleSet file not found: {path}")

        try:
            data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise RuleResolverError(f"Cannot parse RuleSet JSON: {e}") from e

        if data.get("assay_key") != assay_key:
            raise RuleResolverError("RuleSet assay_key mismatch")

        for req in ("lot_rule", "extract_rules", "excel_rules"):
            if req not in data:
                raise RuleResolverError(f"RuleSet missing required section: {req}")

        return RuleSet(assay_key=assay_key, ruleset_file=ruleset_file, data=data)
