# AREV2 Embedding

## Zweck

Dieses Dokument beschreibt die stabile Python-Oberflaeche von AREV2 fuer spaetere Konsumenten. Der Fokus liegt auf Einbettung in andere Anwendungen, ohne AREV2-Interna direkt zu importieren. Das QMTool ist dabei nur ein kuenftiger Konsument; dieses Repo enthaelt weiterhin keinen QMTool-spezifischen Code.

## Public APIs

### Pipeline

- `src.jobcontroller.api.submit` (Default und effektiver neuer Modus `sqlite`; bekannte `both`-/`excel`-Inputs werden normalisiert, unbekannte Modi liefern vor Verarbeitung `FAILED`)
- `src.jobcontroller.api.release_validated_run` / `retry_excel_export` sind stillgelegte Kompatibilitaetsaufrufe: `SKIPPED`, `reason=excel_export_retired`, kein Schreibzugriff und keine Export-Locks. Historische Plaene bleiben unveraendert; Evidence kann `retry_kind=retired` tragen und darf keine ausfuehrbare Wiederholungsaktion aktivieren.
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
- `ResultsController.render_report_pdf_page(report_id, *, page_index=0, zoom=1.0)` liefert `ReportPdfPage` (`report_id`, nullbasierter `page_index`, `page_count`, effektiver `zoom`, `width`, `height`, RGB-PPM-`image_data: bytes`). Aufruf ausserhalb des UI-Threads; der Controller loest die aktuelle PDF-Quelle ueber Ingestion auf und rendert in einem isolierten Prozess. `PdfPreviewError` ist der sichtbare Fehlervertrag fuer fehlende/mehrdeutige/unlesbare PDF, Seiten- oder Prozessfehler. Der Controller akzeptiert endliche positive Zoomwerte und begrenzt sie auf maximal 300 %; Bildlimits koennen weiter reduzieren. Die manuelle UI-Auswahl beginnt bei 25 %, automatische Breitenanpassung darf darunter liegen; 1000 Seiten / 3000 px pro Dimension / 6 Mio. Pixel / 128 MB PDF / 8 s Renderbudget. Kein oeffentlicher Pfad-Renderer, keine MuPDF- oder UI-Objekte im DTO. Einbettende Frozen-Hosts muessen `multiprocessing.freeze_support()` vor ihren UI-Imports im Startpfad aufrufen.
- `RuleSuiteController.discover_assay_candidates` und `discover_assay_candidates_for_job(job_id)` kapseln `src.assaycandidate.api` + `get_job_diagnostic_sources` (Views liefern nur `job_id`).
- `SettingsController.open_output_folder` erstellt den kanonalischen Ausgabeordner `<project_root>/output/final` bei Bedarf und oeffnet ihn kontrolliert; `get_watch_timing()` liefert safe UI-Polling `max(0.5, scan_interval_s or 3.0)` sowie normalisiertes stable window (NaN/±Inf/negativ/zero gemaess Vertrag); `get_device_inventory` / `reload_device_inventory` lesen nur `src.runtime.api`.
- Keine generischen Pfad-Oeffner in `src.application.api.__all__` (`open_path`/`PathOpener` bleiben intern).
- `RuleSuiteController.validate_rules_integrity` delegiert an `src.ruleresolver.api.validate_rules_integrity`.
- Errors: `ApplicationError`, `ApplicationWatchError`, `PathOpenError`, `ReportNotFoundError`, `SettingsLoadError`, `SettingsValidationError`, `SettingsSaveError`, `ValidationInputError`, `ValidationConflictError`
- `SettingsController.load()` liest alte `both`-/`excel`-Werte ohne Dateiaenderung als effektives `sqlite`; normales `save` persistiert SQLite und erhaelt die anderen Settings. Unbekannte JSON-Modi bleiben `SettingsValidationError`, Syntaxfehler `SettingsLoadError`. Runtime-/Processing-Konfigurationen fallen auch bei unbekannten Modi sicher auf SQLite zurueck.

