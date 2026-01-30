from __future__ import annotations

from src.ruleresolver.api import RuleSet
#from .model import AssayRecord
from .extractor import Extractor, AssayRecord

def extract_record(assay_text: str, ruleset: RuleSet) -> AssayRecord:
    """Public API (Extractor)

    Contract:
    - Extract one assay-specific record from assay_text using ruleset.
    - Must produce lot_id and dedupe_key.
    - Dedupe-key policy: test|YYYY-MM-DD|HH:MM:SS
    """
    return Extractor().extract_record(assay_text, ruleset)
