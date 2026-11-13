# Analyzer rebuild: execution and qualification record

Status: **GATE_PASSED for final technical qualification: Statistics, source-manifest correction, full regression, fresh ZIP/EXE and visible PDF/Rule-Editor checks. Exact Git/merge/tag/release outcomes are recorded by the publication step in the PR and release provenance manifest. Human acceptance is separate.**
Date: 2026-11-12; latest technical qualification: 2026-11-13. Implementation checkout: `I:\Projekte\AnalyzerResultExtractorV2`.
HEAD: `5ae98ea9919215e5aea00232f215ae3f8c0dd1e2`, branch `master`.
This record preserves the full requested outcome, including final E2E, Windows
EXE qualification, Git-steward review/improvements, merge and GitHub release.
The approval record in section 8 authorizes the remaining contracts; execution
and verification are recorded separately and unfinished work remains incomplete.

### Final technical qualification (2026-11-13): GATE_PASSED

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

## Build-provenance runtime exclusion checkpoint (2026-11-13)

The user explicitly approved removing local runtime/work metadata from build
inputs while retaining the original local job files. Before writes, the full
copy `I:\Projekte\AnalyzerResultExtractorV2-BUILD-PROVENANCE-SAFETY-20261113`
completed copy exit 1 / comparison exit 0. The exact four-file scope is
`packaging/build_onedir.py`, `tests/test_packaging_build.py` and these gate docs.

Only the existing package input scan now checks relative directory components
with casefold against reserved runtime/cache/work names. Genuine code/static
assets and the separate static rule input path remain; new source needs no Git
registration to affect the fingerprint. The existing resolved-root escape check
is unchanged. Focused packaging tests ran **5 passed, 9 deselected, zero skips
in 1.04s** with `-B`, bytecode disabled, normal Windows rights and fresh
`.tmp/pytest-build-provenance-20261113/focused`. Nested runtime preservation,
code/assets/rules/new-source sensitivity, root-escape rejection before reading,
honest metadata and failure-before-cleanup are covered. Exact command is in
TESTBASELINE; no real full suite/build was invoked.

The actual input scan is **199→197**, excluding exactly the two known local
`interfaces/tk/jobs` files, preserving StatisticsView. All remaining inputs are
tracked or planned according to read-only Git inventory; no staging occurs.
The two runtime files retain exact snapshot SHA/size/mtime. Product fingerprint:
`745d71cc60caac7a99e22ab21ec9dd011091056132b39b826f15e6d1a0b3c40c`.
Audit: `.tmp/build-provenance-freeze-audit-20261113.json`, explicitly separating
the approved builder-source delta from unchanged protected files/build outputs
and Statistics files. Previous snapshots/audits remain preserved. Independent
review and the final canonical full/build subsequently passed; see final technical
qualification above. This section preserves the writer checkpoint.

## Dedicated Statistics navigation checkpoint (2026-11-13)

The user explicitly requested an own Statistics tab. After the verified closed
full copy `I:\Projekte\AnalyzerResultExtractorV2-STATISTICS-NAV-SAFETY-20261113`
(copy exit 1 / comparison exit 0), the approved 14-file scope moved the existing
QC state/widgets/chart/source/history/report actions from ResultsView into the
single StatisticsView. Navigation `statistics` follows `results`; Results retains
report list/detail/validation and no longer constructs QC or its entry button.
The same ResultsController/four services and deferred QC tasks/store/generation
guards remain. There is no second QC flow, controller/API, math/PDF/schema/rule
or builder change. P0 docs and the UI inventory now consistently declare seven
views. Local runtime files and all earlier evidence remain preserved.

The small selected architecture/report/minimum-size/QC callback/chart/export
checks ran **48 passed, 2 failed in 18.20s**, then three affected test-adapter
cases ran **1 passed, 1 failed, 1 skipped in 4.31s**. Failures were obsolete
Results-back/stub assumptions; the known Tcl initialization skip and corrected
stub guard passed in separate fresh processes: **1 passed in 3.79s** and
**1 passed in 1.86s**, zero skips. All 50 selected cases have passing executions;
overlapping runs are not an added inventory. Exact scopes/flags/roots are in
TESTBASELINE. No mathematics/PDF suite, full run, build or CUA/E2E was replayed.

The parent's 24-check final GUI proof and 4/8-page PDF inspection are retained
predecessor evidence. The new audit is
`.tmp/statistics-nav-freeze-audit-20261113.json`, against this exact safety copy.
Independent Statistics review subsequently returned GO: **50 passed, zero skips,
no findings**. The parent's final canonical full/build and visible follow-up now
follow the separately approved build-provenance package above.

## Assay-name and compact-control-PDF checkpoint (2026-11-13)

### Final test-only contract alignment

The valid parent canonical full completed **1 failed, 1235 passed, 1 skipped in
280.18s**. Its only failure used visible candidate names as if they were technical
keys and registered a rule index row without a real named rule file. The bounded
independent escalation confirmed stale test expectations, not a product defect.
The preceding private-temp WinError-5 run was interrupted before cleanup/build;
no source/ACL/configuration repair occurred.

The existing full
`I:\Projekte\AnalyzerResultExtractorV2-FINAL-DISPLAY-PDF-RELEASE-SAFETY-20261113`
still matched all product bytes and test SHA256
`52ccd4b976699de72c13853eab0245e5fd47d41d35daa64cafcf1402a50d5d10`
before the first test-only edit. The exact three-file scope is
`tests/test_test_app_smoke.py` plus these two gate documents. The test now proves
a valid active rule name distinct from the filename hint, explicit missing-name
display, hidden-key/status/IID selection, and unchanged index/rule bytes/mtime.
No product, renderer, rule-root, builder or existing PDF bytes change.

Normal Windows focused checks used `require_escalated`, Python `-B`, bytecode off
and `.tmp/pytest-display-pdf-final-test-alignment-20261113/`: the preview and two
neighboring identity/draft cases first had **1 failed, 2 passed, 0 skipped in
3.45s** (test hint expected an already-stripped `.asy` suffix); only the corrected
preview reran **1 passed, 0 skipped in 1.58s**. Exact selectors/flags are in
TESTBASELINE. This writer ran no full suite/build/CUA/Git. The separate audit is
`.tmp/display-pdf-final-test-alignment-freeze-audit-20261113.json` against the
exact current safety copy. Independent test-only recheck and the parent final
canonical full/build remain pending; this is not a third product rework.

### Rework 2: one confirmed status-presentation finding

The same reviewer confirmed Rework 1's two findings fixed, then identified a new
P2: an empty rule selection/no eligible control values could still print the
unremarkable Westgard sentence. Before Rework-2 writes the verified full copy
was `I:\Projekte\AnalyzerResultExtractorV2-DISPLAY-PDF-REWORK2-SAFETY-20261113`,
98,071 files / 95,737 directories / 2.383 GiB, copy exit 1 / comparison exit 0.

The four-file scope is exactly the existing renderer, its tests and these two
gate documents. Presentation now distinguishes no selected rules, no eligible
values, explicit unavailable reasons and actually performed selected canonical
checks. Only the latter may receive the unremarkable sentence; existing warnings
and rejections remain. No QMMA applicability gate, new statistical calculation,
source/model/SD/actor/schema/rule/builder change or archive rewrite is introduced.

Fresh focused PDF tests under `.tmp/pytest-display-pdf-rework2-20261113/` ran
**7 passed, 0 skipped in 19.40s** (public stored two-control case with c1 n=0 /
c2 n=1 / no selected rules, normal/warn/reject/n0, empty population, unavailable
SD and exact export), then **2 passed, 0 skipped in 12.55s** (fresh compact/info
and frozen-baseline reports). The stored case proves actual open/close/export
and unchanged model/evidence/DB bytes; normal-case Westgard remains independent
of QMMA's relative applicability. Executed command flags and artifact paths are
in TESTBASELINE; main report is
`status/test_stored_two_control_report0/stored-control-status.pdf`.

