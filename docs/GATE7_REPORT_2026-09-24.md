# Gate 7 Report — Rule Lifecycle / History / Trash

## 1. Phase / Gate

Phase 7 completed the planned RuleSuite lifecycle inventory and the read-only
History-to-Draft workflow. Gate 7 was evaluated on 2026-09-24 against the unchanged
approved roadmap.

## 2. Safety and preflight

- HEAD before and after: `887ded85878489c20788735b93956313a06bcc84` (`master`)
- Safety snapshot: `I:\Projekte\AnalyzerResultExtractorV2-V21-PHASE7-SAFETY-20260924`
- Snapshot verification: 41,961 files, 600,904,787 bytes, Robocopy verify exit 0
- Dirty working tree, tracked files and untracked files were preserved
- No reset, checkout, clean, stash, commit, push, merge, branch or worktree write was performed
- Valid preflight focus: **142 passed, 1 skipped in 3.66s**
- Repository rule validation: **PASS**, all five result lists empty

An earlier preflight attempt used a locked pytest basetemp and was invalidated as an
environment/setup attempt. The fresh authorized rerun above is the preflight proof.

## 3. Implemented scope

- History and Trash are visible and filterable in the shared inventory.
- Read-only archive rows expose stable modification time, SHA-256, validity and error metadata.
- History and Trash are explicitly read-only; deletion/mutation is rejected.
- Inactive-to-Draft remains available through the existing controller path.
- History-to-Draft creates a new draft without changing the snapshot or active rule.
- Existing drafts are never overwritten; the UI requires an explicit confirmation flow and
  `Nein` cancels without mutation.
- History sources and draft targets are contained below their canonical roots.
- Draft publication is exclusive and non-overwriting. Write/close/publish failures leave no
  final draft; a source change after successful publication preserves the valid snapshot-derived
  draft and returns an explicit warning.
- The Phase-5 byte-exact, fail-closed pre-activation snapshot contract remains unchanged.

No Phase-8 cleanup, diagnostics, documentation package or packaging work was included.

## 4. Ownership and boundaries

- Persistence/lifecycle owner: `src.rulesuite.api`
- View-facing owner: `RuleSuiteController` from `src.application.api`
- Rule Editor view modules continue to import no RuleSuite internals directly.
- `RulesetInventoryItem` carries additive `modified_at`, `sha256` and `read_only` metadata.
- Public lifecycle addition: `open_history_as_draft`; no parallel entrypoint or duplicate UI was added.

## 5. Review and bounded rework

The local Cursor writer delivered the implementation but could not execute its own shell tests;
the orchestrator therefore ran and recorded all tests. The independent checkpoint reviewer found:

1. path-containment and exclusive-publication gaps;
2. then a zero-write/close-failure gap in the first rework.

Both allowed rework rounds were used. The final reviewer verdict was **GO**, with no gate-relevant
finding. Accepted residual behavior: a source that changes after successful publication leaves the
already valid draft in place and reports a warning; a failed best-effort cleanup may leave a
non-inventoried temporary artifact, never a published `*.draft.json`.

## 6. Automated verification

| Check | Result |
|-------|--------|
| Initial implementation focus | **148 passed, 1 skipped** |
| Rework 1 focus | **156 passed** |
| Rework 2 / final focus | **158 passed in 5.24s** |
| Checkpoint reviewer | **GO** after rework 2 |
| Exactly one post-review full regression | **665 passed, 1 skipped in 43.31s** |
| Repository rule validation | **PASS**, all five lists empty |
| Isolated acceptance-root rule validation | **PASS**, all five lists empty |
| Protected product data | **2,405 / 2,405 files, 0 SHA-256 differences** |

The focused tests cover byte-exact pre-activation history, matching SHA, fail-closed snapshot
failure, no snapshot for a new activation, read-only archives, source/target containment,
exclusive non-overwriting draft publication, write/close/publish failures, concurrent replacement,
source change after publication, controller routing and UI cancellation.

## 7. Visible Windows/Tk acceptance

Computer Use exercised the real Rule Editor against the isolated root
`.tmp/gate7-user-acceptance-20260924/isolated_home`:

1. All, History, Trash and Inactive inventories rendered correctly.
2. History showed timestamp, SHA-256 and `NUR LESEN`.
3. History-to-Draft opened the historical VALUE regex while the active rule stayed current.
4. Broken Trash JSON remained visible with read-only error metadata; its edit action was blocked.
5. Inactive-to-Draft opened the inactive VALUE regex.
6. A second History-to-Draft attempt displayed `Draft vorhanden`; choosing `Nein` cancelled
   without overwriting.
7. The application closed normally and no Rule Editor window remained.

Nine screenshots plus `operator-observations.txt` are stored under the isolated `evidence/`
directory. Post-run inspection found exactly the two expected draft files and no temporary draft.

## 8. Status

**GATE_PASSED**

## 9. Next phase

Phase 8 — cleanup, diagnostics, documentation and packaging — is the next authorized roadmap
step. It may start only with its own clean preflight/safety checkpoint. Any change to the approved
plan still requires explicit user confirmation.
