# AP-11.5: Testanleitung Haupt-App

## App starten

```powershell
cd I:\Projekte\AnalyzerResultExtractorV2
.\.venv\Scripts\python.exe gui_min.py
```

Alternativ: `gui_min_ext.py` (gleiche UI). `gui_min.py` ist Thin Launcher für PyInstaller.

Fenstertitel: **AnalyzerExtractorV2 - Test UI (Direct Mode)**

## Voraussetzungen

- `project_root` zeigt auf das AREV2-Repo (Standard: App-Root via `ARE_HOME` / PyInstaller)
- Rules unter `rules/` und `rules/index.json` vorhanden
- Schreibbare Ordner: `jobs/`, `locks/`, `output/final/`

Schnellcheck vor dem Test:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe rules_validate_main.py
```

## Sample-PDFs

| PDF | Pfad | Hinweis |
|-----|------|---------|
| Single-Sample | `input/sample_single.pdf` | CLI-Referenz (`main02.py`) |
| Multi-Sample | `input/sample_multi.pdf` | Mehrere Assays möglich |
| Eigene PDFs | beliebig | Über **PDFs auswaehlen...** |

Coverage-Lücken: siehe `docs/KNOWN_ISSUES.md` und `docs/TESTBASELINE.md`.

## Ablauf Single E2E

1. Tab **Single PDF** → **PDFs auswaehlen...**
2. Optional: Submit-Konfiguration (`output_mode`, `sqlite_path`, `reject_invalid_runs`)
3. **Single E2E starten**
4. Bereich **Ergebnis** prüfen:
   - Kopfzeile: Outcome, Status, PDF, job_id
   - Tabelle **Laeufe**: PDF / Status / Outcome
   - Tabelle **Assays**: Assay, Lot, Ruleset, Missing, Schreibstatus
   - **Feldwerte (Auswahl)**: vollständige extrahierte Werte nach Assay-Klick
5. **Ausgabe / Testprotokoll**: technische Details, Steps, Rohfehler

## Ablauf Batch E2E

1. Mehrere PDFs in die Liste laden
2. Tab **Batch** → **Batch E2E starten**
3. Ergebnis-Bereich sammelt alle Läufe; Lauf auswählen → Assays und Details

## Erwartete Statusmeldungen

| Status | Bedeutung | GUI-Hinweis |
|--------|-----------|-------------|
| `DONE` | Pipeline erfolgreich | Assays + Schreibziele sichtbar |
| `SKIPPED` + `already_done` | Job-State war bereits DONE | „Bereits verarbeitet … Force rerun moeglich“ |
| `SKIPPED` + `locked` | Pipeline-Lock aktiv | WARN, erneut versuchen |
| `FAILED` + `no_assay_detected` | Kein Assay erkannt | Kurztext in Ergebniszeile |
| `FAILED` + `validation_failed` | Validierungskriterien nicht erfüllt | bei aktivem `reject_invalid_runs` |
| `FAILED` + `excel_write_failed` | Excel nicht beschreibbar | Excel oft geöffnet / Lock |

## Output-Pfade

| Artefakt | Standardpfad |
|----------|--------------|
| Excel | `output/final/{assay_name}.xlsx` (Sheet = lot_id) |
| SQLite | `output/final/results.sqlite3` (Tabelle `runs`) |
| Job-State | `jobs/{job_id}.json` |
| Debug-Text | `jobs/{job_id}_normalized.txt`, `{job_id}_{assay}_block.txt` |

`job_id` = SHA-256(PDF-Inhalt)[:16]

## already_done

- Pipeline überspringt Lauf, wenn `jobs/{job_id}.json` Status `DONE` hat
- **Prüft nicht**, ob Excel/SQLite noch existieren (siehe KNOWN_ISSUES)
- **Force rerun (selektierte PDF)** löscht Job-State + Lock, nicht Excel/SQLite
- Für echten Neuschreib: ggf. `/output/final leeren` oder Dedupe beachten

## Rule Preview (separater Pfad)

Tab **Rule Preview** → **Preview (ohne Write)** nutzt `preview_extract()` — kein Excel/SQLite-Write, für Regel-Tuning.

## Admin / Diagnose

| Aktion | Wirkung |
|--------|---------|
| `/jobs leeren` | Alle Job-State- und Debug-Dateien |
| `/output/final leeren` | Excel + SQLite im Final-Output |
| **Rules Integritaet pruefen** | Strukturcheck `rules/` |

## Bewusst nicht gelöst (Stand AP-11)

- Watchdog/Worker/Queue in dieser GUI
- Funktionale Rules-Matrix (`rules_matrix_main.py --mode preview`) — separater Gate
- Massenkorrektur produktiver `rules/*.json`
- PyQt / QMTool
- Dedupe-Policy-Umbau
- `already_done` ohne Output-Verifikation

## CLI-Referenz

Headless-Vergleich:

```powershell
.\.venv\Scripts\python.exe main02.py
```

Druckt vollständige `JobResult.details` und Step-Summary aus `jobs/{job_id}.json`.
