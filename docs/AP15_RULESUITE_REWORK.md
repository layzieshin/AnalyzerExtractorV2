# AP-15 RuleSuite-Nacharbeitsliste

AP-15A ergänzt im `RULE SUITE`-Tab der Test-App eine evidence-first Nacharbeitsliste für
regelrelevante `FAILED`-Jobs aus der persistenten Arbeitsliste (`jobs/queue/`).

AP-15B macht diese Liste für manuelle Regelarbeit nutzbar: fachliche Filter, kopierbare
Pfade im Detail und nummerierte Kontextausgabe.

## Quelle

- Queue-Jobs mit `status == "FAILED"`
- optionale Job-State-Datei `jobs/{job_id}.json`
- vorhandene Debug-Artefakte aus `steps`:
  - `normalized_dump`
  - `block_dumps`

## Regelrelevante Fehlerklassen

- `no_assay_detected` -> Assay nicht erkannt
- `ruleset missing assay_name` -> Regelset unvollständig
- `content_split_failed` / `split_failed` -> Aufteilung fehlgeschlagen

Generische Queue-Fehler wie `max_attempts_exceeded` werden nur aufgenommen, wenn
`jobs/{job_id}.json["error"]` eine regelrelevante Root-Cause enthält.

Nicht regelrelevant und deshalb ausgeblendet:

- `pdf_not_found`
- Excel-/SQLite-Schreibfehler
- Duplicate-Fälle
- rein technische Worker-Fehler ohne erkennbare Regel-Ursache

## UI (AP-15A)

Im `RULE SUITE`-Tab:

- `Nacharbeit aktualisieren`
- Tabelle mit `Datei`, `Fehler`, `Status`, `Job-ID`, `Kontext`
- Detailbereich
- `Kontext anzeigen`
- `Rule Editor oeffnen`
- `Erneut starten`

`Erneut starten` nutzt den AP-14D-Mechanismus `retry_failed_job(...)` und aktualisiert
danach Arbeitsliste und Nacharbeit.

## UI (AP-15B)

### Nacharbeitsfilter

- Filterauswahl: `Alle`, `Assay nicht erkannt`, `Regelset unvollständig`, `Aufteilung fehlgeschlagen`
- Default: `Alle`
- `Nacharbeit aktualisieren` lädt alle Items aus Queue + Job-State und speichert sie intern
  als vollständige Liste (`_rework_items_all`)
- Filterwechsel rendert nur die Tabelle neu; Queue- und Job-State-Dateien bleiben unverändert
- Log: `Nacharbeit aktualisiert: X geladen, Y angezeigt.`

### Kontextanzeige

Priorität bei `Kontext anzeigen`:

1. vorhandener normalized dump
2. sonst erster vorhandener Block-Dump
3. sonst erster bekannter, aber fehlender Dump-Pfad als Hinweis

Kontextausgabe enthält Kopfbereich (Kontexttyp, PDF-Pfad, Dump-Pfad, Fehlerklasse,
Queue-Fehler, State-Fehler, Root-Cause) und nummerierten Dump-Inhalt (`0001 | ...`).

### Rule Editor

- Kein neuer Kontext-Übergabe-Button
- `Rule Editor oeffnen` startet weiterhin den bestehenden Rule Editor
- Bei ausgewähltem Nacharbeits-Eintrag werden PDF und bevorzugter Dump-Pfad geloggt

## Presenter (`src.testui`)

- `filter_rework_items(items, error_label="Alle")`
- `format_rework_context_text(item, content, context_label, context_path)`
- `resolve_rework_context_source(item)` / `preferred_rework_dump_path(item)`
- `format_rework_item_detail(...)` enthält PDF-Pfad, State-Pfad, Dump-Pfade, Fehlerklasse,
  Queue-/State-Fehler und Root-Cause

## Grenzen

- Keine automatische Kandidatenerkennung
- Keine RuleEditor-Übergabe mit konkreter PDF-/Artefakt-Auswahl
- Keine neuen Debug-Artefakte; nur Anzeige vorhandener Evidenz
- Keine Änderungen an `src.jobcontroller`, `src.jobqueue`, `rules/*`
