from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from src.runtime.api import release_exclusive, try_acquire_exclusive
from src.runtime.api import resolve_device_id

from .model import JobResult

_CONTEXT_MAX_CHARS = 32_000
_OUTPUT_PLAN_VERSION = 2
_EXCEL_DONE = frozenset({"success", "skipped_duplicate_pending", "not_required"})
_EXCEL_RETRY = frozenset({"failed", "pending"})


class JobController:
    def submit(
        self,
        pdf_path: str,
        project_root: str,
        output_mode: str = "both",
        sqlite_path: str | None = None,
        lock_ttl_s: float | None = None,
        sqlite_busy_timeout_ms: int = 5000,
        sqlite_retry_count: int = 3,
        sqlite_retry_sleep_s: float = 0.2,
        device_id: str | None = None,
    ):
        root = Path(project_root)
        pdf = Path(pdf_path)
        try:
            mode = self._normalize_output_mode(output_mode)
        except Exception as e:
            return self._result("FAILED", "", str(pdf), {"error": str(e)})

        if not pdf.exists():
            return self._result("FAILED", "", str(pdf), {"error": "pdf_not_found"})

        pdf_sha256 = self._sha256_file(pdf)
        job_id = pdf_sha256[:16]
        effective_device_id = resolve_device_id(root, device_id)
        locks_dir = root / "locks"
        jobs_dir = root / "jobs"
        rules_dir = root / "rules"
        output_dir = root / "output" / "final"
        locks_dir.mkdir(exist_ok=True)
        jobs_dir.mkdir(exist_ok=True)

        lock_path = locks_dir / f"{job_id}.lock"
        state_path = jobs_dir / f"{job_id}.json"

        # Idempotency: if DONE exists, skip. A versioned export plan is not consulted here.
        if state_path.exists():
            try:
                existing_done = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(existing_done, dict) and existing_done.get("status") == "DONE":
                    return self._result("SKIPPED", job_id, str(pdf), {"reason": "already_done"})
            except Exception:
                pass

        # Acquire lock
        try:
            effective_lock_ttl = lock_ttl_s if lock_ttl_s is not None else self._lock_ttl_from_env()
            self._acquire_lock(lock_path, effective_lock_ttl)
        except FileExistsError:
            return self._result("SKIPPED", job_id, str(pdf), {"reason": "locked"})

        try:
            export_state = self._load_state(state_path)
            if isinstance(export_state, dict) and export_state.get("export_retry_available") is True:
                plan = export_state.get("output_plan")
                # No versioned plan: legacy FAILED stays on the full path.
                if isinstance(plan, dict) and plan.get("version") == _OUTPUT_PLAN_VERSION:
                    return self._retry_excel_export(
                        export_state,
                        state_path,
                        pdf,
                        job_id,
                    )

            state: Dict[str, Any] = {
                "job_id": job_id,
                "pdf_path": str(pdf),
                "pdf_sha256": pdf_sha256,
                "device_id": effective_device_id,
                "status": "LOCKED",
                "steps": [],
            }
            self._save_state(state_path, state)

            # PARSE
            from src.parser.api import parse
            from src.assaychooser.api import detect_assays
            from src.normalizer.api import normalize_lines
            from src.ruleresolver.api import resolve_ruleset
            from src.contentsplitter.api import AssayDescriptor, split_by_assay_name_and_key
            from src.extractor.api import extract_record
            from src.writer.api import write_record
            from src.dbwriter.api import write_record_sqlite

            doc = parse(str(pdf))
            state["status"] = "PARSED"
            state["steps"].append({"step": "parser", "page_count": doc.meta.get("page_count")})
            self._save_state(state_path, state)

            # NORMALIZE
            raw_lines = [ln for p in doc.pages for ln in p.lines]
            norm_lines = normalize_lines(raw_lines)
            norm_text = "\n".join(norm_lines)
            state["status"] = "NORMALIZED"
            state["steps"].append({"step": "normalizer", "lines": len(norm_lines)})
            self._save_state(state_path, state)

            if self._reject_invalid_runs() and "validationskriterien nicht erfüllt" in norm_text.lower():
                state["status"] = "FAILED"
                state["error"] = "validation_failed"
                self._save_state(state_path, state)
                return self._result("FAILED", job_id, str(pdf), {"error": "validation_failed"})

            # DEBUG DUMP: normalized text (full)
            normalized_dump = jobs_dir / f"{job_id}_normalized.txt"
            normalized_dump.write_text(norm_text, encoding="utf-8")
            state["steps"].append({"step": "debug", "normalized_dump": str(normalized_dump)})
            self._save_state(state_path, state)

            # ASSAY DETECT
            index_path = str(rules_dir / "index.json")
            matches = detect_assays(norm_text, index_path)
            assay_keys = [m.assay_key for m in matches]
            state["status"] = "ASSAYS_DETECTED"
            state["steps"].append({"step": "assaychooser", "assay_keys": assay_keys})
            self._save_state(state_path, state)

            if not assay_keys:
                state["status"] = "FAILED"
                state["error"] = "no_assay_detected"
                self._save_state(state_path, state)
                return self._result("FAILED", job_id, str(pdf), {"error": "no_assay_detected"})

            # Resolve rulesets early (required for assay_name-based split)
            assay_rulesets: Dict[str, Any] = {}
            assay_descriptors: List[Any] = []
            for k in assay_keys:
                rs = resolve_ruleset(k, str(rules_dir), index_path)
                assay_rulesets[k] = rs
                assay_name = rs.data.get("assay_name")
                if not assay_name:
                    raise RuntimeError(f"ruleset missing assay_name for {k}")
                assay_descriptors.append(AssayDescriptor(assay_key=k, assay_name=assay_name))

            # SPLIT (NEW): start at FIRST assay_name; valid only if assay_key appears after it
            blocks = split_by_assay_name_and_key(norm_text, assay_descriptors)

            state["status"] = "SPLIT"
            state["steps"].append({
                "step": "contentsplitter",
                "mode": "assay_name_and_key",
                "assays": [{"assay_key": a.assay_key, "assay_name": a.assay_name} for a in assay_descriptors],
                "blocks": {k: len(v.splitlines()) for k, v in blocks.items()},
            })
            self._save_state(state_path, state)

            # DEBUG DUMP: per-assay blocks (exact input to Extractor)
            block_dumps = {}
            block_hashes: Dict[str, str] = {}
            for k, block in blocks.items():
                safe_k = k.replace("(", "").replace(")", "")
                p = jobs_dir / f"{job_id}_{safe_k}_block.txt"
                p.write_text(block, encoding="utf-8")
                block_dumps[k] = str(p)
                block_hashes[k] = self._hash_text(block)

            state["steps"].append({"step": "debug_blocks", "block_dumps": block_dumps})
            self._save_state(state_path, state)

            # EXTRACT all assays before any sink write.
            extracted: List[Dict[str, Any]] = []
            for k in assay_keys:
                ruleset = assay_rulesets[k]
                rec = extract_record(blocks[k], ruleset, device_id=effective_device_id)
                extracted.append({"assay_key": k, "ruleset": ruleset, "record": rec})

            writes: List[Dict[str, Any]] = []
            plan_assays: List[Dict[str, Any]] = []
            for item in extracted:
                k = item["assay_key"]
                ruleset = item["ruleset"]
                rec = item["record"]
                write_item: Dict[str, Any] = {
                    "assay_key": k,
                    "assay_name": str(ruleset.data.get("assay_name", "")).strip(),
                    "ruleset_file": ruleset.ruleset_file,
                    "lot_id": rec.lot_id,
                    "dedupe_key": rec.dedupe_key,
                    "device_id": rec.device_id,
                    "dedupe_version": rec.dedupe_version,
                    "dedupe_basis": rec.dedupe_basis,
                    "pdf_sha256": pdf_sha256,
                    "assay_block_hash": block_hashes.get(k, ""),
                    "data": rec.data,
                    "missing_required": self._missing_required_fields(ruleset, rec.data),
                    "duplicate_status": "none",
                    "duplicate_candidate_id": None,
                    "existing_run_id": None,
                    "outputs": [],
                }
                excel_status = "not_required"
                if mode == "both":
                    excel_status = "pending"
                elif mode == "excel":
                    excel_status = "pending"
                writes.append(write_item)
                plan_assays.append(
                    self._plan_assay(rec, ruleset, write_item, excel_status)
                )

            sqlite_target = sqlite_path or str(output_dir / "results.sqlite3")
            output_plan: Dict[str, Any] | None = None
            if mode in {"both", "excel"}:
                if mode == "excel":
                    for entry in plan_assays:
                        entry["structured_status"] = "not_required"
                        entry["sqlite_status"] = "not_required"
                output_plan = {
                    "version": _OUTPUT_PLAN_VERSION,
                    "output_mode": mode,
                    "excel_output_dir": str(output_dir),
                    "sqlite_path": sqlite_target if mode == "both" else "",
                    "sqlite_status": "pending" if mode == "both" else "not_required",
                    "assays": plan_assays,
                }
                state["output_plan"] = output_plan
                state["sqlite_status"] = "pending" if mode == "both" else "not_required"
                state["structured_status"] = state["sqlite_status"]
                state["excel_status"] = "pending"
                state["export_retry_available"] = False
                state["status"] = "OUTPUT_PLANNED"
                self._save_state(state_path, state)

            if mode in ("both", "sqlite"):
                for index, item in enumerate(extracted):
                    k = item["assay_key"]
                    ruleset = item["ruleset"]
                    rec = item["record"]
                    write_item = writes[index]
                    plan_entry = plan_assays[index]
                    if output_plan is not None:
                        plan_entry["structured_status"] = "pending"
                        plan_entry["sqlite_status"] = "pending"
                        self._save_state(state_path, state)
                    try:
                        db_wr = write_record_sqlite(
                            rec,
                            ruleset,
                            sqlite_target,
                            job_id=job_id,
                            pdf_path=str(pdf),
                            pdf_sha256=pdf_sha256,
                            assay_block_hash=block_hashes.get(k, ""),
                            busy_timeout_ms=sqlite_busy_timeout_ms,
                            retry_count=sqlite_retry_count,
                            retry_sleep_s=sqlite_retry_sleep_s,
                        )
                        sqlite_output: Dict[str, Any] = {
                            "sink": "sqlite",
                            "sqlite_path": db_wr.sqlite_path,
                            "table": db_wr.table_name,
                            "status": db_wr.status,
                        }
                        if db_wr.run_id is not None:
                            sqlite_output["run_id"] = db_wr.run_id
                            write_item["sqlite_run_id"] = db_wr.run_id
                            plan_entry["sqlite_run_id"] = db_wr.run_id
                        if db_wr.existing_run_id is not None:
                            sqlite_output["existing_run_id"] = db_wr.existing_run_id
                        if db_wr.duplicate_candidate_id is not None:
                            sqlite_output["duplicate_candidate_id"] = db_wr.duplicate_candidate_id
                        write_item["outputs"].append(sqlite_output)
                        plan_entry["structured_status"] = "success"
                        plan_entry["sqlite_status"] = "success"
                        if db_wr.status == "duplicate_pending":
                            write_item["duplicate_status"] = "pending"
                            write_item["duplicate_candidate_id"] = db_wr.duplicate_candidate_id
                            write_item["existing_run_id"] = db_wr.existing_run_id
                            plan_entry["structured_status"] = "duplicate_pending"
                            plan_entry["sqlite_status"] = "duplicate_pending"
                            plan_entry["excel_status"] = "skipped_duplicate_pending"
                            write_item["outputs"].append({"sink": "excel", "status": "skipped_duplicate_pending"})
                        elif mode == "both":
                            plan_entry["excel_status"] = "awaiting_validation"
                        if output_plan is not None:
                            self._save_state(state_path, state)
                    except Exception as e:
                        write_item["outputs"].append({"sink": "sqlite", "status": "failed", "error": str(e)})
                        plan_entry["structured_status"] = "failed"
                        plan_entry["sqlite_status"] = "failed"
                        state["sqlite_status"] = "failed"
                        state["structured_status"] = "failed"
                        state["export_retry_available"] = False
                        if output_plan is not None:
                            self._save_state(state_path, state)
                        raise RuntimeError(f"sqlite_write_failed:{k}:{e}") from e

            phase_status = self._structured_sqlite_status(mode)
            state["sqlite_status"] = phase_status
            state["structured_status"] = phase_status
            if mode == "sqlite":
                state["excel_status"] = "not_required"
                state["export_retry_available"] = False
                state["status"] = "DONE"
                state["steps"].append({"step": "writer", "writes": writes})
                self._save_state(state_path, state)
                return self._result("DONE", job_id, str(pdf), {"assay_keys": assay_keys, "writes": writes})

            assert output_plan is not None
            output_plan["sqlite_status"] = phase_status
            state["output_plan"] = output_plan
            if mode == "both":
                state["excel_status"] = "awaiting_validation"
                state["export_retry_available"] = False
                state["status"] = "DONE"
                state["steps"].append({"step": "writer", "writes": writes})
                self._save_state(state_path, state)
                return self._result("DONE", job_id, str(pdf), {"assay_keys": assay_keys, "writes": writes})

            state["excel_status"] = "pending"
            state["export_retry_available"] = True
            state["status"] = "EXPORT_PLANNED"
            self._save_state(state_path, state)

            excel_error = self._write_pending_excel(
                output_plan,
                write_record,
                state=state,
                state_path=state_path,
                writes=writes,
            )
            self._sync_plan_statuses(state, output_plan, writes)
            if excel_error is not None:
                raise RuntimeError(excel_error)

            state["status"] = "DONE"
            state["excel_status"] = "success"
            state["export_retry_available"] = False
            state["steps"].append({"step": "writer", "writes": writes})
            self._save_state(state_path, state)
            return self._result("DONE", job_id, str(pdf), {"assay_keys": assay_keys, "writes": writes})

        except Exception as e:
            if "state" not in locals():
                return self._result("FAILED", job_id, str(pdf), {"error": str(e)})
            state["status"] = "FAILED"
            state["error"] = str(e)
            state["partial_writes"] = writes if "writes" in locals() else []
            if str(e).startswith("excel_write_failed") and self._frozen_excel_retry_allowed(state):
                state["excel_status"] = "failed"
                state["export_retry_available"] = True
            elif not self._frozen_excel_retry_allowed(state):
                state["export_retry_available"] = False
            self._save_state(state_path, state)
            details: Dict[str, Any] = {"error": str(e)}
            if "writes" in locals() and writes:
                details["partial_writes"] = writes
            return self._result("FAILED", job_id, str(pdf), details)
        finally:
            self._release_lock(lock_path)

    def _sha256_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _hash_file(self, path: Path) -> str:
        return self._sha256_file(path)[:16]

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _acquire_lock(self, lock_path: Path, stale_ttl_s: float) -> None:
        if not try_acquire_exclusive(lock_path, stale_ttl_s):
            raise FileExistsError(str(lock_path))

    def _release_lock(self, lock_path: Path) -> None:
        release_exclusive(lock_path)

    def _load_state(self, path: Path) -> Dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _save_state(self, path: Path, state: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _plan_assay(self, rec: Any, ruleset: Any, write_item: Dict[str, Any], excel_status: str) -> Dict[str, Any]:
        excel_rules = ruleset.data.get("excel_rules", {})
        if not isinstance(excel_rules, dict):
            excel_rules = {}
        return {
            "assay_record": {
                "assay_key": rec.assay_key,
                "lot_id": rec.lot_id,
                "dedupe_key": rec.dedupe_key,
                "data": rec.data,
                "device_id": rec.device_id,
                "dedupe_version": rec.dedupe_version,
                "dedupe_basis": rec.dedupe_basis,
            },
            "ruleset": {
                "assay_key": ruleset.assay_key,
                "ruleset_file": ruleset.ruleset_file,
                "assay_name": str(ruleset.data.get("assay_name", "")).strip(),
                "excel_rules": excel_rules,
            },
            "write_item": write_item,
            "sqlite_run_id": write_item.get("sqlite_run_id"),
            "structured_status": "pending",
            "sqlite_status": "pending",
            "excel_status": excel_status,
        }

    def _write_pending_excel(
        self,
        output_plan: Dict[str, Any],
        write_record: Any,
        *,
        state: Dict[str, Any],
        state_path: Path,
        writes: List[Dict[str, Any]],
    ) -> str | None:
        output_dir = str(output_plan.get("excel_output_dir") or "")
        sqlite_status = str(state.get("sqlite_status") or output_plan.get("sqlite_status") or "")
        first_error: str | None = None
        assays = output_plan.get("assays")
        if not isinstance(assays, list):
            return "excel_write_failed::invalid_output_plan"
        for entry in assays:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("excel_status") or "")
            if status in _EXCEL_DONE:
                continue
            if status not in _EXCEL_RETRY:
                entry["excel_status"] = "failed"
                first_error = first_error or f"excel_write_failed:{entry.get('assay_record', {}).get('assay_key', '')}:unexpected_excel_status"
                self._persist_excel_progress(state, state_path, output_plan, writes)
                continue
            assay_key = ""
            try:
                record_payload = entry.get("assay_record")
                ruleset_payload = entry.get("ruleset")
                if not isinstance(record_payload, dict) or not isinstance(ruleset_payload, dict):
                    raise RuntimeError("invalid_export_snapshot")
                assay_key = str(record_payload.get("assay_key") or "")
                from src.extractor.api import AssayRecord
                from src.ruleresolver.api import RuleSet

                record = AssayRecord(
                    assay_key=assay_key,
                    lot_id=str(record_payload.get("lot_id") or ""),
                    dedupe_key=str(record_payload.get("dedupe_key") or ""),
                    data=dict(record_payload.get("data") or {}),
                    device_id=str(record_payload.get("device_id") or ""),
                    dedupe_version=str(record_payload.get("dedupe_version") or "v2"),
                    dedupe_basis=dict(record_payload.get("dedupe_basis") or {}),
                )
                ruleset = RuleSet(
                    assay_key=str(ruleset_payload.get("assay_key") or assay_key),
                    ruleset_file=str(ruleset_payload.get("ruleset_file") or ""),
                    data={
                        "assay_key": str(ruleset_payload.get("assay_key") or assay_key),
                        "assay_name": ruleset_payload.get("assay_name") or assay_key,
                        "excel_rules": ruleset_payload.get("excel_rules") or {},
                    },
                )
                validation = entry.get("validation")
                if isinstance(validation, dict):
                    wr = write_record(
                        record,
                        ruleset,
                        output_dir,
                        validated_by=str(validation.get("operator_initials") or ""),
                        validated_at=str(validation.get("validated_at_utc") or ""),
                    )
                else:
                    wr = write_record(record, ruleset, output_dir)
                entry["excel_status"] = "success"
                write_item = entry.get("write_item")
                if isinstance(write_item, dict):
                    outputs = write_item.setdefault("outputs", [])
                    if isinstance(outputs, list):
                        outputs.append(
                            {
                                "sink": "excel",
                                "excel_path": wr.excel_path,
                                "sheet": wr.sheet_name,
                                "status": wr.status,
                            }
                        )
            except Exception as exc:
                entry["excel_status"] = "failed"
                write_item = entry.get("write_item")
                if isinstance(write_item, dict):
                    outputs = write_item.setdefault("outputs", [])
                    if isinstance(outputs, list):
                        outputs.append({"sink": "excel", "status": "failed", "error": str(exc)})
                prefix = "excel_write_failed_after_save" if sqlite_status == "success" else "excel_write_failed"
                message = f"{prefix}:{assay_key}:{exc}"
                first_error = first_error or message
            self._persist_excel_progress(state, state_path, output_plan, writes)
        return first_error

    def _persist_excel_progress(
        self,
        state: Dict[str, Any],
        state_path: Path,
        output_plan: Dict[str, Any],
        writes: List[Dict[str, Any]],
    ) -> None:
        self._sync_plan_statuses(state, output_plan, writes)
        state["partial_writes"] = list(writes)
        terminal_success = (
            state.get("excel_status") == "success" and self._plan_sqlite_matches(state, output_plan)
        )
        if state.get("excel_status") in {"failed", "pending"} and self._plan_sqlite_matches(state, output_plan):
            state["export_retry_available"] = True
        elif terminal_success:
            state["status"] = "DONE"
            state["export_retry_available"] = False
            state["error"] = ""
        elif state.get("excel_status") == "success":
            state["export_retry_available"] = False
        self._save_state(state_path, state)

    def _sync_plan_statuses(self, state: Dict[str, Any], output_plan: Dict[str, Any], writes: List[Dict[str, Any]]) -> None:
        assays = output_plan.get("assays")
        if isinstance(assays, list):
            refreshed: List[Dict[str, Any]] = []
            for entry in assays:
                if isinstance(entry, dict) and isinstance(entry.get("write_item"), dict):
                    refreshed.append(entry["write_item"])
            if refreshed:
                writes[:] = refreshed
        statuses = [
            str(entry.get("excel_status") or "")
            for entry in assays
            if isinstance(entry, dict)
        ] if isinstance(assays, list) else []
        if any(status == "failed" for status in statuses):
            state["excel_status"] = "failed"
        elif any(status == "awaiting_validation" for status in statuses):
            state["excel_status"] = "awaiting_validation"
        elif statuses and all(status in _EXCEL_DONE for status in statuses):
            state["excel_status"] = "success"
        else:
            state["excel_status"] = "pending"
        state["output_plan"] = output_plan

    def _structured_sqlite_status(self, mode: str) -> str:
        if mode in {"both", "sqlite"}:
            return "success"
        return "not_required"

    def _plan_sqlite_matches(self, state: Dict[str, Any], plan: Any) -> bool:
        if not isinstance(plan, dict) or plan.get("version") != _OUTPUT_PLAN_VERSION:
            return False
        mode = str(plan.get("output_mode") or "")
        sqlite_status = str(state.get("sqlite_status") or "")
        frozen_sqlite = str(plan.get("sqlite_status") or "")
        if frozen_sqlite and frozen_sqlite != sqlite_status:
            return False
        structured = str(state.get("structured_status") or "")
        if mode == "both":
            return sqlite_status == "success" and structured == "success"
        if mode == "excel":
            return sqlite_status == "not_required" and structured == "not_required"
        return False

    def _frozen_excel_retry_allowed(self, state: Dict[str, Any]) -> bool:
        if state.get("excel_status") not in {"failed", "pending"}:
            return False
        return self._plan_sqlite_matches(state, state.get("output_plan"))

    def _retry_excel_export(self, state: Dict[str, Any], state_path: Path, pdf: Path, job_id: str):
        plan = state.get("output_plan")
        if not self._frozen_excel_retry_allowed(state):
            state["status"] = "FAILED"
            state["error"] = state.get("error") or "export_plan_not_retryable"
            state["export_retry_available"] = False
            self._save_state(state_path, state)
            return self._result("FAILED", job_id, str(pdf), {"error": state["error"]})

        from src.writer.api import write_record

        writes: List[Dict[str, Any]] = []
        assays = plan.get("assays") if isinstance(plan, dict) else None
        if isinstance(assays, list):
            writes = [
                entry["write_item"]
                for entry in assays
                if isinstance(entry, dict) and isinstance(entry.get("write_item"), dict)
            ]
        excel_error = self._write_pending_excel(
            plan,
            write_record,
            state=state,
            state_path=state_path,
            writes=writes,
        )
        self._sync_plan_statuses(state, plan, writes)
        if excel_error is not None:
            state["status"] = "FAILED"
            state["error"] = excel_error
            state["excel_status"] = "failed"
            state["export_retry_available"] = True
            state["partial_writes"] = writes
            self._save_state(state_path, state)
            return self._result("FAILED", job_id, str(pdf), {"error": excel_error, "partial_writes": writes})

        state["status"] = "DONE"
        state["excel_status"] = "success"
        state["export_retry_available"] = False
        state["error"] = ""
        state["partial_writes"] = writes
        steps = state.get("steps")
        if not isinstance(steps, list):
            steps = []
            state["steps"] = steps
        steps.append({"step": "excel_export_retry", "writes": writes})
        self._save_state(state_path, state)
        assay_keys = [
            str(item.get("assay_key") or "")
            for item in writes
            if isinstance(item, dict)
        ]
        return self._result("DONE", job_id, str(pdf), {"assay_keys": assay_keys, "writes": writes})

    def release_validated_run(
        self,
        project_root: str | Path,
        job_id: str,
        run_id: int,
        *,
        operator_initials: str,
        validated_at_utc: str,
        validation_id: int,
        correction: bool = False,
    ):
        root = Path(project_root)
        safe_job_id = _sanitize_job_id(job_id)
        if safe_job_id is None:
            return self._result("DONE", str(job_id), "", {"reason": "excel_not_planned"})
        lock_path = root / "locks" / f"{safe_job_id}.excel-export.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if not try_acquire_exclusive(lock_path, self._lock_ttl_from_env()):
            return self._result("FAILED", safe_job_id, "", {"error": "excel_export_locked"})
        try:
            return self._release_validated_run_unlocked(
                root,
                safe_job_id,
                run_id,
                operator_initials=operator_initials,
                validated_at_utc=validated_at_utc,
                validation_id=validation_id,
                correction=correction,
            )
        finally:
            release_exclusive(lock_path)

    def _release_validated_run_unlocked(
        self,
        project_root: str | Path,
        job_id: str,
        run_id: int,
        *,
        operator_initials: str,
        validated_at_utc: str,
        validation_id: int,
        correction: bool = False,
    ):
        """Release one frozen SQLite run to Excel after append-only validation."""
        root = Path(project_root)
        safe_job_id = _sanitize_job_id(job_id)
        if safe_job_id is None:
            return self._result("FAILED", str(job_id), "", {"error": "invalid_job_id"})
        state_path = root / "jobs" / f"{safe_job_id}.json"
        state = self._load_state(state_path)
        if not isinstance(state, dict):
            return self._result("DONE", safe_job_id, "", {"reason": "excel_not_planned"})
        plan = state.get("output_plan")
        if not isinstance(plan, dict) or plan.get("version") != _OUTPUT_PLAN_VERSION:
            return self._result("DONE", safe_job_id, str(state.get("pdf_path") or ""), {"reason": "excel_not_planned"})
        if str(plan.get("output_mode") or "") != "both":
            return self._result("DONE", safe_job_id, str(state.get("pdf_path") or ""), {"reason": "excel_not_planned"})
        assays = plan.get("assays")
        target = next(
            (
                entry
                for entry in assays
                if isinstance(entry, dict) and int(entry.get("sqlite_run_id") or 0) == int(run_id)
            ),
            None,
        ) if isinstance(assays, list) else None
        if target is None:
            return self._result("FAILED", safe_job_id, str(state.get("pdf_path") or ""), {"error": "validated_run_not_in_output_plan"})
        if str(target.get("excel_status") or "") == "skipped_duplicate_pending":
            return self._result("DONE", safe_job_id, str(state.get("pdf_path") or ""), {"reason": "duplicate_pending"})

        validation: Dict[str, Any] = {
            "validation_id": int(validation_id),
            "operator_initials": str(operator_initials),
            "validated_at_utc": str(validated_at_utc),
        }
        effective = self._effective_validation_for_entry(plan, target)
        if effective is not None and int(effective["validation_id"]) >= int(validation["validation_id"]):
            validation = effective
        stored_validation = target.get("validation")
        stored_id = (
            int(stored_validation.get("validation_id") or 0)
            if isinstance(stored_validation, dict)
            else 0
        )
        incoming_id = int(validation.get("validation_id") or 0)
        if stored_id > incoming_id:
            return self._result(
                "DONE",
                safe_job_id,
                str(state.get("pdf_path") or ""),
                {"reason": "stale_validation_ignored", "validation_id": stored_id},
            )
        if stored_id == incoming_id and stored_id > 0 and str(target.get("excel_status") or "") == "success":
            return self._result(
                "DONE",
                safe_job_id,
                str(state.get("pdf_path") or ""),
                {"reason": "validation_already_exported", "validation_id": stored_id},
            )
        if stored_id == incoming_id and isinstance(stored_validation, dict):
            validation = dict(stored_validation)
        prior_excel_status = str(target.get("excel_status") or "")
        target["validation"] = validation
        target["excel_action"] = (
            "metadata_update" if correction and prior_excel_status == "success" else "initial_release"
        )
        target["excel_status"] = "failed"
        target["excel_error"] = "excel_write_failed_after_validation:export_interrupted"
        state["status"] = "DONE"
        state["excel_status"] = "failed"
        state["error"] = target["excel_error"]
        state["export_retry_available"] = True
        state["output_plan"] = plan
        self._save_state(state_path, state)

        error = self._write_validated_entry(
            target,
            plan,
            correction=target["excel_action"] == "metadata_update",
        )
        writes = self._plan_writes(plan)
        if error:
            target["excel_status"] = "failed"
            target["excel_error"] = error
            state["error"] = error
            state["export_retry_available"] = True
        else:
            target["excel_status"] = "success"
            target.pop("excel_error", None)
            state["error"] = ""
        self._sync_plan_statuses(state, plan, writes)
        state["status"] = "DONE"
        failed_entries = [
            entry
            for entry in (assays or [])
            if isinstance(entry, dict)
            and entry.get("excel_status") == "failed"
            and isinstance(entry.get("validation"), dict)
        ]
        state["export_retry_available"] = bool(failed_entries)
        if failed_entries:
            state["error"] = str(failed_entries[0].get("excel_error") or error or "excel_write_failed_after_validation")
        else:
            state["error"] = ""
        state["partial_writes"] = writes
        self._save_state(state_path, state)
        if error:
            return self._result("FAILED", safe_job_id, str(state.get("pdf_path") or ""), {"error": error})
        return self._result("DONE", safe_job_id, str(state.get("pdf_path") or ""), {"run_id": int(run_id)})

    def retry_excel_export_by_job_id(self, project_root: str | Path, job_id: str):
        root = Path(project_root)
        safe_job_id = _sanitize_job_id(job_id)
        if safe_job_id is None:
            return self._result("FAILED", str(job_id), "", {"error": "invalid_job_id"})
        lock_path = root / "locks" / f"{safe_job_id}.excel-export.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if not try_acquire_exclusive(lock_path, self._lock_ttl_from_env()):
            return self._result("FAILED", safe_job_id, "", {"error": "excel_export_locked"})
        try:
            return self._retry_excel_export_by_job_id_unlocked(root, safe_job_id)
        finally:
            release_exclusive(lock_path)

    def _retry_excel_export_by_job_id_unlocked(self, project_root: str | Path, job_id: str):
        """Retry only failed, already validated frozen entries without the source PDF."""
        root = Path(project_root)
        safe_job_id = _sanitize_job_id(job_id)
        if safe_job_id is None:
            return self._result("FAILED", str(job_id), "", {"error": "invalid_job_id"})
        state_path = root / "jobs" / f"{safe_job_id}.json"
        state = self._load_state(state_path)
        plan = state.get("output_plan") if isinstance(state, dict) else None
        if not isinstance(state, dict) or not isinstance(plan, dict) or plan.get("version") != _OUTPUT_PLAN_VERSION:
            return self._result("FAILED", safe_job_id, "", {"error": "export_plan_not_retryable"})
        self._merge_effective_validations(plan)
        state["output_plan"] = plan
        self._save_state(state_path, state)
        assays = plan.get("assays")
        targets = [
            entry for entry in (assays or [])
            if isinstance(entry, dict)
            and entry.get("excel_status") == "failed"
            and isinstance(entry.get("validation"), dict)
        ]
        if not targets:
            return self._result("FAILED", safe_job_id, str(state.get("pdf_path") or ""), {"error": "export_plan_not_retryable"})
        first_error = None
        for entry in targets:
            correction = str(entry.get("excel_action") or "") == "metadata_update"
            error = self._write_validated_entry(entry, plan, correction=correction)
            if error:
                entry["excel_status"] = "failed"
                entry["excel_error"] = error
                first_error = first_error or error
            else:
                entry["excel_status"] = "success"
                entry.pop("excel_error", None)
        writes = self._plan_writes(plan)
        self._sync_plan_statuses(state, plan, writes)
        state["status"] = "DONE"
        state["partial_writes"] = writes
        state["export_retry_available"] = first_error is not None
        state["error"] = first_error or ""
        steps = state.setdefault("steps", [])
        if isinstance(steps, list):
            steps.append({"step": "excel_export_retry", "retry_kind": "export_only", "run_ids": [entry.get("sqlite_run_id") for entry in targets]})
        self._save_state(state_path, state)
        if first_error:
            return self._result("FAILED", safe_job_id, str(state.get("pdf_path") or ""), {"error": first_error})
        return self._result("DONE", safe_job_id, str(state.get("pdf_path") or ""), {"retry_kind": "export_only"})

    def _merge_effective_validations(self, plan: Dict[str, Any]) -> int:
        assays = plan.get("assays")
        if not isinstance(assays, list):
            return 0
        merged = 0
        for entry in assays:
            if not isinstance(entry, dict):
                continue
            effective = self._effective_validation_for_entry(plan, entry)
            if effective is None:
                continue
            stored = entry.get("validation")
            stored_id = int(stored.get("validation_id") or 0) if isinstance(stored, dict) else 0
            effective_id = int(effective.get("validation_id") or 0)
            if effective_id <= stored_id:
                continue
            previous_status = str(entry.get("excel_status") or "")
            previous_action = str(entry.get("excel_action") or "")
            entry["validation"] = effective
            entry["excel_action"] = (
                "metadata_update"
                if previous_status == "success" or previous_action == "metadata_update"
                else "initial_release"
            )
            entry["excel_status"] = "failed"
            entry["excel_error"] = "excel_export_reconcile_required"
            merged += 1
        return merged

    @staticmethod
    def _effective_validation_for_entry(plan: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any] | None:
        sqlite_path = str(plan.get("sqlite_path") or "")
        run_id = int(entry.get("sqlite_run_id") or 0)
        if not sqlite_path or run_id <= 0:
            return None
        try:
            from src.resultvalidation.api import get_run_validation

            record = get_run_validation({"driver": "sqlite", "path": sqlite_path}, run_id)
        except Exception:
            return None
        if record is None:
            return None
        return {
            "validation_id": int(record.validation_id),
            "operator_initials": str(record.operator_initials),
            "validated_at_utc": str(record.validated_at_utc),
        }

    def _has_effective_validation_waiting(self, state: Dict[str, Any]) -> bool:
        plan = state.get("output_plan")
        if not isinstance(plan, dict) or plan.get("version") != _OUTPUT_PLAN_VERSION:
            return False
        assays = plan.get("assays")
        if not isinstance(assays, list):
            return False
        return any(
            isinstance(entry, dict)
            and str(entry.get("excel_status") or "") in {"awaiting_validation", "failed"}
            and self._effective_validation_for_entry(plan, entry) is not None
            for entry in assays
        )

    @staticmethod
    def _plan_writes(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        assays = plan.get("assays")
        return [
            entry["write_item"] for entry in (assays or [])
            if isinstance(entry, dict) and isinstance(entry.get("write_item"), dict)
        ]

    def _write_validated_entry(self, entry: Dict[str, Any], plan: Dict[str, Any], *, correction: bool) -> str | None:
        assay_key = ""
        try:
            record, ruleset = self._restore_frozen_entry(entry)
            assay_key = record.assay_key
            validation = entry.get("validation")
            if not isinstance(validation, dict):
                raise RuntimeError("validation_snapshot_missing")
            kwargs = {
                "validated_by": str(validation.get("operator_initials") or ""),
                "validated_at": str(validation.get("validated_at_utc") or ""),
            }
            output_dir = str(plan.get("excel_output_dir") or "")
            if correction:
                from src.writer.api import update_validation_metadata
                wr = update_validation_metadata(record, ruleset, output_dir, **kwargs)
            else:
                from src.writer.api import write_record
                wr = write_record(record, ruleset, output_dir, **kwargs)
            write_item = entry.get("write_item")
            if isinstance(write_item, dict):
                outputs = write_item.setdefault("outputs", [])
                if isinstance(outputs, list):
                    outputs.append({"sink": "excel", "excel_path": wr.excel_path, "sheet": wr.sheet_name, "status": wr.status})
            return None
        except Exception as exc:
            return f"excel_write_failed_after_validation:{assay_key}:{exc}"

    @staticmethod
    def _restore_frozen_entry(entry: Dict[str, Any]):
        from src.extractor.api import AssayRecord
        from src.ruleresolver.api import RuleSet
        record_payload = entry.get("assay_record")
        ruleset_payload = entry.get("ruleset")
        if not isinstance(record_payload, dict) or not isinstance(ruleset_payload, dict):
            raise RuntimeError("invalid_export_snapshot")
        assay_key = str(record_payload.get("assay_key") or "")
        return (
            AssayRecord(
                assay_key=assay_key,
                lot_id=str(record_payload.get("lot_id") or ""),
                dedupe_key=str(record_payload.get("dedupe_key") or ""),
                data=dict(record_payload.get("data") or {}),
                device_id=str(record_payload.get("device_id") or ""),
                dedupe_version=str(record_payload.get("dedupe_version") or "v2"),
                dedupe_basis=dict(record_payload.get("dedupe_basis") or {}),
            ),
            RuleSet(
                assay_key=str(ruleset_payload.get("assay_key") or assay_key),
                ruleset_file=str(ruleset_payload.get("ruleset_file") or ""),
                data={
                    "assay_key": str(ruleset_payload.get("assay_key") or assay_key),
                    "assay_name": ruleset_payload.get("assay_name") or assay_key,
                    "excel_rules": ruleset_payload.get("excel_rules") or {},
                },
            ),
        )

    def _normalize_output_mode(self, output_mode: str) -> str:
        mode = str(output_mode).strip().lower()
        if mode not in {"both", "excel", "sqlite"}:
            raise ValueError(f"invalid output_mode: {output_mode}")
        return mode

    def _lock_ttl_from_env(self) -> float:
        raw = os.getenv("ARE_PIPELINE_LOCK_TTL_S", "").strip()
        try:
            return float(raw) if raw else 900.0
        except ValueError:
            return 900.0

    def _reject_invalid_runs(self) -> bool:
        raw = os.getenv("ARE_REJECT_INVALID_RUNS", "1").strip().lower()
        return raw not in {"0", "false", "no"}

    @staticmethod
    def _missing_required_fields(ruleset: Any, data: Dict[str, Any]) -> List[str]:
        fields = ruleset.data.get("extract_rules", {}).get("fields", [])
        if not isinstance(fields, list):
            return []
        missing: List[str] = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            key = str(field.get("key", "")).strip()
            if not key or not bool(field.get("required", False)):
                continue
            val = data.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                missing.append(key)
        return missing

    def read_job_evidence(self, project_root: str | Path, job_id: str):
        from .api import JobEvidence

        safe_job_id = _sanitize_job_id(job_id)
        if safe_job_id is None:
            return None
        root = Path(project_root).resolve()
        jobs_dir = (root / "jobs").resolve(strict=False)
        state_path = jobs_dir / f"{safe_job_id}.json"
        if not _path_is_contained(state_path.resolve(strict=False), jobs_dir):
            return None
        if not state_path.is_file():
            return JobEvidence(
                job_id=safe_job_id,
                pdf_path="",
                status="",
                error="",
                steps=(),
                normalized_dump_path="",
                block_dump_paths=(),
                state_path=str(state_path),
                state_available=False,
            )
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return JobEvidence(
                job_id=safe_job_id,
                pdf_path="",
                status="",
                error="",
                steps=(),
                normalized_dump_path="",
                block_dump_paths=(),
                state_path=str(state_path),
                state_available=False,
            )
        if not isinstance(state, dict):
            return None
        normalized_dump = ""
        block_dumps: list[tuple[str, str]] = []
        steps_raw = state.get("steps")
        if isinstance(steps_raw, list):
            steps = tuple(step for step in steps_raw if isinstance(step, dict))
            for step in steps:
                dump = step.get("normalized_dump")
                if dump:
                    safe_dump = _safe_jobs_artifact_path(root, jobs_dir, str(dump))
                    if safe_dump is not None:
                        normalized_dump = str(safe_dump)
                dumps = step.get("block_dumps")
                if isinstance(dumps, dict):
                    for key, value in dumps.items():
                        if not value:
                            continue
                        safe_block = _safe_jobs_artifact_path(root, jobs_dir, str(value))
                        if safe_block is not None:
                            block_dumps.append((str(key), str(safe_block)))
        else:
            steps = ()
        block_dumps.sort(key=lambda item: item[0].casefold())
        context_text, context_truncated, context_available, context_source_label, context_source_kind = (
            _read_diagnostic_context(
                normalized_dump,
                block_dumps,
            )
        )
        reconcile_required = self._has_effective_validation_waiting(state)
        retry_kind = (
            "export_only"
            if (
                state.get("export_retry_available") is True
                and str(state.get("excel_status") or "") == "failed"
            )
            or reconcile_required
            else ""
        )
        evidence_error = str(state.get("error") or "")
        if reconcile_required and not evidence_error:
            evidence_error = "excel_export_reconcile_required"
        return JobEvidence(
            job_id=str(state.get("job_id") or safe_job_id),
            pdf_path=str(state.get("pdf_path") or ""),
            status=str(state.get("status") or ""),
            error=evidence_error,
            steps=steps,
            normalized_dump_path=normalized_dump,
            block_dump_paths=tuple(block_dumps),
            state_path=str(state_path),
            state_available=True,
            context_text=context_text,
            context_truncated=context_truncated,
            context_available=context_available,
            context_source_label=context_source_label,
            context_source_kind=context_source_kind,
            retry_kind=retry_kind,
        )

    def read_job_diagnostic_sources(self, project_root: str | Path, job_id: str):
        from .api import JobDiagnosticSources

        evidence = self.read_job_evidence(project_root, job_id)
        if evidence is None or not evidence.state_available:
            return None
        normalized_text = ""
        if evidence.normalized_dump_path:
            normalized_text = _read_full_text(Path(evidence.normalized_dump_path))
        block_texts: list[tuple[str, str]] = []
        for assay_key, dump_path in evidence.block_dump_paths:
            block_texts.append((assay_key, _read_full_text(Path(dump_path))))
        return JobDiagnosticSources(
            job_id=evidence.job_id,
            normalized_text=normalized_text,
            block_texts=tuple(block_texts),
        )

    def _result(self, status: str, job_id: str, pdf_path: str, details: Dict[str, object]):
        from .api import JobResult
        return JobResult(job_id=job_id, pdf_path=pdf_path, status=status, details=details)


def _sanitize_job_id(job_id: str) -> str | None:
    text = str(job_id or "").strip()
    if not text:
        return None
    if any(separator in text for separator in ("/", "\\")):
        return None
    if text in {".", ".."}:
        return None
    parts = Path(text).parts
    if any(part == ".." for part in parts):
        return None
    if Path(text).is_absolute():
        return None
    if Path(text).drive:
        return None
    return text


def _path_is_contained(candidate: Path, root: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def _safe_jobs_artifact_path(project_root: Path, jobs_dir: Path, raw_path: str) -> Path | None:
    text = str(raw_path or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = (project_root / candidate).resolve(strict=False)
    else:
        candidate = candidate.resolve(strict=False)
    if not _path_is_contained(candidate, jobs_dir):
        return None
    return candidate


def _read_bounded_text(path: Path, *, max_chars: int = _CONTEXT_MAX_CHARS) -> tuple[str, bool]:
    if not path.is_file():
        return "", False
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(max_chars + 1)
    except OSError:
        return "", False
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return text, truncated


def _read_full_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_diagnostic_context(
    normalized_dump: str,
    block_dumps: list[tuple[str, str]],
) -> tuple[str, bool, bool, str, str]:
    if normalized_dump:
        text, truncated = _read_bounded_text(Path(normalized_dump))
        if text:
            return text, truncated, True, "Normalisierter Text", "normalized"
    for assay_key, dump_path in sorted(block_dumps, key=lambda item: item[0].casefold()):
        text, truncated = _read_bounded_text(Path(dump_path))
        if text:
            return text, truncated, True, f"Assay-Block {assay_key}", f"block:{assay_key}"
    if normalized_dump:
        return "", False, False, "Normalisierter Text (fehlend)", "normalized"
    if block_dumps:
        first_key = sorted(block_dumps, key=lambda item: item[0].casefold())[0][0]
        return "", False, False, f"Assay-Block {first_key} (fehlend)", f"block:{first_key}"
    return "", False, False, "-", ""
