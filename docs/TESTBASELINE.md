# AREV2 Test Baseline

Date: 2026-09-22 (Phase 2 / Gate 2 — technical closure)

Purpose: reproducible reference point for the V2.1 GUI refactor orchestration. Supersedes the 2026-07-09 AP-1 baseline (`74 passed` is **obsolete**).

**Latest evaluated gate:** Gate 7 is `GATE_PASSED` on 2026-09-24. The final focused lifecycle slice completed with **158 passed**, the independent checkpoint review returned **GO**, and the single post-review full regression completed with **665 passed, 1 skipped**. Repository and isolated-root rules integrity passed; the visible isolated Windows/Tk flow confirmed History/Trash inventory, History-to-Draft, Inactive-to-Draft, read-only Trash, and non-overwriting cancellation. Gates 4–6 remain `GATE_PASSED`. The Phase 2 table below remains the historical Gate 2 record.

## Current evidence (Phase 2 / Gate 2 — authoritative)

| Check | Result |
|---|---|
| pytest inventory (total cases) | **448** |
| pytest (full suite, orchestrator, fresh basetemp) | **PASS**, **445 passed**, **3 skipped**, 448 total cases, **44.94s** |
| pytest (full suite, Cursor comparison, fresh basetemp) | **PASS**, **447 passed**, **1 skipped**, 448 total cases — same inventory; pass/skip split differs by Tcl/Tk + symlink env only |
| pytest (focused Phase 2 slice, orchestrator) | **PASS**, **126 passed**, **1 skipped** (known WinError 1314 symlink privilege skip) |
| pytest architecture gates | **PASS**, **35 passed** |
| rules_validate_main.py | **PASS**, all integrity lists empty |
| rules_matrix_main.py --mode preview | **Expected non-green**, 2 green / 2 yellow / 7 red; **exit code 1** |
| watchdog_main.py one-shot (`ARE_HOME` isolated smoke) | **PASS**, `watch_disabled`, exit 0 |
| worker_main.py one-shot (`ARE_HOME` isolated smoke) | **PASS**, `[worker] no_pending_jobs`, exit 0 |

**Skip variance (no failures):** Orchestrator full suite **3 skipped** vs Cursor **1 skipped** at the same **448**-case inventory. Only known cause classes: Tcl/Tk installation resolution and Windows symlink privilege (WinError 1314). Not a lost test case and not an unexplained skip class.

Basetemp label (Gate 2 verification): `output\.pytest-orchestrator-phase2-gate2-<timestamp>` (use a **new unique** local path per fresh count comparison).

### Product-data integrity (live vs safety snapshot)

Exact hash comparison at Gate 2 closure — **diff 0** across all checked trees:

| Tree | File count | Diff |
|------|------------|------|
| `rules/` | 22 | 0 |
| `jobs/` | 2302 | 0 |
| `input/` | 2 | 0 |
| `storage/` | 0 | 0 |
| `output/final/` | 8 | 0 |
| `output/quarantine/`, `retry/`, `failed/` | 0 | 0 |

No live `storage/` ingestion record was created or mutated during Gate 2 verification. No product-data changes. No `.tmp` verification artifacts remain in the repository.

### Changed scope (Phase 2 summary)

- **New owner:** `src.ingestion.api` — watchfolder ingest, archive, import-record persistence.
- **Jobqueue:** additive full-content SHA on enqueue (dedupe / identity).
- **Settings:** watch-related fields persisted (`watch_enabled`, `watch_backup_path`, etc.).
- **Headless:** `ARE_HOME` resolution + one-shot env (`ARE_WATCHDOG_ONCE`, `ARE_WORKER_ONCE`).
- **Legacy scanner adapters:** thin `interfaces/headless/*`, `interfaces/tk/watch_scan.py` delegating to public APIs.
- **Recovery / no-overwrite:** archive and import paths avoid overwriting existing targets.

### Contract note (ProcessingOutcome vs archive status)

`ProcessingOutcome` remains **content-job / queue scoped** (one outcome per queue job execution). Archive status and error detail are **per ingestion instance** via `ImportRecordItem` list/get on `src.ingestion.api`, because one content job can serve multiple import records.

### Deferred (not claimed in Gate 2)

- Visible GUI / Phase 3 wiring (Test-App tabs not reworked for ingestion UX).
- Operator initials field and operator-facing validation UI.
- Export retry flows.
- Human Tk acceptance smoke — **not performed**; no GUI acceptance claimed.

## Commands

Run from repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs --basetemp output\.pytest-orchestrator-phase2-gate2-<timestamp>
.\.venv\Scripts\python.exe -m pytest tests/test_architecture_gates.py -q
.\.venv\Scripts\python.exe rules_validate_main.py
.\.venv\Scripts\python.exe rules_matrix_main.py --mode preview
```

Focused Phase 2 slice (orchestrator evidence path):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ingestion.py tests/test_watch_archive.py tests/test_watchdog.py tests/test_application_extraction_controller.py tests/test_application_results_controller.py tests/test_application_services.py tests/test_application_settings_controller.py tests/test_architecture_gates.py -q -rs
```

Adapter one-shot smokes (**mandatory** when `interfaces/common/*` or headless adapters change; per workflow matrix in `.cursor/rules/00-agent-workflow.mdc`):

```powershell
$env:ARE_WATCHDOG_ONCE="1"; .\.venv\Scripts\python.exe watchdog_main.py
$env:ARE_WORKER_ONCE="1"; .\.venv\Scripts\python.exe worker_main.py
```

Optional (out of Gate 2 scope):

```powershell
.\.venv\Scripts\python.exe main02.py
```

