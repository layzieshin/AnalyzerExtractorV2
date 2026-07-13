# AP-16 RuleSuite-Drafts aus Nacharbeit

AP-16B verbindet die read-only Kandidatenvorschau (AP-16A) mit manuellem RuleSuite-Authoring.
Es werden ausschließlich Drafts erzeugt oder erweitert – keine Aktivierung, keine Änderungen an
`rules/index.json` oder produktiven `rules/*.json`.

## AP-16B.1: Draft aus Assay-Kandidat

Im `RULE SUITE`-Nacharbeitsbereich:

1. `Assay-Kandidaten prüfen`
2. Kandidat auswählen
3. `Draft aus Kandidat erstellen`

Voraussetzungen:

- Kandidat mit `assay_key` und `assay_name_hint`
- `known_status` ist `unknown` oder `unchecked`
- bei `known`: kein Draft, Hinweis auf Retry/vorhandene Rule
- bei `unchecked`: Warnung vor Anlage

Erzeugt wird nur `rules/drafts/<safe_assay_key>.draft.json` auf Basis von `template.json`
(8 Pflicht-Header, keine assayspezifischen Zusatzfelder). Bestehende Drafts werden nicht
überschrieert (`status=exists`).

API (`src.rulesuite.api`):

- `draft_path_for_assay(project_root, assay_key)`
- `create_draft_from_template_if_missing(project_root, assay_key, assay_name)`

## AP-16B.2: Felder aus Regelwerk übernehmen

Im Rule Editor (Regelset-Verwaltung):

- Button `Felder aus Regelwerk uebernehmen`
- Quelle: ausgewähltes Regelwerk in der Verwaltungsliste
- Ziel: aktuell geladener Draft
- nur Nicht-Header-Felder; Header-Vertrag im Ziel bleibt erhalten
- bestehende Feldkeys werden übersprungen (`overwrite=False` default)

API:

- `adopt_candidate_fields(project_root, draft_path, candidate_source, ...)`
- nutzt intern `read_candidate_fields(...)` und schreibt den Draft einmal gesammelt

Ergebnis: adopted / skipped_existing / missing, Quelle und Ziel-Pfad.

## Grenzen

- read-only gegenüber produktiven Rules und Index
- keine automatische Aktivierung
- RuleEditor-Öffnung aus der Test-App bleibt optional und ohne Draft-Übergabe-Parameter
