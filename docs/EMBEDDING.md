# AREV2 Embedding

## Zweck

Dieses Dokument beschreibt die stabile Python-Oberflaeche von AREV2 fuer spaetere Konsumenten. Der Fokus liegt auf Einbettung in andere Anwendungen, ohne AREV2-Interna direkt zu importieren. Das QMTool ist dabei nur ein kuenftiger Konsument; dieses Repo enthaelt weiterhin keinen QMTool-spezifischen Code.

## Public APIs

### Pipeline

- `src.jobcontroller.api.submit`
- `src.jobcontroller.api.get_job_evidence` (read-only Job-State/Evidence fuer Application-Diagnose)
- `src.jobcontroller.api.get_job_diagnostic_sources` (vollstaendige validierte Job-Dump-Texte fuer Owner-Discovery; kein Pfad-Lesen aus Views)
- Rueckgabewert: `src.jobcontroller.api.JobResult`; Evidence-DTO: `src.jobcontroller.api.JobEvidence` (Display-Cap `context_text` max. 32 000 Zeichen; `context_source_label`/`context_source_kind`)

### Application (preferred for new views)

- `src.application.api.create_desktop_services`
- `src.application.api.DesktopAppServices` with `extraction`, `results`, `rules`, `settings`
- Controllers: `ExtractionController`, `ResultsController`, `RuleSuiteController`, `SettingsController`
- DTOs: `DesktopSettings` (Gate-1-kompatibel: positional `(output_mode, sqlite_path, watch_dir, device_id)`; Keyword `watch_dir`; Felder `watch_enabled`, `watch_input_path`, `watch_backup_path`, `watch_recursive`), `ProcessingItem`, `ProcessingOutcome`, `ProcessingEnqueueOutcome`, `ProcessingBatchSummary`, `WatchCycleSummary`, `ImportRecordItem`, `IngestionInstanceItem`, `JobDiagnosisItem` (inkl. `context_text`/`context_truncated`), `ReportSummaryItem`, `ReportDetail`, `ReportAssayGroup`, `ReportRunOccurrence`, `ReportFieldValue`, `DuplicateCandidateItem`, `DuplicateCandidateDetail`, `DuplicateExistingRunItem`, `DuplicateDecisionResult`, `AssayCandidateItem`, `WatchTimingSettings`, `DeviceInventoryStatus`, `ResultStoreStatus`, `ResultRunItem` (additiv `source_pdf_path`, `current_pdf_path`, `ingestion_id`, `path_status`), `RulesetInventoryItem`, …
- `ProcessingOutcome` ist queue-/extraktionsbezogen; `ImportRecordItem` / `IngestionInstanceItem` tragen `archive_status` pro Ingestion-Instanz. `ExtractionController.list_ingestion_instances` / `get_ingestion_instance` fuehren Queue + Ledger zentral zusammen (Queue-only-Fallback). `map_ingestion_display_status` / `friendly_processing_message` liefern den nutzerfreundlichen Statusvertrag.
- `ExtractionController.list_job_diagnoses` / `get_job_diagnosis` liefern Nacharbeit-Diagnose ohne direkten Job-JSON-Zugriff in Views (`src.jobcontroller.api.get_job_evidence` inkl. begrenztem `context_text`; `context_source_label` aus Owner-Grenze).
- `ExtractionController.run_watch_cycle(stable_window_s=None)` nutzt safe-normalisiertes `RuntimeConfig.watch_stable_window_s` (wie `SettingsController.get_watch_timing()`), wenn kein Override gesetzt ist; `watch_recursive` wird aus `DesktopSettings` an `src.ingestion.api.run_watch_scan_cycle` durchgereicht.
- `ResultsController.list_recent_reports` / `get_report_detail` / `open_report_pdf` (Report-Gruppierung owner-seitig in `src.resultstore.api`: `job_id` primaer, Legacy via normalisierter `pdf_path` + `LEGACY_REPORT_TIME_WINDOW_S=5.0`; `limit` erst nach Gruppierung); Status via `src.jobqueue.api` + exakte `ingestion_id`. `validate_report_run` erzeugt die Erstvalidation, `correct_report_run` ausschliesslich eine explizite append-only Korrektur. Duplikat-APIs liefern reichhaltige DTOs (`dedupe_basis`, `candidate_meta`, `DuplicateExistingRunItem`) aus `src.dbwriter.api`.
- `RuleSuiteController.discover_assay_candidates` und `discover_assay_candidates_for_job(job_id)` kapseln `src.assaycandidate.api` + `get_job_diagnostic_sources` (Views liefern nur `job_id`).
- `SettingsController.open_output_folder` erstellt den kanonalischen Ausgabeordner `<project_root>/output/final` bei Bedarf und oeffnet ihn kontrolliert; `get_watch_timing()` liefert safe UI-Polling `max(0.5, scan_interval_s or 3.0)` sowie normalisiertes stable window (NaN/±Inf/negativ/zero gemaess Vertrag); `get_device_inventory` / `reload_device_inventory` lesen nur `src.runtime.api`.
- Keine generischen Pfad-Oeffner in `src.application.api.__all__` (`open_path`/`PathOpener` bleiben intern).
- `RuleSuiteController.validate_rules_integrity` delegiert an `src.ruleresolver.api.validate_rules_integrity`.
- Errors: `ApplicationError`, `ApplicationWatchError`, `PathOpenError`, `ReportNotFoundError`, `SettingsLoadError`, `SettingsValidationError`, `SettingsSaveError`, `ValidationInputError`, `ValidationConflictError`
- `SettingsController.load()` wirft bei ungueltigem JSON-Overlay `SettingsValidationError` (semantisch) bzw. `SettingsLoadError` (Syntax)