**Adapter-smoke isolation note (current):** Headless adapters resolve `project_root` via `ARE_HOME` when set (`resolve_app_root()`); without `ARE_HOME` they still fall back to the repository checkout root. For non-destructive smokes, set `ARE_HOME` to an isolated empty home (see Gate 2 Report §6) or use the isolated subprocess tests in `tests/test_watchdog.py`.

Use a **new unique** local basetemp for each fresh count comparison (do not reuse an old path as “fresh”):

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs --basetemp output\.pytest-orchestrator-phase2-gate2-<timestamp>
```

## Historical — Phase 2 final cleanup (2026-09-22, superseded by Gate 2)

> **Historical only.** Superseded by the authoritative Phase 2 / Gate 2 baseline above (inventory **448**, dual-run skip variance).

| Check | Result |
|---|---|
| pytest (full suite, fresh basetemp) | **PASS**, 447 passed, 1 skipped, **448** total cases (~42s) |
| pytest architecture gates | **PASS**, 35 passed |

Basetemp (final cleanup verification): `I:\Projekte\AnalyzerResultExtractorV2\.tmp\pytest-final-cleanup-20260922` *(removed; not retained)*

Prior Phase 2 second rework (historical): 445 passed, 2 skipped, 447 total — superseded.

## Historical — Phase 2 first rework (2026-09-22, superseded)

> **Historical only.** Superseded by Gate 2 authoritative baseline.

| Check | Result |
|---|---|
| pytest (full suite, external basetemp) | **PASS**, 419 passed, 2 skipped, 421 total cases (~33s) |
| pytest architecture gates | **PASS**, 34 passed |
| rules_validate_main.py | **PASS**, all integrity lists empty |
| rules_matrix_main.py --mode preview | **Expected non-green**, 2 green / 2 yellow / 7 red; **exit code 1** |
| watchdog_main.py one-shot (isolated code copy via test) | **PASS**, `watch_disabled`, exit 0 |

Basetemp (external): `I:\Projekte\AnalyzerResultExtractorV2-V21-ORCHESTRATION-20260921\phase2-test-temp-20260922-cursor`

Delta vs Gate 1: **+30 test cases** (391 → 421 inventory); skips unchanged at 2 (Tcl/Tk env).

## Historical — Gate 0 reference (binding for Gate-0 deltas only)

> **Historical binding reference** for Phase-0 delta math. Current pytest inventory is **448 total** (see authoritative Gate 2 baseline above).

| Check | Result |
|---|---|
| pytest (full suite, `-q -rs`) | **347 passed, 3 skipped** (Gate 0 binding reference) |
| Historical note | `319 passed, 2 skipped` is obsolete history only |

**Historical environment run (not competing baseline):** Gate 0 rework final run on 2026-09-21 reported `348 passed, 2 skipped` with basetemp `output\.pytest-orchestrator-gate0-rework-20260921-222840`. That run differed by environment (Tcl/Tk resolution, characterization tests without Tk). Treat **347/3** as the binding Gate-0 reference for deltas; do not treat 348/2 as an alternate baseline.

## Historical — Gate 1 Phase 1 rework (2026-09-22, superseded)

> **Historical only.** Phase 2 ingestion/archive is implemented; counts and gate totals below are Gate-1-era evidence, not current baseline.

| Check | Result |
|---|---|
| pytest (full suite, orchestrator final, external basetemp) | **PASS**, 389 passed, 2 skipped, 391 total cases (~37.7s) |
| pytest (full suite, Cursor rework run, repo basetemp) | **PASS**, 388 passed, 3 skipped, 391 total cases (~35s) — same case inventory; pass/skip split differs by Tcl/Tk process variance only |
| pytest architecture gates | **PASS**, 30 passed |
| rules_validate_main.py | **PASS**, all integrity lists empty |
| rules_matrix_main.py --mode preview | **Expected non-green**, 2 green / 2 yellow / 7 red; **exit code 1** |
| watchdog_main.py one-shot (isolated code copy) | **PASS**, `[watchdog] created_or_seen_jobs=0`, exit 0 |
| worker_main.py one-shot (isolated code copy) | **PASS**, `[worker] no_pending_jobs`, exit 0 |

Orchestrator final full-suite basetemp (external test evidence, not a repo file):

- `I:\Projekte\AnalyzerResultExtractorV2-V21-ORCHESTRATION-20260921\pytest-gate1-final-full-20260922-01`

Cursor rework basetemp (repo-local test evidence, historical Gate 1 label):

- `output\.pytest-orchestrator-gate1-rework-20260922`

Matrix report (latest run):

- `output/verification/rule_matrix_20260922_072253.json`
- `output/verification/rule_matrix_20260922_072253.md`

Gate 0 matrix reference (historical):

- `output/verification/rule_matrix_20260921_222939.json`
- `output/verification/rule_matrix_20260921_222939.md`

## Phase 0 Additions / Rework

Characterization only — no product behavior change:

- `tests/test_ui_v21_characterization.py` — resultstore read-only subset, settings, queue/watch Ist-contracts, `_enqueue_paths` / `pick_manual_files` (Tk-unabhängig via ungebundene Methoden + Fake), identical bytes at two paths
- `tests/test_ui_v21_characterization_rules.py` — draft/preview/activation in isolated temp project roots only

Extended:

- `tests/test_architecture_gates.py` — recursive adapter coverage, exact public-API parser, strict view file/storage I/O gate, exakte Inventarisierung aller elf Root-`*.py`-Dateien, Processing-Tk/interfaces-Gate, exakt vier Controller + vier `DesktopAppServices`-Felder

## Phase 1 Rework Additions

- Settings fail-fast: `SettingsController.load()` semantische Validierung; `SettingsLoadError` / `SettingsValidationError`
- Live settings ohne Service-Rebuild: `settings.load` als Provider in Extraction/Results
- `ProcessingBatchSummary` / `ProcessingEnqueueOutcome` / `ProcessingOutcome` (Application-DTOs)
- `submit_func=None` in `src.processing.service.process_next_pending` (kein gebundener Default)
- Bewusste DTO-Abweichung von V2.2-Mindestkatalog: `WatchStatus` → Phase 2; `ReportListItem`/`ReportDetail`/`AssayResultDetail` → Results-UI; `ValidationInfo` → Phase 4; `FieldTestResult` → später; `RunValidationPlaceholder` entfernt

## Phase 2 Additions

- `src/ingestion/` package with public `src.ingestion.api` owner
- Watchfolder scan, archive, import-record store; recovery without overwrite
- Jobqueue full-content SHA on enqueue
- Settings watch fields; headless `ARE_HOME` + one-shot adapter smokes
- `tests/test_ingestion.py`, `tests/test_watch_archive.py`; extended `tests/test_watchdog.py`, `tests/test_architecture_gates.py`

## Skips (variable events — two cause classes only)

Skip counts vary between runs (e.g. orchestrator **3 skipped** vs Cursor **1 skipped**) while total case count stays **448**. That is Tcl/Tk process variance and/or symlink privilege, not a lost test case and not an additional unexplained skip class.

| Cause class | Typical tests | Observed event |
|-------------|---------------|----------------|
| **Tcl/Tk installation** | `tests/test_test_app_smoke.py` (constructability); optionally `tests/test_tk_scroll_helpers.py` on the same broken install | `Can't find a usable tk.tcl`; missing `ttk/combobox.tcl` or `ttk/fonts.tcl` under the active Python `tcl/tk8.6` tree |
| **Windows symlink privilege** | `tests/test_in_app_watch_scan.py::test_watch_scan_recursive_skips_symlink_directories`; Phase 2 focused slice | **WinError 1314** — client lacks privilege to create symlink |

