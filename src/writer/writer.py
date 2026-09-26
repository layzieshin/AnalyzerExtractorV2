from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Set

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from src.ruleresolver.api import RuleSet
from src.extractor.api import AssayRecord
from src.runtime.api import release_exclusive, try_acquire_exclusive
from .excel_table import sync_worksheet_table
from .model import WriteResult


class WriterError(RuntimeError):
    pass


class Writer:
    _LOCK_STALE_TTL_S = 900.0
    def write_record(
        self,
        record: AssayRecord,
        ruleset: RuleSet,
        output_dir: str,
        *,
        validated_by: str | None = None,
        validated_at: str | None = None,
    ) -> WriteResult:
        # Excel-Regeln aus dem Ruleset lesen
        excel_rules = ruleset.data.get("excel_rules", {})
        filename_template = excel_rules.get("excel_filename_template", "{assay_name}.xlsx")
        assay_name = ruleset.data.get("assay_name") or ruleset.assay_key

        sheet_template = excel_rules.get("sheetname_template", "{lot_id}")

        excel_name = filename_template.format(
            assay_key=self._sanitize_filename(ruleset.assay_key),
            assay_name=self._sanitize_filename(assay_name),
        )
        sheet_name = sheet_template.format(lot_id=self._sanitize_sheetname(record.lot_id))

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        excel_path = out_dir / excel_name

        lock_path = out_dir / ".excel_writer.lock"
        self._acquire_lock(lock_path)
        try:
            status = self._write_with_dedupe(
                excel_path,
                sheet_name,
                record,
                excel_rules,
                validated_by=validated_by,
                validated_at=validated_at,
            )
        finally:
            self._release_lock(lock_path)

        return WriteResult(excel_path=str(excel_path), sheet_name=sheet_name, status=status)

    def update_validation_metadata(
        self,
        record: AssayRecord,
        ruleset: RuleSet,
        output_dir: str,
        *,
        validated_by: str,
        validated_at: str,
    ) -> WriteResult:
        excel_path, sheet_name, lock_path = self._target(record, ruleset, output_dir)
        self._acquire_lock(lock_path)
        try:
            if not excel_path.is_file():
                raise WriterError("excel_validation_row_missing")
            wb = load_workbook(excel_path)
            if sheet_name not in wb.sheetnames:
                raise WriterError("excel_validation_row_missing")
            ws = wb[sheet_name]
            headers = [c.value for c in ws[1] if c.value is not None]
            for header in ("VALIDIERT_DURCH", "VALIDIERT_AM"):
                if header not in headers:
                    headers.append(header)
                    ws.cell(row=1, column=len(headers)).value = header
            if "dedupe_key" not in headers:
                raise WriterError("excel_validation_row_missing")
            dedupe_col = headers.index("dedupe_key") + 1
            target_row = None
            for row_idx in range(2, ws.max_row + 1):
                if str(ws.cell(row=row_idx, column=dedupe_col).value or "") == record.dedupe_key:
                    target_row = row_idx
                    break
            if target_row is None:
                raise WriterError("excel_validation_row_missing")
            ws.cell(target_row, headers.index("VALIDIERT_DURCH") + 1).value = validated_by
            ws.cell(target_row, headers.index("VALIDIERT_AM") + 1).value = validated_at
            sync_worksheet_table(ws, wb, headers, sheet_name)
            self._save_atomic(wb, excel_path)
        finally:
            self._release_lock(lock_path)
        return WriteResult(excel_path=str(excel_path), sheet_name=sheet_name, status="validation_updated")

    def _target(self, record: AssayRecord, ruleset: RuleSet, output_dir: str) -> tuple[Path, str, Path]:
        excel_rules = ruleset.data.get("excel_rules", {})
        filename_template = excel_rules.get("excel_filename_template", "{assay_name}.xlsx")
        assay_name = ruleset.data.get("assay_name") or ruleset.assay_key
        sheet_template = excel_rules.get("sheetname_template", "{lot_id}")
        excel_name = filename_template.format(
            assay_key=self._sanitize_filename(ruleset.assay_key),
            assay_name=self._sanitize_filename(assay_name),
        )
        sheet_name = sheet_template.format(lot_id=self._sanitize_sheetname(record.lot_id))
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / excel_name, sheet_name, out_dir / ".excel_writer.lock"

    def _write_with_dedupe(
        self,
        excel_path: Path,
        sheet_name: str,
        record: AssayRecord,
        excel_rules: Dict[str, Any],
        *,
        validated_by: str | None = None,
        validated_at: str | None = None,
    ) -> str:
        if excel_path.exists():
            wb = load_workbook(excel_path)
            status_base = "appended"
        else:
            wb = Workbook()
            # Default-Sheet entfernen
            if "Sheet" in wb.sheetnames and len(wb.sheetnames) == 1:
                wb.remove(wb["Sheet"])
            status_base = "created"

        ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.create_sheet(sheet_name)

        headers = self._ensure_headers(
            ws,
            record,
            excel_rules,
            include_validation=validated_by is not None or validated_at is not None,
        )

        # Dedupe prüfen
        existing = self._existing_dedupe_keys(ws, headers)
        if record.dedupe_key in existing:
            if validated_by is not None or validated_at is not None:
                self._set_existing_validation_cells(
                    ws,
                    headers,
                    record.dedupe_key,
                    validated_by or "",
                    validated_at or "",
                )
            sync_worksheet_table(ws, wb, headers, sheet_name)
            self._save_atomic(wb, excel_path)
            return "skipped"

        # Mapping: internal_key -> excel_column_name
        mapping: Dict[str, str] = excel_rules.get("column_mapping", {})
        # Reverse: excel_column_name -> internal_key (fürs Zurückübersetzen beim Schreiben)
        reverse_mapping: Dict[str, str] = {v: k for k, v in mapping.items()}

        row_values: List[Any] = []
        for h in headers:
            if h == "assay_key":
                row_values.append(record.assay_key)
            elif h == "device_id":
                row_values.append(record.device_id)
            elif h == "lot_id":
                row_values.append(record.lot_id)
            elif h == "dedupe_key":
                row_values.append(record.dedupe_key)
            elif h == "dedupe_version":
                row_values.append(record.dedupe_version)
            elif h == "VALIDIERT_DURCH":
                row_values.append(validated_by or "")
            elif h == "VALIDIERT_AM":
                row_values.append(validated_at or "")
            else:
                # Wichtig: Wenn Header gemappt ist (z.B. "Haltbarkeit"), dann den originalen Key nehmen (z.B. "expiry_raw")
                internal_key = reverse_mapping.get(h, h)
                row_values.append(record.data.get(internal_key))

        ws.append(row_values)

        sync_worksheet_table(ws, wb, headers, sheet_name)
        self._save_atomic(wb, excel_path)
        return status_base

    def _set_existing_validation_cells(
        self,
        ws: Worksheet,
        headers: List[str],
        dedupe_key: str,
        validated_by: str,
        validated_at: str,
    ) -> None:
        dedupe_col = headers.index("dedupe_key") + 1
        for row_idx in range(2, ws.max_row + 1):
            if str(ws.cell(row=row_idx, column=dedupe_col).value or "") != dedupe_key:
                continue
            ws.cell(row_idx, headers.index("VALIDIERT_DURCH") + 1).value = validated_by
            ws.cell(row_idx, headers.index("VALIDIERT_AM") + 1).value = validated_at
            return

    def _existing_dedupe_keys(self, ws: Worksheet, headers: List[str]) -> Set[str]:
        if "dedupe_key" not in headers:
            return set()
        dedupe_col = headers.index("dedupe_key") + 1
        keys: Set[str] = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and len(row) >= dedupe_col:
                v = row[dedupe_col - 1]
                if v:
                    keys.add(str(v))
        return keys

    def _ensure_headers(
        self,
        ws: Worksheet,
        record: AssayRecord,
        excel_rules: Dict[str, Any],
        *,
        include_validation: bool = False,
    ) -> List[str]:
        mapping: Dict[str, str] = excel_rules.get("column_mapping", {})
        base_cols = ["assay_key", "device_id", "lot_id", "dedupe_key", "dedupe_version"]

        # Excel-Header-Namen (gemappt), aber Keys bleiben intern im record.data
        data_cols = [mapping.get(k, k) for k in record.data.keys()]
        desired = base_cols + data_cols
        if include_validation:
            desired += ["VALIDIERT_DURCH", "VALIDIERT_AM"]

        # Create header row if empty
        if ws.max_row < 1 or ws.cell(1, 1).value is None:
            for col_idx, header in enumerate(desired, start=1):
                ws.cell(row=1, column=col_idx).value = header
            return desired

        existing = [c.value for c in ws[1] if c.value is not None]
        if not existing:
            for col_idx, header in enumerate(desired, start=1):
                ws.cell(row=1, column=col_idx).value = header
            return desired

        # Append missing columns (keeps existing order)
        existing_set = set(existing)
        for h in desired:
            if h not in existing_set:
                existing.append(h)
                ws.cell(row=1, column=len(existing)).value = h

        return existing

    def _save_atomic(self, wb: Workbook, excel_path: Path) -> None:
        tmp_path = excel_path.with_name(f".{excel_path.stem}.{uuid.uuid4().hex}.tmp.xlsx")
        try:
            wb.save(tmp_path)
            os.replace(tmp_path, excel_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def _sanitize_filename(self, s: str) -> str:
        return "".join(ch for ch in str(s) if ch.isalnum() or ch in (" ", "_", "-", ".")).strip().replace(" ", "_")

    def _sanitize_sheetname(self, s: str) -> str:
        invalid = set(':\\/?"*[]')
        cleaned = "".join(ch for ch in str(s) if ch not in invalid).strip()
        return cleaned[:31] if cleaned else "LOT"

    def _acquire_lock(self, lock_path: Path) -> None:
        if not try_acquire_exclusive(lock_path, self._LOCK_STALE_TTL_S):
            raise WriterError("excel_writer_lock_exists")

    def _release_lock(self, lock_path: Path) -> None:
        release_exclusive(lock_path)
