from __future__ import annotations

from dataclasses import dataclass

from src.extractor.api import AssayRecord
from src.ruleresolver.api import RuleSet
from .writer import Writer, WriteResult



def write_record(record: AssayRecord, ruleset: RuleSet, output_dir: str) -> WriteResult:
    """Public API (Writer)

    Contract:
    - One Excel file per assay.
    - One sheet per lot.
    - One row per run.
    - Dedupe by record.dedupe_key (test|date|time).
    - Global excel writer lock file in output dir.
    """
    return Writer().write_record(record, ruleset, output_dir)
