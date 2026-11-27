from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from src.runtime.api import try_acquire_scoped_exclusive
from src.runtime.api import resolve_device_id

from .model import JobResult

_CONTEXT_MAX_CHARS = 32_000
_OUTPUT_PLAN_VERSION = 2


class JobController:
    def submit(
        self,
        pdf_path: str,
        project_root: str,
        output_mode: str = "sqlite",
        sqlite_path: str | None = None,
        lock_ttl_s: float | None = None,
        sqlite_busy_timeout_ms: int = 5000,
        sqlite_retry_count: int = 3,
        sqlite_retry_sleep_s: float = 0.2,
        device_id: str | None = None,
        *,
        expected_sha256: str | None = None,
        source_pdf_path: str | None = None,
    ):
        options = {"output_mode": output_mode, "sqlite_path": sqlite_path, "lock_ttl_s": lock_ttl_s,
                   "sqlite_busy_timeout_ms": sqlite_busy_timeout_ms, "sqlite_retry_count": sqlite_retry_count,
                   "sqlite_retry_sleep_s": sqlite_retry_sleep_s, "device_id": device_id}
        if expected_sha256 is None:
            if source_pdf_path is not None:
                return self._result("FAILED", "", pdf_path, {"error": "relocated_source_requires_full_sha256"})
            return self._submit_pipeline(pdf_path, project_root, **options)
        if not isinstance(expected_sha256, str):
            return self._result("FAILED", "", pdf_path, {"error": "expected_sha256_invalid"})
        expected = expected_sha256.lower()
        if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            return self._result("FAILED", "", pdf_path, {"error": "expected_sha256_invalid"})
        if source_pdf_path is not None:
            from src.ingestion.api import verified_pdf_location
            try:
                if self._path_key(verified_pdf_location(project_root, pdf_path, expected)) != self._path_key(source_pdf_path):
                    raise ValueError("relocated_source_unproven")
            except (OSError, RuntimeError, ValueError):
                return self._result("FAILED", expected[:16], pdf_path, {"error": "relocated_source_unproven"})
        # Capture before even an already-DONE decision. The live pathname is
        # never the parser source of a SHA-bound attempt, including A→B→A.
        with tempfile.TemporaryDirectory(prefix="arev2-bound-processing-source-") as temporary:
            snapshot = Path(temporary) / "source.pdf"
            try:
                shutil.copyfile(source_pdf_path or pdf_path, snapshot)
            except FileNotFoundError:
                return self._result("FAILED", expected[:16], pdf_path, {"error": "source_changed_since_ingest"})
            except OSError as exc:
                return self._result("FAILED", expected[:16], pdf_path, {"error": f"source_pdf_unreadable: {exc}"})
            if not self._matches_source_sha(snapshot, expected):
                return self._result("FAILED", expected[:16], pdf_path, {"error": "source_changed_since_ingest"})
            return self._submit_pipeline(pdf_path, project_root, **options,
                source_snapshot=snapshot, expected_sha256=expected, source_current_path=source_pdf_path)

    def _submit_pipeline(
        self,
        pdf_path: str,
        project_root: str,
        output_mode: str = "sqlite",
        sqlite_path: str | None = None,
        lock_ttl_s: float | None = None,
        sqlite_busy_timeout_ms: int = 5000,
        sqlite_retry_count: int = 3,
        sqlite_retry_sleep_s: float = 0.2,
        device_id: str | None = None,
        *,
        source_snapshot: Path | None = None,
        expected_sha256: str | None = None,
        source_current_path: str | None = None,
    ):
        root = Path(project_root)
        pdf = Path(pdf_path)
        live_source = Path(source_current_path or pdf_path)
        try:
            mode = self._normalize_output_mode(output_mode)
        except Exception as e:
            return self._result("FAILED", "", str(pdf), {"error": str(e)})

        if source_snapshot is not None and (not self._matches_source_sha(source_snapshot, expected_sha256)
                                            or not self._matches_source_sha(live_source, expected_sha256)):
            return self._result("FAILED", expected_sha256[:16], str(pdf), {"error": "source_changed_since_ingest"})
        if not live_source.exists():
            return self._result("FAILED", "", str(pdf), {"error": "pdf_not_found"})

        pdf_sha256 = expected_sha256 if source_snapshot is not None else self._sha256_file(pdf)
        job_id = pdf_sha256[:16]
        sqlite_target = sqlite_path or str(root / "output" / "final" / "results.sqlite3")
        locks_dir = root / "locks"
        jobs_dir = root / "jobs"
        rules_dir = root / "rules"
        output_dir = root / "output" / "final"
        lock_path = locks_dir / f"{job_id}.lock"
        state_path = jobs_dir / f"{job_id}.json"

        existing = self._load_state(state_path)
        if state_path.exists() and existing is None:
            return self._result("FAILED", job_id, str(pdf), {"error": "job_state_unreadable"})
        from src.rulesuite.api import list_assay_identity_job_bindings
        try:
            binding = list_assay_identity_job_bindings(str(root)).get(job_id)
            stored_binding = (existing or {}).get("identity_binding")
            if binding and binding.get("error"):
                raise ValueError(binding["error"])
            if stored_binding and not binding:
                raise ValueError("identity_case_binding_evidence_missing")
            if binding:
                actual_device = resolve_device_id(root, device_id, store_spec={"driver": "sqlite", "path": sqlite_target})
                if (binding["content_sha256"] != pdf_sha256
                        or self._path_key(pdf) != binding["pdf_path"]
                        or self._path_key(sqlite_target) != binding["store_path"]
                        or actual_device != binding["device_id"]
                        or (stored_binding and any(stored_binding.get(key) != binding[key] for key in
                            ("job_id", "content_sha256", "pdf_path", "store_path", "device_id")))):
                    raise ValueError("identity_case_bound_context_mismatch")
                # The context comparison freezes the actual device/store.
                # Never reread a mutable default between it and the commit.
                device_id, sqlite_target = binding["device_id"], binding["store_path"]
                if source_snapshot is None:
                    return self.submit(pdf_path, project_root, output_mode=output_mode, sqlite_path=sqlite_target,
                        lock_ttl_s=lock_ttl_s, sqlite_busy_timeout_ms=sqlite_busy_timeout_ms,
                        sqlite_retry_count=sqlite_retry_count, sqlite_retry_sleep_s=sqlite_retry_sleep_s,
                        device_id=device_id, expected_sha256=binding["content_sha256"])
        except Exception as exc:
            return self._result("FAILED", job_id, str(pdf), {"error": str(exc)})
        if existing is not None and existing.get("status") == "DONE":
            return self._completed_result(root, existing, pdf, binding)
        if existing is not None and self._is_retired_output_state(existing):
            return self._result("FAILED", job_id, str(pdf), {"error": "historical_output_plan_read_only"})

        try:
            effective_device_id = resolve_device_id(root, device_id, store_spec={"driver": "sqlite", "path": sqlite_target})
        except Exception as exc:
            return self._result("FAILED", job_id, str(pdf), {"error": f"device_configuration_unreadable: {exc}"})

        locks_dir.mkdir(exist_ok=True)
        jobs_dir.mkdir(exist_ok=True)

        # Acquire lock
        try:
            effective_lock_ttl = lock_ttl_s if lock_ttl_s is not None else self._lock_ttl_from_env()
            lease = self._acquire_lock(lock_path, effective_lock_ttl, bound=bool(binding))
        except FileExistsError:
            return self._result("SKIPPED", job_id, str(pdf), {"reason": "locked"})

        try:
            # Recheck under the pipeline lock without migrating frozen evidence.
            if source_snapshot is not None and not self._matches_source_sha(live_source, expected_sha256):
                return self._result("FAILED", job_id, str(pdf), {"error": "source_changed_since_ingest"})
            if binding:
                current_binding = list_assay_identity_job_bindings(str(root)).get(job_id)
                if (not current_binding or current_binding.get("error") or any(current_binding.get(key) != binding[key]
                        for key in ("job_id", "content_sha256", "pdf_path", "store_path", "device_id"))):
                    return self._result("FAILED", job_id, str(pdf), {"error": "identity_case_bound_context_mismatch"})
            existing = self._load_state(state_path)
            if state_path.exists() and existing is None:
                return self._result("FAILED", job_id, str(pdf), {"error": "job_state_unreadable"})
            if existing is not None and existing.get("status") == "DONE":
                return self._completed_result(root, existing, pdf, binding)
            if existing is not None and self._is_retired_output_state(existing):
                return self._result("FAILED", job_id, str(pdf), {"error": "historical_output_plan_read_only"})

            state: Dict[str, Any] = {
                "job_id": job_id,
                "pdf_path": str(pdf),
                "pdf_sha256": pdf_sha256,
                "device_id": effective_device_id,
                "status": "LOCKED",
                "steps": [],
            }
            if binding:
                state["identity_binding"] = binding
            self._save_state(state_path, state)

            # PARSE
            from src.parser.api import parse
            from src.assaychooser.api import detect_assays
            from src.assaycandidate.api import canonical_assay_key, load_known_assay_keys
            from src.normalizer.api import normalize_lines
            from src.ruleresolver.api import resolve_ruleset
            from src.contentsplitter.api import AssayDescriptor, split_assay_sections
            from src.extractor.api import extract_record
            from src.dbwriter.api import write_record_sqlite

            # Parse exactly the bytes identified by this job. The live path may
            # be replaced while a worker is reading it; never attach its earlier
            # SHA to text from a different file.
            if source_snapshot is not None:
                if not self._matches_source_sha(source_snapshot, pdf_sha256):
                    raise RuntimeError("source_pdf_changed_during_processing")
                doc = parse(str(source_snapshot))
            else:
                with tempfile.TemporaryDirectory(prefix="arev2-processing-source-") as temporary:
                    snapshot_path = Path(temporary) / "source.pdf"
                    shutil.copyfile(pdf, snapshot_path)
                    if self._sha256_file(snapshot_path) != pdf_sha256:
                        raise RuntimeError("source_pdf_changed_during_processing")
                    doc = parse(str(snapshot_path))
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
            index_bytes = Path(index_path).read_bytes()
            index_sha256 = hashlib.sha256(index_bytes).hexdigest()
            sections = split_assay_sections(norm_text, known_keys=load_known_assay_keys(index_path, index_bytes=index_bytes) or ())
            matches = detect_assays(norm_text, index_path, sections=sections, index_bytes=index_bytes)
            assay_keys = [m.assay_key for m in matches]
            state["status"] = "ASSAYS_DETECTED"
            state["steps"].append({"step": "assaychooser", "assay_keys": assay_keys, "index_sha256": index_sha256})
            self._save_state(state_path, state)

            # A familiar report title with a different manufacturer ID is not
            # an alias. Persist the unresolved case before any assay is written,
            # including PDFs containing other, already configured assays.
            from src.rulesuite.api import observe_assay_identity_changes

            identity_cases = []
            if len(sections) > len(assay_keys):
                identity_cases = observe_assay_identity_changes(
                    str(root), store_path=sqlite_target, pdf_path=str(pdf), pdf_sha256=pdf_sha256,
                    job_id=job_id, device_id=effective_device_id, normalized_text=norm_text, sections=sections,
                    expected_index_sha256=index_sha256,
                )
            if Path(index_path).read_bytes() != index_bytes:
                raise RuntimeError("rules_index_changed_during_processing")
            if identity_cases:
                case_ids = [case["case_id"] for case in identity_cases]
                error = "assay_identity_change_pending"
                state.update(status="FAILED", error=error, identity_case_ids=case_ids)
                state["identity_binding"] = list_assay_identity_job_bindings(str(root))[job_id]
                state["steps"].append({"step": "assay_identity_changes", "case_ids": case_ids,
                                       "assay_keys": [case["assay_key"] for case in identity_cases],
                                       "store_path": str(Path(sqlite_target).resolve())})
                self._save_state(state_path, state)
                return self._result("FAILED", job_id, str(pdf), {"error": error, "identity_case_ids": case_ids})

            if not assay_keys:
                state["status"] = "FAILED"
                state["error"] = "no_assay_detected"
                self._save_state(state_path, state)
                return self._result("FAILED", job_id, str(pdf), {"error": "no_assay_detected"})

            # Identity and occurrence come from document headers, not the
            # user-editable display name in an active ruleset.
            assay_rulesets: Dict[str, Any] = {}
            assay_descriptors: List[Any] = []
            selected_sections = {}
            for k in assay_keys:
                rs = resolve_ruleset(k, str(rules_dir), index_path)
                assay_rulesets[k] = rs
                if not rs.data.get("assay_name"):
                    raise RuntimeError(f"ruleset missing assay_name for {k}")
                section = next(row for row in sections if row.assay_key == canonical_assay_key(k))
                selected_sections[k] = section
                assay_descriptors.append(AssayDescriptor(assay_key=k, assay_name=section.assay_name))

            blocks = {key: section.text for key, section in selected_sections.items()}

            state["status"] = "SPLIT"
            state["steps"].append({
                "step": "contentsplitter",
                "mode": "anchored_assay_sections",
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
                source_provenance = self._source_provenance(
                    norm_text, assay_descriptors, blocks[k], ruleset, pdf_sha256,
                    block_hashes[k], effective_device_id, selected_sections[k],
                )
                source_provenance["project_root"] = str(root.resolve())
                item["source_provenance"] = source_provenance
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
                    "source_provenance": source_provenance,
                    "missing_required": self._missing_required_fields(ruleset, rec.data),
                    "duplicate_status": "none",
                    "duplicate_candidate_id": None,
                    "existing_run_id": None,
                    "outputs": [],
                }
                writes.append(write_item)
                plan_assays.append(
                    self._plan_assay(rec, ruleset, write_item, "not_required")
                )

            if self._sha256_file(live_source) != pdf_sha256:
                raise RuntimeError("source_pdf_changed_during_processing")
            if Path(index_path).read_bytes() != index_bytes:
                raise RuntimeError("rules_index_changed_during_processing")
            output_plan: Dict[str, Any] = {
                "version": _OUTPUT_PLAN_VERSION,
                "output_mode": mode,
                "sqlite_path": sqlite_target,
                "sqlite_status": "pending",
                "assays": plan_assays,
            }
            state["output_plan"] = output_plan
            state["sqlite_status"] = "pending"
            state["structured_status"] = "pending"
            state["excel_status"] = "not_required"
            state["export_retry_available"] = False
            state["status"] = "OUTPUT_PLANNED"
            self._save_state(state_path, state)

            if mode == "sqlite":
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
                            source_provenance=item["source_provenance"],
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

            phase_status = "success"
            state["sqlite_status"] = phase_status
            state["structured_status"] = phase_status
            output_plan["sqlite_status"] = phase_status
            state["output_plan"] = output_plan
            state["status"] = "DONE"
            state["excel_status"] = "not_required"
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
            state["export_retry_available"] = False
            self._save_state(state_path, state)
            details: Dict[str, Any] = {"error": str(e)}
            if "writes" in locals() and writes:
                details["partial_writes"] = writes
            return self._result("FAILED", job_id, str(pdf), details)
        finally:
            lease.release()

    @staticmethod
    def _path_key(value):
        return os.path.normcase(str(Path(value).resolve()))

    def _completed_result(self, root, state, pdf, binding):
        if binding:
            from .completion import verify_completed_job
            receipt = verify_completed_job(root, state["job_id"], expected_sha256=binding["content_sha256"],
                expected_pdf_path=binding["pdf_path"], store_path=binding["store_path"], device_id=binding["device_id"])
            if not receipt["complete"]:
                return self._result("FAILED", state["job_id"], str(pdf), {"error": receipt["reason"]})
        return self._result("SKIPPED", state["job_id"], str(pdf), {"reason": "already_done"})

    def _sha256_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _matches_source_sha(self, path: Path, expected: str) -> bool:
        try:
            return self._sha256_file(path) == expected
        except OSError:
            return False

    def _source_provenance(self, norm_text, descriptors, block, ruleset, pdf_hash, block_hash, device_id, section):
        start, end = section.start, section.end
        if norm_text[start:end] != block:
            raise RuntimeError("source_block_occurrence_unproven")
        rule_text = ruleset.source_text or json.dumps(ruleset.data, ensure_ascii=False, sort_keys=True)
        return {
            "version": 1, "pdf_sha256": pdf_hash, "assay_key": ruleset.assay_key,
            "normalized_sha256": self._hash_text(norm_text), "assay_block_hash": block_hash,
            "block_start": start, "block_end": end,
            "descriptors": [{"assay_key": a.assay_key, "assay_name": a.assay_name} for a in descriptors],
            "ruleset": ruleset.data, "ruleset_file": ruleset.ruleset_file,
            "rule_source_text": rule_text, "rule_sha256": ruleset.source_sha256 or self._hash_text(rule_text),
            "device_id": device_id, "parser_contract": "pymupdf_positional-v1", "normalizer_contract": "lines-v1",
        }

    def _hash_file(self, path: Path) -> str:
        return self._sha256_file(path)[:16]

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _acquire_lock(self, lock_path: Path, stale_ttl_s: float, *, bound: bool = False):
        lease = try_acquire_scoped_exclusive(lock_path, stale_ttl_s, legacy_stale=not bound)
        if lease is None:
            raise FileExistsError(str(lock_path))
        return lease

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

    @staticmethod
    def _valid_sqlite_output_plan(plan: Any) -> bool:
        """Accept only the complete SQLite snapshot shape emitted by this owner."""
        def fields(payload: Any, schema: Dict[str, type]) -> bool:
            return isinstance(payload, dict) and all(type(payload.get(key)) is kind for key, kind in schema.items())

        def nullable_id(value: Any) -> bool:
            return value is None or (type(value) is int and value > 0)

        if not fields(plan, {"version": int, "output_mode": str, "sqlite_path": str, "sqlite_status": str, "assays": list}):
            return False
        if (
            plan["version"] != _OUTPUT_PLAN_VERSION
            or plan["output_mode"] != "sqlite"
            or not plan["sqlite_path"].strip()
            or plan["sqlite_status"] not in {"pending", "success", "failed"}
            or not plan["assays"]
        ):
            return False
        record_schema = {
            "assay_key": str, "lot_id": str, "dedupe_key": str, "data": dict,
            "device_id": str, "dedupe_version": str, "dedupe_basis": dict,
        }
        write_schema = {
            **record_schema, "assay_name": str, "ruleset_file": str,
            "pdf_sha256": str, "assay_block_hash": str, "missing_required": list,
            "duplicate_status": str, "outputs": list,
        }
        for entry in plan["assays"]:
            if not fields(entry, {
                "assay_record": dict, "ruleset": dict, "write_item": dict,
                "structured_status": str, "sqlite_status": str, "excel_status": str,
            }):
                return False
            if (
                "sqlite_run_id" not in entry
                or not nullable_id(entry["sqlite_run_id"])
                or entry["sqlite_status"] not in {"pending", "success", "duplicate_pending", "failed"}
                or entry["structured_status"] != entry["sqlite_status"]
                or entry["excel_status"] != "not_required"
            ):
                return False
            record, ruleset, write = entry["assay_record"], entry["ruleset"], entry["write_item"]
            if not fields(record, record_schema) or not fields(write, write_schema):
                return False
            if not fields(ruleset, {"assay_key": str, "ruleset_file": str, "assay_name": str, "excel_rules": dict}):
                return False
            if (
                not record["assay_key"].strip()
                or any(write[key] != record[key] for key in record_schema)
                or any(write[key] != ruleset[key] for key in ("assay_key", "ruleset_file", "assay_name"))
                or write["duplicate_status"] not in {"none", "pending"}
                or any(type(key) is not str for key in write["missing_required"])
                or any(key not in write or not nullable_id(write[key]) for key in ("duplicate_candidate_id", "existing_run_id"))
                or not nullable_id(write.get("sqlite_run_id"))
                or entry["sqlite_run_id"] != write.get("sqlite_run_id")
                or (entry["sqlite_status"] != "pending" and not write["outputs"])
            ):
                return False
            for output in write["outputs"]:
                if not fields(output, {"sink": str, "status": str}) or output["sink"] != "sqlite":
                    return False
                if output["status"] == "failed":
                    if not fields(output, {"error": str}):
                        return False
                elif (
                    output["status"] not in {"inserted", "already_persisted", "skipped", "duplicate_pending"}
                    or not fields(output, {"sqlite_path": str, "table": str})
                ):
                    return False
                required_ids = (
                    ("run_id",) if output["status"] in {"inserted", "already_persisted"}
                    else ("existing_run_id", "duplicate_candidate_id") if output["status"] == "duplicate_pending"
                    else ()
                )
                if any(key not in output for key in required_ids):
                    return False
                if any(
                    key in output and (type(output[key]) is not int or output[key] <= 0)
                    for key in ("run_id", "existing_run_id", "duplicate_candidate_id")
                ):
                    return False
        return True

    @staticmethod
    def _is_retired_output_state(state: Dict[str, Any]) -> bool:
        """Recognize frozen legacy/unknown plans without repairing their evidence."""
        if "output_plan" in state:
            if not JobController._valid_sqlite_output_plan(state["output_plan"]):
                return True
        return (
            state.get("export_retry_available") is True
            or str(state.get("excel_status") or "") not in {"", "not_required"}
            or str(state.get("error") or "").startswith("excel_")
        )

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
        """Retired compatibility boundary: no locks, plan writes or Excel I/O."""
        return self._result("SKIPPED", str(job_id), "", {"reason": "excel_export_retired", "excel_status": "not_required"})

    def retry_excel_export_by_job_id(self, project_root: str | Path, job_id: str):
        """Retired compatibility boundary; historical plans remain immutable."""
        return self._result("SKIPPED", str(job_id), "", {"reason": "excel_export_retired", "excel_status": "not_required"})

    def _normalize_output_mode(self, output_mode: str) -> str:
        mode = str(output_mode).strip().lower()
        if mode not in {"both", "excel", "sqlite"}:
            raise ValueError(f"invalid output_mode: {output_mode}")
        return "sqlite"

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

    def read_job_evidence(self, project_root: str | Path, job_id: str, *,
                          expected_pdf_sha256: str | None = None, expected_pdf_path: str | None = None,
                          include_context: bool = True):
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
            if not isinstance(state, dict):
                raise ValueError("job_state_unreadable")
        except Exception:
            return JobEvidence(
                job_id=safe_job_id,
                pdf_path="",
                status="",
                error="job_state_unreadable",
                steps=(),
                normalized_dump_path="",
                block_dump_paths=(),
                state_path=str(state_path),
                state_available=False,
                retry_kind="retired",
            )
        if expected_pdf_sha256 is not None:
            expected = expected_pdf_sha256.lower()
            if (str(state.get("pdf_sha256") or "").lower() != expected
                    or str(state.get("job_id") or "") != safe_job_id or safe_job_id != expected[:16]):
                return None
        if expected_pdf_path is not None and os.path.normcase(str(Path(str(state.get("pdf_path") or "")).resolve())) != os.path.normcase(str(Path(expected_pdf_path).resolve())):
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
            _read_diagnostic_context(normalized_dump, block_dumps) if include_context else ("", False, False, "", "")
        )
        # Legacy export evidence remains visible, but can never enable an action.
        retry_kind = "retired" if self._is_retired_output_state(state) else ""
        evidence_error = str(state.get("error") or "")
        source_store = str((state.get("output_plan") or {}).get("sqlite_path") or "")
        if not source_store:
            source_store = next((str(step.get("store_path") or "") for step in steps if step.get("step") == "assay_identity_changes"), "")
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
            store_path=source_store,
            device_id=str(state.get("device_id") or ""),
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
