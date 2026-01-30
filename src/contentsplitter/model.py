from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True)
class AssayDescriptor:
    assay_key: str   # e.g. "(5f03)"
    assay_name: str  # e.g. "Anti-TPO IgG"