# PDF Ergebnis-Extractor (Projekt)

- Windows 11 Zielumgebung
- `src/` ist Project Root (in PyCharm markieren)
- Public APIs existieren ausschließlich in `src/<module>/api.py`
- `api.py` ist die stabile Public Boundary; Implementierungsdetails bleiben hinter `src/<module>/api.py`
- Root-Entrys delegieren nur noch in `interfaces/cli` oder `interfaces/headless`
- `main.py` und `main02.py` sind Harnesses für den End-to-End Lauf (immer `sample_single.pdf` + `sample_multi.pdf`)
- Tests liegen unter `/tests` (pytest)

## Start

### Feldversuch / Testbetrieb (empfohlen)

```powershell
python test_app_main.py
```

Produktionsnahe Test-App mit Arbeitsliste, Queue-Verarbeitung, Nacharbeit und Duplikat-Review.
Details: `docs/AP14_TEST_APP.md`, Feldversuch-Paket: `docs/AP17A_FIELD_TRIAL_PACKAGE.md`

### Rule Editor

```powershell
python rule_editor_main.py
```

Visueller Regelwerk-Editor inkl. Inventar, Drafts, Nacharbeit und Lifecycle (Aktiv / Draft / Inaktiv).

### Headless Dauerbetrieb

```powershell
python watchdog_main.py
python worker_main.py
```

Optional nur ein Durchlauf:

```powershell
$env:ARE_WATCHDOG_ONCE="1"; python watchdog_main.py
$env:ARE_WORKER_ONCE="1"; python worker_main.py
```

Runbook: `DOCUMENTATION/10_headless_runbook.md`

### Legacy Direktmodus (Alt-/Smoke-UI)

```powershell
python gui_min_ext.py
python gui_min.py
```

Direkter `submit`-Pfad ohne Queue/Arbeitsliste. Nicht mehr der Packaging-Entry; nur noch für Entwicklung und Smoke.

### Entwicklung / CLI-Harness

1. Lege PDFs ab:
   - `input/sample_single.pdf`
   - `input/sample_multi.pdf`
2. Pflege `rules/index.json` und die referenzierten RuleSet JSONs unter `rules/`
3. Install:
   - `pip install -r requirements.txt`
   - optional für Embedding-Entwicklung: `pip install -e .`
4. Run:
   - `python main02.py` (empfohlen für bessere CLI-Übersicht)

## Headless Betrieb

- Watchdog dauerhaft starten:
  - `python watchdog_main.py`
- Worker dauerhaft starten:
  - `python worker_main.py`
- Optional nur ein Durchlauf:
  - `$env:ARE_WATCHDOG_ONCE="1"; python watchdog_main.py`
  - `$env:ARE_WORKER_ONCE="1"; python worker_main.py`

## Output-Modi

- `ARE_OUTPUT_MODE=both` (Default: Excel + SQLite)
- `ARE_OUTPUT_MODE=excel` (nur Excel)
- `ARE_OUTPUT_MODE=sqlite` (nur SQLite)
- SQLite-Zielpfad:
  - `ARE_SQLITE_PATH=I:/path/to/results.sqlite3`
- Queue/Pipeline Recovery:
  - `ARE_QUEUE_PROCESSING_TTL_S=300`
  - `ARE_QUEUE_CLAIM_LOCK_TTL_S=120`
  - `ARE_QUEUE_MAX_ATTEMPTS=5`
  - `ARE_PIPELINE_LOCK_TTL_S=900`
- SQLite Robustheit:
  - `ARE_SQLITE_BUSY_TIMEOUT_MS=5000`
  - `ARE_SQLITE_RETRY_COUNT=3`
  - `ARE_SQLITE_RETRY_SLEEP_S=0.2`
- Invalide Läufe blockieren:
  - `ARE_REJECT_INVALID_RUNS=1` (Default)

## Test-App (Arbeitsliste-first)

Start: `python test_app_main.py` — Fenstertitel **AREV2 Test-App**

Die **Arbeitsliste** ist Source of Truth. PDFs werden als Queue-Jobs vorgemerkt und über dieselbe Worker-Logik wie der Headless-Betrieb verarbeitet.

### EXTRACTOR

- **Ergebnisse suchen** — PDFs aus dem Watch-Ordner in die Arbeitsliste übernehmen (optional rekursiv)
- **Dateien hinzufügen** — manuell gewählte PDFs vormerken
- **Automatische Suche** — zyklischer In-App-Scan des Watch-Ordners (Watchdog light, ohne separaten Prozess)
- **Extraktion starten** — wartende Jobs verarbeiten
- **Erneut starten** — ausgewählte fehlgeschlagene Jobs explizit auf `Wartet` setzen (`retry_failed_job`)