### Processing (queue/worker orchestration)

- `src.processing.api.ProcessingConfig`
- `src.processing.api.ProcessingResult`
- `src.processing.api.ProcessingJob`
- `src.processing.api.enqueue_pdf` (optional `expected_sha256`)
- `src.processing.api.list_processing_jobs`
- `src.processing.api.retry_failed`
- `src.processing.api.process_next_pending` (`submit_func=None` → Laufzeit-Lookup von `src.jobcontroller.api.submit`)
- `src.processing.api.default_worker_id`
- `src.processing.api.config_from_runtime_defaults`

### Ingestion (import ledger, watch scan, archive)

- `src.ingestion.api.register_import`
- `src.ingestion.api.run_watch_scan_cycle` (optional `recursive`; von `DesktopSettings.watch_recursive` durchgereicht)
- `src.ingestion.api.reconcile_processing_for_job`
- `src.ingestion.api.reconcile_archive_recovery`
- `src.ingestion.api.retry_archive`
- `src.ingestion.api.resolve_current_path`
- `src.ingestion.api.list_import_records`
- `src.ingestion.api.list_watch_pdf_paths` / `observe_stable_pdfs` (kanonische Enumeration/Stabilitaet; Tk `watch_scan` delegiert hierher)
- DTOs: `ImportRecord`, `WatchCycleResult`, `PathResolution`, Archive-Status inkl. `RECOVERY_REQUIRED`, …

### Headless / Queue

- `src.watchdog.api.scan_watch_once`
- `src.watchdog.api.run_watchdog_forever`
- `src.jobqueue.api.enqueue_pdf_job` (optional `expected_sha256`; additive voller SHA-256 in `QueueJob.content_sha256` — akzeptierte Phase-2-Scope-Erweiterung)
- `src.jobqueue.api.claim_next_job`
- `src.jobqueue.api.mark_job_done`
- `src.jobqueue.api.mark_job_failed`
- `src.jobqueue.api.mark_job_pending`
- `src.jobqueue.api.retry_failed_job`
- `src.jobqueue.api.recover_stale_jobs`
- `src.jobqueue.api.list_jobs`
- DTO: `src.jobqueue.api.QueueJob`

### Assay-Kandidaten (read-only)

- `src.assaycandidate.api.find_assay_candidates`
- `src.assaycandidate.api.annotate_assay_candidates`
- `src.assaycandidate.api.load_known_assay_keys`
- `src.assaycandidate.api.canonical_assay_key`

Read-only Erkennung aus normalisierten Dumps fuer Nacharbeit; keine Schreibpfade.

### Rules / Rule Authoring

Der Rule-Editor (`rule_editor/`, `rule_editor_main.py`) spricht Authoring nur ueber `RuleSuiteController` aus `src.application.api`. Direkte `src.rulesuite`-, `src.parser`- oder `src.normalizer`-Imports sind dort nicht zulaessig. `required_header_field_keys` ist der read-only Pflichtfeldvertrag. `load_normalized_pdf_text` ist der PDF-Volltext-Fallback und darf intern `src.parser.api` sowie `src.normalizer.api` nutzen. `activate_draft` eines bestehenden Regelwerks veroeffentlicht vorher einen byte-genauen Snapshot unter `rules/history/`; Fehler sind fail-closed. `activate_new_draft` erzeugt keinen Snapshot. History/Trash-Inventar ist read-only; `open_history_as_draft` und `open_inactive_as_draft` publizieren ausschliesslich neue, nicht ueberschreibende Drafts. Die privaten View-Module exportieren keine neue Fach-API. Gate 7 ist nach isolierter sichtbarer Lifecycle-Abnahme `GATE_PASSED`.

Kern:

- `src.rulesuite.api.*` (Draft-Authoring, Preview, Aktivierung; fuer Adapter nur hinter `RuleSuiteController`)
- `src.ruleresolver.api.resolve_ruleset`
- `src.ruleresolver.api.validate_rules_integrity`

Inventory / Lifecycle (AP-16C, AP-16D):

