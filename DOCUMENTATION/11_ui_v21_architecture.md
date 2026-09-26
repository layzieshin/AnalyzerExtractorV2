# UI V2.1 — Architektur

**Aktueller Produktstand (2026-09-24):** Default ist `AnalyzerDesktopApp` in `interfaces/tk/test_app.py`. Die Sidebar hat fünf Views: **Auswertung** (`dashboard`), **Ergebnisse** (`results`), **Regelwerke** (`rules`), **Einstellungen** (`settings`), **Diagnose** (`diagnostics`). Start ohne Extra-Flag über `test_app_main.py` → `run_entry` → `main()`. `LegacyTestApp` (`TestApp`) bleibt der ausdrückliche Opt-in-Support-Fallback über `ARE_LEGACY_UI=1|true|yes` (Fenstertitel **AREV2 Test-App**, Tabs EXTRACTOR, OPTIONS, RULE SUITE, LOGS, DUPLIKATE, DATENBANK; ADMIN nur mit `ARE_SHOW_ADMIN`). Sie ist weder die normale Produkt-GUI noch entfernt. Ablauf für Anwender: `DOCUMENTATION/13_ui_v21_user_workflow.md`.

**Historischer Dokumentkopf (Phase 0, Gate 0, 2026-09-21):** Charakterisierung / Migrationsplan — keine Produktänderung in Phase 0. Baseline damals: Dirty Working Tree @ `887ded8` auf `master`. Abschnitte, die den damaligen Ist-Zustand beschreiben, bleiben als historische Aufnahme stehen und werden nicht als heutiger Produkt-Default gelesen.

---

## 1. Zweck

**Historisch (Phase 0):** Dieses Dokument fasste den damaligen Ist-Zustand der Desktop-GUI und die Zielarchitektur V2.1 zusammen, bevor ab Phase 1 eine Application-/Controller-Schicht eingeführt wurde. Phase 0 änderte kein sichtbares Produktverhalten. Der heutige Default ist die Produkt-Shell aus dem Vorspann; die Phase-0-Aussagen darunter werden nicht umgedeutet.

Verbindliche Produktentscheidungen und Mockups: `CURSOR_ROADMAP_ANALYZER_EXTRACTOR_V2_2_ORCHESTRATOR_CORRECTED.md` (Orchestrierungspaket). Korrekturen dazu: `CURSOR_ORCHESTRATOR_ADDENDUM_ANALYZER_V2_3.md`.

---

## 2. Governance-Inventar (live Worktree)

Priorität bei Konflikten: Addendum V2.3 §0.1. Danach gilt die projekteigene Analyzer-Governance in `docs/AGENT_GOVERNANCE.md` und `.cursor/agent-system.json`. Eine pauschale QMTool-Übernahme gibt es nicht.

