# AREV2 Dedupe Policy

## Current Contract

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

Excel writes the technical basis columns:

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

In `output_mode=both`, SQLite is now the ledger and runs before Excel. Excel is
written only when SQLite returns `inserted`. If SQLite returns
`duplicate_pending`, Excel is not written and the job result reports an Excel
status of `skipped_duplicate_pending`.

Known ledger-first recovery case: if SQLite returns `inserted` but the following
Excel write fails, the run is already present in the SQLite ledger. A later
rerun can therefore be reported as `duplicate_pending` and will not
automatically backfill Excel. Until AP-12B.2, inspect the run/candidate manually;
the review list will provide the explicit recovery decision.

In `output_mode=excel`, behavior stays Excel-only. No SQLite duplicate queue is
created in that mode.

AP-12B.1 only records candidates. GUI review and decisions (`added`, `deleted`,
`overwritten`) are reserved for AP-12B.2.

## Explicit Legacy Dedupe

Rulesets with non-empty `extract_rules.dedupe_fields` remain supported. They are marked
as `explicit_legacy` and use the existing configured-field key behavior. New rulesets
should rely on the V2 default once the header contract fields are confirmed.

## Follow-Up

AP-12B should add a duplicate review queue. AP-12A only keeps the previous skip behavior
for duplicates in Excel/SQLite and makes the dedupe basis visible.