Renderer SHA256 is `bb173a9e656c57234a90ead488433ede8e16be0be4d64803bbad42ed4256f633`.
Parent pypdf read all **8 reports / 26 pages**; Poppler confirmed both actual
stored-status pages and the n0 case visually. Normal/warn/reject/no values/no
selected rules are distinct. All four compact page PNGs match the previous
visual qualification byte-/pixel-exactly. Evidence is
`.tmp/display-pdf-rework2-final-poppler-qa-20261113/inspection.json` and
`compact-pixel-comparison.json`; no layout regression was found in that scope.
The separate audit `.tmp/display-pdf-rework2-freeze-audit-20261113.json` compares
the fresh four-file delta and cumulative original display/PDF scope; old audit,
QA and current build files remain preserved. No full/mathematics suite, build,
CUA/E2E or Git action was run by this writer. Independent Rework-2 material
recheck and the parent's canonical full/build remain pending.

### Rework 1 after exactly two P2 findings (subsequently fixed)

The first formal names/PDF review failed on two bounded presentation defects:
unusable optional name containers in public JobEvidence aborted result listing,
and unavailable `measured_at` hid known frozen date/time raw fields. The fresh
full copy before writes is
`I:\Projekte\AnalyzerResultExtractorV2-DISPLAY-PDF-REWORK1-SAFETY-20261113`:
97,874 files / 95,614 directories / 2.377 GiB, copy exit 1 / comparison exit 0.

Only ResultsController and the existing PDF renderer change: suitable name lists,
dict items and string names are checked without suppressing critical result
errors; bad optional evidence falls through the existing owners. Missing combined
timestamps display only the captured raw date/time fields, marking invalid values
from the existing reasons and preserving known counterpart fields. No reparsing,
inferred clock, source/model/math/actor-binding/schema change occurs. Archived
PDF bytes and the existing default/derived export contract are preserved.

The two affected test files ran with `-B`, bytecode disabled, timeout 30, fresh
`.tmp/pytest-display-pdf-rework1-20261113/{findings,essential-pdfs}`:
**12 passed, 0 skipped in 8.86s** for actual public legacy JobEvidence/catalog
shapes, name priority and real raw-field PDF geometry; **6 passed, 0 skipped in
37.02s** for current compact/info/baseline/unavailable/byte-exact/derived archive
cases. Detailed executed selectors and fresh PDF paths are in TESTBASELINE.
The new audit is `.tmp/display-pdf-rework1-freeze-audit-20261113.json`, comparing
the six-file scope against this fresh snapshot and cumulative scope against the
original display/PDF copy. Prior audit/QA files remain preserved. This writer
ran no full/mathematics suite, build, CUA/E2E or Git action. Both findings were
independently confirmed fixed; the new status finding/Rework-2 checkpoint is
recorded above. The parent canonical full/build remains pending.

### Initial implementation checkpoint (before Rework 1)

The separately approved package started after verified full safety copy
`I:\Projekte\AnalyzerResultExtractorV2-DISPLAY-PDF-SAFETY-20261113`:
97,352 files / 95,042 directories / 2.361 GiB, copy exit 1 / comparison exit 0.
It reuses existing owners and adds no controller/service/view, schema or public
entrypoint. Names follow selected revision/original provenance, public stored
Writer/Splitter evidence, then the active RuleSuiteController catalog. Missing
names and filename hints are explicit; duplicate-name selections bind by index,
and technical identity/filter values remain unchanged. New QC models freeze only
separate presentation names; source manifests, raw SD and mathematics are intact.

The v2 renderer starts each control on its own page, retains control/assay/charge
on table continuations, and lists only that control's raw values/date/time/user
and properly bound validator/UTC evidence. Missing, ambiguous or mismatched
evidence is visible. Date-only profiles print date-only axes and no synthetic
measurement clock. Default output is compact: concrete statistics, limits,
findings and exclusions; legend/interpretation/method details are optional.
`include_explanations=False` preserves exact archived PDF export. True creates a
separate no-clobber print from the stored model, with a strictly checked spawn
mode and no DB/model/old-PDF update or recalculation. Supported v1 models remain
unchanged and exactly exportable.

Executed focused evidence is listed with commands/basetemps in TESTBASELINE:
**49 passed** names/controllers; **41 passed** existing owner/architecture;
**4 passed** initial presentation/Tk; **2 passed** final real PDFs;
**12 passed** final archive/print/spawn/model-reader contract;
isolated irrational display **1 passed**, isolated chart **1 passed**;
legacy DB/name/identity and candidate/model-reader slice **5 passed**.
These overlap and are not a summed case inventory. Intermediate collection/temp
setup errors and wrapped-text/date-only assertion failures are preserved in the
baseline; the affected Tk skip passed in isolation. No unchanged full mathematics
group or full suite was rerun by this writer.

Parent final PDF QA used pypdf on all **4 + 15 pages**, Poppler on all compact
pages and appendix 5/15, and the one-page SOLL100/center91/SD1 case. No material
layout findings remain in that inspected scope. Evidence:
`.tmp/display-pdf-final-poppler-qa-20261113/inspection.json`;
renderer SHA256 `22c97de38eebc7e37b3a9969a1dbcd54a03d76463f1c9245c242f56984ee14c0`.
Freeze/source/protected evidence is separately recorded in
`.tmp/display-pdf-freeze-audit-20261113.json` against the new snapshot; all prior
audits and build outputs remain preserved. Formal material review, one parent
canonical full/build, final visible CUA and the authorized Git/release sequence
remain pending. This checkpoint does not self-authorize the review gate.

## Final profile-management escalation correction (2026-11-13)

The visible packaged profile action failed on the retained Trash-only key
`(5f03)`: shell lifecycle inventory defaulted to all, while field resolution uses
the active index. The parent/reviewer approved the bounded escalation correction
after a verified full copy:
`I:\Projekte\AnalyzerResultExtractorV2-FINAL-PROFILE-FIX-SAFETY-20261113`,
97,329 files / 95,022 directories / 2.361 GiB, copy exit 1 / comparison exit 0.
This is not a third normal P5 rework or a fixture-data cleanup.

Exactly the existing shell call changes to `list_inventory(kind="active")`.
Rules/controllers/APIs/storage/metadata/build logic and historical data are
unchanged. The existing deferred-worker/stale-store test was adapted, and one
actual active-plus-Draft/Inactive/History/Trash callback/dialog case verifies
correct fields, unchanged archive bytes/mtimes and propagation of broken-active
errors. Selected tests used `python -B -m pytest`, timeout 20 and
`.tmp/pytest-final-profile-escalation-20261113`: **2 passed, 0 skipped in 3.32s**.
No broader tests, build, CUA or Git action was run by this writer.

The four-file source/protected audit is
`.tmp/final-profile-escalation-freeze-audit-20261113.json`; previous safety copies
and audit files remain unchanged. Exactly the four allowed existing files
changed, with none added/removed; all 13,262 protected files match bytes/size/mtime
(output 8,843; packaging 2,063; config/storage absent on both sides).
Independent recheck subsequently passed **2 passed, 0 skipped in 2.30s**.
The separately approved presentation/PDF package above received its own fresh
snapshot and GO; the parent's canonical full/rebuild follows its material review.

## 1. Authority and answered questions

The user authorizes own GPT-6.1-SOL agents, one package at a time after a green
predecessor, Astra plan review, necessary computer use and the final Git/release
sequence. Plan changes still require confirmation. Current user instructions
override historical Cursor/model defaults; one product writer and one material
checkpoint reviewer remain the execution limits. Requested models/efforts do not
attest observed runtime models.