| Pfad | Geltungsbereich | Aktualität | Roadmap-Bezug |
|------|-----------------|------------|---------------|
| `AGENTS.md` | Agenten-/Entrypoint-Guardrails, P0-Dokumentpriorität | 2026-09 (live) | Alle Phasen; Search-before-create |
| `.cursor/rules/00-agent-workflow.mdc` | Schrittweise Ausführung, Verifikationsmatrix | 2026-09 (live) | Jede Phase |
| `.cursor/rules/01-architecture-boundaries.mdc` | Kurzreferenz Modulgrenzen | 2026-09 (live) | Phase 1+ Application-Grenze |
| `docs/AGENT_GOVERNANCE.md` | P0-Ausführungsvertrag: Rollen, Limits, Stop-Status, Gate-Bericht | 2026-09-23 | Agentenausführung |
| `.cursor/agent-system.json` | Normative Rollen, Modelle, Zahlenlimits | 2026-09-23 | Kosten- und Ablaufgrenzen |
| `.cursor/rules/02-agent-governance.mdc` | Always-apply-Verweis auf Governance und JSON | 2026-09-23 | Keine zweiten Zahlen |
| `.cursor/agents/*.md` | Sechs Analyzer-Rollen, lokal | 2026-09-23 | Ein Product-Writer |
| `.cursor/plans/gui_nutzerfunktionen_inventar_6e1ce550.plan.md` | Planungsnotiz GUI-Inventar | 2026-09 | Phase 0 Matrix |
| `README.md` | Menschliches Onboarding, Startbefehle | P0, leicht dirty | Packaging, Entrypoints |
| `docs/ARCHITECTURE.md` | Pipeline, Module, Entrypoints | P0 kanonisch | Phase 1+ Public APIs |
| `docs/EMBEDDING.md` | Einbettungsvertrag `src/*/api.py` | P0 kanonisch | Keine neuen Bypass-Imports |
| `docs/TESTBASELINE.md` | Erwartete pytest-/Matrix-Baseline | P0, Phase-0-Update | Gate 0 |
| `docs/DEDUPE_POLICY.md` | Dedupe-Interpretation | P1 | Duplikat-UX Phase 4/8 |
| `docs/KNOWN_ISSUES.md` | Bekannte Test-/Umgebungsgrenzen | P1 | Tcl/Tk-Skip |
| `docs/AP14_TEST_APP.md` | Test-App-Feldversuch | P1 | Phase 3+ Shell |
| `docs/AP17A_FIELD_TRIAL_PACKAGE.md` | Feldversuchspaket | P1 | Phase 8 Packaging |
| `docs/GUI_USER_FUNCTIONS_INVENTORY.md` | Interaktive Funktionen (Ist) | 2026-09 Entwurf | Phase-0-Matrix-Quelle |
| `docs/GUI_IA_PROPOSAL.md` | IA-Vorschlag | 2026-09 Entwurf | Phase 3 Navigation |
| `docs/RESTRUCTURE_PLAN_EXTERNAL.md` | Externer Restrukturplan | Referenz | Nicht bindend allein |
| `docs/QMTOOLV7_STRUCTURE_COMPARISON_MATRIX.md` | QMTool-Vergleich | P2 Referenz | Migration, nicht Governance |
| `DOCUMENTATION/08_project_takeover_operational_readiness.md` | Betriebsübernahme | P2 historisch+aktuell | Fallback wenn P0 fehlt |
| `DOCUMENTATION/09_rulesuite_authoring_workflow.md` | RuleSuite-Autorenworkflow | RuleSuite-spezifisch | Phase 5–7 |
| `DOCUMENTATION/00_phase0_architecture.md` … `07_phase7_jobcontroller.md` | Phasen-Handoff-Historie | historisch | „Keine UI“ dort = Alt-Phase-0, blockiert GUI-Umbau nicht |
| `DOCUMENTATION/ki_handoff_phase_*.md` | KI-Übergaben Parser→Jobcontroller | historisch | Fachkern-Referenz |

**Analyzer-Governance ist aktiv.** Kanonisch: `docs/AGENT_GOVERNANCE.md` (menschenlesbar) und `.cursor/agent-system.json` (normative Limits/Modelle). Das ist eine eigene Analyzer-Governance, keine pauschale QMTool-Übernahme. Bewusst weiter nicht erzeugt: Root-`GOVERNANCE.md`, Root-`ARCHITECTURE.md` außerhalb `docs/`, QMTool-Hooks, Runtime-Harness, Worktrees und External-Review-Rollen.

**Gate 3 (2026-09-23):** `GATE_PASSED`. Windows/Tk-Smoke ist abgenommen; Details in `docs/TESTBASELINE.md`. **Phase 4:** Implementierung, Review, Vollregression und der reale Windows/Tk-Persistenztest sind abgeschlossen; Gate 4 ist `GATE_PASSED`. **Phase 5:** ebenfalls `GATE_PASSED`. **Phase 6:** dreispaltige RuleSuite-UI abgeschlossen. **Phase 7:** read-only History/Trash-Inventar, History-/Inactive-to-Draft, Review, Vollregression und sichtbare isolierte Lifecycle-Abnahme abgeschlossen; Gate 7 ist `GATE_PASSED`.

