# AP-15A RuleSuite-Nacharbeitsliste

AP-15A ergänzt im `RULE SUITE`-Tab der Test-App eine evidence-first Nacharbeitsliste für
regelrelevante `FAILED`-Jobs aus der persistenten Arbeitsliste (`jobs/queue/`).

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

## UI

Im `RULE SUITE`-Tab:

- `Nacharbeit aktualisieren`
- Tabelle mit `Datei`, `Fehler`, `Status`, `Job-ID`, `Kontext`
- Detailbereich
- `Kontext anzeigen`
- `Rule Editor oeffnen`
- `Erneut starten`

`Erneut starten` nutzt den AP-14D-Mechanismus `retry_failed_job(...)` und aktualisiert
danach Arbeitsliste und Nacharbeit.

## Grenzen

- Keine automatische Kandidatenerkennung
- Keine RuleEditor-Übergabe mit konkreter PDF-/Artefakt-Auswahl
- Keine neuen Debug-Artefakte; nur Anzeige vorhandener Evidenz
- Keine Änderungen an `src.jobcontroller`, `src.jobqueue`, `rules/*`
