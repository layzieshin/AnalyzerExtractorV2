# UI V2.1 — Funktions-/Owner-Matrix (Phase 0)

**Stand:** 2026-09-21  
**Baseline:** Dirty Working Tree @ `887ded8`  
**Legende Disposition:** `behalten` | `verschieben` | `verstecken` | `ersetzen` | `legacy`

Vollständige Matrix aller **bestehenden sichtbaren Benutzerfunktionen** → Ist-Owner → V2.1-Ziel (gegen Live-Inventar belegt). Keine Funktion ohne Zielowner. **Keine** Behauptung der Produktimplementierungsvollständigkeit — offene Ziele siehe §N.

Quellen: `interfaces/tk/test_app.py`, `rule_editor/*`, `docs/GUI_USER_FUNCTIONS_INVENTORY.md`, Roadmap V2.2 + Addendum V2.3.

---

## A. Test-App — Global

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test (Phase 0+) |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|----------------------|
| Tab wechseln | `test_app.py` Notebook | — | — | Shell-Navigation | — | `shell.py` Sidebar | ersetzen | `test_test_app_smoke.py` | Gate 3 Smoke |
| Statuszeile / Fortschritt | `test_app.py` global | Thread-Callbacks | — | Shell | — | `shell.py` | verschieben | `test_test_app_smoke.py` | — |
| Fenster schließen / Auto-Suche stoppen | `test_app.py` `WM_DELETE_WINDOW` | `stop_auto_watch` | — | ExtractionController + Shell | `ExtractionController` | Auswertung | verschieben | `test_test_app_smoke.py` | — |

---

## B. EXTRACTOR — PDF-Verarbeitung, Queue, Watch

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| Ergebnisse suchen (Watch-Scan) | EXTRACTOR Button | `InAppWatchScanner`, `list_watch_pdf_paths` | — | Watch-Scanner + Queue | `ExtractionController` | Auswertung (Auto-Import) | verschieben | `test_in_app_watch_scan.py` | `test_ui_v21_characterization.py` |
| Dateien hinzufügen (Mehrfach) | EXTRACTOR Dialog | `enqueue_pdf_job` | `jobs/queue/*.json` | Queue-Ingest | `ExtractionController` | Auswertung Import-Karte | ersetzen | `test_test_app_smoke.py`, `test_jobqueue.py` | `test_ui_v21_characterization.py` |
| Unterordner einbeziehen | EXTRACTOR Checkbox | `run_watch_scan_cycle(recursive=…)` via `ExtractionController` | `DesktopSettings.watch_recursive` | Watch-Scanner | `ExtractionController` | Auswertung | behalten | `test_in_app_watch_scan.py`, `test_application_extraction_controller.py` | — |
| Extraktion starten | EXTRACTOR Button | `process_next_pending`, `submit` | Queue + Pipeline-Locks | Queue/Worker via `src.processing.api` | `ExtractionController` | Auswertung / Verarbeitungsliste | verschieben | `test_worker_status_mapping.py`, `test_jobcontroller_*` | `test_ui_v21_characterization.py` |
| Extraktion stoppen | EXTRACTOR Button | UI-Flag `_stop_extraction_event` | — | Queue/Worker | `ExtractionController` | Auswertung | behalten | `test_test_app_smoke.py` | — |
| Fehler erneut verarbeiten | EXTRACTOR Kontext | `retry_failed_job` | Queue JSON | Queue | `ExtractionController` | Verarbeitungsliste | verschieben | `test_jobqueue.py` | — |
| Queue aktualisieren | EXTRACTOR Aktualisieren | `list_jobs` | Queue JSON | Queue (read) | `ExtractionController` | Verarbeitungsliste | verschieben | `test_test_app_smoke.py` | — |
| Automatische Suche start/stop | EXTRACTOR Toggle | `_schedule_auto_watch`, Scanner | — | Watch-Automatik | `ExtractionController` | Auswertung Auto-Import | ersetzen | `test_test_app_smoke.py` | — |
| Ergebnis-/Arbeitsliste (laufende Jobs) | EXTRACTOR Treeview | `list_jobs`, lokale `_watch_rows` | Queue + UI-State | Processing DTOs | `ExtractionController` | Verarbeitungsliste | ersetzen | `test_test_app_smoke.py` | Gate 3 |
| Spalten sortieren | EXTRACTOR Treeview | `TreeviewSorter` | — | UI-only | — | Verarbeitungsliste | behalten | `test_tk_scroll_helpers.py` | — |