### Application reanalysis extensions (Package 3b)

Package 3b adds the following methods on the existing `ResultsController`:

- `reanalyze_selected_cases(cases, operator_initials, *, request_id)` captures one
  effective store and processes the immutable `ValidationQueueItem` snapshots
  sequentially. `ReanalysisBatchResult` has a per-case revision/error result.
- `choose_reanalysis_result(case, action, operator_initials, *, request_id,
  note="")` explicitly resolves the inspected whole comparison (`keep_old` or
  `accept_new`). It never validates automatically.
- `validate_report_run` / `correct_report_run` accept optional keyword arguments
  `expected_selection_token`, `store_path`, `request_id`. Pass the displayed
  occurrence's binding; do not refresh a token silently at action time.

`ValidationQueueItem` adds `store_path`, `selection_token`, `revision_id`,
`comparison`, field/revision errors and reanalysis history. `ReanalysisComparison`
contains all field/metadata old-new pairs, source proof and permitted choices.
`ReportRunOccurrence` carries the displayed store/token as well. `ResultRunItem`
exposes complete revision/selection history. Existing constructors retain
backward-compatible defaults. `ReanalysisError` is the actionable failure type.

### Result revision owners (Package 3b)

- `src.jobcontroller.api.reanalyze_run(project_root, store_spec, run_id, *,
  expected_selection_token, request_id, operator_initials)` proves the original
  source and uses a frozen active rule in a bounded spawn process. It appends a
  candidate; job files/output plans and original runs are never rewritten.
- `src.jobcontroller.api.processing_eligibility_error` is the shared read-only
  Job/Queue completion check used under the result owners' authoritative lock.
- `src.dbwriter.api.append_result_revision` and `select_result_revision` own
  transactional candidate/selection/accepted-identity writes. Request IDs are
  idempotent; differing reuse and stale tokens raise `ResultRevisionConflictError`.
  Other actionable evidence/field failures use `ResultRevisionError`.
- ResultStore reads return `original_result`, `revision_id`, `selection_id`,
  `selection_token`, `pending_revision`, `result_revisions`, `result_selections`,
  `source_provenance`, `configured_fields`, `missing_fields`, `revision_error`.
  Lists carry the canonical `report_id`; charge filters use selected values.
  `list_result_runs(limit=None)` is uncapped. Reads never migrate schema.
- `src.resultvalidation.api.list_run_validations_readonly(store_spec, run_ids)`
  never creates schema or takes a write lock. Missing metadata means no
  validation; legacy binding means original revision 0. Existing readers keep
  their schema-creating compatibility behavior.
- Validation writes accept `expected_selection_token`, `request_id` and optional
  `project_root`; new initial provenance supplies that context automatically.
  Returned `RunValidation` additionally binds revision/selection/token and request.
  Compatibility without an expected token applies only to untouched originals
  with no pending analysis. Revised selections require the inspected token.
- `src.jobqueue.api.list_jobs(..., create_missing=False)` suppresses directory
  creation for strict read guards; default behavior stays compatible.

Neither raw SQLite connections nor arbitrary source file readers enter views.
`RuleSet.source_text` / `source_sha256` contain the exact one-read rule bytes/hash
(UTF-8 text), with empty defaults for existing programmatic constructors.

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

R1 keeps one embedded release area in the loaded Rule Editor workspace:
`Mit PDFs prüfen` checks the current draft directly; successful proof says it is
not yet activated. Structure-only validation and the single extraction preview
remain technical helpers. The wizard may return a checked draft to the editor;
it never invokes final activation. Dirty meta/field state, PDF selection changes,
draft/root changes and external byte changes require another check. Pure diff,
structure inspection and activation do not reserialize a clean proven draft. The
existing details/log area becomes visible for diff inspection. Proof completion
uses the existing TkTaskRunner queue and main-thread poller; workers never call Tk.

