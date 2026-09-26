# Working Agreement – Phase 4: RuleResolver

## Modul
src/ruleresolver/

## Verantwortung
- Laden & Validieren von RuleSets

## Öffentlicher Contract (api.py)
- load_rules_index(path: str)
- resolve_ruleset(assay_key, index, rules_dir) -> RuleSet
- validate_ruleset(ruleset)

## Regeln
- Format: JSON
- index.json ist bindend
