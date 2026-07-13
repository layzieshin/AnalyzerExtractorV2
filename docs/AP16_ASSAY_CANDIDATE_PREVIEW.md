# AP-16A Assay-Kandidaten-Preview

AP-16A ergänzt eine rein lesende Kandidatenvorschau für `no_assay_detected`-Nacharbeit im
`RULE SUITE`-Tab der Test-App.

## Zweck

Aus dem vorhandenen normalized dump werden Analyzer-Testzeilen erkannt und mit dem
read-only `rules/index.json` abgeglichen. Die Vorschau ist eine Entscheidungshilfe für
manuelle Regelarbeit.

- `bekannt` (`known`): Regel existiert bereits – Retry, Job-Alter oder nachträglich
  ergänzte Regeln prüfen.
- `unbekannt` (`unknown`): mögliches neues Regelwerk manuell prüfen.
- `ungeprüft` (`unchecked`): kein Assay-Key erkannt oder Index nicht lesbar.

Gleiche Assay-Namen mit unterschiedlichen Keys bleiben getrennte Kandidaten sichtbar.

## Erkennung

Modul: `src.assaycandidate.api`

- `find_assay_candidates(text)` erkennt Zeilen wie
  `Test: C:\...\ANA Screen IgG.asy (1c9e)` oder `Test: ANA Screen IgG.asy (1C9E)`.
- Deduplizierung nur nach kanonischem Assay-Key `(xxxx)` lowercase.
- Fallback nur ohne Testzeile: Zeilen mit `Validationskriterien erfüllt/nicht erfüllt`
  (`confidence=medium`, kein erfundener Assay-Key).
- Keine Kandidaten aus Reagenz-, Kit- oder Produktzeilen ohne `Test:`.

Known-Abgleich:

- `load_known_assay_keys(rules/index.json)` read-only
- `annotate_assay_candidates(...)` setzt `known_status` auf `known`, `unknown` oder
  `unchecked`

## UI

Button `Assay-Kandidaten prüfen` im Nacharbeitsbereich:

- nur für ausgewählten Fall
- nur sinnvoll bei Fehlerklasse `Assay nicht erkannt`
- Quelle: normalized dump
- Meldungen: `Kein normalisierter Kontext vorhanden.` / `Keine Kandidaten erkannt.`

## Grenzen

- read-only: keine Rules, keine Drafts, keine Änderung an `rules/*`
- keine KI, keine automatische Rule-Erzeugung
- keine RuleEditor-Vorbefüllung (späteres Paket)