`RuleSuiteController.create_authoring_proof` uses the existing readiness owner.
Proof version 2 captures original draft, index, active rule and PDF bytes under
short lifecycle→draft locks, then runs the real parser/splitter/extractor on
private exact snapshots. The private selected index binding is relocated to the
private active copy, including absolute in-root and symlink-alias inputs; original
bindings/hashes remain frozen in the proof. Update requires a different PDF path
and content, and equality of every previous data field plus `lot_id` on the
reference. Every configured field needs a nonempty real extraction, regardless
of its `required` flag. Proof-only success writes no active/index/history file.
Before ready, the complete current mode/binding/hash context is checked again.
Attempt IDs under short locks prevent an old slow success overwriting a newer
pending/failed attempt; a TTL lock is not held across PDF work. Old proof-version-1
sidecars require a new check; archived QC models/PDFs are unrelated and unchanged.

Both existing lower activation APIs accept optional keyword
`require_authoring_proof=False` for compatibility. Product controller calls always
set it true. Within lifecycle→draft locks, the owner rechecks current mode,
active/index binding and exact verified draft bytes, then publishes that captured
snapshot without rereading unchecked draft data. Proof-required create rejects a
supplied effective assay name differing from the tested draft. The editor issues
exactly one final confirmation per explicit activation attempt; structure errors,
stale UI selection and absent proof never reach it. Backend recheck follows user
confirmation. Existing update history remains exact old bytes and fail-closed.
Central draft-key handling rejects path-like keys under Windows and POSIX semantics
without silently renaming them; existing legitimate technical key mapping stays.

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

### Quality control and device authority (P4/P5)

`src.qualitycontrol.api` owns five `qc_*` tables in the same explicit SQLite
`store_spec` as Results. `get_status`, `get_inventory(include_history=False, include_unregistered=False)`,
`list_profiles(include_history=False)`, `get_profile(version_id)`,
`list_lots(include_history=False)`, `get_lot(lot_key)`, `get_lot_sources` and
`get_report_evidence(lot_version_id=...)` are strict non-migrating readers.
Missing inventory returns visible incomplete legacy identities, never an
authoritative JSON fallback. Evidence returns the exact frozen model/PDF bytes
and verifies their stored hashes.

Optional `unregistered_devices` metadata exposes later historical IDs as an
incomplete editor draft outside the stored inventory snapshot. Only explicit
save registers/completes these identities; browsing does not change authority.

Explicit mutations are `migrate_legacy_devices`, `save_inventory`, `save_profile`,
`open_lot`, `configure_lot`, `reopen_lot`, `close_lot`. Every mutation requires
`MutationContext(operator_initials, request_id, reason="")`; ordinary action
labels supply the audit reason when omitted. Reopening requires an explicit
reason. Version IDs/source tokens from the inspected state are mandatory optimistic
guards. Request reuse with different content fails closed. Repeating a completed
request returns its immutable record. Migration requires the exact hash from
`legacy_device_source(project_root)` and retains original source bytes.

Profiles use stable `profile_id`/`control_id`, complete exact field mappings,
`measurement_date_field`/`measurement_date_format`, explicit `numeric_grammar`
(`decimal_dot`/`decimal_comma`), `unit`, optional extracted `unit_field`,
applicability/relative settings, `run_grouping_field` and the approved
`qc_profile="classic-six-v1"` plus `enabled_rules`. SD is optional: manual values
use positive decimal-point strings; a `confirmed_baseline` freezes exact current
validated source values. Statistical results are additional frozen analysis
fields; the raw reference object, including its P4 calculation marker, stays
unchanged.

Optional `measurement_time_field`/`measurement_time_format` form a strict pair.
Both absent/empty preserve the old normalized profile with no new keys; a partial
pair is rejected. Time formats require exactly one %H and %M, optionally %S;
date/locale/zone tokens and simultaneous time-bearing date formats are rejected.
The separate source branch parses both explicit fields with strict roundtrip,
combines their date/time, adds `measurement_time_raw` only in that branch and
sets explicit ordering. Missing/blank time gives `measurement_time_missing`,
invalid time gives `measurement_time_invalid`, with `measured_at=None` and no
midnight/import fallback. Equal timestamps and unknown-time history barriers
remain. No-map manifests/tokens are unchanged at the same database state;
explicitly saving a new profile still changes the profile head/token as before.
All existing APIs/controllers pass these dictionary fields through; no new
public API/table/migration, statistics version or retroactive evidence edit.

