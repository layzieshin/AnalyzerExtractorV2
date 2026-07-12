# AP-11.1: Haupt-App Ist-Aufnahme

Stand: Testphase AREV2. Ziel: Tkinter-Haupt-App für nachvollziehbaren PDF-Testbetrieb.

## Ziel-GUI

| Datei | Rolle | AP-11 |
|-------|-------|-------|
| `gui_min_ext.py` | **Primäre Test-GUI** — `MinimalBatchGUI` | **Weiterführen** |
| `gui_min.py` | Thin Launcher → `MinimalBatchGUI` (PyInstaller) | Alias, keine separate Pflege |
| `main02.py` | CLI-E2E auf `input/sample_*.pdf` | Referenz, nicht GUI-Ziel |
| `rule_editor_main.py` | Rule Authoring | Nicht im Scope |

Start: `.\.venv\Scripts\python.exe gui_min.py`

## Buttons und Flows

### E2E-Pipeline (vollständig: Parse → Extract → Write)

| Button | Tab | Handler | API |
|--------|-----|---------|-----|
| **Single E2E starten** | Single PDF | `on_run_single` → `_run_single_thread` | `src.jobcontroller.api.submit()` |
| **Batch E2E starten** | Batch | `on_run_batch` → `_run_batch_thread` | `submit()` in Schleife |

Konfiguration über Submit-Panel: `output_mode`, `sqlite_path`, Lock/SQLite-Retry, `reject_invalid_runs`.

### Preview (ohne Write)

| Button | Tab | API |
|--------|-----|-----|
| **Preview (ohne Write)** | Rule Preview | `src.rulesuite.api.preview_extract()` |

Separater Pfad für Regel-Tuning, nicht identisch mit E2E.

### Diagnose / Admin

- **Force rerun** — löscht `jobs/{job_id}*` und `locks/{job_id}.lock`, nicht Excel/SQLite
- **/jobs leeren**, **/output/final leeren** — Admin-Aktionen
- **Rules Integritaet pruefen** — `validate_rules_integrity()`

Watchdog, Worker und `jobs/queue/` sind in dieser GUI **bewusst ausgeklammert** (Direktmodus).

## Pipeline und Artefakte

```
PDF → parse → normalize → detect_assays → resolve_ruleset → split → extract_record → write_record / write_record_sqlite
```

Orchestrator: `src/jobcontroller/jobcontroller.py` → `JobController.submit()`

| Artefakt | Pfad | Inhalt |
|----------|------|--------|
| Job-ID | SHA-256(PDF)[:16] | Identisch in Pipeline und Queue |
| Pipeline-State | `jobs/{job_id}.json` | Status, Steps, Fehler, partial_writes |
| Lock | `locks/{job_id}.lock` | Exklusiv-Lock pro Lauf |
| Debug | `jobs/{job_id}_normalized.txt`, `{job_id}_{key}_block.txt` | Normalisierter Text, Assay-Blöcke |
| Excel | `output/final/{assay_name}.xlsx` | Sheet = lot_id |
| SQLite | `output/final/results.sqlite3` (default) | Tabelle `runs`, payload_json |

### JobResult (Rückgabe von submit)

```python
JobResult(job_id, pdf_path, status, details)
# status: DONE | FAILED | SKIPPED
# details bei DONE: assay_keys, writes[]
# details bei FAILED: error, partial_writes?
# details bei SKIPPED: reason (already_done | locked)
```

## Sichtbarkeits-Matrix (Ist-Stand vor AP-11.2)

| Information | Intern | GUI (Log) | CLI (e2e.py) |
|-------------|--------|-----------|--------------|
| status, job_id | JobResult | Ja | Ja |
| reason / error | JobResult | Ja (kurz) | Ja |
| Write-Pfade (Excel/SQLite) | writes[].outputs | Ja (format_write_outputs) | Ja |
| Step-Details (parser, split, …) | jobs/{id}.json | Single nur (_print_job_state) | Ja |
| assay_keys | JobResult | Indirekt | Ja |
| Extrahierte Feldwerte | AssayRecord.data | **Nein** | Nein |
| lot_id, dedupe_key | AssayRecord / SQLite | **Nein** | Nein |
| ruleset_file | RuleSet | **Nein** | Nein |
| missing_required | — | **Nein** | Nein |
| partial_writes bei FAILED | JobResult + state | **Nein** | Ja (details) |
| already_done Erklärung | SKIPPED | Minimal (PASS + reason) | Ja |

Hilfsmodule: `src/testui/helpers.py` — `classify_job_outcome`, `format_write_outputs`, `format_rules_report`.

## P0-Probleme

1. **Ergebnis nur im Scroll-Log** — kein strukturiertes Ergebnispanel
2. **Extrahierte Werte unsichtbar** — Extract läuft, wird aber nicht in JobResult zurückgegeben
3. **already_done zu leise** — als PASS klassifiziert, ohne klare Nutzererklärung im Ergebnisbereich
4. **Batch weniger Detail** — kein `_print_job_state`, keine einheitliche Ergebnisdarstellung

## P1-Probleme

5. **partial_writes** bei FAILED nicht in GUI
6. **Rohfehler** (`excel_write_failed:...`) ohne verständlichen Kurztext
7. **Dedupe/SQLite skipped** nicht erklärt
8. **already_done ohne Output-Check** — siehe `docs/KNOWN_ISSUES.md`

## Nicht im Scope (AP-11)

- PyQt / QMTool
- RuleEditor-Ausbau
- Regex-/Rules-Fachkorrekturen, `rules/*.json`-Massenbereinigung
- Writer-Redesign, Dedupe-Policy-Änderung
- Watchdog/Queue-Integration in Test-GUI
- Packaging/Build

## Empfehlung für AP-11.2–11.5

1. **AP-11.2:** `write_item` in JobController um `data`, `lot_id`, `dedupe_key`, `ruleset_file`, `missing_required` anreichern; GUI kompakte Übersicht + Detail bei Auswahl
2. **AP-11.3/11.4:** Excel/SQLite-Status formatieren, `humanize_job_error`, already_done/partial_writes sichtbar
3. **AP-11.5:** Manueller Testguide `docs/AP11_MAIN_APP_TEST_GUIDE.md`

Formatter-Schicht: `src/testui/helpers.py` (Adapter-GUI importiert nur `src.testui.api`).