**Watchfolder-Archivierung (Phase 2 headless):** `interfaces/headless/watchdog.py` → `ExtractionController.run_watch_cycle()` → `src/ingestion.api` (Import-Ledger + Archiv/Recovery). Tk `interfaces/tk/watch_scan.py` ist ein dünner Kompatibilitäts-Adapter (Enumeration/Stabilität delegiert an `src.ingestion.api`); keine sichtbare UI-Änderung in Phase 2 — GUI-Verdrahtung weiter Phase 3.

---

## C. OPTIONS / Einstellungen

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| Output-Modus (`excel`/`sqlite`/`both`) | OPTIONS Combobox | `load_runtime_config`, ENV | ENV `ARE_OUTPUT_MODE` | Runtime + DesktopSettings | `SettingsController` | Einstellungen (technisch versteckbar) | behalten | `test_runtime_config.py` | `test_ui_v21_characterization.py` |
| SQLite-Pfad | OPTIONS Entry | `RuntimeConfig.sqlite_path` | ENV `ARE_SQLITE_PATH` | Runtime + DesktopSettings | `SettingsController` | Einstellungen (Admin/Diagnose) | verstecken | `test_runtime_config.py` | `test_ui_v21_characterization.py` |
| Watch-Ordner | OPTIONS Entry | `RuntimeConfig.watch_dir` | ENV `ARE_WATCH_DIR` | DesktopSettings | `SettingsController` | Auswertung + Einstellungen | verschieben | `test_runtime_config.py` | — |
| Gerät wählen | OPTIONS Combobox | `list_devices`, `device_id` | ENV `ARE_DEVICE_ID` | DesktopSettings | `SettingsController` | Einstellungen | behalten | `test_runtime_devices.py` | — |
| Geräte neu laden | OPTIONS Button | `list_devices` | Device-Registry | Runtime | `SettingsController` | Einstellungen | behalten | `test_runtime_devices.py` | — |
| Anzeigen (Summary) | OPTIONS Button | `_refresh_options_summary` | — | Settings DTO | `SettingsController` | Einstellungen | ersetzen | — | Phase 1 Controller-Test |
| **`operator_initials`** (Validation) | Einstellungen | `SettingsController.load/save` | `desktop_settings.json` | DesktopSettings | `SettingsController` | Ergebnisdetail + Einstellungen | **Phase 4 umgesetzt** | `test_application_settings_controller.py` | `test_desktop_ui_v21.py` |
| **`backup_dir`, `watch_enabled`** | *noch nicht persistent* | — | — | DesktopSettings | `SettingsController` | Auswertung Auto-Import | **neu Phase 1/2** | — | Phase 2 |

---

## D. RULE SUITE (Test-App-Tab) — Nacharbeit, nicht Authoring

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| Nacharbeit aktualisieren | RULE SUITE | `build_rework_items` (testui) | Queue/Job-JSON | Rework read | `ExtractionController` | Diagnose / selten | verstecken | `test_testui_helpers.py` | — |
| Filter Nacharbeit | RULE SUITE | testui helpers | — | UI-State | — | Diagnose | verstecken | `test_testui_helpers.py` | — |
| Kontext anzeigen | RULE SUITE | Job-Dump | Queue | Result/Job read | `ResultsController` | Diagnose | verstecken | — | — |
| Rule Editor öffnen | RULE SUITE | `subprocess` → `rule_editor_main` | — | Shell/Navigation (Entrypoint) | — (UI-only) | Regelwerke | behalten | `test_test_app_smoke.py` | — |
| Nacharbeit wiederholen | RULE SUITE | `retry_failed_job` / enqueue | Queue | Queue | `ExtractionController` | Verarbeitungsliste | verstecken | `test_jobqueue.py` | — |
| Rules validieren | RULE SUITE | `validate_rules_integrity` | `rules/index.json` read | RuleSuite | `RuleSuiteController` | Regelwerke / Diagnose | behalten | `test_ruleresolver.py`, CLI | — |
| Assay-Kandidaten prüfen | RULE SUITE | `check_candidates` | — | AssayCandidate | `RuleSuiteController` | Regelwerke | behalten | `test_assaycandidate.py` | — |
| Draft aus Kandidat | RULE SUITE | `create_draft_from_template_if_missing` | `rules/drafts/` | RuleSuite | `RuleSuiteController` | Regelwerke / Workspace | behalten | `test_rulesuite.py` | — |