- `src.rulesuite.api.list_rulesuite_inventory`
- `src.rulesuite.api.clone_ruleset_to_draft`
- `src.rulesuite.api.deactivate_ruleset`
- `src.rulesuite.api.delete_inventory_item`
- `src.rulesuite.api.open_history_as_draft`
- `src.rulesuite.api.open_inactive_as_draft`
- `src.rulesuite.api.delete_ruleset` (Kompatibilitaets-Wrapper auf `deactivate_ruleset`)

Nacharbeit / Kandidaten (AP-16A–16B):

- `src.rulesuite.api.read_candidate_fields`
- `src.rulesuite.api.check_candidates`
- `src.rulesuite.api.adopt_candidate_field`
- `src.rulesuite.api.adopt_candidate_fields`

DTO/Error exports:

- `src.contentsplitter.api.AssayDescriptor`
- `src.ruleresolver.api.RuleSet`
- `src.ruleresolver.api.RuleResolverError`
- `src.extractor.api.AssayRecord`
- `src.extractor.api.ExtractionError`

### Runtime

- `src.runtime.api.load_runtime_config`
- `src.runtime.api.resolve_app_root`
- `src.runtime.api.resolve_device_id`
- `src.runtime.api.get_default_device_id`
- `src.runtime.api.get_device_config_status`
- `src.runtime.api.list_devices`
- `src.runtime.api.try_acquire_exclusive`
- `src.runtime.api.release_exclusive`
- `src.runtime.api.is_stale_lock`

### Test UI Helpers

- `src.testui.api.*` (Presenter fuer Test-App: Arbeitsliste, Nacharbeit, Duplikate, DB-Viewer, Formatierung)

### Result Store (read-only)

- `src.resultstore.api.get_result_store_status`
- `src.resultstore.api.list_result_assays`
- `src.resultstore.api.list_result_charges`
- `src.resultstore.api.list_result_runs`
- `src.resultstore.api.get_result_run`

### Result Validation (append-only write owner)

- `src.resultvalidation.api.get_run_validation`
- `src.resultvalidation.api.list_run_validations`
- `src.resultvalidation.api.validate_run`
- `src.resultvalidation.api.correct_validation` / `replace_validation`
- DTOs: `RunValidation`, `RunValidationList`

Alle Funktionen verwenden denselben `store_spec`-Vertrag wie `src.resultstore.api`. Validation
adressiert stabile `run_id`-Werte. Ein normaler `validate_run` ersetzt nie einen bestehenden
Datensatz; nur die explizite Korrektur fuegt einen neuen Datensatz mit
`supersedes_validation_id` hinzu. Das Modul schreibt ausschliesslich seine eigene
`run_validations`-Tabelle und veraendert keine extrahierten Messwerte.

## Nicht-Public

Diese Pfade gelten als intern und duerfen von externen Konsumenten nicht direkt importiert werden:

- `src.<modul>.model`
- `src.<modul>.service`
- `src.jobcontroller.jobcontroller`
- `src.jobqueue.queue`
- `src.runtime.config`
- `src.runtime.paths`
- `src.runtime.file_lock`
- `src.rulesuite.templates`
- `src.testui.helpers`
- `interfaces.tk.test_app` (Adapter-UI, keine Public API)
- `interfaces.common.queue_worker` (duenner Re-Export; Fachlogik in `src.processing.api`)
- `src.processing.service` (intern)
- `src.application.*` ausser `src.application.api` (intern; Views importieren nur `api.py`)

## Pfad- und Laufzeitvertrag

- API-Aufrufe, die `project_root` erwarten, meinen das AREV2-Arbeitsverzeichnis mit `rules/`, `input/`, `jobs/`, `locks/` und `output/`.
- `ARE_HOME` kann gesetzt werden, um den beschreibbaren Laufzeit-Root fuer Standalone- oder eingebettete Runs explizit festzulegen.
- `resolve_app_root()` nutzt folgende Prioritaet:
  1. `ARE_HOME`
  2. PyInstaller-Exe-Verzeichnis
  3. uebergebener Modulpfad / aktueller Prozesskontext

## Packaging fuer Einbettung

- Das Repo kann per `pip install -e .` als Entwicklungs-Dependency eingebunden werden.
- Die Importpfade bleiben unveraendert, z. B.:

```python
from src.jobcontroller.api import submit
from src.jobqueue.api import retry_failed_job
from src.runtime.api import load_runtime_config
from src.assaycandidate.api import find_assay_candidates
```

- Diese Packaging-Schicht ersetzt nicht den Standalone-Build. Fuer Kunden-Bundles bleibt `packaging/build_onedir.py` die kanonische Variante (Entry: `test_app_main.py`).

## QMTool-Hinweis

- Das QMTool soll AREV2 spaeter nur als Konsument der hier dokumentierten Public APIs verwenden.
- Modulvertrag, PyQt-Integration, Navigation oder QM-spezifische Settings liegen bewusst ausserhalb dieses Repos.