`get_lot_sources(store_spec, profile_version_id=..., kit_lot=...)` captures the
entire relevant population, not a UI page. Its manifest contains current result,
selection and effective validation bindings, raw/parsed values, hashes, full
configuration, all exclusion reasons and a source token. Separate read APIs are
not claimed to form one atomic latest snapshot. A publication rechecks the manifest
under `BEGIN IMMEDIATE`. A closed lot remains frozen; later arrivals need explicit
`reopen_lot`. `close_lot` accepts a supplied frozen analysis model/PDF, hashes and
algorithm/renderer identities. It requires at least one eligible target value
and a proven later use of another lot, independent of that witness's statistical
eligibility or earliest date. `get_lot_chronology(store_spec, *, profile_version_id)`
returns immutable `QCUsageSnapshot(snapshot_json, snapshot_sha256)` with all
projected runs, exact lot identities, selected/pending variants, source/validation
bindings, profile heads/mappings, inventory, lot bindings and pairwise witnesses.
Dates/times are half-open precision intervals; only contiguous explicit H→M→S
components narrow them. Missing/invalid separate time permits at most a whole
day when its date is valid, while remaining statistically excluded. Unknown
revision identity requires group-wide clarification. Equal or overlapping
intervals have no import/run-ID tie-breaker; a proven pair never implies a global
newest lot. Offers and chronology reads never mutate lot state.

New callers pass `expected_chronology_token` and `profile_version_id` to
`close_lot`. The full usage snapshot, current sources/configuration, expected lot
head or expected absence, reference binding and model/PDF checks are verified
under `BEGIN IMMEDIATE`. Legacy direct callers may omit the chronology token;
its current state is captured before the transaction and checked again inside.
`expected_version_id=0` permits a direct first closed revision using empty stored
SD references; no preliminary open revision or incidental reference confirmation
occurs. Closure and exact PDF/model evidence are one atomic write. Analysis and
rendering happen before the transaction; idempotent request intent stays checked.

P5 adds these APIs without changing the five-table schema:

- `analyze_lot(manifest, sd_references, *, sd_reference_context=None) -> QCAnalysis`: pure Decimal analysis of
  the exact captured manifest/token and frozen raw SD references. QMMA, relative
  bound status, computed baseline mean/sample SD, classic-six-v1 findings,
  availability reasons and chart geometry are frozen in canonical JSON.
  Nonempty SD references require evidenced origin context; omission never guesses
  the current profile as their origin. QMMA remains independent.
- `get_sd_reference_context(store_spec, *, lot_key, expected_version_id)` is a
  strict read-only QC-owner orchestration API. It verifies the stored reference
  ID/hash, reads its immutable creation profile through `get_profile`, and for
  legacy manual references proves the complete continuous lot chain. It binds
  the explicit store/lot, raw-reference hash, origin profile snapshot/hash and
  origin version. A changed lot during capture raises `QCConflictError`.
  Pass this returned context to `analyze_lot`; no database I/O enters the math.
- `QCAnalysis(model_json, model_sha256)` validates canonical JSON/hash;
  `QCAnalysis.freeze(mapping)` captures a model and `to_dict()` returns a fresh
  copy. The instance stores no mutable nested model. Exact algorithm/renderer
  and reference identities are inside that model.
- `render_analysis_pdf(analysis, *, include_explanations=False) -> QCPdfReport`: fresh bounded spawn using
  existing MuPDF only in the child main thread. Result fields are `pdf_bytes`,
  `pdf_sha256`, `model_sha256`, `renderer_id`, `page_count`. Limits: 25 s including
  slot wait, 200 pages, 64 MiB PDF, 16 MiB model, 4 KiB metadata. Analysis accepts
  at most 50,000 observed points; excessive/unsupported content fails explicitly
  as `QCReportError`. No dependency or runtime/application import is added to QC.