---

## E. LOGS / DUPLIKATE / DATENBANK

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| LOGS anzeigen/kopieren | LOGS Tab | In-Memory `txt_logs` | — | Diagnose | — (UI-only) | Hilfe / Diagnose Dialog | verstecken | — | — |
| Duplikate listen | DUPLIKATE Tab | `list_duplicate_candidates` | SQLite dedupe table | DbWriter read | `ResultsController` | Ergebnisse (Ausnahme) | verstecken | `test_dbwriter.py` | — |
| Duplikat verwerfen | DUPLIKATE | `discard_duplicate_candidate` | SQLite write | DbWriter | `ResultsController` | Kontext Duplikat | verstecken | `test_dbwriter.py` | — |
| Feldvergleich Duplikat | DUPLIKATE | `get_duplicate_candidate` | SQLite | DbWriter | `ResultsController` | Kontext | verstecken | `test_dbwriter.py` | — |
| DATENBANK — Assays/Runs lesen | DATENBANK Tab | `list_result_*`, `get_result_run` | SQLite runs | Resultstore read | `ResultsController` | **Ergebnisse** (ersetzt Tab) | ersetzen | `test_resultstore.py` | `test_ui_v21_characterization.py` |
| Spaltenauswahl DB | DATENBANK | testui presenters | — | UI-State | — | Ergebnisdetail | ersetzen | `test_testui_helpers.py` | — |
| Run validieren | Ergebnisdetail | `src.resultvalidation.api.validate_run` | SQLite `run_validations` | ResultValidation | `ResultsController` | Validation-Panel | **Phase 4 umgesetzt** | `test_resultvalidation.py` | `test_application_results_controller.py`, `test_desktop_ui_v21.py` |
| Validation korrigieren | Ergebnisdetail | `src.resultvalidation.api.correct_validation` | append-only `run_validations` | ResultValidation | `ResultsController` | explizite Korrektur mit Bestätigung | **Phase 4 umgesetzt** | `test_resultvalidation.py` | `test_desktop_ui_v21.py` |

---

## F. ADMIN (optional `ARE_SHOW_ADMIN=1`)

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| Queue-Rohdaten | ADMIN Tab | `list_jobs` raw | Queue JSON | Queue (read) | `ExtractionController` | Diagnose / Technische Details | verstecken | — | — |

---

## G. Rule Editor — Inventar & Lifecycle

