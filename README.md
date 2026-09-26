# PDF Ergebnis-Extractor (Projekt)

- Windows 11 Zielumgebung
- `src/` ist Project Root (in PyCharm markieren)
- Public APIs existieren ausschließlich in `src/<module>/api.py`
- `api.py` ist die stabile Public Boundary; Implementierungsdetails bleiben hinter `src/<module>/api.py`
- Root-Entrys delegieren nur noch in `interfaces/cli` oder `interfaces/headless`
- `main.py` und `main02.py` sind Harnesses für den End-to-End Lauf (immer `sample_single.pdf` + `sample_multi.pdf`)
- Tests liegen unter `/tests` (pytest)

## Start

### Feldversuch / Produkt-UI (empfohlen)

```powershell
python test_app_main.py
```

Startet die **Analyzer Result Extractor** Desktop-Oberfläche (Sidebar mit Auswertung, Ergebnisse, Regelwerke, Einstellungen, Diagnose). Primärer Workflow: PDFs verarbeiten, Auto-Import konfigurieren, Ergebnisse und Klärfälle prüfen, Regelwerke validieren.

In **Ergebnisse** werden alle Assays eines Berichts gemeinsam angezeigt. Einzelne Runs können
mit lokal gespeicherten Operator-Initialen und einem optionalen Kommentar validiert werden.
Eine bestehende Validation wird nie still überschrieben: Die separate Aktion
**Validierung korrigieren** legt nach Bestätigung einen neuen, verknüpften Historieneintrag an.
SQLite bleibt die strukturierte Source of Truth. Excel ist der nachgelagerte Export und kein Validation-Speicher. Schlägt nur die Excel-Ausgabe fehl, bleibt das gespeicherte SQLite-Ergebnis stehen. Die Diagnose zeigt dann genau `Ergebnis gespeichert – Excel-Ausgabe fehlgeschlagen`. **Erneut verarbeiten** wiederholt in diesem Fall nur den eingefrorenen Excel-Export: die PDF und die aktuellen Regelwerke werden nicht neu gelesen, erfolgreiche SQLite-Ergebnisse werden nicht erneut geschrieben.

Alltagstauglicher Ablauf: `DOCUMENTATION/13_ui_v21_user_workflow.md`.

Details: `docs/AP14_TEST_APP.md`, Feldversuch-Paket: `docs/AP17A_FIELD_TRIAL_PACKAGE.md`

Legacy-Tab-UI (EXTRACTOR/OPTIONS/…) nur bei Bedarf:

```powershell
$env:ARE_LEGACY_UI = "1"
python test_app_main.py
```

`ARE_SHOW_ADMIN=1` gilt nur für die Legacy-UI (optionaler ADMIN-Tab). Rule Editor: Regelwerke-Ansicht oder `rule_editor_main.py`.

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

### Headless Phase 2 (Watchfolder + Archiv)

- Watch ist **standardmaessig deaktiviert** (`watch_enabled=false` in `storage/desktop_settings.json`).
- Vor dem Watchdog: `watch_enabled=true` sowie gueltige `watch_input_path` und `watch_backup_path` setzen.
- Isolierter Laufzeit-Root: `$env:ARE_HOME = "I:\pfad\zum\isolierten-home"` (leere `jobs/`, `input/`, `output/`, `storage/` werden bei Bedarf angelegt).
- **Produktion:** `watchdog_main.py` und `worker_main.py` dauerhaft parallel (kontinuierlicher Scan + Queue-Verarbeitung).
- **One-Shot Watchdog** (`ARE_WATCHDOG_ONCE=1`): fuehrt Stabilitaetsbeobachtungen aus; enqueued erst nach konfiguriertem Stabilitaetsfenster.
- **One-Shot Worker** (`ARE_WORKER_ONCE=1`): verarbeitet **einen** wartenden Job; zum Leeren der Queue wiederholt starten.
- Erfolgreiche Queue-Jobs (`DONE`) werden archiviert; `FAILED` wird **nicht** archiviert.
- Manuell hinzugefuegte PDFs werden **nie** automatisch verschoben (nur Watchfolder-Importe).

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
- Das lokale Operator-Kürzel für die Ergebnisvalidation wird in der Produkt-UI unter
  **Einstellungen** gepflegt (`operator_initials` in `storage/desktop_settings.json`).