Astra's corrected plan review and two read-only code-design investigations form
the basis of sections 4–6. They are design evidence, not execution evidence.

Confirmed Dialogkatalog topic: `9fb6d9aa04dc4c158676a8c1361ab34b`.
Catalog: `15a8d5cca67c407a9c698947c513bca4`, revision 2.
Immutable processed handover: `0e72adb7aef24ad6baeae7803ea1a9a2`.
Latest handover and live topic were re-read during this continuation: still
current, processed, no later topic messages. Earlier processed handovers:
`ce28520d872744578df0c7d8c89a165e` (validation/reanalysis),
`2b5f00d65c93478a8fee62328567ff55` (initial QMMA).

Confirmed requirements:

- Normal maximized validation window, original PDF left, validation right.
- Reanalyse selected, still-unvalidated cases with the active rule; compare whole
  old/new results and let the human choose. Empty configured fields require rework.
- Device Name plus at least one of SN/LNR/EVA; preserve stable device IDs.
- Arbitrarily many named controls per assay, editable later; fixed IST/SOLL/MIN/MAX
  mappings. Controls belong to their kit lot.
- Measurement time comes from an assay-mapped extracted field, without an import
  time fallback. Lot start is its oldest measurement date; close when a newer
  dated lot exists; explicit versioned reopen preserves previous PDF evidence.
- New workflows use SQLite/PDF; Excel output is retired. Existing files remain.
- SD is optional: manual or from confirmed validated baseline values, then frozen.
- Only human-validated results feed QMMA/LJ; interactive and PDF output; offer
  the six named Westgard rules with assay-specific activation.
- Assay-specific Rili-BÄK applicability/relative deviation settings are required.

## 2. Safety and exact current boundary

Full dirty-tree snapshots, including tracked and untracked/ignored files:

| Snapshot | Position | Verification |
|---|---|---|
| `I:\Projekte\AnalyzerResultExtractorV2-RULE-ACTIVATION-UX-SAFETY-20261112` | before P1 | retained |
| `I:\Projekte\AnalyzerResultExtractorV2-REMAINING-PLAN-SAFETY-20261112` | before P2 | 77,427 files; copy comparison exit 0 |
| `I:\Projekte\AnalyzerResultExtractorV2-PACKAGE3A-SAFETY-20261112` | before P3a | 79,122 files; copy comparison exit 0 |
| `I:\Projekte\AnalyzerResultExtractorV2-P3B-PLAN-SAFETY-20261112` | after green P3a, before this documentation | 84,073 files; 79,933 directories; 1.428 GiB rounded; copy comparison exit 0 |
| `I:\Projekte\AnalyzerResultExtractorV2-P3B-SAFETY-20261112` | after plan documentation, before approval recording/implementation | 84,075 files; 79,930 directories; 1.428 GiB rounded; copy comparison exit 0 |
| `I:\Projekte\AnalyzerResultExtractorV2-P4-SAFETY-20261112` | after P3b gate recording, before P4 implementation | 87,940 files; 84,807 directories; 1.713 GiB rounded; copy comparison exit 0 |
| `I:\Projekte\AnalyzerResultExtractorV2-P5-SAFETY-20261112` | after P4 passed-gate recording, before P5 implementation | 90,799 files; 88,812 directories; 1.866 GiB rounded; copy comparison exit 0 |
| `I:\Projekte\AnalyzerResultExtractorV2-P5-REWORK1-SAFETY-20261112` | after initial P5 review, before bounded SD-origin rework | 91,167 files; 89,109 directories; 1.897 GiB rounded; copy comparison exit 0 |
| `I:\Projekte\AnalyzerResultExtractorV2-P5-REWORK2-SAFETY-20261112` | after parent build/acceptance, before date-axis rendering correction | 94,338 files; 92,110 directories; 2.135 GiB; copy exit 1 / comparison exit 0 |
| `I:\Projekte\AnalyzerResultExtractorV2-P5-TIMEFIELD-SAFETY-20261112` | after RW2 independent GO, before separately approved optional time field | 94,368 files; 92,119 directories; 2.136 GiB; copy exit 1 / comparison exit 0 |
| `I:\Projekte\AnalyzerResultExtractorV2-FINAL-RELEASE-SAFETY-20261113` | after time-field independent GO, before final canonical regression/build | 94,506 files; 92,165 directories; 2.140 GiB; copy exit 1 / comparison exit 0 |

Robocopy comparisons establish copy metadata/size parity, not a full cryptographic
hash audit. P3a's independent protected-data audit separately established 13,226
files with no added/removed/content differences and seven workbooks with unchanged
mtime. No reset, clean, checkout or blanket staging has been performed.

At the earlier plan continuation's preflight: 49 tracked modifications and three untracked
P2 source/test files; index empty; HEAD and live GitHub master match. No product
writer was active while that design document was prepared. Those preflight
counts describe that historical point. The parent subsequently verified the
fresh full P5 snapshot above and gave the exclusive product writer GO; all
other agents remained read-only for product sources. No Git writes, real
cleanup/build, final E2E or product-data migration were performed by the writer.

## 3. Completed package gates

### P2: embedded PDF validation

1. **Phase/gate:** P2 PDF/validation workplace.
2. **Preflight:** HEAD before/after unchanged; one writer; pre-P2 snapshot above;
   P1 files preserved; no unexplained external edit recorded.
3. **Scope:** existing ValidationView, ResultsController/API/DTO, process-isolated
   renderer, shell maximize/restore, frozen child dispatch, tests and aligned docs.
   No second validation flow/controller. One bounded review rework fixed fitting
   below manual zoom limits and recovery after a page error/source shrink.
4. **Contracts:** four application controllers and six views retained; PDF source
   resolution through ingestion; MuPDF only in a spawned render process; bounded
   images, timeout/cleanup and stale selection rejection.
5. **Tests:** final independent review 121 passed/one Tk skip (passed separately).
   One post-GO full run: **869 passed, 2 skipped in 135.82s** using
   `.\.venv\Scripts\python.exe -m pytest -q -rs --basetemp .tmp\pytest-package2-gate-20261112-1`.
   Rules integrity: all five lists empty. Inventory 871, +41 versus P1's 830.
6. **Visible checks:** synthetic three-page source in
   `.tmp/package2-visible-acceptance-20261112`; maximized titled window, equal
   panes, page change, zoom, fit, case switch and prior window restoration observed.
   GUI closed; screenshots are in computer-use transcript, not separate PNG files.
7. **Risks:** prior cumulative Tk stall not reproduced in identical bounded order;
   known Tcl/Tk/symlink environment skips. Frozen build/final E2E still NOT RUN.
8. **Status:** `GATE_PASSED` (agent qualification; human sign-off not recorded).
9. **Next:** P3a, subsequently completed below.

### P3a: new processing without Excel

1. **Phase/gate:** P3a SQLite-only transition.
2. **Preflight:** HEAD before/after unchanged; one writer; complete pre-P3a
   snapshot; accepted P1/P2 behavior preserved at overlapping files.
3. **Scope:** runtime/processing defaults, legacy mode normalization, settings,
   JobController outputs/retired APIs, first validation/correction, diagnostics
   and protected retries including LegacyTestApp, tests/docs. The original
   34-file slice gained two existing test files for read-Evidence/legacy cases.
4. **Contracts:** existing Excel files/frozen plans preserved; new SQLite plans;
   no writer call from processing/validation/correction; malformed/unreadable
   historical state is non-retryable; missing state/new processing failure is
   retryable. Archive eligibility remains processing DONE. `excel_rules` schema
   and historical writer APIs remain compatible.
