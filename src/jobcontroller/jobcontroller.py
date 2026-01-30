from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .model import JobResult


class JobController:
    def submit(self, pdf_path: str, project_root: str):
        root = Path(project_root)
        pdf = Path(pdf_path)

        if not pdf.exists():
            return self._result("FAILED", "", str(pdf), {"error": "pdf_not_found"})

        job_id = self._hash_file(pdf)
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
            self._acquire_lock(lock_path)
        except FileExistsError:
            return self._result("SKIPPED", job_id, str(pdf), {"reason": "locked"})

        state: Dict[str, Any] = {"job_id": job_id, "pdf_path": str(pdf), "status": "LOCKED", "steps": []}
        self._save_state(state_path, state)

        try:
            # PARSE
            from src.parser.api import parse
            from src.assaychooser.api import detect_assays
            from src.normalizer.api import normalize_lines
            from src.ruleresolver.api import resolve_ruleset
            from src.contentsplitter.api import split_by_assay_name_and_key
            from src.contentsplitter.model import AssayDescriptor
            from src.extractor.api import extract_record
            from src.writer.api import write_record

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
            for k, block in blocks.items():
                safe_k = k.replace("(", "").replace(")", "")
                p = jobs_dir / f"{job_id}_{safe_k}_block.txt"
                p.write_text(block, encoding="utf-8")
                block_dumps[k] = str(p)

            state["steps"].append({"step": "debug_blocks", "block_dumps": block_dumps})
            self._save_state(state_path, state)

            # EXTRACT + WRITE (reuse already loaded rulesets)
            writes: List[Dict[str, Any]] = []
            for k in assay_keys:
                ruleset = assay_rulesets[k]
                rec = extract_record(blocks[k], ruleset)
                wr = write_record(rec, ruleset, str(output_dir))
                writes.append({
                    "assay_key": k,
                    "excel_path": wr.excel_path,
                    "sheet": wr.sheet_name,
                    "status": wr.status
                })

            state["status"] = "DONE"
            state["steps"].append({"step": "writer", "writes": writes})
            self._save_state(state_path, state)
            return self._result("DONE", job_id, str(pdf), {"assay_keys": assay_keys, "writes": writes})

        except Exception as e:
            state["status"] = "FAILED"
            state["error"] = str(e)
            self._save_state(state_path, state)
            return self._result("FAILED", job_id, str(pdf), {"error": str(e)})
        finally:
            self._release_lock(lock_path)

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def _acquire_lock(self, lock_path: Path) -> None:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)

    def _release_lock(self, lock_path: Path) -> None:
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass

    def _save_state(self, path: Path, state: Dict[str, Any]) -> None:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _result(self, status: str, job_id: str, pdf_path: str, details: Dict[str, object]):
        from .api import JobResult
        return JobResult(job_id=job_id, pdf_path=pdf_path, status=status, details=details)
