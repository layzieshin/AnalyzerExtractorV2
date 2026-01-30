from dataclasses import dataclass

@dataclass(frozen=True)
class AssayMatch:
    assay_key: str
    occurrence_index: int
