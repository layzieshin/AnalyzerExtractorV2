from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .ruleresolver import RuleResolver
from .model import RuleSet

def resolve_ruleset(assay_key: str, rules_dir: str, rules_index_path: str) -> RuleSet:
    """Public API (RuleResolver)"""
    return RuleResolver().resolve_ruleset(assay_key, rules_dir, rules_index_path)