Phase-7-Stand: die Editor-Aufrufe laufen weiterhin ueber `RuleSuiteController.list_inventory` und die uebrigen Controller-Methoden. Das Inventar ist die Startseite; der Rule-Änderungsflow wechselt in den dreispaltigen Workspace. Gate 7 ist abgeschlossen; die sichtbare isolierte Abnahme bestaetigte read-only History/Trash, History-/Inactive-to-Draft und Abbruch ohne Draft-Overwrite.

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| Inventarliste Active/Draft/Inactive/History/Trash | Inventar-Startseite | `list_rulesuite_inventory` | `rules/`, `drafts/`, `inactive/`, `history/`, `trash/` | RuleSuite | `RuleSuiteController` | Regelwerke Inventar | Phase 7 umgesetzt; History/Trash read-only | `test_rule_editor_inventory_lifecycle.py`, `test_rulesuite.py` | `test_rule_editor_phase6_layout.py` |
| Filter Inventar | Inventar-Startseite | inventory filters | — | UI-State | — (UI-only) | Regelwerke | behalten | `test_rule_editor_inventory_lifecycle.py` | — |
| Deaktivieren | Inventar-Aktion | `deactivate_ruleset` | `rules/` → `inactive/` | RuleSuite | `RuleSuiteController` | Regelwerke | behalten | `test_rulesuite.py` | isolierte Kopie |
| Löschen / Trash | Inventar-Aktion | `delete_inventory_item` | `trash/` | RuleSuite | `RuleSuiteController` | Regelwerke Trash | behalten | `test_rulesuite.py` | isolierte Kopie |
| Inaktiv → Draft | Inventar-Aktion | `open_inactive_as_draft` | drafts | RuleSuite | `RuleSuiteController` | Workspace | behalten | `test_rulesuite.py` | isolierte Kopie |
| Undo / Redo | Workspace + Shortcuts | `HistoryMixin` (`load_draft`/`save_draft`) | Draft JSON | RuleSuite | `RuleSuiteController` | Workspace | behalten | `test_rulesuite.py` (indirekt) | — |
| Autosave / Dirty-Tracking | Erweiterte Optionen | `HistoryMixin._schedule_autosave` | Draft JSON | RuleSuite | `RuleSuiteController` | Workspace | behalten | — | Phase 5 Controller-Test |
| Hilfe / i-Buttons | Workspace-Bereiche | `GuideMixin._show_help` | — | UI-Hilfe | — (UI-only) | Workspace / Wizard | behalten | — | `test_rule_editor_phase6_layout.py` |
| Rule-Version-History ansehen / als Draft oeffnen | Inventar-Startseite | `list_rulesuite_inventory`, `open_history_as_draft` | `rules/history/` read, `rules/drafts/` exclusive create | RuleSuite | `RuleSuiteController` | Regelwerke Historie / Workspace | Phase 7 umgesetzt; Archiv read-only, kein Draft-Overwrite | `test_rulesuite.py`, `test_application_rules_controller.py` | `test_rule_editor_controller_routing.py` |

---

## G2. Rule Editor — Projekt, Assay, Clone, Feldimport

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| Projektroot wählen | Top-Bar „Ordner…“ | `on_pick_root` | — | Settings | `SettingsController` | Workspace Header | behalten | — | Phase 1 |
| Assays neu laden | Top-Bar Button | `_reload_assays` | `rules/index.json` read | RuleSuite | `RuleSuiteController` | Workspace Header | behalten | `test_rulesuite.py` | — |
| Step-by-Step | Top-Bar Button | `open_step_by_step` / `guide.py` | — | UI-Hilfe | — (UI-only) | Wizard sekundär | behalten | — | — |
| Regelwerk klonen/kopieren | Inventar / Clone-Dialog | `CloneRulesetDialog`, `clone_ruleset_to_draft` | drafts | RuleSuite | `RuleSuiteController` | Workspace | behalten | `test_rulesuite.py` | — |
| Felder aus aktivem Regelwerk importieren | Erweiterte Optionen | `on_adopt_fields_from_ruleset`, `adopt_candidate_fields` | draft JSON | RuleSuite | `RuleSuiteController` | Workspace | behalten | `test_rulesuite.py` | — |

---

