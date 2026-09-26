# SQLite to QMTool PostgreSQL Mapping

**Status:** Phase-4 migration contract; no PostgreSQL implementation in this repository.

## Scope

AnalyzerResultExtractorV2 keeps SQLite as the V2.1 structured source of truth. A later QMTool
integration migrates that structured SQLite truth in a controlled one-time migration. Excel is an
optional downstream export and is not migration input. The concrete PostgreSQL owner and schema
design remain outside V2.1. This note does not define QMTool tables, APIs, or an implementation.

| Analyzer SQLite source | Future QMTool concept | Required preserved identity |
|------------------------|-----------------------|-----------------------------|
| `runs` | Analyzer run/result entity | Analyzer database identity + stable `run_id` mapping |
| `run_validations` | Validation/audit entity | `validation_id`, mapped `run_id`, supersession chain |
| `duplicate_candidates` | clarification/dedupe case | candidate identity + referenced existing run |

The concrete PostgreSQL table names are deliberately not fixed here; they belong to the future
QMTool owner and its canonical schema.

## Runs

- Preserve the original Analyzer `run_id` in an explicit migration map or source-reference field.
- Preserve `job_id`, PDF/source references, assay/ruleset identity, lot/charge, device, timestamps,
  hashes/dedupe basis and the extracted payload without reinterpretation during transport.
- Do not derive canonical data from Excel when the SQLite row exists.
- Re-running a migration must be idempotent for the same source database and source `run_id`.

## Run validations

- Migrate every append-only row, not only the latest effective validation.
- Resolve `run_id` through the run migration map.
- Preserve `validation_id`, `operator_initials`, `validated_at_utc`, `comment`,
  `created_at_utc` and `supersedes_validation_id`.
- Rebuild the supersession relation only after all validation rows have stable target identities.
- `operator_initials` is a local operator label, not a verified QMTool user identity. Any later
  actor mapping needs an explicit, auditable migration decision; never infer a user silently.
- UTC timestamps retain their instant and timezone meaning.

## Duplicate candidates

- Preserve candidate state, detection/decision timestamps, comparison payload and links to the
  existing run through the run migration map.
- A migrated clarification case must not create or mutate a measurement run implicitly.

## Migration order and checks

1. Freeze a read-only SQLite source snapshot and record its hash plus schema inventory.
2. Import runs and persist the source-to-target run map.
3. Import all validation rows and then resolve their supersession links.
4. Import duplicate/clarification candidates and their run references.
5. Reconcile source/target counts, per-table hashes or deterministic digests, orphan references,
   latest-validation resolution and duplicate status counts.
6. Produce an immutable migration report. Do not delete or rewrite the SQLite source.

## Out of scope

- No live PostgreSQL connection, schema migration or QMTool write path is introduced by Phase 4.
- No user/role model is added to the desktop application.
- No bidirectional sync is defined.
- No Excel-to-PostgreSQL import path is defined. Excel is not a migration source.
- No PostgreSQL owner, schema, or table design is fixed in V2.1.