- `export_report_evidence(store_spec, *, lot_version_id, destination, include_explanations=False)` verifies
  the saved evidence and writes its exact PDF bytes with exclusive creation.
  Existing destinations fail. The default exports exact stored bytes, including
  old v1 evidence. With the strict boolean option enabled, the same renderer
  produces a separate extended print from the stored model only; no live sources,
  reanalysis, store/model update or old-PDF replacement occurs. The mode is bound
  to spawn input and verified metadata. The compact control sections start on
  separate pages and contain only that control's values; explanations are an
  optional appendix. Raw operators and bound validator/UTC data use the frozen
  manifest, with explicit missing/ambiguous states and no invented time.

Manual SD is centered on consistent SOLL. Confirmed baseline SD uses the frozen
mean/sample SD (`n-1`); a later source population cannot enlarge the baseline.
No usable SD means SD bands/Westgard unavailable, while QMMA remains independent.
Strict threshold equality, current-group structural 2-SD trigger, explicit
analytical grouping, chronological ambiguity and unusable-observation barriers
are part of `arev2-qc-analysis-v2`. Raw list/run-ID ordering is not chronology.
The model freezes `sd_reference_context` in addition to the exact unchanged
`source_manifest` and raw `sd_references`. SD compatibility compares stable
profile/device/assay/control identity, mapped IST, numeric grammar and effective
unit/unit field. Name/date/group/rule/relative-bound/SOLL/MIN/MAX changes alone
do not invalidate a compatible SD. Missing/unprovable context gives
`sd_origin_unavailable`; mismatches give `sd_unit_incompatible` or
`sd_parameter_incompatible`, with no SD bands/z scores/Westgard availability.
Newly declared manual references include `profile_version_id` before reference
ID hashing, so the same numeric SD can be deliberately redeclared under a new
unit. Existing by-ID references are copied exactly, never retrospectively
modified. Supported archived v1 models retain their exact JSON/hash and PDF;
no default context is injected into historical evidence. `QCAnalysis.is_supported`
bounds display/render support to the four prior model-version-1 combinations of
v1/v2 analysis and v1/v2 renderer, plus exactly model version 2 / analysis v3 /
renderer v3, and exactly model version 3 / analysis v4 / renderer v4. New models freeze independent manufacturer/single-value percentage
limits, point findings and exact `chart.reference_lines`; UI/PDF draw those values
without recomputation. Percentage exceedance never changes statistical inclusion
or Westgard run status. The current renderer can print supported archived v1
models without changing their JSON/hash or retrofitting percentage lines.
Export of original evidence remains independent.

P4 (2026-11-13) adds frozen schema-3 fields without new public calls or database
tables: per-level `descriptive` with availability/value/reason for mean,
`sample_sd` (n-1), `cv_percent`, plus n and a fixed descriptive version; `period`
with readable start/end dates and unknown-date count; per-point `position`,
`measurement` (actual contiguous clock precision and raw counterpart), and
`deviation.absolute` / `deviation.relative_percent`. Only already eligible
values enter statistics; SD needs n>=2, CV positive mean, relative deviation
positive SOLL. These empirical statistics never create a Westgard SD reference.
Mean reference lines and findings summaries are frozen by QC, not calculated by
UI/PDF. Literal schema-2/v3/v3 compatibility remains intact; old archive models
are not enriched. The compact A4 standard renderer includes the primary right
legend, measurements and important position-bound findings/exclusion reasons.
Complete raw/source/validator evidence remains in the unchanged frozen model;
the footer identifies that digital model. No JSON/raw-data attachment is added.
`include_explanations=True` additionally prints the point-bound technical evidence,
methods, references and full rule details; that optional print may use more pages.
Explicit configured source grouping is the sole analytical-run label; technical
result IDs remain labeled evidence identities. Missing source metadata is not
inferred from the layout reference or other people fields.

