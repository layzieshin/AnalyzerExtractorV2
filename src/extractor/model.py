from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class AssayRecord:
    assay_key: str
    lot_id: str
    dedupe_key: str
    data: dict[str, Any]
