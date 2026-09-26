from __future__ import annotations

from pathlib import PureWindowsPath
import re
from typing import Any, Dict

from src.ruleresolver.api import RuleSet
from .model import AssayRecord


class ExtractionError(RuntimeError):
    pass


class Extractor:
    def extract_record(self, assay_text: str, ruleset: RuleSet, device_id: str = "DEFAULT_DEVICE") -> AssayRecord:
        rs = ruleset.data
        lot_id = self._extract_lot_id(assay_text, rs["lot_rule"])
        data = self._extract_fields(assay_text, rs["extract_rules"])
        dedupe_key, dedupe_version, dedupe_basis = self._build_dedupe(ruleset, rs, data, device_id, lot_id)
        return AssayRecord(
            assay_key=ruleset.assay_key,
            lot_id=lot_id,
            dedupe_key=dedupe_key,
            data=data,
            device_id=device_id,
            dedupe_version=dedupe_version,
            dedupe_basis=dedupe_basis,
        )

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
        lines = text.splitlines()
        empty_keys: list[str] = []

        for f in fields:
            key = f.get("key")
            regex = f.get("regex")
            # required bleibt im Ruleset erhalten, steuert die Laufzeit-Leere aber nicht mehr.

            if not key or not regex:
                raise ExtractionError("field requires key+regex")

            search_text = text  # default: kompletter Block

            # 🔹 optionaler Such-Start
            search_from = f.get("search_from")
            if isinstance(search_from, dict):
                if "after" in search_from:
                    marker = search_from["after"]
                    try:
                        for i, ln in enumerate(lines):
                            if re.search(marker, ln):
                                search_text = "\n".join(lines[i + 1:])
                                break
                    except re.error as e:
                        raise ExtractionError(f"search_from.after invalid regex for field {key}: {e}") from e
                elif "line" in search_from:
                    try:
                        start = int(search_from["line"])
                    except Exception as e:
                        raise ExtractionError(f"search_from.line invalid int for field {key}") from e
                    if start < 0:
                        raise ExtractionError(f"search_from.line must be >= 0 for field {key}")
                    search_text = "\n".join(lines[start:])

            m = re.search(regex, search_text)
            if not m:
                empty_keys.append(str(key))
                out[key] = None
                continue

            captured = m.group(1) if m.groups() else m.group(0)
            value = captured.strip() if captured is not None else None
            if value is None or value == "":
                empty_keys.append(str(key))
            out[key] = value

        if empty_keys:
            raise ExtractionError(f"configured_fields_empty: {','.join(empty_keys)}")

        return out

    def _build_dedupe(
        self,
        ruleset: RuleSet,
        rs: Dict[str, Any],
        data: Dict[str, Any],
        device_id: str,
        lot_id: str,
    ) -> tuple[str, str, dict[str, str]]:
        configured = rs.get("extract_rules", {}).get("dedupe_fields")
        if isinstance(configured, list) and configured:
            keys = [str(k) for k in configured if str(k).strip()]
            if keys:
                return self._build_explicit_legacy_dedupe(ruleset, data, device_id, lot_id, keys)

        return self._build_v2_dedupe(data, device_id)

    def _build_explicit_legacy_dedupe(
        self,
        ruleset: RuleSet,
        data: Dict[str, Any],
        device_id: str,
        lot_id: str,
        dedupe_fields: list[str],
    ) -> tuple[str, str, dict[str, str]]:
        parts = [ruleset.assay_key, lot_id]
        basis: dict[str, str] = {"device_id": device_id, "lot_id": lot_id}
        non_empty = False
        for key in dedupe_fields:
            val = self._normalize_scalar(data.get(key))
            if val:
                non_empty = True
            parts.append(val)
            basis[key] = val
        if not non_empty:
            raise ExtractionError(f"dedupe fields empty: {dedupe_fields}")
        return "|".join(parts), "explicit_legacy", basis

    def _build_v2_dedupe(self, data: Dict[str, Any], device_id: str) -> tuple[str, str, dict[str, str]]:
        basis = {
            "device_id": self._normalize_scalar(device_id) or "DEFAULT_DEVICE",
            "PLATTE": self._normalize_scalar(self._first_present(data, ("PLATTE", "plate_name"))),
            "DATUM": self._normalize_date(self._first_present(data, ("DATUM", "date"))),
            "ZEIT": self._normalize_time(self._first_present(data, ("ZEIT", "time"))),
            "TEST": self._normalize_test(self._first_present(data, ("TEST", "test"))),
        }
        missing = [key for key in ("PLATTE", "DATUM", "ZEIT", "TEST") if not basis[key]]
        if missing:
            raise ExtractionError(f"dedupe basis missing: {','.join(missing)}")
        key = "|".join(["v2", basis["device_id"], basis["PLATTE"], basis["DATUM"], basis["ZEIT"], basis["TEST"]])
        return key, "v2", basis

    @staticmethod
    def _first_present(data: Dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in data:
                return data.get(key)
        return None

    @staticmethod
    def _normalize_scalar(value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    def _normalize_test(self, value: Any) -> str:
        text = self._normalize_scalar(value)
        if not text:
            return ""
        m = re.search(r"([^\\/]+\.asy)\b", text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        try:
            name = PureWindowsPath(text).name
            if name.lower().endswith(".asy"):
                return name
        except Exception:
            pass
        return text

    def _normalize_date(self, value: Any) -> str:
        text = self._normalize_scalar(value)
        m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", text)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return text

    def _normalize_time(self, value: Any) -> str:
        text = self._normalize_scalar(value)
        m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
        if not m:
            return text
        seconds = m.group(3) or "00"
        return f"{int(m.group(1)):02d}:{m.group(2)}:{seconds}"