5. **Tests:** final independent review **132 passed** after two bounded reworks.
   One post-GO full run: **954 passed, 3 skipped in 158.23s** using
   `.\.venv\Scripts\python.exe -m pytest -q -rs --basetemp .tmp\pytest-package3a-gate-20261112-1`.
   Rules integrity: all five lists empty. Inventory 957, +86 versus P2.
6. **Checks:** independent audit of protected files/workbooks as above; SQLite-only
   settings visibly checked in the synthetic root; GUI closed. Migration tests
   prove no Workbook writes and preserve bytes/mtime of historical evidence.
7. **Risks:** old explicit Legacy admin cleanup tools remain user-invoked support
   functions; new workflows do not call them. Final E2E/build/release NOT RUN.
8. **Status:** `GATE_PASSED` (agent qualification; human sign-off not recorded).
9. **Next:** P3b, approved and subsequently completed below.

### P3b: immutable reanalysis and revision-bound validation

1. **Phase/gate:** P3b true reanalysis.
2. **Preflight:** HEAD before/after unchanged; one writer; full pre-P3b snapshot
   `I:\Projekte\AnalyzerResultExtractorV2-P3B-SAFETY-20261112`; dry-run parity exit 0.
3. **Scope:** 36 source/test/document files differ from that exact snapshot by
   SHA-256, including this execution record; no extra product owner or entrypoint.
4. **Contracts:** append-only candidate/selection history, corrected identity
   aliases, original-source/rule proof, whole-result choice, strict configured
   field completeness, current-revision human validation and no-write readers.
5. **Tests:** independent initial reviews 123 and 161 passed; one bounded rework
   retained read-only UNC URI fallback and removed duplicate architecture text.
   Final independent review **37 passed**, **GO**, no findings. One post-GO full
   run: **1008 passed, 2 skipped in 145.97s** using
   `.\.venv\Scripts\python.exe -m pytest -q -rs --basetemp .tmp\pytest-p3b-gate-20261112-1`.
   Rules validation exit 0 with all five lists empty. Inventory 1010, +53 vs P3a.
6. **Checks:** protected rules/input/jobs/storage/build/dist/packaging preserved;
   8843 output files matched the snapshot with zero content/mtime differences
   under ordinary Windows access. Restricted enumeration was incomplete and was
   independently rechecked; no files were removed. `git diff --check` passed.
7. **Risks:** environment skips are Tcl initialization and symlink privilege.
   Real UNC share, final integrated GUI/E2E/build and Git/release NOT RUN.
8. **Status:** `GATE_PASSED` (agent qualification; human sign-off not recorded).
9. **Next:** approved P4, subsequently completed below.

### P4: one device/QC authority, control profiles and lots

1. **Phase/gate:** P4 unified inventory/profile/source/lot ownership.
2. **Preflight:** HEAD/master unchanged; one product writer; complete P4 safety
   snapshot listed above, dry-run parity exit 0. Existing dirty work preserved.
3. **Scope:** 29 project files (9 added, 20 changed), including docs/tests; new
   six-file `src.qualitycontrol` owner, existing Runtime/Application/Tk owners.
   Narrow legacy `gui_min_ext.py` store forwarding included as documented.
4. **Contracts:** one explicit Results SQLite authority, no-write browsing,
   explicit migration preserving IDs/JSON evidence, immutable complete profile
   revisions, complete validated-source population, strict parsing, frozen SD
   references, atomic supplied evidence/lot closure and preserved reopen history.
   Four controllers/six views retained. P5 calculations/rendering NOT implemented.
5. **Tests:** independent core 73, QC UI 12, desktop 80 and architecture 40 passed
   without skips. Two P2 findings (inactive automatic default, colliding device
   labels) were corrected in one bounded rework; final independent **15 passed**,
   **GO**, no findings. Single post-GO full run: **1052 passed, 2 skipped in
   151.51s**; exact command in TESTBASELINE. Inventory 1054, +44 versus P3b.
   Rules validation exit 0, all five lists empty.
6. **Checks:** independent and rework protected audits: zero content/size/mtime
   differences across 13,258 files, including 8,843 output files; config/storage
   absent on both sides. One-shot Watchdog/Worker adapters exited 0 in isolated
   `.tmp/p4-adapter-smoke-20261112` (disabled/empty). `git diff --check` passed.
7. **Risks:** earlier combined focused Tk wait remains historical evidence, not
   a claimed product fix; the completed full suite did not hang. Full-run skips:
   Tk `ttk/scale.tcl` load and symlink privilege. Final visible EXE/E2E, P5 and
   Git/release remain NOT RUN; human acceptance not recorded.
8. **Status:** `GATE_PASSED`.
9. **Next:** approved P5 after a fresh complete safety snapshot.

## 4. Approved P3b contract: true reanalysis

**Architecture approved by the user's explicit question reply; implemented and GATE_PASSED as recorded in section 3.**

Keep stable `runs.id`, original rows, job files and frozen output plans. DbWriter
adds immutable `run_result_revisions` and `run_result_selections`; ResultStore
projects the selected revision and exposes its history. Original result is
revision 0; every selection identifies the exact chosen revision and has one
successor per expected selection token. Record request ID, source/rule hashes,
exact rule snapshot, device, completeness/errors, actor and timestamps.

ResultValidation adds an explicit selected revision/selection binding to its own
append-only records. Existing validation records mean original revision 0.
Migration is additive, transactional and versioned per component; ResultStore
reads never migrate. No reinterpretation of already validated measurements.
Compatibility calls without an expected token are allowed only for an untouched
original selection with no pending reanalysis; revised selections require the
explicit token so an older caller cannot approve values it did not inspect.

Workflow, through existing ResultsController/ValidationView:

1. Select one or more open cases. Capture the effective SQLite store and expected
   selection tokens once; recheck eligibility at the service boundary.
2. Resolve the original/archived PDF through ingestion. Snapshot and verify its
   complete SHA-256; uniquely prove the original assay block/source occurrence.
   Original descriptors/block hashes in normal job plans can support legacy
   cases. Missing/ambiguous evidence produces an actionable source clarification,
   never a guess based on first matching assay or list position.
3. Freeze the current active rule; preserve the run's original device. Use the
   existing parser/normalizer/splitter/extractor. Persist a candidate, not a new
   effective result. New initial processing also records source/rule provenance.
4. Compare whole old/new payloads and metadata; append the human keep/accept
   decision. A separate validation action binds the chosen state.
5. Any configured empty field creates rework evidence and blocks acceptance and
   validation. Approved strict choice contract: both choices satisfy the fields
   of the frozen reanalysis rule, so retaining an old result cannot bypass a newly
   missing configured field. The UI explains the reason and offers rule rework.

To support genuine corrections of identity-bearing fields, include an append-only
dedupe ownership/alias mapping to the same stable run. Normal ingestion consults
original and revised identities. A collision with another existing run requires
explicit duplicate clarification; never silently reassign ownership. This avoids
restricting reanalysis to fields that happen not to affect the dedupe key.
Alias claims become authoritative only with acceptance of their revision.
Collision checks, alias insertion and result selection commit in the same
`BEGIN IMMEDIATE` transaction; rejected candidates claim nothing. Earlier accepted
aliases remain. Normal ingestion checks claims under its write lock and preserves
the exact-attempt test for `already_persisted`; a different import matching an
alias still requires duplicate review.

Atomicity: DbWriter candidate/selection writes and ResultValidation writes take
`BEGIN IMMEDIATE` on the same captured database **before** authoritative checks.
The validation guard exposed by ResultValidation is strictly read-only; current
schema-creating validation readers cannot be called inside an outer writer.
Recheck effective selection, pending reanalysis, completeness and validation
under that lock. Expensive PDF extraction occurs outside the transaction; repeat
checks when publishing. Request IDs handle repeated submission; stale expected
tokens reject concurrent choices. No raw connection enters the UI/Application.

