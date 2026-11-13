# AREV2 Test Baseline

Date: 2026-11-13 (A1 integrated source release 2.1.0)

Purpose: current verified source baseline with preserved historical phase evidence.
The current release gate is A1 below; older gate labels, build results and pending
review statements describe their recorded checkpoints and do not qualify 2.1.0.
The 2026-07-09 AP-1 baseline (`74 passed`) is obsolete.

## Current rebuild gates (2026-11-13)

### A1 integrated source release 2.1.0: GATE_PASSED (2026-11-13)

Root issued **GO for P4+A1** on source metadata 2.1.0 after the independent
standard-print review and one integrated native full-suite run: **1418 passed,
0 failed, 0 errors, 0 skipped in 86.06s**. This is the observed full-suite result;
focused totals are not added into it. External evidence: `test_runs/final_native.xml`
and `test_runs/root_final_review.json`. All **249 frozen Python hashes** still
match the functional freeze. Current release notes: [2.1.0](RELEASE_NOTES_2_1_0.md).
Current acceptance/evidence owner: [A1 final verification](A1_FINAL_VERIFICATION_2026-11-13.md).

Root ran isolated synthetic CLI checks: rules integrity, matrix preview, main02
E2E, watchdog once and worker once all exit 0; both assays are matrix-green and
three processed PDF runs produced three SQLite rows. All five shipped rule
integrity error lists are empty. All **121 CLI-owner files** match the execution
copy byte-for-byte. CLI evidence: `test_runs/root_final_cli_smokes.json`. GitHub
upload is the subsequent separate Root action. No Windows EXE/packaging
qualification or completed GitHub upload is claimed here.

### P4 compact PDF layout: ROOT-GO / GATE_PASSED (2026-11-13)

Schema 3 / analysis-v4 / PDF-v4 freezes eligible-sample descriptive statistics,
absolute/relative deviations, genuine source precision, periods/positions and
the mean line. Literal schema-2/v3/v3 compatibility and genuine pre-P4 archived
model/PDF bytes remain intact. Root independently passed eight numeric vectors,
an excluded outlier and 48 version tuples, plus 242 native focused cases without
skips before the print-only reworks; those analysis/version owners are unchanged.

The user's later explicit print requirement supersedes the earlier plan for
mandatory technical evidence pages. Standard print is compact and defaults to
false for additional evidence: 11 usual rows = 1 page; 60 one-level rows = 2
pages; two levels with 30 rows each = 3 pages in executed synthetic real-store
examples. Times-Roman with bold headings, 7.5 pt measurement text, 14 pt rows and
one-line date/time preserve readability and actual seconds. Important exclusions,
limit and Westgard findings stay position-bound and visible. Complete identities,
raw values and bound validations stay in the frozen digital model, identified in
the footer. No JSON/raw-data attachment was added. Explicitly selected additional
technical evidence/method/full-rule printing may use more pages. The UI flag
resets after successful export and stays selected on failure for retry.

Final writer focus: **34 passed, 0 failed, 0 skipped in 44.20s**, covering the
entire PDF owner plus the existing shell-export capture/reset/retry case. Tests
check all 60 positions across one/two levels, visible findings, layout bounds,
no attachments or repeated source lists by default, exact unmodified models,
full optional hash/token/point-key/raw exceptions, historical exact export and
bounded spawn behavior. The writer rendered and visually checked all six real-store standard-print
pages. Historical focused evidence: `test_runs/p4_rework2_focused.xml`,
`tmp/P4_rework2_freeze.json` (249 Python hashes).

Root independently generated real-store PDFs: **11 points = 1 page**, **60
one-level points = 2 pages**, **2 x 30 points with long names = 3 pages**, and
**120 points including an invalid raw value = 4 pages**. Every page was rendered
with Poppler; representative views were checked at full size. Geometry found
**zero out-of-bounds spans** across all ten pages. No raw-data attachment was
embedded; complete raw evidence remains in the frozen model and rendering did
not mutate it. Optional paper details and exact legacy export are covered by
focused/full-suite checks. Root issued P4-GO; external evidence:
`test_runs/root_final_review.json`, `test_runs/root_p4_pdf_geometry_final.json`.
Details: [P4 result](P4_PDF_LAYOUT_RESULT_2026-11-13.md).

### R1 functional implementation: ROOT-GO (2026-11-13)

The existing Rule Editor now separates loaded-draft PDF proof from one final
activation confirmation. Proof-v2 uses privately frozen input bytes, current
mode/binding checks, short lock scopes and attempt-token publication. Product
activation rechecks the exact captured snapshot under existing owner locks;
private-index relocation closes absolute/alias live-file escapes. Existing
lower APIs remain compatible with optional proof enforcement. No shipped rule
JSON, runtime data or governance configuration was changed.

The six previously established P1/Linux baseline failures were treated by cause:
four scoped test-context fixes (two simulated Windows case comparisons, two
exact synthetic UNC/resolved-path mocks) and two product fixes (visible narrow
editor controls/first-mapped sashes, and fail-closed host-independent draft keys).
No skips or production case-fold policy were added. Real local SQLite query-only
behavior and pure synthetic network classification are additionally verified.

Writer's focused R1 selection: **403 passed, 21 existing Tk environment skips in
3.64s**, including all Rule Editor/RuleSuite/controller tests, baseline contexts
and architecture. This is not a full-suite result. Root's independent real-PDF
backend checks passed create/update proof-only isolation, exact old history,
same-byte reference revocation, mode/name/binding guards and optional-field
emptiness. A reproduced absolute-binding transient-mutation hole was corrected;
independent absolute/alias × good/mismatch checks then all resolved private
snapshots and preserved original BASE values. Independent native R1 review passed **424 tests, 0 skips in 5.91s** with all
Python-freeze hashes matching. The first actual click flow exposed lost worker-thread Tk-timer delivery hidden
by an ImmediateThread test double. Rework 1 uses the existing TkTaskRunner queue
and main-thread poller, replaces that double with a real worker/mainloop and makes
the existing diff log visible. Focused rework check: **92 passed, 9 existing Tk
skips in 2.16s**. Root independently confirmed actual main-thread completion,
cleared busy state and zero worker Tk calls. The independent native rework selection passed **148 tests, 0 skips**, with
matching hashes. Actual create/update flows at 1024x768 and 1280x900 passed using
real workers, PDFs and final confirmation dialogs: proof-only/cancel do not write,
all required reference blockers reject, successful final publication creates the
exact checked draft and one exact-old-byte history entry. Root issued R1-GO;
evidence `test_runs/root_r1_review_final.json`. Details: `docs/R1_RULE_RELEASE_RESULT_2026-11-13.md`.


### Authorized package implementation: P2/P3 ROOT-GO (2026-11-13)

The current user authorized all agreed packages with one product writer, read-only
planning and independent Root review. No per-package full-suite repetition, build,
Git mutation or rule/runtime-data change has been made by the writer. Source and
safety checkpoints are external to the materialized checkout (no `.git`).

P2 adds frozen manufacturer/percentage reference lines, independent point findings
and schema-2 / analysis-v3 / PDF-v3 models; genuine pre-P2 model/PDF archives stay
byte-exact. Root's independent native selection passed **72 tests, 0 skips in
5.67s**, followed by actual AnalyzerDesktopApp and independently generated PDF
visual checks. Result: `docs/P2_QK_LIMITS_RESULT_2026-11-13.md`.

P3 adds complete read-only usage chronology, precision intervals, proactive
pairwise close offers and a prepared model/PDF preview. Final publication remains
in the existing atomic QC owner, including direct first closure. Writer checks:

| Focused check | Observed result |
|---|---|
| Profile/source/store tests including usage overlap, pending candidates, >500 observations, unknown revision identity and contiguous explicit clock precision | **111 passed in 3.23s** |
| New real-preview/direct-close/empty-target integrity checks and 18 preparation/publication race cases | **21 passed in 8.27s** |
| Application + profile/source/store + real PDF + architecture selection | **222 passed, 21 existing Tk environment skips in 39.89s** |
| Additional explicit-profile/configuration binding checks | **2 passed in 1.02s** |

No skips were added. Native P3 selection passed 246 tests without skips; the focused refresh rework
passed a further 5 native tests without skips. Actual preview/cancel/direct-first-
close/archive/exact-export flow was reviewed. See `docs/P3_LOT_CLOSE_RESULT_2026-11-13.md` for the final package
status. These targeted checks do not claim an integrated full-suite result. The
previously established Linux/P1 full baseline of 1267 passed / 6 failed is recorded
separately; those qualification failures are not hidden or converted to skips.
The integrated final run subsequently passed as recorded under A1 above.
Windows target qualification remains outstanding.


### Post-push duplicate comparison correction (2026-11-13): GATE_PASSED

