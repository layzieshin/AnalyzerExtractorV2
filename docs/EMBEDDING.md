# AREV2 Embedding

## Zweck

Dieses Dokument beschreibt die stabile Python-Oberflaeche von AREV2 fuer spaetere Konsumenten. Der Fokus liegt auf Einbettung in andere Anwendungen, ohne AREV2-Interna direkt zu importieren. Das QMTool ist dabei nur ein kuenftiger Konsument; dieses Repo enthaelt weiterhin keinen QMTool-spezifischen Code.

## Public APIs

### Pipeline

- `src.jobcontroller.api.submit`
- Rueckgabewert: `src.jobcontroller.api.JobResult`

### Headless / Queue

- `src.watchdog.api.scan_watch_once`
- `src.watchdog.api.run_watchdog_forever`
- `src.jobqueue.api.enqueue_pdf_job`
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

Kern:

- `src.rulesuite.api.*` (Draft-Authoring, Preview, Aktivierung)
- `src.ruleresolver.api.resolve_ruleset`
- `src.ruleresolver.api.validate_rules_integrity`

Inventory / Lifecycle (AP-16C, AP-16D):

- `src.rulesuite.api.list_rulesuite_inventory`
- `src.rulesuite.api.clone_ruleset_to_draft`
- `src.rulesuite.api.deactivate_ruleset`
- `src.rulesuite.api.delete_inventory_item`
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
- `interfaces.common.queue_worker` (interner Adapter-Helfer)

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
