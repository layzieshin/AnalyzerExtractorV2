from __future__ import annotations

from typing import Any, Dict

from .ruleresolver import RuleResolver, RuleResolverError
from .model import RuleSet
from .validator import validate_rules_integrity as _validate_rules_integrity

__all__ = ["RuleResolverError", "RuleSet", "resolve_ruleset", "validate_rules_integrity"]

def resolve_ruleset(assay_key: str, rules_dir: str, rules_index_path: str) -> RuleSet:
    """Public API (RuleResolver)"""
    return RuleResolver().resolve_ruleset(assay_key, rules_dir, rules_index_path)


def validate_rules_integrity(rules_dir: str, rules_index_path: str) -> Dict[str, Any]:
    """Rules integrity check across index and ruleset files."""
    return _validate_rules_integrity(rules_dir, rules_index_path)
