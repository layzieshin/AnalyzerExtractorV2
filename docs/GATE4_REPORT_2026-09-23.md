# Gate 4 Report — Results and Validation

Date: 2026-09-23  
Phase: 4 — Results and append-only run validation  
Status: **GATE_PASSED**  
Next phase state: Gate 5 was completed separately; Phase 6 is **NOT STARTED**

## 1. Preflight and safety

| Check | Result |
|---|---|
| Branch | `master` |
| HEAD before / after | `887ded85878489c20788735b93956313a06bcc84` / unchanged |
| Safety snapshot | `I:\Projekte\AnalyzerResultExtractorV2-V21-PHASE4-SAFETY-20260923` |
| Snapshot verification | 30,605 files, 578,413,274 bytes; source and snapshot identical at creation |
| Dirty baseline | preserved; no reset, checkout, clean, stash or Git write |
| Exclusive writer before review | restored; `cursor-agent` process count 0 |
| Product/runtime data | hash comparison against snapshot: input 2/2, output 8839/8839, jobs 2302/2302, storage 0/0, rules 22/22; **0 differences** |
| Exclusive writer before final documentation | restored after an external-change stop; two checks five seconds apart found no Python, `pythonw` or `cursor-agent` process and no Gate-file change |

One Cursor client remained alive after producing its result and briefly left child processes
running. The exact processes were stopped, the complete Phase-4 delta was audited against the
safety snapshot, and no source/test change outside the approved allowlist or unknown external
worktree change was found. Test cache files remained confined to `.tmp` / pytest basetemps.

## 2. Scope

Planned and implemented:

- new public owner `src.resultvalidation.api` for validation schema, reads and writes;
- append-only first validation and explicit append-only correction using
  `supersedes_validation_id`;
- compatible creation of `run_validations` for an existing runs database without changing
  `runs`; missing databases are not created;
- validation-enriched report DTOs and statuses `Unvalidiert`, `Teilweise validiert`,
  `Validiert`, with `Prüfung erforderlich` retaining precedence;
- persisted, trimmed `operator_initials` in settings;
- separate Tk validation panel with current state, history, save and explicitly confirmed
  correction;
- synchronized architecture, embedding, test-baseline and SQLite-to-QMTool migration mapping
  documentation.

Intentionally not done:

- no write path in `src.resultstore`;
- no PostgreSQL/QMTool integration;
- no package rebuild or destructive build-target cleanup;
- no Rule changes, product-data processing or Phase-5 work.

## 3. Contracts and owners

- `src.resultvalidation.api` is the sole cross-module validation surface.
- `src.resultstore.api` remains read-only.
- `ResultsController` remains the application boundary; Tk views do not access SQLite.
- The application still exposes exactly four controllers and four service fields.
- A normal second validation never overwrites an existing effective validation. Correction is
  a separate operation and creates a linked record.
- Concurrency uses a bounded SQLite busy timeout and permits at most one effective first head.

## 4. Review

The configured/requested checkpoint reviewer was `gpt-5.6-terra-medium-fast`. The Cursor run
stopped before review because its usage limit was reached. Observed runtime model and effort:
`UNAVAILABLE`. No silent fallback to Sol or another paid model was made.

The governance-authorized orchestrator review covered the complete Phase-4 allowlist,
architecture boundaries, append-only and concurrent persistence, error mapping, UI state,
documentation and product-data integrity. Two minor hardenings were made before review GO:

- `RunValidationItem.created_at_utc` now accepts legacy `NULL` values;
- controlled busy/unreadable/invalid-comment errors have explicit user-facing messages.

Review result: **PASS / GO for one full regression**.

## 5. Automated verification

| Command / check | Result |
|---|---|
| Focused Phase-4 suite with fresh project-local basetemp | **165 passed** in 5.89s |
| Current-tree Gate-4 closeout rerun after Gate-5 changes | **164 passed, 1 skipped** in 4.94s (`resultvalidation`, Results/Settings controllers, desktop UI and architecture gates) |
| Full `pytest -q` after review GO | **614 passed, 1 skipped** in 41.95s |
| Gate-3 baseline comparison | 587 passed, 2 skipped → **+27 passed, -1 skipped, +26 cases** |
| `rules_validate_main.py` | **PASS**; all integrity arrays empty |
| `git diff --check` on Phase-4 files | **PASS**; only existing line-ending notices |
| Obsolete validation API-name search | **0 hits** |
| Product/runtime/rules hash comparison | **0 differences** |

An initial focused invocation used a basetemp whose parent did not yet exist and therefore
failed during pytest setup. After creating only that project-local test directory, the run
executed normally. A newly added assertion was then corrected from case-sensitive to
case-insensitive text matching before the final green focused run. Neither issue was a product
failure.

The single full-suite skip is an existing environment-dependent class; it is not treated as
visible Windows/Tk acceptance.

The first current-tree closeout invocation was invalid because sandbox isolation denied pytest
access to its fresh project-local basetemp (`WinError 5`). The identical narrowly scoped command
was rerun outside the sandbox with approval and produced the authoritative green result above.

## 6. Manual Gate-4 check

The mandatory visible persistence scenario passed against the verified synthetic-only fixture:

`I:\Projekte\AnalyzerResultExtractorV2\.tmp\gate4-user-acceptance-20260923-162313`

1. Preflight confirmed the synthetic manifest and zero pre-existing Analyzer windows.
2. The exact prepared launch script produced one visible `Analyzer Result Extractor` window.
3. `gate4_synthetic_report.pdf` initially appeared as `Unvalidiert` with the two assays
   `(G4A1)` and `(G4B2)`.
4. Both assays were selected and their distinct synthetic fields were inspected.
5. `(G4A1)` was validated exactly once with initials `G4` and comment
   `GATE4_SYNTH_ERSTVALIDIERUNG`; the report status changed to `Teilweise validiert`.
6. After a normal close and relaunch with the same isolated `ARE_HOME`, the status and validation
   remained visible unchanged.
7. A read-only SQLite check found exactly one row in `run_validations`, with
   `supersedes_validation_id = NULL`; no duplicate or correction was created.
8. The final Analyzer process/window count was zero.

Evidence:

- `.tmp/gate4-user-acceptance-20260923-162313/evidence/01_results_unvalidated.png`
- `.tmp/gate4-user-acceptance-20260923-162313/evidence/02_assay_g4a1_fields.png`
- `.tmp/gate4-user-acceptance-20260923-162313/evidence/03_assay_g4b2_fields.png`
- `.tmp/gate4-user-acceptance-20260923-162313/evidence/04_validation_saved_partial.png`
- `.tmp/gate4-user-acceptance-20260923-162313/evidence/05_validation_persisted_after_restart.png`
- `.tmp/gate4-user-acceptance-20260923-162313/evidence/operator-observations.txt`

The operator record preserves the earlier no-window attempt and appends the successful retest, so
the audit trail is not rewritten.

## 7. Open risks

- The acceptance used synthetic fixture data and an isolated `ARE_HOME`; no product data was
  changed.
- The local environment still has the documented Tk- and symlink-dependent skip classes.
- PostgreSQL/QMTool integration remains outside Phase 4.

None of these items blocks the Phase-4 acceptance criteria.

## 8. Status

**GATE_PASSED**

Automated verification, architecture review, append-only persistence, visible Windows/Tk behavior
and persistence across restart are accepted.

## 9. Next phase

Phase 5 was authorized and completed in a separate package while the Gate-4 operator retest was
still outstanding; its status remains `GATE_PASSED`. Phase 6 is **NOT STARTED** and requires a
separate user authorization.
