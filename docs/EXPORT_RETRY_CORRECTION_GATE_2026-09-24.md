# Export-only Retry Correction Gate — 2026-09-24

## Verdict

**PASS / REVIEW_GO.** The correction package is complete. Phase 8 may resume unchanged.

## Scope and safety

- Safety snapshot: `I:\Projekte\AnalyzerResultExtractorV2-V21-EXPORT-RETRY-SAFETY-20260924`
- Snapshot parity at creation: 45,589 files and 606,470,184 bytes on source and target; verification exit 0.
- Branch: `master`
- HEAD before and after: `887ded85878489c20788735b93956313a06bcc84`
- No reset, checkout, clean, stash, commit, push, branch or worktree mutation.
- No queue, ingestion schema, worker, service, entrypoint or second retry flow was added.
- Protected product areas (`input`, `jobs`, `locks`, `output`, `storage`, `rules`) were compared after visible acceptance: 11,165 files, **0 differences** against the correction snapshot.

## Implemented behavior

- All assays are extracted before any sink write.
- All required SQLite writes finish before the first Excel write.
- A versioned, self-contained Excel output plan is atomically persisted in the existing job JSON.
- The plan freezes the extracted `AssayRecord`, the required writer rules and the original output directory.
- SQLite, Excel and archive remain separate statuses; Excel-only records SQLite as `not_required`.
- A retry of a versioned Excel failure uses only the frozen plan and the writer. It does not invoke parser, normalizer, assay chooser, content splitter, extractor or DB writer.
- Successful and duplicate-skipped Excel items are not written again.
- State is atomically persisted after each Excel attempt.
- The last successful Excel attempt atomically persists the job as `DONE`, closing the final crash window.
- Legacy failed job JSON without the versioned plan retains full-retry behavior.
- The existing queue vocabulary and existing Diagnostics retry action remain unchanged.
- For SQLite success plus Excel failure the UI displays exactly `Ergebnis gespeichert – Excel-Ausgabe fehlgeschlagen`; Diagnostics classifies it as `Excel-Ausgabe`.

## Changed package files

Production:

- `src/jobcontroller/jobcontroller.py`
- `src/application/presentation.py`
- `interfaces/tk/view_models.py`

Tests:

- `tests/test_jobcontroller_export_retry.py` (new)
- `tests/test_application_extraction_controller.py`
- `tests/test_desktop_ui_v21.py`
- `tests/test_watch_archive.py`

This gate report is the only documentation file added by the correction package.

## Review and rework history

1. Initial implementation: focused run exposed one overly strict test expectation (`created` although an existing workbook correctly produced `appended`).
2. Rework 1 corrected that assertion; focused result: 197 passed.
3. Independent review found two P1 issues: untruthful Excel-only SQLite status and non-persisted per-assay Excel progress.
4. Rework 2 added explicit `sqlite_status`, truthful `not_required`, per-attempt atomic persistence and a hard-abort multi-assay test. Focused result: 197 passed, 2 skipped.
5. Review then found the final-success crash window between the last persisted Excel success and outer `DONE`.
6. The user explicitly approved exception rework 3. It atomically marks terminal Excel success as `DONE` and adds a hard-abort/follow-up idempotency test.
7. Final independent verdict: `REVIEW_GO`, no remaining findings in scope.

## Verification

- Correction preflight: **198 passed, 1 skipped** in 9.09 s.
- Final export-retry test file: **9 passed** in 1.47 s.
- Final focused correction set: **199 passed, 1 skipped** in 10.22 s.
- Rules integrity (`rules_validate_main.py`): no missing files, key mismatches, duplicate JSON keys, content errors or orphan rulesets.
- `git diff --check`: clean.
- Exactly one post-review full suite: **676 passed, 2 skipped** in 55.11 s.

No second post-review full suite was run.

## Visible Windows/Tk acceptance

Isolated root:

`I:\Projekte\AnalyzerResultExtractorV2\.tmp\export-retry-visible-20260924-v1\isolated_home`

The product Tk shell was launched visibly with Computer Use. A copied sample PDF was processed in `both` mode while a synthetic Excel writer lock forced the partial failure.

Observed sequence:

1. Dashboard showed the partial result and Diagnostics showed `Excel-Ausgabe` plus the exact partial-success message.
2. A visible retry while the lock remained left the job failed and retryable, with exactly one SQLite run, no Excel file, source still in Watch and no archive file.
3. Only the synthetic lock was removed.
4. The same visible retry completed successfully.
5. Diagnostics cleared and Dashboard showed `Fertig` with one result.
6. SQLite remained at run ID `[1]`; normalized/block dump hashes and mtimes were unchanged.
7. `25-OH_Vitamin_D.xlsx` was created.
8. The source moved to archive with matching SHA-256.

Evidence:

- `.tmp/export-retry-visible-20260924-v1/isolated_home/evidence/01_dashboard_partial_failure.png`
- `.tmp/export-retry-visible-20260924-v1/isolated_home/evidence/02_diagnostics_excel_failure.png`
- `.tmp/export-retry-visible-20260924-v1/isolated_home/evidence/03_retry_with_lock_still_failed.png`
- `.tmp/export-retry-visible-20260924-v1/isolated_home/evidence/04_diagnostics_clear_after_success.png`
- `.tmp/export-retry-visible-20260924-v1/isolated_home/evidence/05_dashboard_finished.png`
- `.tmp/export-retry-visible-20260924-v1/isolated_home/evidence/operator-observations.txt`

## Deferred to the unchanged roadmap

- No package rebuild was performed for this inserted source correction gate.
- Packaging/build verification remains part of the subsequently resumed roadmap phase and its gate.
- No QMTool/PostgreSQL integration was implemented here.