Orchestrator full suite: **445 passed / 3 skipped**. Cursor comparison: **447 passed / 1 skipped**. Focused Phase 2 slice: **126 passed / 1 skipped** (Win1314 only in that run).

**Not** characterization skips: `_enqueue_paths` / `pick_manual_files` in `test_ui_v21_characterization.py` run without Tk construction.

**Not** a GUI acceptance substitute. Phase 3 / human Gate requires a real Windows/Tk user smoke test. No manual GUI acceptance was performed for Gate 2.

## Matrix Interpretation

Expected matrix summary for current sample PDFs: **2 green / 2 yellow / 7 red**.

- yellow: detected and extractable, but optional fields missing and/or dedupe fallback
- red: active assays not covered by the current sample PDFs (`not_detected_in_selected_pdfs`)

Do not treat red matrix rows as a code regression until representative PDFs exist or the rule index is intentionally narrowed for the test set. Matrix exit code 1 remains the honest baseline while red status comes from sample-coverage gaps.

## Git Baseline (Orchestrator)

- Branch: `master`
- HEAD: `887ded85878489c20788735b93956313a06bcc84` (unchanged through Gate 2 technical closure)
- Divergence: +55 / -0 vs tracking ref
- Staged: 0
- Dirty tree: pre-existing user baseline; Gate 2 touches only the 37-file Phase 2 allowlist (see Gate 2 Report §3)
- Safety snapshot and exclusive writer lock: intact

## Related Docs

- `DOCUMENTATION/11_ui_v21_architecture.md` — Phase 0 architecture characterization
- `DOCUMENTATION/11_ui_v21_function_owner_matrix.md` — function → owner mapping
- `DOCUMENTATION/10_headless_runbook.md` — headless watch/worker operations
- `docs/KNOWN_ISSUES.md` — known test/environment caveats
- `docs/DEDUPE_POLICY.md` — dedupe interpretation

---

## Gate 2 Report — Phase 2 technical closure (Addendum §12)

> **Technical completion report only.** Status `READY_FOR_GATE2_REVIEW` — not `GATE_PASSED`, not human acceptance. Human Gate 2 acceptance remains pending.

### 1. Phase / Gate

Phase 2 / Gate 2 — ingestion owner (`src.ingestion.api`), watchfolder archive, jobqueue content SHA, settings watch fields, headless `ARE_HOME`/one-shot, legacy scanner adapters, recovery/no-overwrite. Visible GUI / Phase 3 **not started**.

### 2. Preflight

| Item | Value |
|------|-------|
| HEAD vorher | `887ded85878489c20788735b93956313a06bcc84` |
| HEAD nachher | `887ded85878489c20788735b93956313a06bcc84` |
| Exclusive writer lock | vorhanden, unverändert |
| Safety snapshot | vorhanden, unverändert |
| Externe Worktree-Änderung durch Agent | nein (nur Allowlist-Dateien + dieses TESTBASELINE-Doc-Gate) |
| Staged | 0 |
| Product data | live-vs-snapshot hash diff **0** (see authoritative product-data table) |
| `.tmp` artifacts | keine verbleibenden Gate-2-Verifikations-Artefakte |

### 3. Scope — Phase 2 snapshot delta (exakt 37 Dateien)

