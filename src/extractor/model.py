from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class AssayRecord:
    assay_key: str
    lot_id: str
    dedupe_key: str
    data: dict[str, Any]
    device_id: str = "DEFAULT_DEVICE"
    dedupe_version: str = "v2"
    dedupe_basis: dict[str, str] = field(default_factory=dict)