**CI/Workflow:** Kein `.github/workflows` im Live-Worktree; Verifikation lokal über `AGENTS.md` / `.cursor/rules/00-agent-workflow.mdc`.

---

## 3. Ist-Architektur (Adapter → API)

### 3.1 Aktueller Default

```text
test_app_main.py
        |
        v
AnalyzerDesktopApp (Default)  |  LegacyTestApp nur bei ARE_LEGACY_UI
        |
        v
interfaces/tk/views/*  →  src.application.api  (extraction, results, rules, settings)
        |
        v
src.processing.api / src.ingestion.api / src.resultstore.api / src.resultvalidation.api / src.rulesuite.api
```

Die Produkt-GUI ist die Sidebar mit den fünf Views aus dem Vorspann. Neue Views orchestrieren über `src.application.api`. Queue und Worker gehoeren `src.processing.api`; `interfaces/common/queue_worker.py` ist nur der duenne Kompatibilitaets-Re-Export. `LegacyTestApp` bleibt der Support-Fallback und teilt dieselbe Moduldatei `interfaces/tk/test_app.py`.

### 3.2 Historische Phase-0-Aufnahme

```text
test_app_main.py / rule_editor_main.py / *_main.py  (dünne Wrapper)
        |
        v
interfaces/tk/test_app.py  |  rule_editor/*  |  interfaces/common/queue_worker.py
        |                           |
        +-------- src.*.api --------+ (jobqueue, jobcontroller, rulesuite, resultstore, runtime, …)
        |
        v
src/<modul>/ (Fachimplementierung hinter api.py)
```

**Historisch (Phase 0), nicht der heutige Default:** `interfaces/tk/test_app.py` — Tabs EXTRACTOR, OPTIONS, RULE SUITE, LOGS, DUPLIKATE, DATENBANK (+ optional ADMIN). Diese Tabs sind heute `LegacyTestApp` und nur mit `ARE_LEGACY_UI` erreichbar.

**Regelwerk-GUI:** `rule_editor/` — eigene Fensterlogik. Fachaufrufe laufen ueber den injizierten `RuleSuiteController` (`src.application.api`). Direkte `src.rulesuite`/`src.parser`/`src.normalizer`-Imports sind entfernt. Phase 6 zerlegt den Widget-Aufbau in private View-Module: Inventar-Startseite sowie dreispaltiger Workspace aus Feldliste, Beispielbericht und Feldeinstellungen; seltene Funktionen bleiben unter `Erweiterte Optionen` erreichbar.

**Queue-Orchestrierung (historische Phase-0-Formulierung, nicht der heutige Owner):** `interfaces/common/queue_worker.py` ruft `src.jobqueue.api` + `src.jobcontroller.api.submit` auf. Wird von Test-App und Headless-Worker geteilt. Aktueller Owner: Abschnitt 3.1.

**Watch-Scan (UI-nah):** `interfaces/tk/watch_scan.py` — dünner Kompatibilitäts-Adapter; Enumeration/Stabilität delegiert an `src.ingestion.api` (keine sichtbare UI-Änderung in Phase 2). Headless-/Service-Owner ab Phase 2: `src/ingestion` + `ExtractionController.run_watch_cycle()`; Legacy `src/watchdog` bleibt kompatibel.

---

## 4. Zielarchitektur V2.1 (ab Phase 1)

**Hinweis zum Lesen:** Die fuenf-View-Shell aus Abschnitt 3.1 ist der heutige Produkt-Default. Die folgende Skizze und die Phasentabelle bleiben der historische Migrationsplan und werden nicht nachtraeglich umgeschrieben.

```text
interfaces/tk/views/*  (Tkinter, Theme, Widgets)
        |
        v
src/application/api.py  →  DesktopAppServices + Controller
        |
        +-- ExtractionController  →  src/processing/api (neu) → jobqueue, jobcontroller, watchdog
        +-- ResultsController     →  resultstore (read), resultvalidation (write, Phase 4)
        +-- RuleSuiteController   →  rulesuite
        +-- SettingsController    →  DesktopSettings (persistent, Phase 1)
        |
        v
bestehende src/<modul>/api.py
```