- Invalide Läufe blockieren:
  - `ARE_REJECT_INVALID_RUNS=1` (Default)

## LegacyTestApp / Support-Fallback (nur mit ARE_LEGACY_UI)

Die tabbed **LegacyTestApp** (`TestApp`) ist kein Default mehr. Sie bleibt für Support, Vergleich und historische Bedienpfade verfügbar:

```powershell
$env:ARE_LEGACY_UI = "1"
python test_app_main.py
```

Fenstertitel: **AREV2 Test-App**. Optionaler Support-Tab **ADMIN** (technische Queue-Rohdaten) — **nur in der Legacy-UI**:

```powershell
$env:ARE_LEGACY_UI = "1"
$env:ARE_SHOW_ADMIN = "1"
python test_app_main.py
```

Legacy-Standard-Tabs: **EXTRACTOR**, **OPTIONS**, **RULE SUITE**, **LOGS**, **DUPLIKATE**, **DATENBANK**.

In der Legacy-UI ist die **Arbeitsliste** Source of Truth. PDFs werden als Queue-Jobs vorgemerkt und über dieselbe Worker-Logik wie der Headless-Betrieb verarbeitet.

GUI-Inventar und IA-Vorschlag (Legacy-Kontext): `docs/GUI_USER_FUNCTIONS_INVENTORY.md`, `docs/GUI_IA_PROPOSAL.md`.

Details: `docs/AP14_TEST_APP.md` (Abschnitt LegacyTestApp).

### Legacy: EXTRACTOR

- **Ergebnisse suchen** — PDFs aus dem Watch-Ordner in die Arbeitsliste übernehmen (optional rekursiv)
- **Dateien hinzufügen** — manuell gewählte PDFs vormerken
- **Automatische Suche** — zyklischer In-App-Scan des Watch-Ordners (Watchdog light, ohne separaten Prozess)
- **Extraktion starten** — wartende Jobs verarbeiten
- **Fehler erneut verarbeiten** — ausgewählte fehlgeschlagene Jobs explizit auf `Wartet` setzen (`retry_failed_job`)

Fehlgeschlagene Jobs werden durch erneutes Suchen/Hinzufügen **nicht** automatisch reaktiviert.

### Legacy: Nacharbeit (RULE SUITE)

Für fehlgeschlagene Läufe mit normalisiertem Dump (nur Legacy-UI):

- **Nacharbeit wiederholen** — ausgewählte fehlgeschlagene Jobs erneut in die Queue stellen
- Assay-Kandidaten anzeigen (read-only Erkennung)
- Draft aus Kandidat erstellen
- Felder aus bestehendem Regelwerk übernehmen
- Rule Editor öffnen, Draft bearbeiten, aktivieren, Job erneut starten

### Legacy: Duplikate

Tab **DUPLIKATE** (nur Legacy-UI) listet SQLite-Duplicate-Kandidaten, zeigt Vergleich und unterstützt manuelles Verwerfen.

## Rule Suite

### Rule Editor (empfohlen)

```powershell
python rule_editor_main.py
```

Editor-Funktionen (Auszug):

- Inventar als Startseite und dreispaltiger Arbeitsbereich: Feldliste, Beispielbericht, Feldeinstellungen
- Geführter Anlage-Wizard, Regex-Bibliothek, Markierungs-Ansicht, Undo/Redo und Auto-Save; seltene Funktionen unter `Erweiterte Optionen`
- Draft-vs-Active-Diff vor Aktivierung

### Inventar und Lifecycle (AP-16C / AP-16D)

Auf der Inventar-Startseite **Regelwerke**:

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
  - `interfaces/tk/` (Produkt-Shell `AnalyzerDesktopApp`; Legacy `LegacyTestApp`)

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

Entry der gebündelten EXE: `test_app_main.py` (Produkt-Shell, nicht mehr `gui_min.py`).

Auf dem Ziel-PC: ZIP entpacken, `AnalyzerResultExtractorV2.exe` starten.
Optional `$env:ARE_HOME` auf den entpackten Ordner setzen.

Anleitung: `docs/AP17A_FIELD_TRIAL_PACKAGE.md`

Legacy: `AnalyzerResultExtractorV2.spec` ist nur noch Altbestand und **nicht** der bevorzugte Build-Weg.
