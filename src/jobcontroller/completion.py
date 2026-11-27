"""Read-only reconciliation of a job's actual, complete SQLite output."""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.resultstore.api import get_processing_output_evidence


def _path(value):
    return os.path.normcase(str(Path(str(value)).resolve()))


def _same_json(left, right):
    # Raw False/0/empty values stay distinct; no display/numeric coercion.
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def verify_completed_job(project_root, job_id, *, expected_sha256, expected_pdf_path, store_path, device_id, include_outputs=False):
    """Return an honest receipt without importing or changing historical data.

    Inserted/already-persisted rows and real duplicate candidates are supported.
    Thin legacy DONE files, another store/device/source, incomplete mixed output,
    and an unrelated existing_run_id do not establish completion.
    """
    result = {"complete": False, "reason": "processing_completion_evidence_missing"}
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)
            or job_id != expected_sha256[:16] or not store_path or not device_id):
        return result
    try:
        state = json.loads((Path(project_root) / "jobs" / f"{job_id}.json").read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("status") != "DONE":
            return result
        if (state.get("job_id") != job_id or state.get("pdf_sha256") != expected_sha256
                or _path(state.get("pdf_path", "")) != _path(expected_pdf_path)
                or state.get("device_id") != device_id):
            return {**result, "reason": "processing_completion_source_context_mismatch"}
        plan = state.get("output_plan")
        if plan is not None:
            from .jobcontroller import JobController
            if (not JobController._valid_sqlite_output_plan(plan) or plan["sqlite_status"] != "success"
                    or _path(plan["sqlite_path"]) != _path(store_path)
                    or any(row["sqlite_status"] not in {"success", "duplicate_pending"} for row in plan["assays"])):
                return {**result, "reason": "processing_completion_plan_incomplete"}
            writes = [row["write_item"] for row in plan["assays"]]
        else:
            # Older complete SQLite receipts may predate output_plan. Do not
            # manufacture a plan or rewrite them; require every original field.
            writes = next((row.get("writes") for row in reversed(state.get("steps", []))
                           if isinstance(row, dict) and row.get("step") == "writer"), None)
        if not isinstance(writes, list) or not writes:
            return result
        chosen = next((row.get("assay_keys") for row in state.get("steps", [])
                       if isinstance(row, dict) and row.get("step") == "assaychooser"), None)
        if not isinstance(chosen, list) or sorted(chosen) != sorted(row.get("assay_key", "") for row in writes):
            return {**result, "reason": "processing_completion_plan_incomplete"}
        outputs, runs, candidates = [], set(), set()
        for write in writes:
            required = {"assay_key", "lot_id", "dedupe_key", "device_id", "dedupe_version", "dedupe_basis",
                        "data", "ruleset_file", "pdf_sha256", "assay_block_hash", "outputs"}
            if (not isinstance(write, dict) or not required.issubset(write)
                    or write["pdf_sha256"] != expected_sha256 or write["device_id"] != device_id
                    or not isinstance(write["assay_block_hash"], str) or len(write["assay_block_hash"]) != 64
                    or not isinstance(write["data"], dict) or not isinstance(write["dedupe_basis"], dict)
                    or not isinstance(write["outputs"], list) or len(write["outputs"]) != 1):
                return result
            output = write["outputs"][0]
            if (output.get("sink") != "sqlite" or output.get("table") != "runs"
                    or _path(output.get("sqlite_path", "")) != _path(store_path)):
                return {**result, "reason": "processing_completion_store_mismatch"}
            if output.get("status") in {"inserted", "already_persisted"}:
                runs.add(output["run_id"])
            elif output.get("status") == "duplicate_pending":
                candidates.add(output["duplicate_candidate_id"])
                runs.add(output["existing_run_id"])
            else:
                return result
            outputs.append((write, output))
        evidence = get_processing_output_evidence({"driver": "sqlite", "path": store_path},
                                                  run_ids=runs, candidate_ids=candidates)
        for write, output in outputs:
            duplicate = output["status"] == "duplicate_pending"
            row_id = output["duplicate_candidate_id"] if duplicate else output["run_id"]
            row = evidence["duplicate_candidates" if duplicate else "runs"].get(row_id)
            if not row:
                return result
            meta = json.loads(row["candidate_meta_json"]) if duplicate else row
            if (meta.get("job_id") != job_id or _path(meta.get("pdf_path", "")) != _path(expected_pdf_path)
                    or meta.get("lot_id") != write["lot_id"] or meta.get("ruleset_file") != write["ruleset_file"]
                    or any(row.get(key) != write[key] for key in ("assay_key", "dedupe_key", "device_id", "dedupe_version", "pdf_sha256", "assay_block_hash"))
                    or not _same_json(json.loads(row["dedupe_basis_json"]), write["dedupe_basis"])
                    or not _same_json(json.loads(row["candidate_payload_json" if duplicate else "payload_json"]), write["data"])):
                return {**result, "reason": "processing_completion_output_mismatch"}
            if duplicate and (row.get("existing_run_id") != output["existing_run_id"]
                              or output["existing_run_id"] not in evidence["runs"]):
                return result
        result = {"complete": True, "reason": "", "kind": "sqlite_plan" if plan is not None else "legacy_sqlite_receipt"}
        if include_outputs:
            result.update(run_ids=sorted({output["run_id"] for _, output in outputs if output["status"] != "duplicate_pending"}),
                          duplicate_pending=any(output["status"] == "duplicate_pending" for _, output in outputs))
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return result
    except Exception as exc:
        # Unavailable/corrupt SQLite is never a successful reconciliation.
        return {**result, "reason": f"processing_completion_store_unavailable:{type(exc).__name__}"}