## H. Rule Editor — Draft / PDF / Felder / Meta

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| Draft aus aktiver Rule | Inventar-Startseite | `create_draft`, `clone_ruleset_to_draft` | `rules/drafts/` | RuleSuite | `RuleSuiteController` | Workspace Header | behalten | `test_rulesuite.py`, `test_rule_editor_draft_actions.py` | `test_ui_v21_characterization_rules.py` |
| Blank Draft / Wizard | Inventar / Wizard | `create_draft_from_template`, `wizard.py` | drafts | RuleSuite | `RuleSuiteController` | Workspace / Wizard sekundär | behalten | `test_rule_editor_wizard_focus.py` | — |
| Draft speichern | Draft | `save_draft` | drafts JSON | RuleSuite | `RuleSuiteController` | Workspace | behalten | `test_rulesuite.py` | isolierte Kopie |
| Beispiel-PDF laden | Workspace Mitte | `get_assay_text` | — | RuleSuite | `RuleSuiteController` | Workspace Mitte | behalten | `test_rulesuite.py` | — |
| Assay-Text / Zeilen | Workspace Mitte | normalizer/parser via rulesuite | — | RuleSuite | `RuleSuiteController` | Workspace | behalten | — | — |
| Feld anlegen/bearbeiten | Workspace links/rechts | `add_field`, `update_field`, … | draft JSON | RuleSuite | `RuleSuiteController` | Workspace links/rechts | behalten | `test_rulesuite.py` | — |
| Pflichtfeld setzen | Fields | field `required` | draft JSON | RuleSuite | `RuleSuiteController` | Feldeinstellungen | behalten | `test_rulesuite.py` | — |
| Meta & Excel | Meta-Tab | `set_excel_rules`, `set_dedupe_fields` | draft JSON | RuleSuite | `RuleSuiteController` | Erweiterte Optionen | behalten | `test_rule_editor_meta_actions.py` | — |

---

## I. Rule Editor — Markierung, Regex, search_from, Preview

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| Text/Zeile markieren | Beispielbericht | Tk Text selection | — | UI + RuleSuite | `RuleSuiteController` | Workspace Mitte | **behalten (Algorithmus)** | `test_rule_editor_markings.py` | — |
| Muster aus Markierung | Regex-Actions | `suggest_regex_from_selection`, `build_regex_from_builder_spec` | draft | RuleSuite | `RuleSuiteController` | Feldeinstellungen | behalten | `test_regex_suggest.py`, `test_regex_builder.py` | — |
| Regex-Bibliothek | Feldeinstellungen + Erweitert | `RegexLibraryPopup`, `on_open_regex_library` | — | RuleSuite | `RuleSuiteController` | Feldeinstellungen | Phase 6 umgesetzt | — | `test_rule_editor_phase6_layout.py` |
| Batch-Regex-Check | Felder-Tab | `on_batch_regex_check`, `batch_check_fields` | — | RuleSuite | `RuleSuiteController` | Feldeinstellungen | behalten | `test_rulesuite.py` | — |
| Ergebnisliste leeren | Felder-Tab | `_clear_regex_results` | — | UI-State | — (UI-only) | Feldeinstellungen | behalten | — | — |
| Markierungs-Sichtbarkeit umschalten | Beispielbericht | `_toggle_selected_marking_visibility`, `_apply_marking_visibility` | — | UI + RuleSuite | `RuleSuiteController` | Workspace Mitte | behalten | `test_rule_editor_markings.py` | — |
| Markierungs-Builder | Beispielbericht | `MarkingsMixin` Builder-Widgets | draft JSON | RuleSuite | `RuleSuiteController` | Workspace Mitte | behalten | `test_rule_editor_markings.py` | — |
| Feld umbenennen / verschieben | Felder-Tab | `rename_field`, `move_field` | draft JSON | RuleSuite | `RuleSuiteController` | Feldeinstellungen | behalten | `test_rulesuite.py` | — |
| `search_from` setzen (Zeile/Marker/vorherige Zeile) | Marking-Actions | `update_field` search_from | draft JSON | RuleSuite | `RuleSuiteController` | Feldeinstellungen | behalten | `test_rule_editor_markings.py` | — |
| Feldtreffer farbig markieren | Marking-Actions | `locate_fields`, `batch_check_fields` | — | RuleSuite | `RuleSuiteController` | Workspace Mitte | behalten | `test_rule_editor_markings.py` | — |
| Markierung → Feld laden | Marking-Actions | UI binding | — | UI | — | Workspace | behalten | `test_rule_editor_markings.py` | — |
| Regex testen | Felder-Tab (`on_test_regex`) | `test_regex` | — | RuleSuite | `RuleSuiteController` | Feldeinstellungen | behalten | `test_rulesuite.py` | — |
| Gesamtpreview / Preview Extract | Release/Validierung | `preview_extract` | — | RuleSuite | `RuleSuiteController` | Workspace | behalten | `test_rulesuite.py` | `test_ui_v21_characterization_rules.py` |
| Validierung Draft | Erweiterte Optionen | `validate_draft`, `check_required_fields` | — | RuleSuite | `RuleSuiteController` | Workspace | behalten | `test_rulesuite.py` | — |
| Diff Draft vs Active | Release | `diff_draft_vs_active` | — | RuleSuite | `RuleSuiteController` | Erweitert | behalten | `test_rulesuite.py` | — |
| **Als aktiv setzen** | Release | `activate_draft`, `activate_new_draft` | `rules/*.json`, index | RuleSuite (+ History Phase 5) | `RuleSuiteController` | Workspace Header | behalten | `test_rulesuite.py` | `test_ui_v21_characterization_rules.py` (negativ, temporär Phase 0) |