| Datei |
|-------|
| `AGENTS.md` |
| `README.md` |
| `docs/ARCHITECTURE.md` |
| `docs/EMBEDDING.md` |
| `docs/TESTBASELINE.md` |
| `DOCUMENTATION/10_headless_runbook.md` |
| `DOCUMENTATION/11_ui_v21_architecture.md` |
| `DOCUMENTATION/11_ui_v21_function_owner_matrix.md` |
| `interfaces/headless/watchdog.py` |
| `interfaces/headless/worker.py` |
| `interfaces/tk/watch_scan.py` |
| `src/application/api.py` |
| `src/application/errors.py` |
| `src/application/extraction_controller.py` |
| `src/application/models.py` |
| `src/application/results_controller.py` |
| `src/application/settings_controller.py` |
| `src/ingestion/__init__.py` |
| `src/ingestion/api.py` |
| `src/ingestion/archive.py` |
| `src/ingestion/models.py` |
| `src/ingestion/service.py` |
| `src/ingestion/store.py` |
| `src/jobqueue/api.py` |
| `src/jobqueue/model.py` |
| `src/jobqueue/queue.py` |
| `src/processing/service.py` |
| `src/watchdog/api.py` |
| `src/watchdog/service.py` |
| `tests/test_application_extraction_controller.py` |
| `tests/test_application_results_controller.py` |
| `tests/test_application_services.py` |
| `tests/test_application_settings_controller.py` |
| `tests/test_architecture_gates.py` |
| `tests/test_ingestion.py` |
| `tests/test_watch_archive.py` |
| `tests/test_watchdog.py` |

Geplant und tatsächlich geändert gegen Safety-Snapshot: dieselben 37 Dateien. Abweichung: keine (dieses Doc-Gate editiert nur `docs/TESTBASELINE.md`).

### 4. Verträge / Owner

| Thema | Ergebnis |
|-------|----------|
| Ingestion owner | `src.ingestion.api` — scan, archive, import records |
| Jobqueue | additive full-content SHA on enqueue |
| Settings | watch fields persisted; fail-fast unchanged from Phase 1 |
| Headless | `ARE_HOME` + `ARE_WATCHDOG_ONCE` / `ARE_WORKER_ONCE` one-shot smokes |
| ProcessingOutcome | content-job / queue scoped |
| Archive status / error | per ingestion instance via `ImportRecordItem` list/get (`src.ingestion.api`) |
| Legacy adapters | `interfaces/headless/*`, `interfaces/tk/watch_scan.py` delegate to public APIs only |
| Recovery | no-overwrite on archive targets |
| Deferred | visible GUI (Phase 3), operator initials, validation UI, export retry, human Tk acceptance |

| Layer | Owner API | Persistenz |
|-------|-----------|------------|
| Ingestion | `src.ingestion.api` | import records + archive paths |
| Extraction | `src.processing.api` | `src.jobqueue` queue files |
| Processing | `src.processing.api` | delegates queue/runtime |
| Results | `src.resultstore.api` (read-only) | SQLite read via store spec |
| Rules | `src.rulesuite.api` | rules tree via rulesuite |
| Settings | `src.runtime.api` + `storage/desktop_settings.json` | local JSON overlay |

### 5. Tests (frozen evidence)

| Befehl | Ergebnis |
|--------|----------|
| `pytest -q -rs --basetemp output\.pytest-orchestrator-phase2-gate2-<timestamp>` (Orchestrator full suite) | **445 passed, 3 skipped**, 448 total, **44.94s** |
| `pytest -q -rs` (Cursor full-suite comparison) | **447 passed, 1 skipped**, 448 total — skip variance only (Tcl/Tk + symlink) |
| Focused Phase 2 slice (orchestrator) | **126 passed, 1 skipped** (Win1314) |
| `pytest tests/test_architecture_gates.py -q` | **35 passed** |
| `rules_validate_main.py` | **PASS** |
| `rules_matrix_main.py --mode preview` | **2 green / 2 yellow / 7 red**, exit 1 (erwartet) |

**Baseline-Differenz vs. bindende Gate-0-Referenz (347 passed / 3 skipped = 350 total cases):**

| Metrik | Wert |
|--------|------|
| Gate 2 inventory vs. Gate 0 | **448** vs. **350** → **+98 neue Testfälle** kumulativ (Phase 1 + Phase 2) |
| Orchestrator vs. Cursor (Gate 2) | gleiche 448-Fall-Inventur; **+2 passed / +2 skipped** Orchestrator-seitig = Tcl/Tk + symlink env only |
| Failures | **0** in beiden Full-Suite-Läufen |

### 6. Manuelle Checks

| Check | Ergebnis |
|-------|----------|
| `watchdog_main.py` one-shot (`ARE_HOME` isoliert) | **PASS**, `watch_disabled`, exit 0 |
| `worker_main.py` one-shot (`ARE_HOME` isoliert) | **PASS**, `[worker] no_pending_jobs`, exit 0 |
| Product `rules/` / `jobs/` / `input/` / `output/` / `storage/` | hash diff **0** vs. snapshot |
| Packaging / main02 / GUI | nicht Teil von Gate 2; keine manuelle GUI-Abnahme |
| Phase 3 visible GUI | **nicht gestartet** |

### 7. Offene Risiken / Deferred

- Visible GUI / Phase 3 wiring (ingestion UX in Test-App) — deferred
- `operator_initials` — deferred
- Validation UI — deferred (Phase 4 scope)
- Export retry — deferred
- Human Tk acceptance smoke — **pending** (required before human Gate 2 sign-off)
- Tcl/Tk- und Symlink-Skips environment-abhängig (zwei Ursacheklassen, variable Anzahl pro Lauf)
- Matrix rot/gelb aus Sample-Coverage (erwartet, exit 1)

### 8. Status

**READY_FOR_GATE2_REVIEW**

*(Not `GATE_PASSED`. Not human acceptance. Human Gate 2 acceptance pending.)*