Bounded existing owners: `src/dbwriter`, `resultstore`, `resultvalidation`,
`jobcontroller`; ResultsController/Application DTOs; existing ValidationView and
shell; extractor error details only if needed. Exactly four controllers; no new
queue, entrypoint, CLI or Excel path. Names of new methods/tables remain internal
design details until implementation review, within these responsibilities.

Acceptance: legacy/new migration, original-source proof, active-rule/device
provenance, whole-result choice/history, repeated requests, all-field rework,
corrected dedupe/collision, >1 selected case, validation/selection races,
restart/crash rollback, read-only projections and UI/PDF stale-selection tests.

### P3b writer checkpoint

The exclusive writer implemented the section-4 contract within the existing
DbWriter, ResultStore, ResultValidation, JobController and ResultsController
owners. RuleResolver captures its exact once-read source bytes/hash; Extractor
errors retain partial fields. Existing ValidationView/shell gained multiselection,
whole-result comparison and explicit keep/accept actions. The existing Results
view supplies its displayed binding to save/correct actions. Four controllers and
six views remain. A bounded `list_jobs(create_missing=False)` extension preserves
strict read guards without changing the default queue API.

Normal submit parses a verified temporary copy and rechecks the live source hash
before the first SQLite sink. A shared read-only completion guard rejects failed
or unfinished source jobs/queues before analysis and again under the authoritative
candidate/choice/validation write lock. Legacy grouping IDs come from ResultStore's
existing grouping, including multiple rows from the same PDF.

Focused executed evidence and corrected test/layout findings are recorded in
[`TESTBASELINE.md`](TESTBASELINE.md). Tests preserve original rows/job plans and
use synthetic temporary roots. Writer verification is not self-approval.
Independent checkpoint review, protected-data audit and the single post-review
full regression subsequently passed as recorded in section 3. E2E/build/Git/release
were not run. P4 may start after its fresh full safety snapshot.

## 5. Approved P4 contract: one QC/device authority

**Architecture approved; P4 implementation, independent recheck and parent post-review gates passed as recorded in section 3. Writer notes below are historical.**

Add `src.qualitycontrol.api`, using the **same effective SQLite store** as Results.
It owns device versions, assay/control profile versions, lot lifecycle, optional
frozen SD references, analysis snapshots and PDF evidence. Existing
SettingsController and ResultsController orchestrate it; retain four controllers
and six views. SettingsView houses configuration; ResultsView houses lot/QC work.

Runtime device APIs become compatibility delegates to that single authority,
receiving the explicit effective store instead of independently using a default
database. QC does not import runtime. Original `config/devices.json` is retained
as migration evidence, then ceases to be a parallel authority. Migration is
explicit/idempotent/transactional with source hash and component schema version.
Preserve device IDs and historical references; legacy IDs lacking required
identifiers become visible incomplete entries. Never fabricate SN/LNR/EVA.

Store immutable complete profile revisions with stable control IDs and exact
IST/SOLL/MIN/MAX field mappings. Later renaming/reconfiguration preserves history.
Configure the extracted measurement-date field/format, numeric grammar, unit,
applicability/relative deviation settings, optional SD and chosen QC profile.
Use finite decimal values and explicit date parsing; preserve raw strings.
Malformed/qualified/ambiguous values are diagnosed, never converted to zero or
given an import-date fallback. Target/unit conflicts within a series require
configuration clarification rather than choosing the first value.

Group by device, assay and exact extracted kit lot. Lot start is its oldest
eligible measurement date. Closing records a newer lot/date witness and freezes
the source/configuration manifest; late data requires explicit reopen with a new
lot revision. Prior snapshots/PDFs remain available. SD stays optional; a manual
or confirmed-baseline reference is immutable. No SD means SD-dependent evaluation
is unavailable, while ordinary validation and QMMA remain usable.

Validated-source access needs a strict read-only ResultValidation API: its existing
readers intentionally create schema and must preserve that older contract.
Capture all eligible rows (not a UI 500-row page), effective unambiguous validation,
revision, raw values and hashes into the analysis manifest. Do not claim multiple
independent reads are one atomic latest snapshot; the manifest defines the exact
source population, rechecked before publication.

Acceptance: migration rollback/idempotency, correct store override, legacy IDs,
single authority, no-write browsing, profile revision history, parsing errors,
complete population, closed-lot/late-data/reopen, optional/frozen SD.

### P4 writer checkpoint

The exclusive writer implemented this contract in the new `src.qualitycontrol`
owner and the existing Runtime/JobController/Settings/Results/Tk owners. Exactly
five QC tables hold immutable versions and supplied analysis/PDF evidence in
the explicitly selected Results store. No P5 statistics or PDF rendering runs
in P4. The existing UI uses German named forms, source field selections and
background I/O; close remains visibly disabled until PDF evaluation is present.
Four controllers, four service fields and six views remain.

Runtime device compatibility now requires the captured effective store and uses
lazy QC imports. Before setup the incomplete DEFAULT_DEVICE sentinel preserves
ordinary imports; explicit historical selected IDs are resolved without database
reads or registration. QC eligibility requires usable inventory identity. An
unreadable inventory produces a controlled FAILED JobResult for new resolution;
historical DONE jobs retain their skip. Migration and subsequent editing preserve
all observed historical IDs. IDs arriving later appear as an incomplete editor
draft, never as automatic registration. The narrowly approved scope addition
`gui_min_ext.py::_refresh_device_choices` only forwards its existing effective
store, as required for the legacy caller.

Profiles retain complete mappings/stable controls and explicit parsing rules.
Source manifests include all relevant rows, raw/parsed fields, current result,
selection and unambiguous matching validation, hashes, configuration and reasons.
The executed population case includes 603 rows. Sources/configurations are
rechecked under the QC write lock. Lot start uses the oldest eligible extracted
date; an extracted time remains intact. Late closed-lot data needs a reasoned
reopen; earlier snapshots/PDF bytes remain immutable. Optional SD, manual SD and
confirmed baseline values are frozen without calculating SD or mean in P4.

Fresh safety snapshot verified before writes:
`I:\Projekte\AnalyzerResultExtractorV2-P4-SAFETY-20261112` (87,940 files,
84,807 directories, 1.713 GiB). HEAD stayed
`5ae98ea9919215e5aea00232f215ae3f8c0dd1e2`. A full normal-rights protected-tree
audit against that exact snapshot found zero byte/size/mtime differences across
13,258 files, including all 8,843 output files. `config/` and `storage/` are
absent on both sides. Original runtime/product data and rule JSON were untouched.

The separate executed runs and commands are in
[`TESTBASELINE.md`](TESTBASELINE.md): Stage 1 52 passed; Stage 2 32 passed;
first Stage-3 checkpoint 269 passed/2 skipped; final isolated desktop 78 passed/
2 Tcl skips; new QC application/UI 10 passed/1 Tcl skip; targeted compatibility
and previously skipped lot-dialog rerun 23 passed; smoke/architecture 100 passed;
later historical-ID check plus inventory 12 passed. Do not add these overlapping
run totals. A combined final Stage-3 run was interrupted after an unexplained
Tk wait; isolated runs completed. No product-hang fix or full-suite outcome is
claimed from that interruption.

This writer checkpoint was subsequently independently reviewed and the parent's
single post-GO full regression/rules/adapter checks passed; see section 3.
At that historical P4 checkpoint, final E2E/build/Git/release had not run and P5
had not started. The later P5 evidence is recorded in section 6.

### P4 independent review: rework 1

