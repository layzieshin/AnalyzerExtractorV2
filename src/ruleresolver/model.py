from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True)
class RuleSet:
    assay_key: str
    ruleset_file: str
    data: Dict[str, Any]
