from __future__ import annotations

import json
from typing import Dict, List, Tuple

from src.assaycandidate.api import canonical_assay_key
from src.contentsplitter.api import AssaySection

from .model import AssayMatch



class AssayChooserError(RuntimeError):
    pass


class AssayChooser:
    def detect_assays(self, norm_text: str, rules_index_path: str, *, sections: List[AssaySection] | None = None,
                      index_bytes: bytes | None = None) -> List[AssayMatch]:
        try:
            index = json.loads(index_bytes.decode("utf-8") if index_bytes is not None else Path(rules_index_path).read_text(encoding="utf-8"))
        except Exception as e:
            raise AssayChooserError(f"Cannot read index.json: {e}") from e

        assays = index.get("assays", [])
        keys: List[str] = [a.get("assay_key") for a in assays if a.get("assay_key")]
        if not keys:
            raise AssayChooserError("index.json contains no assay_key entries")

        if sections is not None:
            configured: Dict[str, str] = {}
            for key in keys:
                canonical = canonical_assay_key(key)
                if canonical in configured:
                    raise AssayChooserError("assay_key_ambiguous_in_index")
                configured[canonical] = key
            return [AssayMatch(assay_key=configured[section.assay_key], occurrence_index=1)
                    for section in sections if section.assay_key in configured]

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