### 9. Nächste Phase

Phase 3 (visible GUI wiring, operator-facing watch/ingestion UX) — **not started**. Requires human Tk acceptance before human Gate 2 sign-off.

---

## Historical — Gate 0 Report (Addendum §12)

### 1. Phase / Gate

Phase 0 / Gate 0 — final rework (V2.1 UI migration characterization, governance, architecture gates).

### 2. Preflight

| Item | Value |
|------|-------|
| HEAD vorher | `887ded85878489c20788735b93956313a06bcc84` |
| HEAD nachher | `887ded85878489c20788735b93956313a06bcc84` |
| Exclusive writer | bestätigt (`exclusive-writer-root-cursor-phase0.lock` vorhanden) |
| Externe Worktree-Änderung durch Agent | nein (nur sechs erlaubte Phase-0-Dateien editiert) |
| Staged | 0 |

### 3. Scope

| Item | Value |
|------|-------|
| Geplant | 6 Dateien (Architektur-Doku, Owner-Matrix, TESTBASELINE, 3 Testdateien) |
| Tatsächlich geändert | dieselben 6 Dateien |
| Abweichung | keine |

### 4. Verträge / Owner

| Thema | Ergebnis |
|-------|----------|
| View-File-/Storage-I/O-Gate | Strikt: verbotene Storage-Imports, `open()`, direkte Path-/OS-/Shutil-I/O |
| Root-Surface-Gate | Exakt elf erlaubte Root-`*.py`-Dateien inventarisiert |
| Controller-Topologie | Vier Controller geplant für Phase 1 |

### 5. Tests

| Befehl | Ergebnis |
|--------|----------|
| `pytest -q -rs --basetemp output\.pytest-orchestrator-gate0-rework-20260921-222840` | 348 passed, 2 skipped (historischer Umgebungslauf; **nicht** bindende Baseline) |
| Bindende Gate-0-Referenz | **347 passed, 3 skipped** |
| `pytest tests/test_architecture_gates.py -q` | 22 passed (Gate 0 final) |
| `rules_validate_main.py` | PASS |
| `rules_matrix_main.py --mode preview` | 2 green / 2 yellow / 7 red, exit 1 (erwartet) |

### 6. Manuelle Checks

- Safety snapshot untouched
- Lock vorhanden; HEAD unverändert

### 7. Offene Risiken

- Tcl/Tk-Smoke environment-skip (Gate 3 manuell)
- Matrix rot/gelb aus Sample-Coverage

### 8. Status

**GATE_PASSED** *(historical Gate 0 label)*

### 9. Nächste Phase

Phase 1 (Application-/Controller-Grenze) — **nicht automatisch gestartet**.

---

## Historical — Gate 1 Report (Addendum §12) — Phase 1 Rework

> **Historical only.** Statements such as „Phase 2 — nicht gestartet“, deferred `watch_enabled` operator UI, and hard-bound live-checkout adapter smokes describe Gate-1 planning status and are superseded by Phase 2 implementation (headless ingestion/archive, `ARE_HOME` isolation, settings fields persisted).

### 1. Phase / Gate

Phase 1 / Gate 1 rework — Application-/Controller-Grenze, Settings fail-fast, Live-Settings-Provider, Application-DTOs, Processing-DI-Naht, Architektur-Gates.

### 2. Preflight

| Item | Value |
|------|-------|
| HEAD vorher | `887ded85878489c20788735b93956313a06bcc84` |
| HEAD nachher | `887ded85878489c20788735b93956313a06bcc84` |
| Exclusive writer | `exclusive-writer-root-cursor-phase1.lock` vorhanden |
| Safety snapshot | `I:\Projekte\AnalyzerResultExtractorV2-V21-PHASE1-SAFETY-20260922` vorhanden, unverändert |
| Externe Worktree-Änderung durch Agent | nein (nur Allowlist-Dateien) |
| Staged | 0 |

### 3. Scope

#### 3A — Rework patch (exakt 16 Dateien)

| Datei |
|-------|
| `src/application/api.py` |
| `src/application/models.py` |
| `src/application/extraction_controller.py` |
| `src/application/results_controller.py` |
| `src/application/services.py` |
| `src/application/settings_controller.py` |
| `src/processing/service.py` |
| `tests/test_application_extraction_controller.py` |
| `tests/test_application_results_controller.py` |
| `tests/test_application_services.py` |
| `tests/test_application_settings_controller.py` |
| `tests/test_processing_api.py` |
| `tests/test_architecture_gates.py` |
| `docs/ARCHITECTURE.md` |
| `docs/EMBEDDING.md` |
| `docs/TESTBASELINE.md` |

Geplant und tatsächlich geändert: dieselben 16 Dateien. Abweichung: keine.

#### 3B — Phase 1 kumulativ gegen Safety-Snapshot (exakt 25 Dateien)

| Datei |
|-------|
| `AGENTS.md` |
| `docs/ARCHITECTURE.md` |
| `docs/EMBEDDING.md` |
| `docs/TESTBASELINE.md` |
| `interfaces/common/queue_worker.py` |
| `src/application/__init__.py` |
| `src/application/api.py` |
| `src/application/errors.py` |
| `src/application/extraction_controller.py` |
| `src/application/models.py` |
| `src/application/results_controller.py` |
| `src/application/rules_controller.py` |
| `src/application/services.py` |
| `src/application/settings_controller.py` |
| `src/processing/__init__.py` |
| `src/processing/api.py` |
| `src/processing/models.py` |
| `src/processing/service.py` |
| `tests/test_application_extraction_controller.py` |
| `tests/test_application_results_controller.py` |
| `tests/test_application_rules_controller.py` |
| `tests/test_application_services.py` |
| `tests/test_application_settings_controller.py` |
| `tests/test_architecture_gates.py` |
| `tests/test_processing_api.py` |

