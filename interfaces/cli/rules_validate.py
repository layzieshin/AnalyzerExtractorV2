from __future__ import annotations

import json
from pathlib import Path

from src.ruleresolver.api import validate_rules_integrity


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    report = validate_rules_integrity(str(root / "rules"), str(root / "rules" / "index.json"))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if any(bool(value) for value in report.values()):
        raise SystemExit(1)
