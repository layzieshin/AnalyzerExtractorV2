from __future__ import annotations

import re
from typing import Any, Dict

from src.ruleresolver.api import RuleSet
from .model import AssayRecord


class ExtractionError(RuntimeError):
    pass


class Extractor:
    def extract_record(self, assay_text: str, ruleset: RuleSet) -> AssayRecord:
        rs = ruleset.data
        lot_id = self._extract_lot_id(assay_text, rs["lot_rule"])
        data = self._extract_fields(assay_text, rs["extract_rules"])

        test = self._require_str(data.get("test"), "test")
        date = self._require_str(data.get("date"), "date")
        time = self._require_str(data.get("time"), "time")

        dedupe_key = f"{test}|{date}|{time}"
        return AssayRecord(assay_key=ruleset.assay_key, lot_id=lot_id, dedupe_key=dedupe_key, data=data)

    def _extract_lot_id(self, text: str, lot_rule: Dict[str, Any]) -> str:
        regex = lot_rule.get("regex")
        if not regex:
            raise ExtractionError("lot_rule.regex missing")
        m = re.search(regex, text)
        if not m:
            raise ExtractionError("lot_id not found")
        return (m.group(1) if m.groups() else m.group(0)).strip()

    def _extract_fields(self, text: str, extract_rules: Dict[str, Any]) -> Dict[str, Any]:
        fields = extract_rules.get("fields", [])
        if not isinstance(fields, list) or not fields:
            raise ExtractionError("extract_rules.fields missing/empty")
        out: Dict[str, Any] = {}
        for f in fields:
            key = f.get("key")
            regex = f.get("regex")
            req = bool(f.get("required", False))
            if not key or not regex:
                raise ExtractionError("field requires key+regex")
            m = re.search(regex, text)
            if not m:
                if req:
                    raise ExtractionError(f"required field not found: {key}")
                out[key] = None
                continue
            out[key] = (m.group(1) if m.groups() else m.group(0)).strip()
        return out

    def _require_str(self, v: Any, key: str) -> str:
        if v is None:
            raise ExtractionError(f"required field missing: {key}")
        s = str(v).strip()
        if not s:
            raise ExtractionError(f"required field empty: {key}")
        return s