Kumulativ geplant und tatsächlich geändert gegen Safety-Snapshot: dieselben 25 Dateien. Abweichung: keine.

### 4. Verträge / Owner

| Thema | Ergebnis |
|-------|----------|
| Settings | `load()` validiert semantisch; `SettingsLoadError` / `SettingsValidationError`; `create_desktop_services` fail-fast |
| Live settings | `settings.load` als Provider; kein Rebuild nach `save()` |
| Extraction | `ProcessingBatchSummary`, `ProcessingOutcome`; `submit_func` injizierbar |
| Processing | `submit_func=None` → Runtime-Lookup `submit` |
| Deferred DTOs | `WatchStatus` (Ph.2), Report-DTOs (Results-UI), `ValidationInfo` (Ph.4), `FieldTestResult` (später); `RunValidationPlaceholder` entfernt |
| Architektur | `src/processing` rekursiv Tk/interfaces-frei; exakt 4 Controller + 4 Service-Felder |
| Doku phasengleich | `ARCHITECTURE.md`, `EMBEDDING.md`, `TESTBASELINE.md` aktualisiert |

| Layer | Owner API | Persistenz |
|-------|-----------|------------|
| Extraction | `src.processing.api` | `src.jobqueue` queue files |
| Processing | `src.processing.api` | delegates queue/runtime |
| Results | `src.resultstore.api` (read-only) | SQLite read via store spec |
| Rules | `src.rulesuite.api` | rules tree via rulesuite |
| Settings | `src.runtime.api` + `storage/desktop_settings.json` | local JSON overlay |

### 5. Tests

| Befehl | Ergebnis |
|--------|----------|
| `pytest tests/test_application_extraction_controller.py tests/test_application_results_controller.py tests/test_application_rules_controller.py tests/test_application_services.py tests/test_application_settings_controller.py tests/test_processing_api.py -q` | **33 passed** |
| obige + `pytest tests/test_architecture_gates.py -q` | **63 passed** |
| `pytest tests/test_architecture_gates.py -q` (separat) | **30 passed** |
| `pytest -q -rs --basetemp I:\Projekte\AnalyzerResultExtractorV2-V21-ORCHESTRATION-20260921\pytest-gate1-final-full-20260922-01` (Orchestrator final) | **389 passed, 2 skipped**, 391 total cases, 37.67s |
| `pytest -q -rs --basetemp output\.pytest-orchestrator-gate1-rework-20260922` (Cursor rework) | **388 passed, 3 skipped**, 391 total cases (~35s) |
| `rules_validate_main.py` | **PASS** (alle Listen leer) |
| `rules_matrix_main.py --mode preview` | **2 green / 2 yellow / 7 red**, exit 1 (erwartet) |

**Baseline-Differenz vs. bindende Gate-0-Referenz (347 passed / 3 skipped = 350 total cases):**

| Metrik | Wert |
|--------|------|
| Orchestrator final vs. Gate 0 | **+42 passed**, **−1 skipped** (389/2 vs. 347/3) |
| Total cases | **391** vs. **350** → **+41 neue Testfälle** (Phase-1 Application/Processing/Architektur-Abdeckung) |
| Pass/Skip-Wechsel über die 41 neuen Fälle hinaus | reine Tcl/Tk-Umgebungsvarianz zwischen Läufen (388/3 vs. 389/2 bei gleicher 391-Fall-Inventur) |

Keine falsche Kausalität: die 41 zusätzlichen Fälle erklären den Anstieg von 350 auf 391; der weitere eine Pass mehr und ein Skip weniger im Orchestrator-Lauf gegenüber dem Cursor-Lauf ist derselbe Tk-Installations-Effekt, nicht ein zusätzlicher Scope-Gewinn.

### 6. Manuelle Checks

| Check | Ergebnis |
|-------|----------|
| `watchdog_main.py` one-shot | **PASS** — isolierte Codekopie, siehe unten |
| `worker_main.py` one-shot | **PASS** — isolierte Codekopie, siehe unten |
| Packaging / main02 / GUI | nicht Teil dieses Reworks; keine manuelle GUI-Abnahme |
| Produktive `jobs/`/`input/`/`output/`/`storage/`/`rules/` | nicht für Smokes verwendet oder verändert |

**Isolierte Adapter-Smoke (datenfrei, ehrliche Ausführung):**

| Item | Wert |
|------|------|
| Isolations-Root | `I:\Projekte\AnalyzerResultExtractorV2\.tmp\gate1-adapter-smoke-isolated-20260922-01` |
| Kopiert | nur `src/`, `interfaces/`, `watchdog_main.py`, `worker_main.py` |
| Angelegt (leer) | `input/watch`, `output/final`, `jobs`, `temp` |
| Env (nur im isolierten Root) | `ARE_WATCH_DIR`, `ARE_SQLITE_PATH` → isolierte Pfade; `ARE_OUTPUT_MODE=sqlite`; `ARE_WATCHDOG_ONCE=1` / `ARE_WORKER_ONCE=1` |
| Venv | Workspace-`.venv` aus Original-Checkout |
| watchdog | `[watchdog] created_or_seen_jobs=0`, exit 0 |
| worker | `[worker] no_pending_jobs`, exit 0 |
| Aufräumen | isolierte Temp-Codekopie vollständig entfernt nach Lauf |

