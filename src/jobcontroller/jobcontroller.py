from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from src.runtime.api import release_exclusive, try_acquire_exclusive
from src.runtime.api import resolve_device_id

from .model import JobResult


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

        # Idempotency: if DONE exists, skip
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                if state.get("status") == "DONE":
                    return self._result("SKIPPED", job_id, str(pdf), {"reason": "already_done"})
            except Exception:
                pass

        # Acquire lock
        try:
            effective_lock_ttl = lock_ttl_s if lock_ttl_s is not None else self._lock_ttl_from_env()
            self._acquire_lock(lock_path, effective_lock_ttl)
        except FileExistsError:
            return self._result("SKIPPED", job_id, str(pdf), {"reason": "locked"})

        state: Dict[str, Any] = {
            "job_id": job_id,
            "pdf_path": str(pdf),
            "pdf_sha256": pdf_sha256,
            "device_id": effective_device_id,
            "status": "LOCKED",
            "steps": [],
        }
        self._save_state(state_path, state)

        try:
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

            # EXTRACT + WRITE (reuse already loaded rulesets)
            writes: List[Dict[str, Any]] = []
            for k in assay_keys:
                ruleset = assay_rulesets[k]
                rec = extract_record(blocks[k], ruleset, device_id=effective_device_id)
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

                if mode in ("both", "sqlite"):
                    sqlite_target = sqlite_path or str(output_dir / "results.sqlite3")
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
                        if db_wr.existing_run_id is not None:
                            sqlite_output["existing_run_id"] = db_wr.existing_run_id
                        if db_wr.duplicate_candidate_id is not None:
                            sqlite_output["duplicate_candidate_id"] = db_wr.duplicate_candidate_id
                        write_item["outputs"].append(sqlite_output)
                        if db_wr.status == "duplicate_pending":
                            write_item["duplicate_status"] = "pending"
                            write_item["duplicate_candidate_id"] = db_wr.duplicate_candidate_id
                            write_item["existing_run_id"] = db_wr.existing_run_id
                    except Exception as e:
                        write_item["outputs"].append(
                            {
                                "sink": "sqlite",
                                "status": "failed",
                                "error": str(e),
                            }
                        )
                        raise RuntimeError(f"sqlite_write_failed:{k}:{e}") from e

                if mode == "both" and write_item["duplicate_status"] == "pending":
                    write_item["outputs"].append(
                        {
                            "sink": "excel",
                            "status": "skipped_duplicate_pending",
                        }
                    )
                elif mode in ("both", "excel"):
                    try:
                        wr = write_record(rec, ruleset, str(output_dir))
                        write_item["outputs"].append(
                            {
                                "sink": "excel",
                                "excel_path": wr.excel_path,
                                "sheet": wr.sheet_name,
                                "status": wr.status,
                            }
                        )
                    except Exception as e:
                        write_item["outputs"].append(
                            {
                                "sink": "excel",
                                "status": "failed",
                                "error": str(e),
                            }
                        )
                        raise RuntimeError(f"excel_write_failed:{k}:{e}") from e

                writes.append(write_item)

            state["status"] = "DONE"
            state["steps"].append({"step": "writer", "writes": writes})
            self._save_state(state_path, state)
            return self._result("DONE", job_id, str(pdf), {"assay_keys": assay_keys, "writes": writes})

        except Exception as e:
            state["status"] = "FAILED"
            state["error"] = str(e)
            state["partial_writes"] = writes if "writes" in locals() else []
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

    def _save_state(self, path: Path, state: Dict[str, Any]) -> None:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")

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

    def _result(self, status: str, job_id: str, pdf_path: str, details: Dict[str, object]):
        from .api import JobResult
        return JobResult(job_id=job_id, pdf_path=pdf_path, status=status, details=details)