The authorized PR-review improvement uses the existing selected ResultStore
projection for duplicate lot, payload and dedupe key/version/basis. One captured
store supplies the complete detail read. Original job/PDF provenance and raw
DbWriter history remain unchanged. Legacy and smoke displays use that same
controller DTO and existing presenter, including their discard caches.

Before product edits, the real public-API original L1/value 1 -> accepted
L2/value 2 -> alias duplicate regression failed as expected: **1 failed in
2.61s**. After the bounded fix, the following selection passed **7 tests,
0 skips in 4.06s**, with `-B`, bytecode disabled and normal Windows rights:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q tests/test_application_results_controller.py::test_duplicate_detail_follows_accepted_projection_not_original_or_pending_and_never_writes tests/test_application_results_controller.py::test_duplicate_detail_captures_one_store_with_same_ids_in_another_store tests/test_application_results_controller.py::test_duplicate_controller_list_detail_and_discard tests/test_application_results_controller.py::test_duplicate_field_comparison_preserves_falsy_values tests/test_test_app_smoke.py::test_duplicate_adapters_show_selected_projection_and_preserve_discard_cache --basetemp=.tmp/pytest-postpush-duplicate-20261113/green -o faulthandler_timeout=30 --tb=short -rs
```

Coverage includes pending newer revisions, 0/False/None, selected dedupe metadata,
unchanged original/revision/SQLite bytes and mtimes, same-ID store switching,
and both adapters' selection/discard paths. The seven-file freeze audit is
`.tmp/postpush-duplicate-freeze-audit-20261113.json`, compared with the full
`AnalyzerResultExtractorV2-POSTPUSH-REWORK-SAFETY-20261113` copy (copy 1 / compare
0). Protected data/current build outputs and previous audits remain unchanged.
Independent recheck and replacement full/build/visible qualification passed
as recorded next. The writer ran no full suite/build/CUA/Git write; parent
qualification is recorded separately.

### Replacement technical qualification after PR correction: GATE_PASSED

The sole independent reviewer returned GO, no findings: **7 passed, 0 skipped
in 3.33s**. The canonical builder completed **1243 passed, 2 skipped in 416.84s**,
then PyInstaller, bundled rules/structure checks and EXE startup. Skips: known
Windows symlink privilege and one transient Tk library read error. The exact
wizard test was subsequently rechecked: **2 passed, 0 skipped in 2.93s**, with
no product/installation/environment repair and no repeated full suite.
Log: `.tmp/final-postpush-duplicate-qualified-20261113.log`;
Tk proof: `.tmp/final-postpush-tk-recheck-20261113.xml`.

Replacement portable ZIP: **35,332,280 bytes / 720 entries**, SHA-256
`e58175a053353e012ddeb382ba6f98fec08db7d73f92f2b2f6f00ccd0a635b8e`.
EXE SHA-256: `a92658ba3592029b82894a46d1bb1c2f22bc29f5ed31e4947010f78978318d40`.
All **197** raw product inputs match fingerprint
`25c62844239fbc35c8e8a1cde4778a1985adb7638b716fd5abfd0d8ae18f0c52`.
Fresh extraction, ZIP content/integrity and extracted EXE startup passed:
`.tmp/p5-final-package-verification-20261112-5.json`.

Actual extracted EXE: accepted L2/value 2 against candidate L2/value 2; equal
0/False/empty values; selected dedupe metadata; original-job provenance; newer
L3 remained pending. Statistics opened with selected L2. The EXE closed normally.
The synthetic SQLite bytes, selected/original/history state and raw duplicate
evidence stayed identical. Three screenshots and
`.tmp/final-round5-visible-qualification-20261113.json` retain the proof.
Earlier complete synthetic E2E and QC/PDF qualification are preserved; this
correction changed no processing, persistence, QC mathematics or PDF code.

Postbuild comparison: **12,524 protected files unchanged** outside the three
authorized build targets, plus both nested local job files checked separately.
No source exception was needed; `deploy_smoke` is preserved. Evidence:
`.tmp/final-postpush-duplicate-release-protected-audit-20261113.json`.
The preceding ZIP below is superseded for release and retained as evidence.
Publication remains a separate authorized step; exact commit/actual merge/tag
and asset identities belong to the PR/steward/release provenance. Human acceptance
is separate. The documented sample-rule matrix remains 2 green / 0 yellow /
9 red and does not qualify every supplied rule.

### Predecessor technical qualification before PR correction (2026-11-13)

Independent reviews: Statistics 50 passed / 0 skips / no findings; approved
build-provenance correction 5 passed / 0 skips / no findings. The final canonical
builder completed **1239 passed, 1 skipped in 195.71s**, rule-integrity validation,
PyInstaller, bundled rules/structure checks and EXE startup smoke. The only skip
requires Windows symlink privilege. No duplicate full regression followed.
Log: `.tmp/final-statistics-provenance-qualified-20261113.log`.

Fresh ZIP extraction and separate EXE startup passed. Portable ZIP: 35,331,506
bytes / 720 entries; SHA-256
`37d7bd82eeae0d6dc56f6b4007d7702d63bdf5418f52e13a11b1a8f381462cfa`.
EXE SHA-256: `5ad605ea808746c61ff02cc10c6c9c540388dff98ab7160cb53ba66bd9c9d8de`.
All **197** raw inputs match fingerprint
`745d71cc60caac7a99e22ab21ec9dd011091056132b39b826f15e6d1a0b3c40c`;
all inputs are tracked or explicitly planned. Both excluded local job files
remain byte/size/mtime-identical. Earlier ZIPs are superseded for publication.

Actual visible qualification used this fresh EXE and synthetic data only:
separate Statistics navigation, frozen 19-measurement/two-control report,
compact and optional explained PDF exports. The compact four-page copy is
byte-exact to stored evidence. All eight explained pages have identical text
and drawing streams to the already visually inspected version. Rule inventory
tables display assay names. Right-click opens the existing test draft; its PDF
finds 13/13 fields and PC_IST / NC_IST switching remains responsive. Results has
no duplicate QC entry. Screenshots 42-49 are retained in
`.tmp/final-qualification-20261112-2/screenshots-final`. Both EXE windows closed
normally without saving or changing a rule/draft.

The final public-API evidence audit passed **24 checks**: unchanged profile 1
and reports 3/6/8, frozen SD baseline n=18, selected date/time profile and current
19/38 measurement/control population. Evidence:
`.tmp/final-display-pdf-ui-proof-20261113-110835-9a81487d.json`,
`.tmp/final-round4-pdf-export-proof-20261113.json` and
`.tmp/final-round4-visible-qualification-20261113.json`.
The earlier complete synthetic import/archive/reanalysis/human-validation/QC/
closure/restart qualification remains valid; this follow-up changed no backend,
mathematics, PDF rendering or persistence code.

Postbuild preservation: **12,523** protected files outside the three authorized
build replacements and the separately approved builder-source edit are exact;
both nested runtime job files are separately exact. `deploy_smoke` is preserved.
Audit: `.tmp/final-statistics-provenance-release-protected-audit-20261113.json`.
This is technical qualification; human acceptance is separate. The sample-rule
matrix retains its documented 2 green / 0 yellow / 9 red baseline and does not
qualify every supplied assay against every PDF. Git publication follows as a
separate authorized step; exact pushed/merged/tagged revisions and asset checks
are recorded in the PR and release provenance manifest. Raw Windows hashes and
Git clean-filter blob hashes are distinct.

### Build-provenance runtime exclusion (historical writer checkpoint; subsequent GO)

The user explicitly approved excluding local runtime/work metadata while
preserving the two existing `interfaces/tk/jobs` files. The full copy
`I:\Projekte\AnalyzerResultExtractorV2-BUILD-PROVENANCE-SAFETY-20261113`
completed copy exit 1 / comparison exit 0 before writes. Exactly the builder's
existing `_product_inputs`, its existing test file and the two gate documents
are in scope. The package scan now filters relative directory components with
casefold for reserved runtime/cache/work directories. Source/static assets,
new code without a Git index, the separate static rule tree and the existing
resolved-root escape guard remain. No data, cleanup target or build flow changes.

Executed focused command: `python -B -m pytest -q tests/test_packaging_build.py
-k "fingerprint or nested_runtime or input_escape or manifest_records or failed_canonical"
--basetemp=.tmp/pytest-build-provenance-20261113/focused
-o faulthandler_timeout=30 --tb=short -rs`, bytecode disabled, normal Windows
rights via `require_escalated`: **5 passed, 9 deselected, 0 skipped in 1.04s**.
Synthetic nested directories under all three packages remain byte-/mtime-intact
when scanned; runtime changes do not change the fingerprint, while code/assets/
rules/new untracked source do. A simulated resolved symlink/junction escape
fails before external payload reading, without requiring Windows link privilege.
The existing failed-preflight check still prevents cleanup/build.

The actual read-only scan changed **199 to 197** inputs, removing exactly the
two known local job files. StatisticsView remains included. A read-only Git
inventory confirms every remaining input is tracked or a planned new file;
the input algorithm itself does not use Git. Both local files match the new
safety copy's SHA/size/mtime. Current product fingerprint:
`745d71cc60caac7a99e22ab21ec9dd011091056132b39b826f15e6d1a0b3c40c`.

Freeze audit: `.tmp/build-provenance-freeze-audit-20261113.json`. The authorized
builder source is the sole permitted packaging-tree delta; all other protected
files/build outputs, local runtime files and the twelve non-gate Statistics
files remain unchanged. No full suite, build, CUA/E2E or Git write was run.
Independent review and final canonical full/build subsequently passed; see the
final technical qualification above. This writer checkpoint is historical.

### Dedicated Statistics navigation (2026-11-13, independent GO)

The user's explicit request for an own Statistics tab authorizes seven views.
The existing QC state/widgets/chart/source/history/PDF actions were moved once
from ResultsView to StatisticsView; the Results QC entry and internal back-to-
report switch were removed. Results retains report lists/details/validation.
The same ResultsController, four services and `qc-lots`/`qc-sources` TaskRunner
callbacks/store/generation guards remain. No math, PDF, schema, rules, backend API
or builder change is part of this package.

Verified full safety copy:
`I:\Projekte\AnalyzerResultExtractorV2-STATISTICS-NAV-SAFETY-20261113`,
copy exit 1 / closed comparison exit 0. Scope is the approved 14 files, including
one new UI view, existing shell/navigation/results view, three affected test
files and six P0/gate documents. Tests used `python -B -m pytest -q --tb=short -rs
-o faulthandler_timeout=30`, bytecode disabled, normal Windows rights through
`require_escalated`, below `.tmp/pytest-statistics-nav-20261113/`:

| Executed selection | Result | Basetemp suffix |
|---|---|---|
| Existing 40 architecture gates; Statistics declarations/deferred store guard; report binding; seven-view minimum size; six existing QC source/status/chart/history/close/export cases | **48 passed, 2 failed in 18.20s** | `focused` |
| Three affected test-adapter cases after adapting the old report-back expectation | **1 passed, 1 failed, 1 skipped in 4.31s** | `fixed` |
| Statistics deferred/store guard, isolated | **1 passed, 0 skipped in 1.86s** | `final-guard` |
| Statistics state/actions/footer, isolated | **1 passed, 0 skipped in 3.79s** | `final-state` |

The failures were test coupling only: a SimpleNamespace treated as a dataclass,
an obsolete Results-only back action, then Tk's missing-attribute forwarding on
the uninitialized shell stub. These test adapters were corrected. The single
known Tcl `init.tcl` initialization skip passed in isolation. All 50 selected
cases have passing executions; overlapping runs are not summed. No unchanged
math/PDF suite, full run, build, CUA or E2E was replayed.

The parent's existing 24-check GUI proof and 4-page compact/8-page explained PDF
inspection qualify the predecessor; they are not proof of this new navigation.
Fresh source/protected audit:
`.tmp/statistics-nav-freeze-audit-20261113.json` against this exact full copy;
previous safety/audit evidence and runtime files remain preserved. Independent
Statistics review subsequently returned GO: **50 passed, zero skips, no findings**.
The parent final canonical full/build/visible follow-up follows the separately
approved build-provenance correction above.

### Assay names and compact control PDF (2026-11-13, final test-only recheck pending)

The user approved full assay names in human tables, compact default control
reports with optional interpretation, and each control's own graph/value section.
The verified full copy is
`I:\Projekte\AnalyzerResultExtractorV2-DISPLAY-PDF-SAFETY-20261113`:
97,352 files / 95,042 directories / 2.361 GiB, copy exit 1 / comparison exit 0.

Selected revision names precede original provenance, stored public Writer/Splitter
evidence and the active catalog through the existing RuleSuiteController.
Pending candidates do not rename current results; missing names are explicit,
filename hints are labelled, duplicate selections retain index/key identity and
technical keys stay internal. No architecture allowlist was expanded.
New QC presentation metadata is frozen separately from unchanged source/SD/math.
Renderer v2 uses separate control pages/continuations and frozen operator/bound
validator/UTC data. Date-only sources show no invented time, including on axes.
Default export remains archive-byte-exact; the strict boolean option renders a
separate explained print only from the stored model. Existing evidence is unchanged.

Focused commands used `.venv/Scripts/python.exe -B -m pytest -q`,
`PYTHONDONTWRITEBYTECODE=1`, `--tb=short -o faulthandler_timeout=30` and the following
roots below `.tmp/pytest-display-pdf-20261113/`. Runs overlap and are not summed.

| Executed selection | Result | Basetemp suffix |
|---|---|---|
| Results/RulesController files; actual profile callback; duplicate-name legacy selection | **49 passed, 0 skipped, 7.66s** | `names-run` |
| Selected/original/job/catalog name case and unchanged architecture-gate file | **41 passed, 0 skipped, 5.38s** | `name-owner-arch` |
| Compact/explained real PDF; duplicate-name profile selection; human table projections; hidden RuleEditor key column | **4 passed, 0 skipped, 17.76s** | `presentation` |
| Final compact/explained pagination case plus baseline-center PDF | **2 passed, 0 skipped, 11.88s** | `final-qa-pdf` |
| Archived exact/derived print, boolean validation, spawn metadata, actual close/history/export and v1/v2 reader | **12 passed, 0 skipped, 13.08s** | `final-export-contract` |
| Irrational calculated display/raw-value geometry, isolated Tk process | **1 passed, 0 skipped, 6.96s** | `final-irrational` |
| Frozen chart selection/zoom/pan/reset, isolated Tk process | **1 passed, 0 skipped, 3.12s** | `final-chart` |
| Actual legacy DB/name/run-identity read; candidate-name projections; v1/v2 reader | **5 passed, 0 skipped, 3.40s** | `final-legacy-names` |

During implementation an indentation collection failure and a missing basetemp
parent were corrected. An intermediate wider affected slice had **56 passed,
2 failed, 1 skipped** (66.43s): the failures assumed contiguous text across
wrapped table columns; the existing Tk initialization skip passed in isolation.
Checks now use extracted span geometry for raw values/reasons. The later
axis/time/presentation command had **3 passed, 1 failed** (31.27s), solely because
the optional appendix's date heading still included time wording; this was
corrected and the final compact/extended case passed. Earlier PDF assertions also
exposed wrapping, appendix/control-page classification and date-only explanatory
text; corrected focused outputs above replace those provisional layouts.

The parent independently read all **4 compact + 15 explained pages** with pypdf,
rendered/visually checked every compact page and appendix pages 5/15 with Poppler,
and checked the one-page SOLL100/center91/SD1 baseline example. Final evidence:
`.tmp/display-pdf-final-poppler-qa-20261113/inspection.json`.
Compact SHA256 `6f7475064cb38ca43d9e5bb6d3652fcd5cc8781d359a8a3672179a6c343ea6ce`;
explained SHA256 `6895adee8a7718f4e9f31c660fc68dda9741a1ed81b43e5960d5bd623d5febbf`.
Provisional QA was preserved and is not the final layout evidence.

Freeze audit: `.tmp/display-pdf-freeze-audit-20261113.json`, against the fresh
full copy. All allowed source deltas/hashes and protected-tree byte/size/mtime
comparison are recorded there, including current build outputs and every
packaging file. Prior audits remain unchanged. This writer ran no full suite,
build, CUA/E2E or Git action. Material review and one parent canonical full/build
with final visible qualification remain pending.

#### Final test-only contract alignment

The parent's valid Windows-rights canonical full ran **1 failed, 1235 passed,
1 skipped in 280.18s**. The sole failure was the legacy candidate test indexing
visible column 0 by technical keys, contrary to the approved name-only contract.
Its fixture also registered an index entry without an actual rule/name. A bounded
independent escalation confirmed a stale test and no product defect. The earlier
private-temp WinError-5 attempt was interrupted before cleanup/build; source,
ACL and configuration were unchanged.

The unchanged full copy
`I:\Projekte\AnalyzerResultExtractorV2-FINAL-DISPLAY-PDF-RELEASE-SAFETY-20261113`
contained the exact pre-edit test SHA256
`52ccd4b976699de72c13853eab0245e5fd47d41d35daa64cafcf1402a50d5d10`,
verified again before this first test-only write. Only that test and these two
gate documents change. The fixture now has a genuinely valid active rule with
a proven full name distinct from its filename hint; assertions cover visible
name/missing-name/hint, hidden key/status/IID selection, and unchanged index/rule
bytes and mtimes. No product code, renderer or existing PDF is changed.

Focused `python -B -m pytest -q --tb=short -rs -o faulthandler_timeout=30`,
`PYTHONDONTWRITEBYTECODE=1`, normal Windows execution via `require_escalated`,
used `.tmp/pytest-display-pdf-final-test-alignment-20261113/`:
selectors were `tests/test_test_app_smoke.py::test_test_app_preview_assay_candidates_shows_known_and_unknown`,
`tests/test_test_app_smoke.py::test_test_app_create_draft_from_known_candidate_is_blocked`
and `tests/test_test_app_smoke.py::test_test_app_create_draft_from_unknown_candidate_creates_header_draft`,
first under `candidates`, then only the first selector under `candidate-fixed`.
the candidate-preview plus known/unknown draft-identity cases gave **1 failed,
2 passed, 0 skipped in 3.45s** because the new test initially retained `.asy` in
the already-normalized hint. Correcting only those two expectations, the sole
affected preview case reran **1 passed, 0 skipped in 1.58s** under `candidate-fixed`.
No unchanged cases were rerun, and this writer ran no full/build/CUA/Git.
Audit: `.tmp/display-pdf-final-test-alignment-freeze-audit-20261113.json` against
that exact full copy, with three-file delta and unchanged product/protected hashes.
Independent test-only recheck and the parent's final canonical full/build remain
pending. This is not another product rework or a self-approved gate.

#### Names/PDF Rework 2: one confirmed P2 status finding

Rework 1's original two findings were independently fixed. A new confirmed P2
showed the renderer could call no selected rules/no eligible values unremarkable.
The fresh full safety copy is
`I:\Projekte\AnalyzerResultExtractorV2-DISPLAY-PDF-REWORK2-SAFETY-20261113`:
98,071 files / 95,737 directories / 2.383 GiB, copy exit 1 / comparison exit 0.

Only the existing renderer's status sentence changes: intentional empty selection
says "keine Regeln ausgewählt"; no frozen eligible control points says
"nicht auswertbar". The unremarkable sentence requires an existing selected
canonical `pass`/`not_triggered` finding. Otherwise availability/reasons and actual
warnings/rejections remain explicit. QMMA/Rili applicability is not a Westgard
availability test. No rules, statistics, models, source eligibility, SD handling,
actor binding or previously stored PDF bytes are changed.

Executed commands used `python -B -m pytest -q --tb=short -rs
-o faulthandler_timeout=30`, bytecode disabled, with fresh roots below
`.tmp/pytest-display-pdf-rework2-20261113/`:

| Executed selection in `tests/test_qualitycontrol_pdf.py` | Result | Basetemp suffix |
|---|---|---|
| Public stored two-control close/export case; selected normal/warning/rejection/n0 cases; empty population; unavailable SD and exact export | **7 passed, 0 skipped in 19.40s** | `status` |
| Existing compact/extended control pagination and frozen-baseline-center PDF cases | **2 passed, 0 skipped in 12.55s** | `essential-pdfs` |

The public stored case has c1 n=0, c2 n=1 and `enabled_rules=[]`; open/atomic
close/exact export succeed while both pages explicitly show empty selection and
c1 also shows missing eligible values. The actually evaluated normal case remains
unremarkable even when QMMA's relative applicability is off. Canonical model,
source, stored evidence and DB bytes/mtime preservation are checked.
Main fresh PDF: `status/test_stored_two_control_report0/stored-control-status.pdf`.
Normal/warning/rejection/n0 reports and fresh compact/info/baseline reports remain
under the same fresh test root. Renderer SHA256:
`bb173a9e656c57234a90ead488433ede8e16be0be4d64803bbad42ed4256f633`.

Parent fresh PDF QA passed: pypdf read all **8 reports / 26 pages**; Poppler
confirmed both stored-status pages and the n0 case visually. Normal, warning,
rejection, no values and no selected rules remain distinct. All four compact
page PNGs are pixel-/byte-identical to the previously inspected renderings.
Evidence: `.tmp/display-pdf-rework2-final-poppler-qa-20261113/inspection.json`
and `compact-pixel-comparison.json`. Compact PDF SHA256:
`63594a8feca27ce445bd0ad511b5adf99950d32e731bf450b754a3df3b743e89`;
explained PDF SHA256:
`37ab93e845f91df352fbc96c11e99d1f433959a6f75cf1ac1b38f045377b124b`.

Audit: `.tmp/display-pdf-rework2-freeze-audit-20261113.json`, comparing the four
allowed files against the fresh Rework-2 copy and cumulative scope against the
original display/PDF copy. Prior audits/QA and build artifacts are preserved.
No further source owner, mathematics group, full suite, build, CUA/E2E or Git
action was used. Independent Rework-2 recheck and the parent's one
canonical full/build remain pending.

#### Names/PDF Rework 1: exactly two P2 findings (subsequently fixed)

The first independent review found malformed public JobEvidence name containers
could abort result listing, and unavailable combined timestamps hid otherwise
known frozen date/time raw fields. The fresh full safety copy is
`I:\Projekte\AnalyzerResultExtractorV2-DISPLAY-PDF-REWORK1-SAFETY-20261113`:
97,874 files / 95,614 directories / 2.377 GiB, copy exit 1 / comparison exit 0.

The ResultsController now accepts only list containers, matching dict entries
and nonempty string names; unusable optional names continue through the existing
Writer/Splitter/catalog/missing-name fallback. Critical result errors remain
visible. PDF display uses known frozen `measurement_date_raw` and
`measurement_time_raw` when `measured_at` is unavailable. Existing field reasons
mark the affected raw value "Ungültig"; its known counterpart is preserved and
missing fields remain "Nicht erfasst". There is no reparsing, guessed timestamp,
source/model/statistics/schema change or altered actor binding.

Both commands used `python -B -m pytest -q --tb=short -rs
-o faulthandler_timeout=30`, bytecode disabled, with fresh roots below
`.tmp/pytest-display-pdf-rework1-20261113/`:

| Executed selection | Result | Basetemp suffix |
|---|---|---|
| `test_application_results_controller.py::test_real_job_name_evidence_ignores_unusable_shapes_and_preserves_result_errors` (10 real public-read cases), existing name-priority case, `test_qualitycontrol_pdf.py::test_real_pdf_preserves_frozen_raw_date_time_counterparts_without_interpretation` | **12 passed, 0 skipped in 8.86s** | `findings` |
| Existing compact/explained control pages, frozen-baseline center, unavailable QMMA, actual no-SD evidence/byte-exact export, archived v1/v2 exact/derived prints | **6 passed, 0 skipped in 37.02s** | `essential-pdfs` |

Fresh raw-field PDFs are under `findings/test_real_pdf_preserves_frozen0/`:
`raw-date-time-fields.pdf` and `raw-date-only-fields.pdf`. Fresh compact/explained,
baseline-center and unavailable examples are under the corresponding test
directories in `essential-pdfs/`. Prior layouts/QA and archives remain unchanged;
the preceding initial-package QA is historical, not fresh Rework-1 QA.
New source/protected audit: `.tmp/display-pdf-rework1-freeze-audit-20261113.json`,
against the fresh Rework-1 snapshot, including cumulative comparison to the
original display/PDF snapshot and preservation hashes for previous audits.
Exactly the two owners, their two test files and the two gate documents are in
scope. No full suite, mathematics group, build, CUA/E2E or Git action was run.
The original two Rework-1 findings were independently confirmed fixed; the new
status finding and Rework-2 checkpoint are recorded above. Parent canonical
full/build remains pending; this is not a self-approved gate.

### Final profile-management escalation correction (2026-11-13)

A legitimate unindexed Trash rule `(5f03)` blocked profile management because
the shell enumerated all lifecycle inventory but resolved every field list via
the active index. This is a bounded escalation correction, not a third normal P5
rework. The verified full safety copy is
`I:\Projekte\AnalyzerResultExtractorV2-FINAL-PROFILE-FIX-SAFETY-20261113`:
97,329 files, 95,022 directories, 2.361 GiB, copy exit 1 / comparison exit 0.

Only the existing shell call now requests `list_inventory(kind="active")`.
No archive/profile/rule data is removed or rewritten; active-rule errors remain
visible. The existing worker/stale-dialog test and a real lifecycle-inventory /
callback / mapped-dialog regression ran with bytecode writes disabled:
**2 passed, 0 skipped in 3.32s**, `-B -m pytest`, `-q --tb=short
-o faulthandler_timeout=20 --basetemp .tmp/pytest-final-profile-escalation-20261113`.
The real case preserves Draft/Inactive/History/Trash bytes/mtimes, loads active
field mappings and confirms a broken active rule still raises its error.
Scope: shell, existing QC application tests and these two gate documents only.
Audit: `.tmp/final-profile-escalation-freeze-audit-20261113.json` against the fresh
copy: exactly four allowed existing files changed, none added/removed, and all
13,262 protected files match bytes/size/mtime (output 8,843; packaging 2,063;
config/storage absent on both sides). Prior audits are preserved.
No full/build/CUA/Git was run by this writer.
Independent recheck subsequently passed **2 passed, 0 skipped in 2.30s**.
The parent's canonical full/rebuild now follows the separate presentation package.

| Package | Independent review | Single post-GO full regression | Rules integrity |
|---|---|---|---|
| P1: draft selection and continuation | GO after two reworks | **828 passed, 2 skipped** | PASS |
| P2: embedded PDF validation | GO after one rework | **869 passed, 2 skipped**, 135.82s | PASS |
| P3a: new processing without Excel | GO after two reworks; final independent slice **132 passed** | **954 passed, 3 skipped**, 158.23s | PASS |
| P3b: true reanalysis/result revisions | GO after one rework; independent slices **123 + 161 passed**, rework **37 passed** | **1008 passed, 2 skipped**, 145.97s | PASS |
| P4: unified devices/control profiles/lots | GO after one rework; independent core **73**, QC UI **12**, desktop **80**, architecture **40**; final recheck **15 passed** | **1052 passed, 2 skipped**, 151.51s | PASS |
| P5 plus approved time field: technical qualification; final visible follow-up pending | SD-origin recheck **49 passed**; axis recheck **2 passed**; time-field review **34 passed, 0 skipped**, 8.85s | **1201 passed, 2 skipped**, 140.62s, inside final canonical builder | PASS |

P2 total inventory: 871 cases; P3a: 957 cases (**+86**). Skip classes remain
local Tcl/Tk initialization and Windows symlink privilege. P3a full-suite command:
`.\.venv\Scripts\python.exe -m pytest -q -rs --basetemp .tmp\pytest-package3a-gate-20261112-1`.

Visible synthetic Windows checks passed for P2 maximization, equal PDF/workflow
panes, page navigation, zoom, fit width, case switching and window restoration.
P3a settings visibly present SQLite/PDF storage without an Excel selection.
Screenshots were observed in the orchestrator's computer-use transcript; separate
PNG evidence files were not recorded for these checks. The source GUI was closed.
This is agent verification, not a recorded human operator sign-off.

P3b's single post-GO full command was
`.\.venv\Scripts\python.exe -m pytest -q -rs --basetemp .tmp\pytest-p3b-gate-20261112-1`.
Inventory: **1010 cases**, +53 versus P3a's 957. Known skips: local Tcl/Tk
initialization and Windows symlink privilege. Rules integrity passed with all
five lists empty. The independent protected-data audit found zero content/mtime
differences; the full-rights output comparison confirmed 8,843 files on each side.
Root's exact SHA-256 source/doc comparison against P3B-SAFETY counted 36 changed
files including the execution record. See its P3b gate for scope details.

P4's single post-GO command was
`.\.venv\Scripts\python.exe -m pytest -q -rs -o faulthandler_timeout=60 --basetemp .tmp\pytest-p4-gate-20261112-1`.
Inventory: **1054 cases**, +44 versus P3b. The completed full run did not hang.
Skips were one Tk library load (`ttk/scale.tcl`) and Windows symlink privilege.
Rules validation exited 0 with all five lists empty. One-shot Watchdog and Worker
entrypoints exited 0 in `.tmp/p4-adapter-smoke-20261112` (watch disabled, no jobs).
The two review defects were fixed without altering IDs or migration evidence;
15 independent recheck tests passed without skips. Protected audit: 13,258 files,
zero content/size/mtime differences. P4 source scope: 29 project files, including
documentation, with the bounded six-file rework contained within that scope.

### Final technical qualification (2026-11-13)

The canonical command was `.\.venv\Scripts\python.exe -B packaging/build_onedir.py`,
with `PYTEST_ADDOPTS=-rs --basetemp=.tmp/pytest-final-release-20261113` and
`PYTHONDONTWRITEBYTECODE=1`. Its single post-final-GO regression passed **1201 / 2
skipped** in **140.62s** before any cleanup. Inventory: **1203**, +149 versus P4.
Skips: Windows symlink privilege and a local Tk `ttk/altTheme.tcl` load in
`test_rule_editor_phase6_layout.py`. The earlier candidate's **1167 / 2** run
preceded the visible axis finding and approved time extension; this final rerun
qualifies those subsequent changes, rather than duplicating an unchanged run.

Build, bundle integrity/rules and automatic EXE smoke passed. Independent fresh
ZIP extraction/checksum inspection and startup smoke passed: **720 files**,
**35,317,905 bytes**, ZIP SHA-256
`17c1ac2b53bacd7b745ae826236d31d6e4abfe53534b4c32e8370bd28505174b`;
raw product-input fingerprint
`e520033b3dbd8b6bea4177cebd11bd43c7b63138ac6fcfa7253dcc725694d6f8`.
Rules validation returned five empty lists. One-shot Watchdog/Worker exited 0 in
`.tmp/final-release-adapter-smoke-20261113` (disabled/empty).

The final read-only sample matrix (`rules_matrix_main.py --mode preview
--no-write-report`) returned **2 green / 0 yellow / 9 red**, exit 1. Seven assays
remain absent from the two sample PDFs. The other two now fail with
`configured_fields_empty` instead of the historical optional-field warning:
`(6bd7)` lacks eight configured fields and `(42d4)` lacks `SOLL_S3,FILE_NAME`.
This reflects the approved rule that every configured extraction field must be
populated; it does not establish that those existing rules work on these samples.
Rules and sample PDFs were unchanged. Log:
`.tmp/final-release-rule-matrix-20261113.log`. The older **2/2/7** matrix records
below remain historical; they are not the current sample result.

Full pre-build snapshot: `I:\Projekte\AnalyzerResultExtractorV2-FINAL-RELEASE-SAFETY-20261113`,
94,506 files, 92,165 directories, 2.140 GiB; copy exit 1/comparison exit 0.
Post-build SHA/size/mtime comparison excluded only the three authorized build
targets: **12,524 remaining protected files unchanged**, including 8,843 output
files and `deploy_smoke`. Product-input bytes still match build metadata.
Local evidence: `.tmp/final-release-build-20261113.log`,
`.tmp/p5-final-package-verification-20261112-2.json`,
`.tmp/final-release-protected-audit-20261113.json` (SHA-256
`3ffd9bf2da438da9c812aaec8f088f3e41a9140af393fa381a0efacb853bb55a`).

Earlier final-workflow qualification retained 26 screenshots, three real UI
validations including whole-result reanalysis, 64 backend checks and an actual
packaged PDF closure/export/restart/history check. The final artifact still needs
the targeted visible time-field/axis/PDF follow-up; automatic smoke is not that
evidence. Git/merge/release and human operator sign-off remain unrecorded.

P5's historical implementation checkpoints follow.
See [the execution record](REBUILD_EXECUTION_2026-11-12.md).
All older gate labels and pending-review statements below describe their
historical checkpoint only; the table above is the current rebuild baseline.

## P5 writer checkpoint (2026-11-12, independent review pending)

Scope: immutable Decimal QC analysis and shared chart/PDF model, classic-six-v1,
real bounded-spawn PDF rendering, explicit successor-lot closure, frozen report
history/exact no-overwrite export, existing Results UI, version 2.0.0 and honest
build metadata. Five QC tables, four controllers/services and six views remain.
The optional separate extracted time-field extension is not approved or
implemented in this checkpoint. Existing explicit date/timestamp mappings and
honest same-day ambiguity handling remain.

The fresh full snapshot is
`I:\Projekte\AnalyzerResultExtractorV2-P5-SAFETY-20261112`: 90,799 files,
88,812 directories, 1.866 GiB rounded; copy comparison exit 0 before writes.
HEAD remains `5ae98ea9919215e5aea00232f215ae3f8c0dd1e2`.
Commands use `.\.venv\Scripts\python.exe -m pytest`, fresh synthetic `.tmp/`
basetemps for file fixtures and authorized normal Windows rights. These
executed slices overlap; their counts must not be summed into a regression total.

| Scope | Executed result | Basetemp under `.tmp/` |
| --- | --- | --- |
| Initial complete `tests/test_qualitycontrol_analysis.py` vector slice | **52 passed, 0 skipped in 0.66s** | pure in-memory vectors; no file fixtures |
| Actual PDF generation, large multipage document, atomic evidence/export, timeout cleanup and frozen baseline center | **4 passed, 0 skipped in 19.85s** | `pytest-p5-stage2-green-20261112` |
| Same PDF component file after parent layout findings were corrected | **4 passed, 0 skipped in 19.22s** | `pytest-p5-stage2-layout-fixed-20261112` |
| Complete small analysis file including excluded-observation history barrier, plus configured-limit/unavailable PDF case | **54 passed, 0 skipped in 3.62s** | `pytest-p5-stage2-parameters-20261112` |
| New Application close/history/export and render-failure/source-race cases | **2 passed, 0 skipped in 3.89s** | `pytest-p5-stage3-controller-20261112` |
| Architecture plus affected chart/history/source-generation cases | **43 passed, 0 skipped in 6.63s** | `pytest-p5-stage3-ui-fixed-20261112` |
| Explicit witness/export shell actions | **2 passed, 0 skipped in 1.62s** | `pytest-p5-stage3-actions-20261112` |
| Runtime version, packaging metadata/preflight-before-cleanup and shell-title payload | **22 passed, 0 skipped in 2.12s** | `pytest-p5-stage4-20261112` |
| Affected `tests/test_desktop_ui_v21.py` file | **79 passed, 2 skipped in 10.85s** | `pytest-p5-stage4-title-ui-20261112` |

Earlier component attempts are not green gate evidence: the first combined
PDF/analysis run had 53 passed / 2 failed (large-report timeout and absent
pdftotext executable). Cached glyph metrics/file-based exchange bounded the
large report; text checks now use an isolated MuPDF process. Subsequent focused
attempts exposed/fixed a missing µ glyph and an assertion that failed on valid
line wrapping. The initial App/architecture selection had 54 passed, one Tcl
skip and two architecture failures: the UI's timestamp string replacement was
replaced by the existing presenter API. The green affected slice is above.
Final desktop skips were local Tcl/Tk library initialization, not assertion
passes. No full suite was run by the writer.

The parent independently rendered all **44 PDF pages** (38 + 2 + 2 + 2) with
Poppler at 110 dpi, extracted all four documents with independent pypdf and
inspected eight representative page images. Stage-2 visual QA is **GO** after
bounded layout corrections: table separators, whole control/chart blocks,
source-bound table continuation, wrapped reference URLs, Originalstand label,
configured QMMA 10% bound, µg/L and baseline n. SOLL 100 versus frozen mean 91 /
SD 1 / QMMA 6% and no-SD/no-value unavailability were independently confirmed.
Artifacts: `.tmp/p5-poppler-qa-layout-fixed-20261112/`; generated PDFs remain in
the named component-test roots. This is component verification, not final E2E.

Source/protected-tree evidence against the exact P5 snapshot is recorded in
`.tmp/p5-freeze-audit-20261112.json`: **27 source/doc/test files** (four added,
23 changed, none missing). The full protected inventory contains **13,258 files**:
**13,256 have zero byte/size/mtime differences**, `packaging/build_onedir.py`
is the one authorized source edit, and the exact file
`packaging/__pycache__/build_onedir.cpython-314.pyc` is the one separately
approved generated-bytecode difference from the authorized test import. No
cache pattern or other packaging artifact is excluded; deploy_smoke remains
unchanged. Counts: rules 22, input 2, jobs 2,302, output 8,843, build 14, dist 16,
unchanged packaging 2,057, plus the two identified packaging files. `config/`
and `storage/` are absent on both sides; no real devices.json was created.
The first full audit remains unchanged in
`.tmp/p5-freeze-audit-before-cache-restore-20261112.json`; despite that preparatory
filename no cache restoration occurred. Both cache versions are preserved as
hash evidence/copies under `.tmp`. After the narrow exception was approved,
packaging alone was rechecked; the complete first comparison covers the other
protected groups. The P4 audits and full P5 snapshot are preserved.
`git diff --check` returned 0 (existing line-ending notices only).

Status: **IMPLEMENTED / FOCUSED_CHECKS_PASSED / INDEPENDENT_REVIEW_PENDING**.
P5 full regression, current rules gate, actual cleanup/build, final visible
packaged E2E, Git writes, release and human acceptance: **NOT RUN by the writer**.
Builder failure tests inject failures and touch only synthetic temporary targets;
they are not a real build or permission to claim a release-qualified artifact.

### P5 review rework 1: SD origin compatibility (independent recheck pending)

The first independent P5 review failed on one P1: a frozen SD could remain
available after changing its unit or measured-variable interpretation. The
review reported no other material findings. The parent verified a fresh full
snapshot before authorizing this bounded correction:
`I:\Projekte\AnalyzerResultExtractorV2-P5-REWORK1-SAFETY-20261112`, 91,167 files,
89,109 directories, 1.897 GiB rounded, copy comparison exit 0. HEAD is unchanged.

New models use `arev2-qc-analysis-v2`. Pure analysis receives a separately read
and frozen origin context. Unit/IST/number-interpretation mismatches or missing
origin leave SD unavailable with an explicit UI/PDF reason; QMMA stays available.
Profile names, dates, groups, rules, relative limits, SOLL and MIN/MAX do not
impose a blanket version restriction. Existing raw references and manifests are
unchanged. The only approved P4-owner extension is `_freeze_sd` recording the
current profile version for **new** manual references before hashing their ID.
Older manual references use an unbroken immutable lot history or fail closed.
Archived supported v1 models/PDFs remain exact and are never recalculated.

All following commands used the venv, `-q --tb=short -o faulthandler_timeout=20`,
synthetic stores and normal Windows rights. Runs overlap and are not a full suite.

| Selected scope | Result | Basetemp under `.tmp/` |
| --- | --- | --- |
| Full small analysis file + 20 public profile/lot semantic cases + initial three legacy-origin cases | **89 passed, 0 skipped in 6.48s** | `pytest-p5-rework1-core-20261112` |
| Origin-read race; Results with two stores/same IDs; real archived-v1 PDF; existing atomic-close/render-race cases; small mismatch/baseline PDFs | **8 passed, 0 skipped in 12.48s** | `pytest-p5-rework1-app-pdf-20261112` |
| Architecture and existing P4 optional/manual/baseline freezing case | **41 passed, 0 skipped in 5.08s** | `pytest-p5-rework1-boundaries-20261112` |
| Final raw-reference hash guard: four legacy cases plus unit-change/redeclaration and Results guards | **8 passed, 18 deselected, 0 skipped in 3.36s** | `pytest-p5-rework1-refhash-20261112` |

The genuine mismatch PDF's extracted text confirms QMMA 6 B and
"SD gehört zu einer anderen Einheit", unavailable SD bands/Westgard and v2
algorithm identity. A separate real v1 evidence/PDF was loaded after profile/unit
change and explicit reopening without calling the analyzer, then exported with
identical original JSON/hash/bytes. No unchanged 44-page QA set was repeated.
The temporary final-qualification helper was not executed or modified.

Rework source/protected hashes are recorded separately in
`.tmp/p5-rework1-freeze-audit-20261112.json`; the initial P5 audit, original P5
snapshot and fresh Rework-1 snapshot are preserved. Against Rework-1 safety,
**17 existing files changed, none added/removed**; cumulative original-P5 scope
is **29 files: four new and 25 changed**. The full-rights Rework-1 audit verified
**zero byte/size/mtime differences across all 13,258 protected files**, including
8,843 output and all 2,059 packaging files. This comparison includes the builder
and its already generated bytecode, unchanged since the fresh rework snapshot;
the original P5 audit's two explicit differences remain separately recorded.
`config/` and `storage/` are absent on both sides. The acceptance helper SHA-256
matches the fresh snapshot and remains unexecuted. The new real PDF is
`.tmp/pytest-p5-rework1-app-pdf-20261112/test_real_pdf_explains_incompa0/incompatible-sd-report.pdf`.
Review recheck, full suite,
current rules gate, actual builder/cleanup, final E2E and Git/release remain
**NOT RUN by the writer**. This checkpoint is not a passed P5 gate.

### P5 review rework 2: visible date-axis bounds (independent recheck pending)

The parent verified the fresh full snapshot
`I:\Projekte\AnalyzerResultExtractorV2-P5-REWORK2-SAFETY-20261112`: 94,338 files,
92,110 directories, 2.135 GiB, copy exit 1 / comparison exit 0. The correction
changes only the existing UI/PDF date-axis labels: visible ordinal xlo/xhi,
controlled unrepresentable dates, true right-edge PDF alignment, no date labels
for an empty point series. Model/statistics/version IDs and old PDFs are unchanged.

Exactly two targeted checks ran with `-q --tb=short -o faulthandler_timeout=20`
and `.tmp/pytest-p5-rework2-axis-20261112`: **2 passed, 0 skipped in 16.14s**.
The Canvas case checks actual labels after zoom/pan/reset and date boundaries;
the small real PDF case verifies padded endpoints, text geometry and empty/date-
edge cases. No broad suite, build, Git or E2E was run by this writer. Separate
protection/source evidence: `.tmp/p5-rework2-freeze-audit-20261112.json`.
Normal-rights SHA/size/mtime comparison found **zero differences across all
13,262 protected files**, including 8,843 output and 2,063 packaging files;
config/storage are absent on both sides. Exactly the six authorized existing
source/test/doc files changed, with none added/removed. The Rework-1 audit is
preserved unchanged. Small PDF examples are `axis-visible.pdf`, `axis-date-edge.pdf`
and `axis-empty.pdf` in the basetemp's `test_real_pdf_axis_uses_visibl0` directory.

Parent-reported prior acceptance: **1167 passed, 2 environment skips in 187.08s**,
builder/ZIP, three visible validations including a new revision, 64 backend E2E
checks and a real packaged PDF closure. This is predecessor evidence, not proof
of this patch. After this focused recheck passes, a fresh snapshot/separate task
will implement the user's newly approved optional extracted time field; it is
not implemented by Rework 2. The parent will combine the final full/build gate
after both steps. Git remains NO-GO until the remaining gates pass.

### Optional extracted time field checkpoint (2026-11-13, review pending)

RW2 independently passed two checks without skips in 9.17s. The parent then
verified the fresh full `I:\Projekte\AnalyzerResultExtractorV2-P5-TIMEFIELD-SAFETY-20261112`
snapshot: 94,368 files, 92,119 directories, 2.136 GiB, copy exit 1 / parity exit 0.
The explicitly approved optional field/format pair is implemented in the existing
profile/source/dialog owners. Old normalized no-map profiles contain no new
keys; separate time is strict, never inferred or replaced by midnight. SD,
analysis, model/API/schema/store/builder, existing snapshots and PDFs are unchanged.

Executed focused checks (synthetic roots, normal Windows rights):

| Scope / command suffix for `.\.venv\Scripts\python.exe -m pytest` | Result |
| --- | --- |
| `tests/test_qualitycontrol_profiles_lots.py tests/test_application_qualitycontrol.py tests/test_qualitycontrol_pdf.py -k "optional_time or measurement_dates_have_no_import" -q --tb=short -o faulthandler_timeout=20 --basetemp .tmp/pytest-p5-timefield-20261113` | **33 passed, 1 failed, 73 deselected in 11.18s**; only the PDF phrase assertion failed because table columns interleave wrapped text |
| `tests/test_qualitycontrol_pdf.py::test_optional_time_pdf_names_errors_and_preserves_old_profile_sd_and_evidence -q --tb=short -o faulthandler_timeout=20 --basetemp .tmp/pytest-p5-timefield-pdf-20261113` | **1 passed, 0 skipped in 5.66s**, after accepting the valid line/column wrapping; no product change |

Coverage includes pair/format conflicts, date/time and DATUM/ZEIT, %H:%M,
%H:%M:%S and %H%M, missing/blank/24:00/format errors, reverse run IDs with same-day
2_2s and 4_1s, equal-time/no-map/unknown-time barriers, blank/default/load/save
dialog fields, readable source/PDF reasons and unchanged old profile/SD/PDF evidence.
The parent also verified its real unchanged-DB legacy golden; DB SHA/mtime and
complete profile/manifest/token matched, recorded in
`.tmp/final-qualification-20261112-2/timefield-legacy-after.json`.
The two owner hashes remain identical to that check. A deliberately new profile
version still changes head/token normally; no stale guard was weakened.

Separate audit: `.tmp/p5-timefield-freeze-audit-20261112.json`; earlier audits and
all snapshots remain unchanged. Exactly 13 authorized existing files changed,
none were added/removed. Normal-rights comparison found zero byte/size/mtime
differences across 13,262 protected files (output 8,843; packaging 2,063;
config/storage absent on both sides). The final small PDF is
`.tmp/pytest-p5-timefield-pdf-20261113/test_optional_time_pdf_names_e0/optional-time-errors.pdf`.
Review/final full/build/visible follow-up are
parent-owned and pending; this writer ran no full suite, build, Git or E2E.

## Historical P3b implementation checkpoint (superseded by passed gate above)

The green predecessor remains P3a. This is bounded writer verification, **not a
P3b passed gate**. HEAD is unchanged. The exclusive writer started only after the
full `I:\Projekte\AnalyzerResultExtractorV2-P3B-SAFETY-20261112` copy and dry-run
comparison. No Git writes, rule JSON changes, live runtime/product writes, full
suite, E2E or build were performed for this checkpoint.

All commands below use `.\.venv\Scripts\python.exe -m pytest`, `-q`, and the
named fresh `.tmp\` basetemp. Slices overlap; their counts must not be summed.

| Focused scope | Basetemp | Executed result |
|---|---|---|
| `test_result_revisions`, `test_dbwriter`, `test_resultvalidation`, `test_resultstore` | `pytest-p3b-owner1-20261112` | **54 passed**, 4.57s |
| `test_jobcontroller_reanalysis`, field completeness, dual output, export retry, resolver, extractor | `pytest-p3b-source1-20261112` | **89 passed**, 6.44s |
| Revisions + reanalysis + new Application reanalysis + validation, after completion/source/store fixes | `pytest-p3b-contracts-final2-20261112` | **48 passed**, 8.25s |
| Revision owner including alias/ingestion races and post-alias rollback; genuine second-assay sink failure; displayed Results binding | `pytest-p3b-atomic-checks-20261112` | **18 passed**, 4.18s |
| Final legacy failed-queue expectation and both Results save/correct displayed-token cases | `pytest-p3b-final-targets-20261112` | **3 passed**, 1.47s |

The UI/PDF/architecture slice `pytest-p3b-ui-final-20261112` executed **129 passed,
1 skipped** plus three new fixture setup failures. The latter were corrected
without product changes and each passed in exact targeted reruns: **2 passed**
in `pytest-p3b-ui-fixtures-20261112`, and the displayed-occurrence case in the
18-case atomic slice above. The earlier 50/50 minimum-size layout finding was
fixed with a bounded grid; its exact two-test retest passed in
`pytest-p3b-layoutfix-20261112`. Known Tk initialization remains the skip cause.

The compatibility slice `pytest-p3b-compatibility-20261112` covered existing
JobController SQLite/retired export/field tests, RuleResolver, Extractor,
ResultStore, DbWriter, ResultsController, JobQueue and architecture: **184 passed**
and one now-obsolete assertion allowed a new validation on a FAILED queue. Its
fixture now preserves old legacy validation metadata while asserting new-action
rejection; that exact case passed in the final three-case slice. No failing
assertion remains unresolved in these executed slices.

New qualification includes verified initial source copies, full PDF/block/rule
hashes and bytes, original device, frozen legacy descriptors, unchanged original
rows/job plans, optional-field rework, whole old/new selection, complete reads
beyond 500 rows, one captured store despite live settings changes, idempotency,
stale-screen rejection, real SQLite writer races, alias collision/rollback and
restart, read-only legacy access, actual spawned parsing plus timeout/crash
cleanup, focused multiselection/PDF targeting and separate validation.

Restricted Windows temp access first produced WinError 5. The identical focused
owner command was rerun with normal user rights; subsequent bounded commands used
those rights. No ACL was changed. Final independent review, protected-data audit,
one post-GO full regression and any final operator/EXE qualification remain with
the orchestrator. This record makes no human acceptance claim.

## Historical Package 3a implementation checkpoint (superseded by current gates above)

Current contract: new processing, validation and correction are SQLite-only.
Legacy `both`/`excel` inputs normalize before processing; historical output plans
remain read-only and no longer expose an executable Excel retry. Workbook fixtures
are checked by SHA-256 and mtime, with writer spies and no new XLSX/temp/lock files.
SQLite crash recovery, stable ledger IDs, append-only validation across restart,
and queue-DONE archive eligibility remain covered.

| Focused slice | Result |
|---|---|
| Runtime, settings, application services, UI characterization | **54 passed** in **1.65s** |
| JobController, Processing, DBWriter, ResultValidation, ResultsController | **98 passed** in **12.89s** |
| Extraction, Watch/Worker, existing harness/unit smoke, desktop, architecture | **238 passed, 1 skipped** in **78.75s** (known Tk environment variance) |
| Rules integrity (schema compatibility; no rule JSON edited) | **PASS**, all five integrity lists empty |
| Pre-Package-3a snapshot SHA-256 comparison | **0 differences** across **13,226 files** in rules, input, output, jobs, storage, locks and both packaging output trees |

Checkpoint review returned `GATE_FAILED` with two findings: malformed V2 SQLite
plans could be overwritten, and two LegacyTestApp actions bypassed the protected
Processing retry boundary. Rework 1 adds shared structural plan validation and
routes both legacy actions through that boundary. Its bounded checks completed
with **67 passed** (plan corruption/recovery + Processing), **8 passed, 1 skipped**
(legacy retry actions; known Tk variance), and **40 passed** (architecture).
Plan/SQLite/queue bytes and mtime remain unchanged in all 32 corrupt-plan cases;
valid SQLite crash recovery and normal new-failure retries remain green.
Independent re-review is pending; these checks do not approve the package.

Rework 2 makes existing unreadable or non-object job JSON explicitly non-retryable
through the existing Evidence boundary. Processing and both LegacyTestApp actions
refuse it without calling the low-level queue retry or changing queue/state bytes
or mtime. Missing states and normal new failures remain retryable. Bounded checks:
**28 passed** (Evidence/Processing/direct unreadable-submit preservation),
**12 passed** (both legacy actions), and **40 passed** (architecture).
Final independent review is pending; no full regression or package approval is implied.

Tests use isolated temporary project roots and normal Windows rights. The initial
restricted-token attempt could not create pytest's shared temp root (WinError 5);
no ACL was changed. No full suite, E2E execution or packaging was run for this
implementation checkpoint. Independent review and post-review gates are pending.
The gate records below remain historical evidence and are not a Package-3a approval.

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

## Historical P4 writer checkpoint (subsequently GATE_PASSED)

P4 adds the unified versioned SQLite device/QC owner, explicit legacy migration,
profile/source/lot revisions and supplied immutable PDF-evidence publication.
Existing Settings/Results controllers and views organize configuration/lot work;
four controllers, four service fields and six views remain. P5 statistics and
PDF generation are not implemented by this package. UI close is disabled with
the explicit label "Abschluss mit PDF-Auswertung folgt".

All commands below used `.\.venv\Scripts\python.exe -m pytest`, synthetic
temporary roots and the indicated repository-local basetemp. These are separate
executed runs and must not be added into a fictitious regression total.

| Run / selected tests | Executed result | Basetemp under `.tmp/` |
| --- | --- | --- |
| Stage 1: `tests/test_qualitycontrol_inventory.py tests/test_runtime_devices.py tests/test_application_settings_controller.py tests/test_jobcontroller_dual_output.py -q --tb=short` | **52 passed in 2.10s** | `pytest-p4-stage1-fixed-20261112` |
| Stage 2: `tests/test_qualitycontrol_profiles_lots.py tests/test_qualitycontrol_inventory.py tests/test_runtime_devices.py -q --tb=short` | **32 passed in 5.91s** | `pytest-p4-stage2-20261112` |
| First Stage-3 checkpoint: `tests/test_architecture_gates.py tests/test_application_settings_controller.py tests/test_application_results_controller.py tests/test_desktop_ui_v21.py tests/test_test_app_smoke.py tests/test_qualitycontrol_inventory.py tests/test_qualitycontrol_profiles_lots.py -q --tb=short` | **269 passed, 2 skipped in 55.28s** (before final bounded UI/compatibility refinements) | `pytest-p4-stage3-first-20261112` |
| Final isolated desktop file: `tests/test_desktop_ui_v21.py -vv -x -o faulthandler_timeout=20 --tb=short` | **78 passed, 2 skipped in 9.24s** | `pytest-p4-stage3-ui-diagnosis-20261112` |
| New QC application/UI file: `tests/test_application_qualitycontrol.py -vv -x -o faulthandler_timeout=20 --tb=short` | **10 passed, 1 skipped in 7.61s** (before adding the later historical-ID case) | `pytest-p4-stage3-qcui-diagnosis-20261112` |
| Final compatibility and skipped-dialog slice: `tests/test_qualitycontrol_inventory.py tests/test_runtime_devices.py tests/test_jobcontroller_dual_output.py tests/test_application_qualitycontrol.py::test_qc_form_save_is_visible_at_small_mapped_size[lot] -q --tb=short -o faulthandler_timeout=20` | **23 passed in 2.80s**, including the previously skipped mapped lot dialog | `pytest-p4-stage3-regression-20261112` |
| Final smoke/architecture slice: `tests/test_test_app_smoke.py tests/test_architecture_gates.py -q --tb=short -o faulthandler_timeout=20` | **100 passed in 28.19s** | `pytest-p4-stage3-smoke-20261112` |
| Later historical identity: `tests/test_application_qualitycontrol.py::test_historical_id_arriving_after_setup_is_visible_draft_until_explicit_save tests/test_qualitycontrol_inventory.py -q --tb=short` | **12 passed in 2.27s** | `pytest-p4-stage3-late-identities-20261112` |

The initial restricted Stage-1 attempt produced fixture setup errors and was
aborted without a completed result. Targeted runs then used the authorized
normal Windows rights. The first such Stage-1 run had 50 passed / 2 failed:
the old Settings test still assumed implicit JSON authority, and an actual
file-disappearance test encountered a Windows open-file handle from existing
ResultStore readers. The test contracts/lifetime setup were corrected; no
foreign ResultStore implementation was rewritten.

A combined final Stage-3 run (QC application + profile/lot + inventory +
architecture + desktop + smoke) stopped producing output and was explicitly
interrupted without a final result. Isolated files subsequently completed as
listed above. This is **not evidence of a product hang being fixed**. Tcl-load
skips reported unavailable `init.tcl`, `icons.tcl`, or `ttk/sizegrip.tcl` under
the Python 3.14 / Tk 8.6 installation; `TCL_LIBRARY`/`TK_LIBRARY` were not set.
The new lot-dialog skip was separately rerun and passed. The final visible EXE
and single-Tk user acceptance remain separate later work.

Acceptance cases include migration rollback/idempotency, exact store overrides,
historical identifiers and no fabricated identifiers, one authority, no-write
browsing, immutable complete profile/control history, explicit dates/numbers,
603-row source population, individual validation ambiguity, source/config race
rechecks, closed-lot/late-data/reopen, optional/manual/frozen baseline SD without
calculation, atomic supplied model/PDF evidence, and preserving old PDF bytes.
Two stores with identical local IDs cannot receive actions from stale dialogs;
late background responses are discarded. Mapped Tk checks cover reachable
Save actions at 640x420, Settings at 960x620, and state-aware lot actions.

The fresh full safety snapshot is
`I:\Projekte\AnalyzerResultExtractorV2-P4-SAFETY-20261112` (87,940 files,
84,807 directories, 1.713 GiB). HEAD stayed
`5ae98ea9919215e5aea00232f215ae3f8c0dd1e2`. The exclusive writer's full-rights
audit found **0 byte/size/mtime differences across 13,258 protected files**:
rules 22, input 2, jobs 2,302, output 8,843, build 14, dist 16, packaging 2,059.
`storage/` and `config/` are absent on both sides; no real `devices.json` was
created or migrated. Per-file source SHA-256 and protected-tree evidence live
in `.tmp/p4-freeze-audit-20261112.json`, against this exact P4 snapshot.

At this historical writer checkpoint the independent/post-review gates had not
yet run. They subsequently passed for P4 as recorded in the current gate table;
these old implementation notes do not supersede that GATE_PASSED status.

### Historical P4 review rework 1 (two P2 findings resolved; P4 passed)

The independent review identified two bounded compatibility defects. The writer
corrected only `src/runtime/devices.py` and the existing QC profile dialog in
`interfaces/tk/widgets/dialogs.py`, with corresponding existing tests and these
checkpoint notes.

Automatic device resolution now uses the stored default only when that device
is active; otherwise it uses the first active inventory entry, or the existing
DEFAULT_DEVICE sentinel when none is active. The migrated stored default and
source evidence are not rewritten. Explicit historical selected IDs remain
resolvable. The original P4 inactive-default test had inverted the pre-P4
selection contract; its corrected active/no-active cases also verify unchanged
JSON/SQLite bytes and mtimes.

The profile device selector no longer collapses aliases sharing both display
name and SN/LNR/EVA. Ordinary unique names remain short; collisions show the
identifying attributes and, where necessary, the stable device ID. No new
attribute uniqueness rule is imposed. The mapped regression case verifies that
both IDs remain visible/selectable and both existing profiles load and save
without reassignment.

Executed smallest affected slice:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_devices.py tests/test_application_qualitycontrol.py::test_profile_device_options_keep_alias_ids_with_identical_name_and_serial -q --tb=short -o faulthandler_timeout=20 --basetemp .tmp/pytest-p4-rework1-20261112
```

Result: **6 passed, 0 skipped in 4.26s**, under authorized normal Windows rights,
using synthetic temporary sources/stores. No broad regression, E2E or build was
repeated. The fresh Rework-1 audit again found **0 byte/size/mtime differences
across all 13,258 protected files**, including 8,843 output files; `config/` and
`storage/` remain absent on both sides. The separate evidence is
`.tmp/p4-rework1-freeze-audit-20261112.json`; the initial
`.tmp/p4-freeze-audit-20261112.json` is preserved. HEAD stayed unchanged.
Independent recheck and the parent's post-review gates subsequently passed;
see the current P4 gate above.