**Historical (Gate 1 evidence — superseded for smokes with `ARE_HOME`):** One-shot im Original-Checkout ohne `ARE_HOME` adressiert weiter den Live-Root. Mit gesetztem `ARE_HOME` nutzen Headless-Adapter den isolierten Home-Pfad.

### 7. Offene Risiken

**Historical (Gate 1 report — not current Phase 2 status):**

- UI noch nicht auf `src.application.api` umverdrahtet (keine sichtbare GUI-Änderung in Phase 1)
- `watch_enabled` / `watch_backup_path` in Desktop-Settings implementiert; Operator-UI-Verdrahtung weiter Phase 3
- `operator_initials` deferred (spätere Phase)
- Headless one-shot ohne `ARE_HOME` weiterhin Live-Pfade — mit `ARE_HOME` isolierbar
- Tcl/Tk- und Symlink-Skips environment-abhängig (zwei Ursacheklassen, variable Anzahl pro Lauf)

### 8. Status

**GATE_PASSED** *(historical Gate 1 label — do not reuse for Phase 2 sign-off)*

### 9. Nächste Phase

**Historical (superseded):** „Phase 2 (Watchfolder-Fachlogik und Archivierung) — nicht gestartet.“ — Phase 2 ingestion/archive rework **is implemented**; GUI wiring remains Phase 3.

---

## Phase 3B implementation note (2026-09-22)

**Scope:** Product-entry cutover — `test_app_main.py` unchanged; `main()` defaults to `AnalyzerDesktopApp`; `ARE_LEGACY_UI` fallback; packaging desktop-runtime import manifest.

### Evidence run in B2 pass only (focused)

| Check | Result |
|-------|--------|
| `tests/test_desktop_ui_v21.py` | **PASS** (routing + shell tests; Tcl/Tk skips possible) |
| `tests/test_test_app_smoke.py` | **PASS** (legacy `LegacyTestApp` behavioral tests) |
| `tests/test_packaging_build.py` | **PASS** (entry + desktop manifest + import preflight) |
| `tests/test_architecture_gates.py` | **PASS** |
| `rules_validate_main.py` | **PASS** |
| `packaging/build_onedir.py` full build | **NOT RUN** (next Gate-3 step) |
| Full pytest inventory | **NOT RUN** in B2 pass |
| Manual Tk / bundled EXE GUI smoke | **NOT RUN** / **NOT CLAIMED** |

### Pending for Gate 3 closure

- Full `pytest -q` on fresh basetemp
- `packaging/build_onedir.py` onedir + bundled `ARE_SMOKE_EXIT` smoke
- Operator acceptance on real Windows display / field-trial EXE

**Superseded 2026-09-23:** the items above are closed by the Gate 3 record below.

## Gate 3 closure (2026-09-23)

**Status:** `GATE_PASSED` on 2026-09-23. Phase 4 is `NOT STARTED`.

| Check | Result |
|-------|--------|
| Final source suite | **587 passed, 2 skipped** |
| Build preflight | **587 passed, 2 skipped** |
| ZIP entries | **715** |
| ZIP SHA256 | `D7D9F6BF1995B0C0DE2AAAA6FA72076EF1F4E337CAC4CF8C49A565DE2EE8BD1C` |
| EXE SHA256 | `1A11BB9C4708009746C26128B383DC7BCD75EA91F237872186E11733AF568694` |
| Windows/Tk smoke | **PASS** — multi-PDF, watch/archive hash, settings persistence, and the final corrected selection-refresh routing |
| Evidence root | `I:\Projekte\AnalyzerResultExtractorV2-V21-ORCHESTRATION-20260921\gate3-selection-retest-20260923-134345\AnalyzerResultExtractorV2\evidence` |
| Processes left running | **0** |

Detailed closeout: [`GATE3_REPORT_2026-09-23.md`](GATE3_REPORT_2026-09-23.md).

## Phase 4 closure (2026-09-23, Gate 4 passed)

Scope: Results + append-only run validation, including visible Windows/Tk acceptance and
persistence across restart.

| Check | Result |
|-------|--------|
| `src.resultvalidation.api` contract + architecture | PASS |
| Final focused domain/application/settings/Tk/architecture suite | **165 passed** |
| Current-tree closeout rerun after Gate-5 changes | **164 passed, 1 skipped** in **4.94s**; focused validation/controller/Tk/architecture set |
| Orchestrator checkpoint review | **PASS**; configured Terra reviewer unavailable due usage limit, no model escalation |
| Full regression after review GO | **614 passed, 1 skipped** in **41.95s** |
| Baseline delta from Gate 3 | **+27 passed, -1 skipped; +26 collected cases** |
| `rules_validate_main.py` | **PASS**; all five integrity lists empty |
| Resultstore write boundary | unchanged; `src.resultstore` remains read-only |
| Validation persistence | append-only `run_validations`; explicit correction via `supersedes_validation_id` |
| Product data / Rules / package | snapshot hash comparison: **0 diffs**; no Phase-4 package build |
| Visible Gate-4 scenario | **PASS in final operator retest**: both synthetic assays inspected, one first validation saved, status changed to `Teilweise validiert`, and the same validation remained visible after close/relaunch |
| SQLite persistence evidence | **PASS**: exactly one `run_validations` row for run 1, initials `G4`, comment `GATE4_SYNTH_ERSTVALIDIERUNG`, no superseding row |
| Screenshot evidence | **PASS**: five PNGs under `.tmp/gate4-user-acceptance-20260923-162313/evidence/` cover initial state, both assays, saved state and post-restart state |

Prepared acceptance fixture and exact prompt:
`.tmp/gate4-user-acceptance-20260923-162313/`. Detailed status:
[`GATE4_REPORT_2026-09-23.md`](GATE4_REPORT_2026-09-23.md).

