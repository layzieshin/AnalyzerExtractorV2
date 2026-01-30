from __future__ import annotations

import json
from typing import Dict, List, Tuple

from .model import AssayMatch



class AssayChooserError(RuntimeError):
    pass


class AssayChooser:
    def detect_assays(self, norm_text: str, rules_index_path: str) -> List[AssayMatch]:
        try:
            index = json.loads(Path(rules_index_path).read_text(encoding="utf-8"))
        except Exception as e:
            raise AssayChooserError(f"Cannot read index.json: {e}") from e

        assays = index.get("assays", [])
        keys: List[str] = [a.get("assay_key") for a in assays if a.get("assay_key")]
        if not keys:
            raise AssayChooserError("index.json contains no assay_key entries")

        hits: List[Tuple[int, str]] = []
        for key in keys:
            pos = norm_text.find(key)
            if pos != -1:
                hits.append((pos, key))

        # keep first occurrence per key
        first: Dict[str, int] = {}
        for pos, key in sorted(hits, key=lambda x: x[0]):
            if key not in first:
                first[key] = pos

        ordered = sorted(first.items(), key=lambda x: x[1])
        return [AssayMatch(assay_key=k, occurrence_index=1) for k, _ in ordered]


from pathlib import Path