### 4.1 Migrationsguardrails (bindend)

- GUI orchestriert Persistenz nicht direkt; keine Rule-JSON-Schreibvorgänge aus Views.
- `src/application` importiert **kein** `interfaces.*` und **kein** `tkinter`.
- Neue Views importieren **kein** `sqlite3`, schreiben **keine** Rule-Dateien, umgehen **keine** `src.*.api`.
- **Phase-0-Gates (implementiert in `tests/test_architecture_gates.py`):** rekursive Prüfung von `interfaces/**`, `rule_editor/**`, Root-Grenzskripten; exakte Inventarisierung aller elf erlaubten Root-`*.py`-Dateien (keine zusätzliche Root-Surface); exakte Public-API-Form `src.<modul>.api` (kein `src.foo.bar.api`); striktes View-File-/Storage-I/O-Gate (verbotene Storage-Imports, `open()`, direkte Path-/OS-/Shutil-I/O — ohne Pfad-Herkunftsverfolgung); Live-Scan für `interfaces/tk/views/**`, `interfaces/tk/widgets/**`, `interfaces/tk/app.py` und `src/application/**` ist leer solange Verzeichnisse fehlen.
- **Deferred (ab Phase 1/3):** Existenz-Gates für `src/application/**` und View-Verzeichnisse werden erst ab Einführung der Pakete zusätzlich als „mindestens eine Datei vorhanden“ durchgesetzt; View-Imports dürfen dann nur noch `src.application.api` nutzen.
- Main-App und Rule-Editor teilen **ein** Inventar über `RuleSuiteController` / `src.rulesuite.api` (Gate 5).
- Tkinter bleibt; kein Framework-Wechsel.

### 4.2 Phasenkomponenten

| Komponente | Phase | Anmerkung |
|------------|-------|-----------|
| `src/application/*` | 1 | umgesetzt: Controller-Fassade |
| `src/processing/api.py` | 1–2 | umgesetzt: Queue-/Worker-Owner-Grenze |
| `src/resultvalidation/api.py` | 4 | umgesetzt: Append-only Validation |
| `interfaces/tk/views/*`, `widgets/*` | 3 | umgesetzt: neue Shell-Views |
| Pre-Activation Rule-History | 5 | Fail-closed vor visuellem RuleSuite-Umbau |
| `rule_editor/*_panel.py`, `inventory_view.py`, `workspace.py`, `advanced_view.py`, `toolbar.py` | 6 | private Tk-Views; keine neue Fach-API |

---

## 5. Verträge (Phase-0-Bestätigung)

### 5.1 `src.resultstore` — read-only

Öffentliche API (`src/resultstore/api.py`): ausschließlich Lesefunktionen (`list_result_runs`, `get_result_run`, `list_result_assays`, `list_result_charges`, `get_result_store_status`). Keine Write-/Update-/Relocate-Exporte.

**Schreibpfad für Runs:** `src/dbwriter.api` / Pipeline über `src.jobcontroller.api`.

**Konsequenz V2.1:** PDF-Pfad-Relocation nach Archivierung ist Owner **`src/ingestion`** (Phase 2 umgesetzt); `resultstore` bleibt read-only.

### 5.2 Validation (Phase 4 umgesetzt)

Addendum §6: Owner `src.resultvalidation.api`, append-only `run_validations`, kein stilles Überschreiben. Roadmap-Abschnitt 7.3 (Overwrite-Standard) ist durch Addendum aufgehoben. `validate_run` erzeugt nur die Erstvalidation; `correct_validation` / `replace_validation` fuegt einen neuen Datensatz mit `supersedes_validation_id` hinzu. `ResultsController` liefert aktuelle Validation, Historie und Berichtstatus an die Tk-View.

### 5.3 Watchfolder / Import-Herkunft (Phase 2 umgesetzt, GUI Phase 3)