## Phase 5 closure (2026-09-23, Gate 5 passed)

Scope: Rule-Editor uses one injected `RuleSuiteController`. Existing activation publishes a
byte-exact, fail-closed snapshot under `rules/history/` before overwrite. `activate_new_draft`
does not snapshot. Assay combo and manage inventory share `list_inventory`. `rule_editor/**/*.py`
may import `src` only as `src.application.api`. Gate 5 and the subsequently completed Gate-4
operator retest are `GATE_PASSED`. Phase 6 subsequently completed with `GATE_PASSED`.

Focused commands (fresh project-local basetemp; not a full suite):

| Check | Result |
|-------|--------|
| Editor/wizard/characterization slice | **25 passed** in 1.16s (`.pytest-basetemp-phase5-step2b`) |
| `tests/test_architecture_gates.py` | **39 passed** in 1.87s (`.pytest-basetemp-phase5-step2b-arch`) |
| Phase-5 focus set | **161 passed** in 6.07s (`.pytest-basetemp-phase5-step2b-focus`) |

Final gate evidence:

| Check | Result |
|-------|--------|
| Orchestrator focus rerun | **161 passed** in **6.28s** |
| Checkpoint review | **PASS** by orchestrator; requested Terra reviewer unavailable due usage limit, no model fallback |
| Full regression after review | **641 passed, 3 skipped** in **48.92s** |
| Skip classification | two Tk-dependent tests skipped because local Tcl/Tk is incomplete; one symlink test skipped for Windows privilege error 1314 |
| `rules_validate_main.py` | **PASS**; all five integrity lists empty |
| Product data / Rules | final SHA-256 tree comparison against Phase-5 snapshot: **0 diffs** in `rules`, `input`, `output`, and `jobs` |
| Detailed report | [`GATE5_REPORT_2026-09-23.md`](GATE5_REPORT_2026-09-23.md) |

## Phase 6 implementation evidence (2026-09-23/24, Gate 6 passed)

Scope: Rule-Editor information architecture rebuilt around an inventory landing page and a
three-column workspace (field list, sample report, field settings). Rare functions remain under
`Erweiterte Optionen`; the wizard remains secondary. No new public API or persistence owner was
introduced. At Gate-6 closure, History/Trash inventory plus restore-as-draft were still deferred
to Phase 7; Gate 7 later completed that scope.

| Check | Result |
|-------|--------|
| Phase-6 preflight slice | **78 passed, 2 skipped** in **3.99s** |
| Final post-review-rework focused slice | **85 passed, 2 skipped** in **4.71s** (environment-dependent Tk/symlink skip split) |
| Real Tk layout regression before the text-only review rework | **6 passed** in **2.06s**; caught and fixed an invalid `ttk.Panedwindow.pane(..., minsize=...)` option and verifies bounded controls at 1024x768 |
| Compile check | `python -m compileall -q rule_editor rule_editor_main.py` — **PASS** |
| Public boundary | `rule_editor/**/*.py` continues to import `src` only via `src.application.api` |
| Product data / Rules | SHA-256 comparison against the Phase-6 safety snapshot: **0 diffs** in `rules`, `input`, `jobs`, `storage`, `locks`, and product output subdirectories |
| Checkpoint review | **PASS** by orchestrator after one bounded UX rework; configured Cursor reviewer was unavailable due its usage limit, with no model substitution |
| First full-regression invocation after review | **INVALID** — 221 passed, 2 skipped, 428 setup errors in 23.58s because the fresh `--basetemp` parent did not exist; no assertion failures |
| Human-authorized exception full-suite rerun | **649 passed, 2 skipped** in **48.73s** |
| Rules integrity after full suite | **PASS** for repository and isolated acceptance root; all result lists empty |
| Visible Gate-6 Rule change flow | **PASS** in isolated Windows/Tk root: edit, regex hit, 9/9 apply, save, preview, activation |
| Activation history proof | **PASS:** one history JSON; SHA-256 equals the pre-activation active bytes |
| Product-data protection | **PASS:** 0 diffs across 2,405 protected files against the Phase-6 safety snapshot |

**Status:** `GATE_PASSED`. The explicitly authorized exception rerun repaired only the invalid
test setup, not product code. Full details and screenshot paths are recorded in
[`GATE6_REPORT_2026-09-24.md`](GATE6_REPORT_2026-09-24.md).

## Phase 7 implementation evidence (2026-09-24, Gate 7 passed)

Scope: History and Trash are now read-only inventory kinds with timestamp, SHA-256 and error
metadata. Inactive and History entries can be opened as new non-overwriting drafts through the
existing `RuleSuiteController`; the Phase-5 fail-closed activation snapshot remains unchanged.

| Check | Result |
|-------|--------|
| Phase-7 preflight focus | **142 passed, 1 skipped in 3.66s** |
| Final focused lifecycle slice | **158 passed in 5.24s** |
| Checkpoint review | **GO** after two bounded rework rounds |
| Post-review full regression | **665 passed, 1 skipped in 43.31s** |
| Rules integrity | **PASS** for repository and isolated acceptance root; all lists empty |
| Visible Rule Lifecycle flow | **PASS**: History/Trash/Inactive inventory, History-/Inactive-to-Draft and existing-draft cancellation |
| Product-data protection | **PASS:** 0 diffs across 2,405 protected files against the Phase-7 safety snapshot |
| Detailed report | [`GATE7_REPORT_2026-09-24.md`](GATE7_REPORT_2026-09-24.md) |

**Status:** `GATE_PASSED`.
