# AP-3 Acceptance: Kandidatenfelder + guided Wizard

## Scope

- Wizard: genau zwei Modi (`similar`, `blank`); kein sichtbarer Vollklon
- Header sofort im Draft (canonical); Zusatzfelder als Kandidaten bis zur manuellen Uebernahme
- `derive_draft()` nur API/Editor/CLI — nicht im Wizard
- Keine Aenderungen an `rules/*.json`, Pipeline oder Extractor
- Keine Regex-Auto-Generierung

## Definition of Done

| Kriterium | Status |
|---|---|
| Modus „Aehnlich wie Vorlage“: `create_draft_from_ruleset` + Alias-Normalisierung | API + Tests |
| Modus „Von Grund auf“: `create_draft_from_template` unveraendert | Regression |
| Kandidaten-API: `read_candidate_fields`, `check_candidates`, `adopt_candidate_field` | API + Tests |
| Legacy-Header nicht als Kandidaten | Filter + Tests |
| Wizard Kandidaten-UI (Test / Uebernehmen / Verwerfen session-only) | `wizard.py` / `wizard_ui.py` |
| `adopt_candidate_field`: `required` + `column_mapping` aus Quelle; Formular-Overrides | API + Tests |
| pytest gruen (86 Tests) | Gate |

## Gates

```bash
python -m pytest -q
```

## Out of Scope

- Persistente dismissed-Liste
- Pipeline-/Extractor-Fallbacks
- Aenderungen an produktiven Rulesets
