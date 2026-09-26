from __future__ import annotations

from dataclasses import dataclass

from src.extractor.api import AssayRecord
from src.ruleresolver.api import RuleSet
from .writer import Writer, WriteResult



def write_record(
    record: AssayRecord,
    ruleset: RuleSet,
    output_dir: str,
    *,
    validated_by: str | None = None,
    validated_at: str | None = None,
) -> WriteResult:
    """Public API (Writer)

    Contract:
    - One Excel file per assay.
    - One sheet per lot.
    - One row per run.
    - Dedupe by record.dedupe_key.
    - Global excel writer lock file in output dir.
    """
    return Writer().write_record(
        record,
        ruleset,
        output_dir,
        validated_by=validated_by,
        validated_at=validated_at,
    )


def update_validation_metadata(
    record: AssayRecord,
    ruleset: RuleSet,
    output_dir: str,
    *,
    validated_by: str,
    validated_at: str,
) -> WriteResult:
    """Update only the validation cells of an already exported dedupe row."""
    return Writer().update_validation_metadata(
        record,
        ruleset,
        output_dir,
        validated_by=validated_by,
        validated_at=validated_at,
    )
