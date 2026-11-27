# AREV2 Dedupe Policy

## Current Contract

Package 3a (2026-11-12): every new processing path writes SQLite only. Legacy
`both`/`excel` inputs normalize to `sqlite`. Duplicate candidates retain their
SQLite ledger IDs and produce no Excel sink, including no skipped Excel output.
Existing workbooks and frozen historical plans remain unchanged; historical
exports cannot be resumed. `excel_rules` and historical readers remain compatible.

`src.extractor.api.extract_record()` builds a structured dedupe identity.

Default Dedupe V2:

```text
v2 | device_id | PLATTE | DATUM | ZEIT | TEST
```

`device_id` is runtime context, not a regex field. The default device is `DEFAULT_DEVICE`
unless `config/devices.json` or the GUI selection provides another device.

The extracted `AssayRecord` contains:

- `dedupe_key`
- `dedupe_version`
- `dedupe_basis`
- `device_id`

## Result correction aliases (Package 3b)

Genuine reanalysis can correct identity-bearing fields while keeping the stable
`runs.id`. Original rows and their uniqueness guard remain unchanged.
`run_identity_aliases` adds append-only claims for identities of accepted
revisions. Candidates and rejected revisions claim nothing; earlier accepted
aliases remain authoritative even after another correction.

DbWriter takes `BEGIN IMMEDIATE` before looking up original keys and aliases.
Accepting a revision checks collisions, adds its alias and appends the human
selection in that same transaction. A key owned by another run rejects selection
with an explicit duplicate-clarification message; ownership is never reassigned.
An interrupted selection rolls back its alias as well.

Normal ingestion consults both original keys and accepted aliases under its
write lock. Only the exact original identified job/PDF/block/payload attempt can
return `already_persisted`. Another import matching any accepted identity still
creates ordinary `duplicate_pending` evidence. Reanalysis selection changes a
whole effective result; it does not implement the separate duplicate queue's
reserved Add/Overwrite operations.

## Device Source

Optional local config:

```json
{
  "default_device_id": "analyzer_i_1",
  "devices": [
    {
      "device_id": "analyzer_i_1",
      "display_name": "Analyzer I",
      "active": true
    }
  ]
}
```

If the file is missing or invalid, runtime falls back to `DEFAULT_DEVICE` and exposes
that status through `get_device_config_status()`.

## Storage

Historical workbooks contain the technical basis columns (new processing does not write them):

```text
assay_key, device_id, lot_id, dedupe_key, dedupe_version
```

SQLite stores the same identity plus evidence fields:

- `device_id`
- `dedupe_version`
- `dedupe_basis_json`
- `pdf_sha256`
- `assay_block_hash`

SQLite keeps the uniqueness guard on `(assay_key, dedupe_key)`.

## Duplicate Queue Backend

AP-12B.1 uses SQLite as the duplicate review ledger. When a new SQLite write
hits the existing `(assay_key, dedupe_key)` uniqueness guard, the new payload is
stored in `duplicate_candidates` with status `pending` instead of being silently
discarded.

Important boundary:

- `jobs/{job_id}.json` idempotency is checked before the pipeline reaches
  SQLite. A repeated PDF hash with existing `DONE` state still returns
  `SKIPPED: already_done` and does not create a duplicate candidate.
- Candidates are created only when the pipeline actually reaches SQLite, for
  example with a different PDF file that has the same fachliche dedupe identity
  or after an intentional force rerun / deleted job state.

All accepted new modes use the SQLite ledger. `inserted`/`already_persisted`
retain stable run IDs; `duplicate_pending` retains the candidate and existing-run
IDs. New results/plans list SQLite sinks only and keep compatibility metadata
`excel_status=not_required`, `export_retry_available=false`.

Historical note (AP-12B, retired by Package 3a): the former `both` mode ran SQLite
before Excel, and the former `excel` mode bypassed SQLite. Those historical
outputs and plans remain diagnostic evidence. They are never backfilled,
migrated, resumed, or automatically marked complete. An old Excel failure must
not trigger full re-extraction or create a new duplicate candidate.

## Duplicate Review in the Main App

AP-12B.2 makes the SQLite duplicate queue visible in the Tkinter main app. The
`Duplikate` tab lists candidates from `duplicate_candidates`, opens the live
comparison against the referenced `runs` row, and supports exactly one manual
decision: discard the candidate.

Discarding a candidate changes only the candidate audit state:

- `duplicate_candidates.status` becomes `deleted`.
- `decision_at`, `decision_by`, and `decision_note` are stored on the candidate.
- `duplicate_decision_log` receives an action entry with `discard`.
- The existing `runs` row and Excel output remain unchanged.

Overwrite and add-entry behavior remain follow-up work requiring separate write
semantics and audit rules. Excel recovery is retired; historical files stay unchanged.

AP-12B.1 only records candidates. AP-12B.2 adds the first GUI review action:
`deleted`. `added` and `overwritten` are reserved for later packages.

## Explicit Legacy Dedupe

Rulesets with non-empty `extract_rules.dedupe_fields` remain supported. They are marked
as `explicit_legacy` and use the existing configured-field key behavior. New rulesets
should rely on the V2 default once the header contract fields are confirmed.

## Follow-Up

AP-12B.1 and AP-12B.2 are done:

- SQLite duplicate candidates are recorded when the uniqueness guard triggers.
- The Test-App **Duplikate** tab lists candidates and supports manual discard.

Still open (future packages):

- **Add** — accept candidate as additional entry with audit trail
- **Overwrite** — replace an existing SQLite run with explicit semantics and audit trail

Excel recovery is not an available or planned action under the Package-3a contract.

AP-12A established the visible dedupe basis and legacy skip behavior for duplicates
in Excel/SQLite.