| Aspekt | Owner |
|--------|--------|
| Import-Instanz-Ledger, Stabilitätsscan, Enqueue-Orchestrierung | `src/ingestion/api` |
| Watch-Zyklus (headless) | `ExtractionController.run_watch_cycle()` |
| Archivierung / Recovery / `current_path` | `src/ingestion/api` (nur `watch_folder` + Queue `DONE`) |
| Persistenz | `<project_root>/storage/ingestion/*.json` |
| Ergebnis-Pfad-Anzeige | `ResultsController` + `resolve_current_path` (additiv) |

Addendum §7: persistenter Import-/Ingest-Zustand (`ingestion_id`, `source_kind` manual|watch_folder, `current_path`, Archivstatus inkl. `RECOVERY_REQUIRED`). Gleicher PDF-Inhalt an zwei Pfaden → gleicher Content-Job möglich, separate `ingestion_id`. Manuell → nie auto-archivieren.

**Ist (Phase 2):** Ledger unter `storage/ingestion/*.json`; Queue-Jobs mit vollem `content_sha256`; `src.ingestion.api` ist Owner fuer Scan/Stabilitaet/Archiv/Recovery. Charakterisierung in `tests/test_ui_v21_characterization.py` und `tests/test_ingestion.py`.

### 5.4 Rule-Lifecycle / Aktivierung

**Historischer Phase-0-Befund:** `activate_draft()` überschrieb aktive JSON ohne verpflichtenden
History-Snapshot. Dieser Befund war in einer isolierten Kopie negativ charakterisiert.

**Ist (Phase 5 und Phase 7, Gate 7 abgeschlossen):** Vor dem Überschreiben eines bestehenden Regelwerks wird ein
byte-genauer Snapshot unter `rules/history/` veröffentlicht. Fehler beim Lesen, Schreiben,
Veröffentlichen oder Verifizieren blockieren die Aktivierung; aktive Datei und Draft bleiben
unverändert. `activate_new_draft()` erzeugt keinen Snapshot. Phase 7 zeigt History und Trash
read-only mit Zeitstempel, SHA-256 und Fehlerstatus. History/Inactive werden ausschliesslich als
neue, nicht ueberschreibende Drafts geoeffnet; aktive Rule und Archivquelle bleiben unveraendert.

### 5.5 Settings (Phase-0-Ist vs. damaliges V2.1-Ziel)

Die Spalte **Ist-Owner** ist die Phase-0-Aufnahme. Live persistiert `SettingsController` die Desktop-Settings inklusive `output_mode` in `storage/desktop_settings.json`; ENV bleibt zusaetzlicher Runtime-Weg. Diese Tabelle wird nicht als heutige Owner-Matrix umgedeutet.

| Setting | Ist-Owner | Ist-Persistenz | V2.1-Ziel |
|---------|-----------|----------------|-----------|
| `output_mode` | `src.runtime.config` / ENV `ARE_OUTPUT_MODE` | ENV, Default `both` | `SettingsController` + DesktopSettings JSON |
| `sqlite_path` | `RuntimeConfig` / ENV `ARE_SQLITE_PATH` | ENV, Default unter `output/final/` | beibehalten, GUI optional versteckt |
| `watch_dir` | `RuntimeConfig` / ENV | ENV | `watch_dir` in DesktopSettings |
| `device_id` | ENV `ARE_DEVICE_ID` | ENV | DesktopSettings |
| `watch_enabled`, `backup_dir`, `operator_initials` | `SettingsController` / DesktopSettings | `storage/desktop_settings.json` | umgesetzt; Initialen als Validation-Default |
| TTL/Lock/Retry-Parameter | `RuntimeConfig` | ENV | Runtime-only, nicht Haupt-GUI |

Keine Semantikänderung ohne Charakterisierungstest + Gate.

---

## 6. Baseline (Gate 0, live gemessen)

