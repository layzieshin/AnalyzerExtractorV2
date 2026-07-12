from __future__ import annotations

from src.ruleresolver.api import RuleSet
from .extractor import ExtractionError, Extractor, AssayRecord

__all__ = ["AssayRecord", "ExtractionError", "extract_record"]

def extract_record(assay_text: str, ruleset: RuleSet, device_id: str = "DEFAULT_DEVICE") -> AssayRecord:
    """Public API (Extractor)

    Contract:
    - Extract one assay-specific record from assay_text using ruleset.
    - Must produce lot_id and dedupe_key.
    - Default Dedupe V2: device_id|PLATTE|DATUM|ZEIT|TEST.
    """
    return Extractor().extract_record(assay_text, ruleset, device_id=device_id)
