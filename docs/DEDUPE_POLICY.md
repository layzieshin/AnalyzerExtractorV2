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

## Explicit Legacy Dedupe

Rulesets with non-empty `extract_rules.dedupe_fields` remain supported. They are marked
as `explicit_legacy` and use the existing configured-field key behavior. New rulesets
should rely on the V2 default once the header contract fields are confirmed.

## Follow-Up

AP-12B should add a duplicate review queue. AP-12A only keeps the previous skip behavior
for duplicates in Excel/SQLite and makes the dedupe basis visible.