| Check | Erwartung Orchestrator | Live (Phase 0 Rework) |
|-------|------------------------|------------------------|
| pytest | 319 passed, 2 skipped (Start) | siehe `docs/TESTBASELINE.md` nach Gate-0-Rework-Lauf |
| Architektur-Gate | 5 passed (Start) | siehe `docs/TESTBASELINE.md` nach Gate-0-Rework-Lauf |
| rules_validate | grün | grün |
| rules_matrix preview | 2 green / 2 yellow / 7 red, exit 1 | erwartete Sample-Coverage-Lücke (kein PASS) |

**Skips:** zwei historische Umgebungs-Skips — fehlendes Tcl/Tk (Test-App-Smoke) vs. Windows-Symlink-Privileg (WinError 1314). Charakterisierungstests für Mehrfachauswahl sind Tk-unabhängig. **Gate 3 (2026-09-23): `GATE_PASSED`.** Der echte Windows/Tk-Smoke ist abgenommen. Phase 4 ist technisch mit 614 bestandenen Tests und einem umgebungsabhängigen Skip abgeschlossen; der spätere sichtbare Windows/Tk-Retest bestätigte die Validierungspersistenz nach Neustart, daher ist Gate 4 `GATE_PASSED`.

---

## 7. Scope-Korrekturen vor Phase 1 *(historical baseline — partially resolved)*

1. **`src/application` und `src/processing.api`** — **implemented** (Phase 1/2); Tk wiring deferred Phase 3.
2. **`operator_initials`** — in DesktopSettings/SettingsController und Settings-/Validation-UI umgesetzt; bewusst keine Benutzerverwaltung.
3. **`watch_enabled`, `watch_input_path`, `watch_backup_path`** — **persisted** in `desktop_settings.json`; GUI exposure deferred Phase 3.
4. **Test-App DATENBANK-Tab** — Legacy bleibt Support-Fallback; die Produkt-Ergebnisansicht nutzt `ResultsController` und `src.resultvalidation.api`.
5. **Rule-Editor** — **implemented in Phase 5:** Fachzugriff nur ueber `RuleSuiteController`; Gate 5 abgeschlossen.
6. **Pre-Activation-History** — **Snapshot implemented in Phase 5; Lifecycle UI completed in Phase 7** (byte-genau, fail-closed, nur beim Ueberschreiben eines bestehenden Regelwerks; History/Trash read-only, History-to-Draft ohne Overwrite).
7. **Import-/Archiv-Persistenz** — **Phase 2 implemented** under `src/ingestion` (hardlink publish, recovery, ledger); GUI deferred Phase 3.
8. **View-/Application-Existenz-Gates** — `src/application/**` live; `interfaces/tk/views/**` deferred Phase 3.

Die Funktionsmatrix in `DOCUMENTATION/11_ui_v21_function_owner_matrix.md` ist gegen Live-Inventar vollständig belegt; **keine** Behauptung der Produktimplementierungsvollständigkeit — offene Ziele bleiben in §N deferred.

---

## 8. Phase-0-Artefakte

| Artefakt | Pfad |
|----------|------|
| Funktions-/Owner-Matrix | `DOCUMENTATION/11_ui_v21_function_owner_matrix.md` |
| Charakterisierungstests | `tests/test_ui_v21_characterization*.py` |
| Rekursive Architektur-Gates | `tests/test_architecture_gates.py` |
| Baseline-Doku | `docs/TESTBASELINE.md` |

---

## 9. Verwandte Dokumente

- `DOCUMENTATION/11_ui_v21_function_owner_matrix.md` — detaillierte Owner-Zuordnung
- `docs/ARCHITECTURE.md` — Pipeline und Entrypoints (P0)
- `docs/EMBEDDING.md` — Public-API-Regeln (P0)
- `AGENTS.md` — Agenten-Guardrails (live Worktree)
- `docs/AGENT_GOVERNANCE.md` — projekteigener Ausführungsvertrag (P0); keine pauschale QMTool-Übernahme
- `DOCUMENTATION/13_ui_v21_user_workflow.md` — aktueller Endnutzer-Ablauf der Produkt-Shell