---

## J. Excel-/Output-Aktionen (Pipeline, nicht direkte GUI)

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| Excel schreiben | Pipeline (Worker) | `writer.api`, `jobcontroller` | `output/final/*.xlsx` | Writer + Jobcontroller | `ExtractionController` (Status) | Ergebnisdetail „Ausgabeordner“ | behalten | `test_writer.py`, `test_jobcontroller_dual_output.py` | deferred — kein Phase-2-Export-Retry (Archiv-Retry nur ingestion) |
| SQLite Runs schreiben | Pipeline | `dbwriter.api` | SQLite | DbWriter | Jobcontroller | intern | behalten | `test_dbwriter.py` | — |
| Ausgabeordner öffnen | *teilweise DATENBANK* | OS shell | — | SettingsController | `SettingsController` | Ergebnisdetail | **Phase 3A** | `test_application_settings_controller.py` | — |
| PDF öffnen | *begrenzt* | `ResultsController.open_report_pdf` (injizierbarer OS-Opener) | aufgeloester `current_pdf_path` | Import/Result path owner | `ResultsController` | Ergebnisdetail | **Phase 3A read-only API** | `test_application_results_controller.py` | Phase 3B GUI |

---

## K. Headless / Legacy

| Ist-Funktion | Ist-Einstieg/View | Ist-Service/API | Persistenz-Owner | Ziel-Owner | Ziel-Controller | Ziel-View | Disposition | Bestehender Test | Neuer Test |
|--------------|-------------------|-----------------|------------------|------------|-----------------|-----------|-------------|------------------|------------|
| Watchdog einmalig | `watchdog_main.py` | `src.application.api` (via `interfaces/headless/watchdog.py`) | Ingestion-Ledger + Queue | `src.ingestion.api` + Processing | `ExtractionController` | — (headless) | behalten | `test_watchdog.py`, `test_watch_archive.py` | — |
| Worker einmalig | `worker_main.py` | `interfaces/headless/worker.py` | Queue | Processing | `src.processing.api` | — | behalten | `test_worker_status_mapping.py` | — |
| Direct Submit (Legacy) | `gui_min_ext.py` | `jobcontroller.submit` direkt | Pipeline | legacy | — | legacy | legacy | — | — |
| E2E Harness | `main02.py` | `interfaces/cli/e2e.py` | Jobs/Output | Jobcontroller | — | — | behalten | `test_embedding_smoke.py` | — |

---

## L. Settings-Matrix (Pflicht Addendum §8)

