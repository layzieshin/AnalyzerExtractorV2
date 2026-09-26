# Gate 3 Report — First User Acceptance

## 1. Phase / Gate

- Phase: 3 — product shell, settings, processing, watch/archive, and packaged field-trial application
- Gate: 3 — first real Windows/Tk user acceptance
- Date: 2026-09-23
- Final status: `GATE_PASSED`

## 2. Preflight

- Repository: `I:\Projekte\AnalyzerResultExtractorV2`
- HEAD before/after: `887ded85878489c20788735b93956313a06bcc84`
- Baseline: explicitly confirmed complete dirty working tree, tracked and untracked
- Safety-Snapshot: `I:\Projekte\AnalyzerResultExtractorV2-V21-PHASE3-SAFETY-20260922`
- Exclusive writer: `root+local-cursor`; no competing writer detected
- External worktree changes during the package: none detected
- Destructive Git commands: not used
- External Git writes: not performed

## 3. Scope

Gate-3 rework was limited to the existing desktop settings/result routing owners and regression
coverage, primarily:

- `interfaces/tk/views/settings_view.py`
- `interfaces/tk/views/results_view.py`
- `interfaces/tk/test_app.py`
- `tests/test_desktop_ui_v21.py`
- `tests/test_application_settings_controller.py`

Only the three explicitly authorized packaging targets were replaced:

- `packaging/build_work`
- `packaging/dist_output/AnalyzerResultExtractorV2`
- `packaging/dist_output/AnalyzerResultExtractorV2.zip`

`packaging/dist_output/deploy_smoke`, production Rules, input, output, jobs, storage, and unrelated
dirty files remained unchanged. Phase 4 work was outside scope and was not started.

## 4. Contracts / owners

- Settings persistence remains owned by `SettingsController`; asynchronous UI refresh/save no longer
  re-enables a deliberately disabled watch setting.
- Report path resolution remains owned by `ResultsController` and the ingestion/current-path
  contract; no new persistence owner or public API was introduced.
- `ResultsView` now separates live list selection from the currently rendered detail identity.
- Result-list re-render preserves a still-existing selected `report_id`, preventing the periodic
  watch refresh from clearing the operator's Watch selection.
- No Rule, resultstore schema, or validation contract changed.
- Documentation was synchronized in `docs/TESTBASELINE.md` and
  `DOCUMENTATION/11_ui_v21_architecture.md`.

## 5. Tests and package verification

| Check | Result |
|-------|--------|
| Focused final Tk/UI regression | `57 passed` |
| Final full source suite | `587 passed, 2 skipped` |
| Build-integrated preflight | `587 passed, 2 skipped` |
| Rules integrity | PASS, no missing/key/content/orphan findings |
| Isolated watchdog one-shot | PASS — watch disabled |
| Isolated worker one-shot | PASS — no pending jobs |
| Bundled EXE smoke | PASS |
| ZIP entries | 715 |
| Forbidden runtime/test entries in ZIP | 0 |
| ZIP SHA-256 | `D7D9F6BF1995B0C0DE2AAAA6FA72076EF1F4E337CAC4CF8C49A565DE2EE8BD1C` |
| EXE SHA-256 | `1A11BB9C4708009746C26128B383DC7BCD75EA91F237872186E11733AF568694` |
| `deploy_smoke` | unchanged, 1,323 files |

The two skips are documented environment capabilities; they are not substitutes for the manual
Windows/Tk acceptance described below.

## 6. Manual checks

The accumulated isolated synthetic Gate-3 evidence confirms:

- application startup, navigation, status, resize, and packaged main window;
- persisted isolated input, archive, SQLite, and output settings;
- Auto-Import remained disabled across restart after the settings rework;
- manual single/multi-PDF processing and three separately selectable Multi assays;
- output-folder, archived-PDF, and Rule Editor actions without Rule edits;
- Watch processing and collision-safe archive flow;
- fixture/archive SHA-256 match:
  `1DB07474A4F4DFF477E30E374A66FAC519301C61F3387832F1862D70584BB498`;
- final selection-refresh routing: Watch selection remained selected after refresh, details showed
  `gate3_synthetic_watch.pdf` / `(6bd7)`, and Acrobat opened the archived Watch PDF;
- final Analyzer process count: 0.

Final routing evidence:

`I:\Projekte\AnalyzerResultExtractorV2-V21-ORCHESTRATION-20260921\gate3-selection-retest-20260923-134345\AnalyzerResultExtractorV2\evidence`

The preceding complete synthetic processing evidence is retained under:

`I:\Projekte\AnalyzerResultExtractorV2-V21-ORCHESTRATION-20260921\gate3-retest-20260923-075812\AnalyzerResultExtractorV2\evidence`

## 7. Open risks / accepted observation limits

- The transient `Lade Anwendung` state was too fast for reliable visual capture.
- Processing completed before navigation/resize-during-batch could be observed; no artificial delay
  was introduced.
- The Rule matrix remains the documented expected non-green sample-coverage baseline
  (`2 green / 2 yellow / 7 red`, exit 1), not a new Gate-3 regression.
- Pre-existing ACL-locked pytest temp directories remain untouched.

These items were reported honestly as observation/environment limits and do not contradict the
accepted Gate-3 user flows.

## 8. Status

`GATE_PASSED`

## 9. Next phase

Phase 4 — Results + Validation. **Named only; not started and not authorized by this report.**