The independent checkpoint review found two material P2 defects. The bounded
rework restores the pre-P4 automatic device choice: stored default only if
active, otherwise first active device, otherwise the existing DEFAULT_DEVICE
sentinel. Stored migration defaults/evidence and explicit historical-ID
resolution remain unchanged. The corresponding initial inactive-default test
expectation was corrected to the original compatibility contract.

The existing profile dialog now retains every device ID even when aliases have
the same name and serial/other identifying attributes. Labels expand only for
collisions; aliases are neither merged nor prohibited. A mapped test loads and
saves existing profiles for both IDs without reassignment.

Product changes are limited to `src/runtime/devices.py` and
`interfaces/tk/widgets/dialogs.py`. The smallest affected test slice
(`tests/test_runtime_devices.py` plus the exact new profile-alias regression in
`tests/test_application_qualitycontrol.py`) completed with **6 passed, 0 skipped
in 4.26s**; command and basetemp are in TESTBASELINE. The separate Rework-1
full-rights audit again reports zero protected byte/size/mtime differences across
13,258 files, including all 8,843 output files. `config/`/`storage/` are absent
on both sides. Initial freeze evidence and the P4 safety snapshot are preserved;
HEAD is unchanged. Rework evidence is
`.tmp/p4-rework1-freeze-audit-20261112.json`.

This first bounded rework subsequently passed independent recheck (15 passed,
zero skips, GO). The parent's post-GO full/rules/adapter gates passed as recorded
in section 3. No E2E, build or Git write was run for this rework.

## 6. Approved P5 contract: QMMA, Levey-Jennings and Westgard

**Feature scope and classic profile confirmed; P3b/P4 are green. P5 is implemented after the verified fresh snapshot; focused checks passed and independent review is pending.**

One immutable analysis model supplies the interactive chart and the PDF. Include
measurement/validation/revision IDs, dates, raw/parsed values, included/excluded
counts and reasons, device/assay/lot/control/profile/SD identities and algorithm
versions. Human extraction validation and statistical QC status remain separate.

For a consistent target, QMMA is `sqrt(sum((IST - SOLL)^2) / n)`; also show
the relative percentage when the positive target permits it. No SD is required
for this calculation. Do not derive SD from manufacturer MIN/MAX. Missing SD
means SD bands and Westgard are unavailable, never an automatic green result.
Store the guideline/reference version; do not claim the user's lot-based report
alone proves complete regulatory compliance.

Approved versioned profile `classic-six-v1` makes the classic procedure
explicit: an absolute current-group value strictly above 2 SD is the structural
trigger for rejection-rule evaluation, independent of enabled checkboxes.
`1_2s` controls the displayed warning only; a previous group's trigger is not latched.
`1_3s`, `2_2s`, `R_4s`, `4_1s` and `10x` are rejection findings under that
procedure. Profiles select enabled rules per assay; no silent modern variant.
`R_4s` requires one control above +2 SD and another below -2 SD in the same
analytical run. Longitudinal sequences stay within the same device/assay/lot,
stable control and parameter version. Multiple controls from one stored assay
run share that analytical run; repeated measurements need an explicit grouping
key from the source/profile. A common calendar date is not a run identifier.
Insufficient grouping/history is marked unavailable. The implementation review
must include threshold equality, warning trigger, cross-control and across-run
reference cases for all six enabled rules.

Store the frozen analysis and generated PDF bytes/hash as immutable evidence;
export those exact bytes. Prepare rendering outside long database locks, then
recheck source/config tokens and commit report/closure atomically. Rendering
failure leaves the lot open. PDF dependency and process isolation are included
in P5/packaging review; no cross-repository runtime dependency.

Primary references checked in this continuation:

- [BÄK formula, 2023 reference text](https://www.bundesaerztekammer.de/fileadmin/user_upload/BAEK/Themen/Qualitaetssicherung/_Bek_BAEK_RiLi_BAEK_ONLINE_FINAL_VERS_26_05_2023.pdf), definition on page 2.
- [BÄK edition listing](https://www.bundesaerztekammer.de/themen/aerzte/qualitaetssicherung/richtlinien-leitlinien-empfehlungen-stellungnahmen): the live page lists a 2026 revision with publication date 13 November 2026; its 2026 PDF could not be fetched in this check. Do not label the 2023 text the current applicable edition without rechecking at P5/release.
- [Westgard's original definitions](https://www.westgard.com/westgard-rules.html): classical warning-trigger distinction and within-run R4s.
- [Westgard's within-run R4s clarification](https://www.westgard.com/lessons/westgard-rules/westgard-rules/quest7.html): one control above +2 SD and one below -2 SD; a numerical range above 4 SD alone is insufficient.

### P5 writer checkpoint and staged evidence

P5 adds only internal `qualitycontrol/analysis.py` and `pdf_report.py` behind
the existing public owner. The immutable canonical model preserves the entire
source manifest and unchanged raw P4 SD references, then adds Decimal QMMA,
baseline mean/sample SD, classic-six-v1 findings, availability reasons, counts
and the shared UI/PDF chart. Equal/unproven times and known unusable observations
are sequence barriers; deterministic IDs/list order never become chronology.
Threshold equality is not an exceedance. SD/ordering failures stay unavailable,
while eligible-value QMMA and separately proven analytical groups remain useful.

The renderer uses a fresh MuPDF spawn, 25 s including slot wait plus bounded
terminate/kill cleanup, file-based exchange, 200 pages / 64 MiB PDF and 16 MiB
model. The generated PDF is reopened/verified and hashed. Existing App/Results
methods manage analysis, explicit newer witness selection, atomic P4 closure,
stored historical models and exact no-clobber PDF export. Existing Tk Results
shows control selection, findings and point provenance with zoom/pan; TaskRunner
and store/generation binding reject stale callbacks. No controller, view, table,
service field, rule JSON, dependency or entrypoint was added.

Executed focused checks (separate overlapping runs, not a summed total):

| Stage / evidence | Result |
| --- | --- |
| Initial complete analysis vectors | **52 passed**, 0.66s |
| Real PDF component file, first final green | **4 passed**, 19.85s |
| PDF file after parent layout feedback | **4 passed**, 19.22s |
| Full small analysis file plus configured-limit/unavailable PDF case | **54 passed**, 3.62s |
| Application closure/history/export and render/source races | **2 passed**, 3.89s |
| Architecture plus affected chart/stale-generation cases | **43 passed**, 6.63s |
| Explicit witness/export shell actions | **2 passed**, 1.62s |
| Runtime/build metadata, synthetic fail-before-cleanup, title | **22 passed**, 2.12s |
| Affected desktop file | **79 passed, 2 local Tcl/Tk skips**, 10.85s |

Exact test slices and fresh basetemps, initial failed attempts and their bounded
corrections are in [TESTBASELINE.md](TESTBASELINE.md#p5-writer-checkpoint-2026-11-12-independent-review-pending).
No writer full-suite run was performed. The parent rendered all 44 pages of
four real PDFs with independent Poppler and independently extracted all text
with pypdf; eight representative page images were inspected. Stage-2 visual QA
is **GO** after fixing separators, page-bound control/chart blocks, row
continuations and reference wrapping. QMMA limit, reference kind/frozen n and
SOLL100 versus baseline center91/SD1/QMMA6 were visible. Evidence remains under
`.tmp/p5-poppler-qa-layout-fixed-20261112/` and the component-test roots.

Version **2.0.0** is now declared in pyproject. Runtime build info resolves
relative to code or the EXE, independent of ARE_HOME; background loading updates
the existing window title. The canonical builder captures raw-byte product
inputs, runs the single full regression before cleanup, rechecks those inputs,
and prepares honest version/base-commit/dirty-state/dependency/time metadata.
Raw CRLF hashes are not claimed equal to Git LF blobs. No future merge SHA or
release qualification is invented. Only the three authorized output targets
may be replaced; deploy_smoke is preserved. Tests used synthetic destinations;
the real builder/cleanup was **NOT RUN** by the writer.

The P5 snapshot remains unchanged. Separate source/protected evidence is
`.tmp/p5-freeze-audit-20261112.json`: 27 source/doc/test files (four new,
23 changed, none missing) with per-file SHA-256. The complete 13,258-file
protected inventory separates **13,256 unchanged files**, the allowed builder
source edit and exactly one generated-bytecode difference at
`packaging/__pycache__/build_onedir.cpython-314.pyc`. The parent approved that
single cache path after the full comparison exposed the authorized test import's
output; no broad cache exclusion or restoration occurred. The first audit and
before/after cache evidence are preserved under `.tmp`; packaging alone was
rechecked after classification. All other packaging artifacts, including
deploy_smoke, match byte/size/mtime. Output contains 8,843 matching files;
config/storage are absent on both sides. Original P4/rework evidence is retained.
`git diff --check` returned 0 with line-ending notices only.
The optional separately mapped extracted time field was not approved or
implemented at that initial checkpoint. It is now explicitly approved (section
8), but remains unimplemented until its separate task after Rework-2 GO.

Checkpoint status: **IMPLEMENTED / FOCUSED_CHECKS_PASSED /
INDEPENDENT_REVIEW_PENDING**. This is not self-approval. After material-review
GO the parent owns the canonical builder's one full regression, current rules
gate, actual build, final visible E2E and authorized Git/release sequence.
Those final steps and human acceptance remain **NOT RUN** for P5.

### P5 material review: bounded rework 1

The first independent review identified one P1: a baseline/manual SD remained
available when the same stable control was assigned a different unit or IST
interpretation. The parent reported no other material findings and authorized
this correction only after the fresh full Rework-1 snapshot above passed parity.

The read-only QC API now captures immutable origin profile/hash, reference hash
and origin version into additional `sd_reference_context`. Pure analysis v2
compares stable profile/device/assay/control identity, IST mapping, numeric
grammar and effective unit/unit field. Missing/ambiguous legacy origin or
incompatibility disables SD/z/bands/Westgard with visible reasons; QMMA remains
independent. Name/date/group/rule/relative-limit/SOLL/MIN/MAX changes alone remain
compatible. Legacy manual origin needs its complete continuous immutable lot
chain. A final reference-ID/hash check prevents interpreting damaged raw
reference bytes as a proven new binding. Store/lot capture races are rechecked.

The one narrow added owner permission is `qualitycontrol/store.py::_freeze_sd`:
new manual references freeze `profile_version_id` before reference-ID hashing.
Existing by-ID references, old profiles/manifests/models/PDFs and the schema are
untouched; no migration, time-field feature, new controller or dependency was
introduced. The same manual SD1 can now be consciously redeclared under unit B
with a distinct reference bound to B. Archived supported v1 evidence retains
its exact JSON/hash/PDF and is never enriched with a default context or recalc.

Executed focused slices: **89 passed in 6.48s**, **8 passed in 12.48s**,
**41 passed in 5.08s**, and a final hash-guard slice **8 passed / 18 deselected in
3.36s**, all zero skips. These separate runs overlap; no full suite or unchanged
large-report QA was repeated. Exact scopes/basetemps are in the P5 Rework-1
section of TESTBASELINE. The small genuine PDF confirms the mismatch reason
while QMMA remains 6 B; actual archived-v1 PDF/hash/JSON export was also checked.

Separate source/protected evidence is
`.tmp/p5-rework1-freeze-audit-20261112.json`, comparing the exact fresh Rework-1
snapshot and recording cumulative source differences from the original P5
snapshot: 17 existing rework files, none added/removed; cumulative 29 files
(four new/25 changed). Normal-rights audit found zero byte/size/mtime differences
across all 13,258 protected files versus Rework-1 safety, including 8,843 output
and all 2,059 packaging files. The builder/cache's original P5 differences are
preserved in the first audit, not silently reclassified as unchanged against
the original snapshot. Config/storage remain absent on both sides.
The new genuine mismatch PDF is under
`.tmp/pytest-p5-rework1-app-pdf-20261112/test_real_pdf_explains_incompa0/incompatible-sd-report.pdf`.
All initial P5/P4 audits remain unchanged. The .tmp acceptance helper
remains prepared only, unchanged and unexecuted. Status:
**REWORK_1_IMPLEMENTED / FOCUSED_CHECKS_PASSED / INDEPENDENT_RECHECK_PENDING**.
Parent owns the later single full regression inside the canonical builder,
current rules gate, actual build, final visible E2E and authorized Git/release.

### P5 acceptance rework 2: visible date-axis bounds

The parent's prior qualification passed: 1167 tests / two environment skips in
187.08s, builder/ZIP, three visible validations with a real new revision, 64 API
E2E checks and a real packaged PDF closure. Final inspection found one bundled
P2: UI/PDF axis labels used point min/max instead of visible padded/zoomed xlo/xhi.

After the verified fresh Rework-2 snapshot, the six-file correction converts the
actual ordinal-day/timeshare bounds to displayed timestamps, right-aligns the
PDF label using existing glyph metrics and handles unsupported dates. Empty
series keep no fabricated date axis. Models, math, IDs, old reports and rules
remain unchanged. Exactly the Canvas and real-small-PDF checks passed:
**2 passed / 0 skipped in 16.14s**, basetemp
`.tmp/pytest-p5-rework2-axis-20261112`. Zoom/pan/reset, true PDF text positions,
date edges, empty series and original model/hash are covered. No full/build/E2E
or Git action was run by this writer. Source/protected comparison is separate:
`.tmp/p5-rework2-freeze-audit-20261112.json`; Rework-1 evidence remains unchanged.
The fresh normal-rights comparison found zero byte/size/mtime differences across
all 13,262 protected files (output 8,843; packaging 2,063; config/storage absent
on both sides). Exactly the six authorized existing files changed; none were
added/removed. The new small PDF examples remain in the named test root.

Status: **REWORK_2_IMPLEMENTED / FOCUSED_CHECKS_PASSED /
INDEPENDENT_RECHECK_PENDING**. After GO, a fresh snapshot and separately scoped
task implement the optional time field now directly authorized in section 8.
No time-field code is included here. The parent combines the final canonical
full regression/build after both steps; Git stays NO-GO until remaining gates pass.

### Optional extracted time field: implementation checkpoint 2026-11-13

After RW2 independent GO (two passed / zero skips, 9.17s), the parent verified
the fresh full Timefield snapshot above and authorized the exact 13-file scope.
The optional `measurement_time_field`/`measurement_time_format` pair is now
implemented in existing profile normalization, source capture and profile dialog.
Both absent/blank retain the exact old normalized form. Partial/conflicting or
non-H/M/optional-S formats are rejected; date and explicit time are parsed with
roundtrip and combined without fallback. Only the new branch adds raw-time
provenance and explicit ordering. Missing/invalid time is excluded with named
German UI/PDF reasons; equal or unknown times still block invented history.
Existing controller/API/schema/store/model/analysis/SD/builder owners are unchanged.

The focused profile/source/UI/PDF selection ran **33 passed, one PDF text-assertion
failure, 73 deselected in 11.18s**. The assertion ignored valid interleaving of
wrapped table columns; only that assertion was corrected. Its exact one-test
rerun passed **1 / zero skips in 5.66s**. No broad repeat/full/build/Git/E2E was
performed. Exact commands are in TESTBASELINE. New profile versions and stable
control IDs, reverse run IDs/real same-day 2_2s and 4_1s, no-map/equal/invalid-time
barriers, explicit dialog load/save, old SD/profile/PDF preservation and readable
reasons are covered. The parent independently passed the real unchanged-DB
no-map golden with identical DB SHA/mtime and profile/manifest/token; the owner
hashes in the separate audit match that golden. Its E2E fixture was not modified.

Audit: `.tmp/p5-timefield-freeze-audit-20261112.json`, against the exact fresh
Timefield snapshot. Exactly 13 authorized existing files changed, none added or
removed. All 13,262 protected files match bytes/size/mtime (output 8,843;
packaging 2,063; config/storage absent on both sides). Prior P5/RW1/RW2 audits
and safety copies are preserved. New PDF:
`.tmp/pytest-p5-timefield-pdf-20261113/test_optional_time_pdf_names_e0/optional-time-errors.pdf`.
Subsequent independent review returned **GO: 34 passed, 0 skipped, 73 deselected
in 8.85s**; all 13 source hashes and the audit matched. No material findings.
The parent then passed the final canonical full/build below. The targeted
visible time-field/axis/PDF follow-up remains before the authorized Git sequence.

### Final technical qualification, 2026-11-13

The final canonical builder ran **1201 passed, 2 skipped in 140.62s** before
replacing only the three authorized targets. Total inventory 1203, +149 versus
P4. Skips were Windows symlink privilege and local Tk `ttk/altTheme.tcl` loading.
The earlier 1167/2 candidate preceded the axis correction and time-field addition;
the new full run qualifies those actual subsequent changes. No redundant full
run was executed immediately before either canonical build.

Fresh ZIP integrity, independent extraction and automatic EXE smoke passed:
720 files, 35,317,905 bytes. ZIP SHA-256:
`17c1ac2b53bacd7b745ae826236d31d6e4abfe53534b4c32e8370bd28505174b`.
EXE SHA-256: `8a17255505d02217b439117198efce2db9f3152ab470977f0d016257a94267d8`.
Raw qualified product-input fingerprint:
`e520033b3dbd8b6bea4177cebd11bd43c7b63138ac6fcfa7253dcc725694d6f8`.
Rules validation passed with five empty lists; isolated one-shot Watchdog and
Worker exited 0. Post-build data audit matched all **12,524 protected files
outside the three authorized targets**, including all 8,843 output files and
`deploy_smoke`, by content/size/mtime. Current product inputs match build metadata.
Evidence paths and exact command are in TESTBASELINE's current qualification.

The final read-only sample matrix returned **2 green / 0 yellow / 9 red**, exit 1:
seven assays are not present in the two sample PDFs; `(6bd7)` and `(42d4)` now
report empty configured fields under the explicitly approved completeness rule.
Their former optional-field warnings are no longer the current baseline.
This is an outstanding rule/sample compatibility limitation, not a claim of
complete qualification of all eleven rules. No rules or samples were modified;
the exact result is retained in `.tmp/final-release-rule-matrix-20261113.log`.

The earlier packaged synthetic end-to-end workflow passed three visible
validations, true reanalysis/identity correction, 64 backend checks and actual
EXE PDF closure/export/history/restart. Twenty-six screenshots and original
report hashes remain under `.tmp/final-qualification-20261112-2`. Old reports
and original processing proof were unchanged; no Excel file was produced.
This is prior-candidate evidence, not a claim that the final time-field/axis
artifact has completed its targeted visible follow-up. Physical Escape stopped
computer use; renewed permission has been requested while independent code,
build and data-preservation work finished. No further UI input is issued pending
that answer. Git publication, merge, release and human acceptance remain pending.

## 7. Publication sequence and final delivery contract

Order: **P3b -> P4 -> P5 -> final E2E/build/Git/release**. Each package: exact
preflight/snapshot, one writer, focused tests, one material reviewer, at most two
normal reworks, one post-GO full regression/rules check. Failed gates stop advance.
E2E is reserved for the final overall acceptance as requested.

The final canonical builder itself runs full pytest: count that as the final
single full regression rather than running a duplicate immediately beforehand.
Qualify import/archive -> reanalysis -> human choice/validation -> lot/QC -> PDF,
with restart/error paths, SD present/absent and no new workbook creation. Use
isolated synthetic fixtures, a visible packaged Windows/Tk session and retained
screenshots. `ARE_SMOKE_EXIT` alone is only startup/config/rules evidence.

Historical pre-P5 read-only release refresh: public repository
`https://github.com/layzieshin/AnalyzerExtractorV2`, remote master matches HEAD,
no tags/releases/open PRs. Elevated `gh` API access succeeds; actual push/upload
had not yet been exercised. That preflight's old ZIP was stale (2026-09-25), SHA-256
`a8f3ec54f8b2864cbe0835ae1b5bbf94fa0454a41c1fada159b9eb0f3638bb70`.
`pyproject.toml` at that preflight said `0.0.0`; P5 now declares **2.0.0**.
The final tag is intended as `v2.0.0` after the reviewed merge. The builder records
actual base commit, dirty snapshot and raw product fingerprint; the steward must
verify that same local fingerprint and a clean reviewed worktree against the
merged/tagged revision before mapping the build to that release. Never reuse
the old ZIP as current work.

Before the authorized build, resolve/preserve exactly the three allowed output
targets: `packaging/build_work`, `packaging/dist_output/AnalyzerResultExtractorV2`,
`packaging/dist_output/AnalyzerResultExtractorV2.zip`. Preserve `deploy_smoke`.
Inspect public asset contents: builder currently includes inactive/history/trash
rules except drafts. Do not upload runtime data, private source fixtures or
unreviewed local rules. Complete the authorized privacy/integrity review first.

Git steward stages explicit reviewed paths on an authorized review branch,
commits/pushes, reports exact resulting SHA/state and waits for required review
results. Product improvements return to the writer and are requalified. Merge
only at green gates. Tag the exact merged revision and ensure the built source
tree matches it. Upload the freshly qualified **portable ZIP containing EXE,
`_internal` and rules**, plus checksum/manifest, using a draft release; inspect
then publish and verify remote SHA/tag/release/assets. An individual onedir EXE
does not contain all runtime dependencies.

## 8. Explicit approval record

On 2026-11-12, the user explicitly answered all three asynchronous questions
(`request_user_input_async`, call `call_85948207b8414200ad75bc4a0baf15d4`):

1. P3b result revisions, validation binding, corrected identity handling and strict
   configured-field choice rule (section 4): **"Ja, freigeben (Empfohlen)"**.
2. Unified SQLite device/QC authority and controlled migration (section 5):
   **"Ja, freigeben (Empfohlen)"**.
3. Westgard procedure (section 6): **"Klassisch wie vorgeschlagen"**.

This is direct user authorization, not an inferred automatic continuation or
an agent-written answer. The previous confirmation blocker is resolved. Start
each following package only after its predecessor passes; the user retains
approval of any further material plan changes. The existing authorization for
the final commit/push, steward report/improvements, merge and EXE release remains.

Later explicit user reply `call_b8d24b0a81554182aafcd66b39adb6f0`:
**"Ja, optionales Zeitfeld ergänzen"**. This authorizes a separately mapped
optional extracted time field/format with no heuristic fallback. It follows
Rework-2 review GO and a fresh safety snapshot in a separate implementation step;
existing profiles, manifests and PDF evidence remain unchanged. Approval is not
implementation or gate evidence, and Rework 2 contains no time-field code.

On 2026-11-13 the user additionally approved full assay names in human tables;
compact default QC PDF output with raw value/date/time/operator/validator data
and optional printed graph explanations; and a separate graph/value section for
each control (within the same PDF). The existing evidence must remain unchanged.
The implementation/review evidence for that bounded package is recorded above;
authorization alone is not material review, build or release evidence.
