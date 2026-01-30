from dataclasses import dataclass
from typing import Dict, List

@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    lines: List[str]

@dataclass(frozen=True)
class ParsedDocument:
    source_path: str
    pages: List[ParsedPage]
    meta: Dict[str, object]
