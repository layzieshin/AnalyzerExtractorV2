from __future__ import annotations

from typing import List

from .model import AssayMatch
from .assaychooser import AssayChooser


def detect_assays(norm_text: str, rules_index_path: str) -> List[AssayMatch]:
    """Public API (AssayChooser)

    Contract:
    - Read assay_key list from rules/index.json.
    - Search in normalized text.
    - Match: contains, case-sensitive.
    - Multi-assay: return all found keys, deduped by key, sorted by first occurrence position.
    """
    return AssayChooser().detect_assays(norm_text, rules_index_path)
