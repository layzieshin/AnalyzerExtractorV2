# AP-9: Header-Vertrag (8 Pflichtfelder)

## Ziel

RuleSuite und RuleEditor kennen fuer neue und abgeleitete Drafts **acht** canonical Header-Pflichtfelder. Der Vertrag gilt fuer Draft-Erzeugung, `check_required_fields`, Authoring-Readiness und den Wizard — **ohne** Aenderung am JSON-Schema und **ohne** Massenkorrektur produktiver `rules/*.json`.

## Canonical Felder (Reihenfolge)

1. `DATUM`
2. `ZEIT`
3. `ANWENDER`
4. `PLATTE`
5. `TEST`
6. `CHARGE`
7. `HALTBARKEIT`
8. `VALIDATION`

Felder bleiben normale Eintraege in `extract_rules.fields`.

## Legacy-Aliase (Import/Ableitung)

| Legacy | Canonical |
|--------|-----------|
| `date` | `DATUM` |
| `time` | `ZEIT` |
| `user` | `ANWENDER` |
| `plate_name` | `PLATTE` |
| `test` | `TEST` |
| `lot_id` | `CHARGE` |
| `lot_expiry_yymmdd` | `HALTBARKEIT` |
| `lot_expiry_date` | `HALTBARKEIT` |
| `Haltbarkeit` | `HALTBARKEIT` |

Aufloesung zentral in `src/rulesuite/header_aliases.py` (`resolve_required_headers_from_source`). `templates.py` delegiert ohne eigene Alias-Logik.

## Gates

- `create_draft_from_template()` / `create_draft_from_ruleset()` → 8 Pflichtfelder
- `check_required_fields()` → `total=8`, `all_confirmed` nur bei 8 Treffern
- `check_authoring_readiness()` mit Assay-Text → gleicher Vertrag
- Kandidaten schliessen canonical Header + Legacy-Aliase aus

## Nicht im Scope

- Dedupe-Policy-Umbau
- Massenbereinigung aktiver `rules/*.json` (z.B. Anti-MPO `TEST required=false` bleibt bis zur separaten fachlichen Bereinigung)
- Aenderung an `rules/template.json` / `rules/index.json`

## Verifikation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe rules_validate_main.py
```