Use existing Application controllers for UI work:
`SettingsController.get_qc_configuration`, `migrate_qc_devices`,
`save_qc_inventory`, `save_qc_profile`; `ResultsController.list_qc_lots`,
`get_qc_lot_detail`, `save_qc_lot`, `reopen_qc_lot`,
`get_qc_analysis(detail, evidence_lot_version_id=None)`,
`list_qc_report_versions(case)`, `list_qc_close_witnesses(detail)`,
`prepare_qc_lot_close(detail) -> QCLotClosePreview`,
`close_qc_lot(preview, operator_initials=..., request_id=...)`
and `export_qc_report(case, evidence_lot_version_id=..., destination=..., include_explanations=False)`.
`QCAnalysisView` carries canonical model/hash and optional archived evidence
version/hash; `QCReportVersion` identifies a stored report revision. Current open
analysis recaptures/rechecks sources. Closed or historical analysis loads only
the stored model and checks lot ownership; unknown historical model versions
fail explicitly rather than being silently recalculated. `QCLotCase` adds last-use
and offer/clarification presentation; `QCLotDetail` adds the captured usage context
and a live-source-change flag. Preparation is strictly read-only, binds the frozen
analysis and actual verified PDF bytes/hash, and rechecks the complete context
after rendering. Cancellation or late callbacks cannot publish. Final confirmation
publishes only that preview through the existing atomic API; it performs no new
PDF rendering. During the write, cancel/window-close are disabled. Closed lots
retain an independent live-change notice beside their archived model view.
The public DTOs `QCConfigurationState`, `QCLotCase`, `QCLotDetail` carry their inspected effective
store. A store switch rejects mutations even when database-local IDs coincide.
Errors are `QualityControlApplicationError`. Four controllers/services and seven
views remain; no new entrypoint or cross-repository dependency is required.
The explicit Statistics navigation owns the single existing QC presentation in
`StatisticsView`, still using ResultsController. ResultsView retains report
lists/details and report validation. The existing TaskRunner callbacks/store
guards, chart model, history and PDF options are moved rather than duplicated.

Assay-name fields are additive DTO defaults at the end of existing records.
`ReportAssayGroup.assay_display_label` remains the group display field; identities
remain `assay_key`/run/lot IDs. Names prefer the selected revision's ruleset (or
the original source ruleset), then public stored Writer/Splitter evidence, then
the active catalog through the existing RuleSuiteController. Pending revision
names and filename hints never replace the current name. Missing names display
"Assayname fehlt"; duplicate-name selectors preserve index/key identity. New
QC models freeze a separate `presentation` mapping with assay/run names; exact
source manifests, raw SD refs, math and existing evidence are unchanged.

Runtime device compatibility functions below keep their positional arguments
and require keyword `store_spec=...`; omitted stores fail with an actionable error.
No facade picks its own default database or reads the legacy JSON. Explicit
historical selected IDs require only a valid store specification; before
inventory setup `DEFAULT_DEVICE` remains incomplete and QC-ineligible. Lazy QC
imports prevent the ResultValidation -> JobController -> Runtime import cycle.

### Runtime compatibility functions

- `src.runtime.api.load_runtime_config`
- `src.runtime.api.get_build_info` (code-relative pyproject version in source;
  EXE-adjacent build-info.json when frozen; independent of ARE_HOME; unavailable
  metadata returns `version="UNKNOWN"`, never a guessed release identity).
  `SettingsController.get_build_info` exposes this to the existing shell.
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
adressiert stabile `run_id`-Werte. Erstvalidation und Korrektur rufen keinen Excel-Writer oder Release-Pfad auf; der kompatible Rueckgabe-DTO meldet `excel_export_status=not_required` und einen leeren Exportfehler. Ein normaler `validate_run` ersetzt nie einen bestehenden
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
