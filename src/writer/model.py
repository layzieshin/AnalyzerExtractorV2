from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass(frozen=True)
class WriteResult:
    excel_path: str
    sheet_name: str
    status: str  # created|appended|skipped

