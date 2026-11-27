from dataclasses import dataclass
from typing import Dict, Any

@dataclass(frozen=True)
class AssayDescriptor:
    assay_key: str   # e.g. "(5f03)"
    assay_name: str  # e.g. "Anti-TPO IgG"


@dataclass(frozen=True)
class AssaySection:
    """One unambiguous document header and its exact normalized-text occurrence."""

    assay_key: str
    assay_name: str
    raw_assay_key: str
    start: int
    end: int
    text: str