Fehlgeschlagene Jobs werden durch erneutes Suchen/Hinzufügen **nicht** automatisch reaktiviert.

### Nacharbeit (RULE SUITE)

Für fehlgeschlagene Läufe mit normalisiertem Dump:

- Assay-Kandidaten anzeigen (read-only Erkennung)
- Draft aus Kandidat erstellen
- Felder aus bestehendem Regelwerk übernehmen
- Rule Editor öffnen, Draft bearbeiten, aktivieren, Job erneut starten

### Duplikate

Tab **DUPLIKATE** listet SQLite-Duplicate-Kandidaten, zeigt Vergleich und unterstützt manuelles Verwerfen.

Weitere Details: `docs/AP14_TEST_APP.md`

## Rule Suite

### Rule Editor (empfohlen)

```powershell
python rule_editor_main.py
```

Editor-Funktionen (Auszug):

- Hybrid-Layout mit Tabs (`Draft`, `PDF/Assay-Text`, `Felder`, `Meta & Excel`, `Validierung & Aktivierung`, `Log`)
- Geführter Anlage-Wizard, Regex-Bibliothek, Markierungs-Ansicht, Undo/Redo, Auto-Save
- Draft-vs-Active-Diff vor Aktivierung

### Inventar und Lifecycle (AP-16C / AP-16D)

Im Draft-Tab **Regelwerk-Verwaltung**:

| Typ | Bedeutung |
|-----|-----------|
| **Aktiv** | produktiv in `rules/index.json` referenziert |
| **Draft** | Arbeitsstand unter `rules/drafts/` |
| **Inaktiv** | deaktiviert unter `rules/inactive/` |

Wichtige Aktionen:

- **Inaktivieren** — aktives Regelwerk aus dem Index entfernen, Datei nach `rules/inactive/` verschieben (kein direktes Löschen aktiver Rules)
- **Löschen** — nur für Drafts und Inaktive nach `rules/trash/`
- **Als Basis für Draft verwenden / klonen** — sicheres Ableiten ohne Überschreiben
- **Draft aus Kandidat** — Nacharbeit aus normalisiertem Dump
- **Format übernehmen** — Felder aus bestehendem Regelwerk in Draft übernehmen

Inaktive Regelwerke werden nicht direkt bearbeitet; stattdessen Kopie nach `rules/drafts/`.

### CLI (optional)

- Draft erstellen: `python rule_suite_main.py create-draft --assay-key "(6bd7)"`
- Felder anzeigen: `python rule_suite_main.py list-fields --assay-key "(6bd7)"`
- Preview: `python rule_suite_main.py preview --pdf input/sample_single.pdf --assay-key "(6bd7)" --draft-path <path>`

## Rules-Integrität prüfen

- `python rules_validate_main.py`

## Rule-/Pipeline-Matrix (Testbetrieb)

- Funktionaler Preview-Check gegen aktive Rulesets und Sample-PDFs:
  - `python rules_matrix_main.py --mode preview`
- Voller E2E-Modus inkl. Write-Pfad:
  - `python rules_matrix_main.py --mode e2e`
- Ergebnisdateien liegen unter `output/verification/`.
- Aktueller Testbetrieb:
  - Baseline: `docs/TESTBASELINE.md`
  - Dedupe-Policy: `docs/DEDUPE_POLICY.md`
  - Known Issues: `docs/KNOWN_ISSUES.md`

## Tests

- `pytest -q`

## Architektur / Embedding

- Architekturüberblick: `docs/ARCHITECTURE.md`
- Embedding/Public API: `docs/EMBEDDING.md`
- Root-Wrapper delegieren auf:
  - `interfaces/cli/`
  - `interfaces/headless/`
  - `interfaces/tk/` (Test-App)

## Build (Feldversuch-Paket)

Kanonischer portabler Build für Windows ohne Python auf dem Ziel-PC:

```powershell
python packaging/build_onedir.py
```

Ausgabe:

| Artefakt | Pfad |
|----------|------|
| Onedir | `packaging/dist_output/AnalyzerResultExtractorV2/` |
| ZIP | `packaging/dist_output/AnalyzerResultExtractorV2.zip` |

Entry der gebündelten EXE: `test_app_main.py` (Test-App, nicht mehr `gui_min.py`).

Auf dem Ziel-PC: ZIP entpacken, `AnalyzerResultExtractorV2.exe` starten.
Optional `$env:ARE_HOME` auf den entpackten Ordner setzen.

Anleitung: `docs/AP17A_FIELD_TRIAL_PACKAGE.md`

Legacy: `AnalyzerResultExtractorV2.spec` ist nur noch Altbestand und **nicht** der bevorzugte Build-Weg.
