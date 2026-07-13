# AP-16C RuleSuite-Inventar und sicherer Regelwerk-Clone

AP-16C erweitert den Rule Editor um ein gemeinsames Inventar aktiver Regelwerke und Drafts
sowie einen sicheren Clone-Dialog.

## Inventar

- API: `list_rulesuite_inventory(project_root, kind="all")`
- Filter: `all`, `active`, `draft`
- Zeilen mit `kind`, `display_type`, `assay_key`, `assay_name`, `path`, `field_count`, `valid`, `error`
- Defekte Drafts erscheinen mit `valid=False`, brechen die Liste nicht ab
- Tree-IID: `kind|path` fuer eindeutige Selektion bei gleichem Assay-Key

## Clone

- API: `clone_ruleset_to_draft(...)`
- Quelle: aktives Regelwerk; Ziel: `rules/drafts/<target_key>.draft.json`
- Status: `created`, `overwritten`, `exists`
- `overwrite=False`: kein Write bei vorhandenem Ziel-Draft
- `include_fields=True`: Nicht-Header-Felder inkl. Mapping; `False`: nur Header-/Basisstruktur
- Ziel-`assay_key` und Ziel-`assay_name` bleiben immer die Zielwerte

## Rule Editor

- Inventarliste mit Filter `Alle | Aktiv | Drafts`
- `Regelwerk als Basis verwenden...` ersetzt den unsicheren Pfad `Aus aktivem ableiten`
- Aktive Zeile bearbeiten: vorhandenen Draft oeffnen statt still ueberschreiben
- Draft-Zeile: Draft direkt laden
- Kontextmenue fuer Clone-/Oeffnen-Aktionen

## Grenzen

- Keine Writes an aktive Rules oder `rules/index.json`
- Draft-Ueberschreiben nur nach expliziter Bestaetigung im Dialog