| Key | Ist-Quelle | Default / Semantik | V2.1 GUI-Sichtbarkeit | Ziel-Persistenz | Verlust verboten |
|-----|------------|--------------------|-----------------------|-----------------|------------------|
| `output_mode` | ENV `ARE_OUTPUT_MODE` | `both`; steuert Excel/SQLite | versteckt / Diagnose | DesktopSettings + ENV fallback | ja |
| `sqlite_path` | ENV `ARE_SQLITE_PATH` | `{root}/output/final/results.sqlite3` | versteckt / Admin | DesktopSettings + ENV | ja |
| Excel-/Output-Verzeichnis | Writer/Runtime Pfade | unter `output/final/` | Ergebnisdetail Link | Runtime | ja |
| Watch-Eingangsordner | ENV `ARE_WATCH_DIR` | `{root}/input/watch` | Auswertung Auto-Import | DesktopSettings | ja |
| Watch-Backupordner | *nicht persistent* | — | Auswertung Auto-Import | DesktopSettings Phase 2 | neu |
| Watch aktiv | Test-App UI-State | Auto-Scan an/aus | Auswertung Toggle | DesktopSettings | ja |
| `watch_recursive` | Test-App Checkbox / DesktopSettings | Default `false`; rekursiver Watch-Scan | Auswertung Auto-Import | DesktopSettings | ja |
| `operator_initials` | DesktopSettings | leer; getrimmt; lokales Kürzel, keine Identität | Einstellungen + Ergebnisdetail Validation | `storage/desktop_settings.json` | ja |
| `device_id` | ENV `ARE_DEVICE_ID` | optional | Einstellungen | DesktopSettings | ja |
| Scan-/Stable-/TTL-/Lock-/Retry | ENV (`ARE_*`) | siehe `RuntimeConfig` | nicht in Haupt-GUI | Runtime ENV only | ja |

---

## M. Charakterisierte Ist-Verträge (Kurz)

| Thema | Ist-Befund | Ziel-Phase |
|-------|------------|------------|
| Resultstore | read-only public API | unverändert; Relocation anderer Owner |
| Validation | append-only Owner `src.resultvalidation.api`; Resultstore bleibt read-only | Phase 4 umgesetzt; Gate 4 nach sichtbarem Persistenztest `GATE_PASSED` |
| Rule-Aktivierung | historischer Phase-0-Befund: Überschreiben ohne Snapshot | **Phase 5 umgesetzt:** byte-genauer, fail-closed Snapshot vor bestehender Aktivierung; Gate 5 abgeschlossen |
| Gleicher PDF-Inhalt, zwei Pfade | content-`job_id`; ein Queue-Eintrag; `pdf_path` bleibt Erstpfad; zwei `ingestion_id` | `src.ingestion.api` (Phase 2) |
| Queue `source` | String auf Job (z. B. manual, watch, test-app-auto-watch) | Phase 2 `source_kind` persistenter |

---

## N. Offene Scope-Korrekturen / Deferred

| ID | Thema | Status |
|----|-------|--------|
| SC-1 | `src/application` package | **Phase 3A implemented** — Readmodels/DTOs + Desktop-Aktionen; Tk shell wiring **Phase 3B** |
| SC-2 | Pre-Activation-History | **Phase 5 umgesetzt:** Snapshot byte-genau und fail-closed; History-Anzeige/Restore deferred; Gate 5 abgeschlossen |
| SC-3 | Import-/Archiv-Persistenz | **Phase 2 implemented** (`src/ingestion` ledger + hardlink archive + recovery) |
| SC-4 | Rule-Editor + Test-App Inventar-Lesewege | **Phase 5 umgesetzt:** gemeinsame Quelle `RuleSuiteController.list_inventory`; Gate 5 abgeschlossen |
| SC-5 | `ExtractionController` watch/archive orchestration | **implemented** via `src.application` + `src.ingestion.api`; GUI deferred Phase 3B |
| SC-6 | Mehrfachauswahl-/Duplicate-Pfad-Verhalten vs. Addendum §7 | Ist charakterisiert; Produktänderung Phase 2 |
| SC-7 | View-Existenz-Gates (`interfaces/tk/views/**`) | Live-Scan leer; Helper-Tests aktiv; **Existenz-Gate ab Phase 3** |

**Phase 2 (Gate 2):** Import-/Archiv-Semantik headless unter `src/ingestion` umgesetzt (exclusive hardlink publish, partial recovery, stale-ledger reconciliation). Queue-Archiv-Eligibility nur bei `DONE`. GUI-Verdrahtung deferred Phase 3. *(No Phase 2 export-retry scope — archive retry is ingestion-only.)*
