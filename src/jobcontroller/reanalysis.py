"""Proven-source reanalysis; PDF work stays on a fresh child main thread."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from src.dbwriter.api import ResultRevisionConflictError, ResultRevisionError, append_result_revision
from src.ingestion.api import resolve_current_path
from src.resultstore.api import get_result_run
from src.resultvalidation.api import list_run_validations_readonly
from src.ruleresolver.api import RuleSet, resolve_ruleset

MAX_PDF_BYTES = 128 * 1024 * 1024
MAX_RESULT_BYTES = 8 * 1024 * 1024
REANALYSIS_TIMEOUT_S = 20.0
_PROCESS_LOCK = threading.Lock()


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _failure(message: str) -> ResultRevisionError:
    return ResultRevisionError(message + " Bitte Quelle/Regelwerk in der Nacharbeit klaeren und erneut analysieren.")


def _legacy_source_contract(root: Path, original: dict[str, Any]) -> dict[str, Any]:
    from .jobcontroller import _path_is_contained, _sanitize_job_id

    job = _sanitize_job_id(str(original.get("job_id") or ""))
    if not job:
        raise _failure("Der urspruengliche Verarbeitungsnachweis fehlt.")
    path = root / "jobs" / f"{job}.json"
    if not _path_is_contained(path, root / "jobs") or not path.is_file():
        raise _failure("Der urspruengliche Verarbeitungsnachweis fehlt.")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("status") != "DONE":
            raise _failure("Die urspruengliche Verarbeitung ist nicht abgeschlossen.")
        entries = state["output_plan"]["assays"]
        matches = [entry for entry in entries if entry.get("sqlite_run_id") == original["id"]]
        if not matches:
            matches = [entry for entry in entries if
                entry.get("assay_record", {}).get("assay_key") == original["assay_key"]
                and entry.get("assay_record", {}).get("data") == original["payload"]
                and entry.get("assay_record", {}).get("dedupe_key") == original["dedupe_key"]]
        if len(matches) != 1:
            raise _failure("Die urspruengliche Assay-Zuordnung ist nicht eindeutig.")
        entry = matches[0]
        record, write = entry["assay_record"], entry["write_item"]
        if any(record.get(key) != original.get(key) for key in ("assay_key", "lot_id", "dedupe_key", "device_id")) or record.get("data") != original["payload"]:
            raise _failure("Verarbeitungsnachweis und urspruengliche Messung widersprechen sich.")
        if not original.get("assay_block_hash") or write.get("assay_block_hash") != original["assay_block_hash"]:
            raise _failure("Der genaue urspruengliche Assay-Block ist nicht nachgewiesen.")
        if not original.get("pdf_sha256") or state.get("pdf_sha256") != original["pdf_sha256"] or write.get("pdf_sha256") != original["pdf_sha256"]:
            raise _failure("Der vollstaendige urspruengliche PDF-Hash fehlt oder widerspricht sich.")
        descriptors = [{"assay_key": item["ruleset"]["assay_key"], "assay_name": item["ruleset"]["assay_name"]} for item in entries]
        recorded = [step["assays"] for step in state.get("steps", []) if step.get("step") == "contentsplitter" and step.get("mode") == "assay_name_and_key"]
        if recorded and (len(recorded) != 1 or recorded[0] != descriptors):
            raise _failure("Die eingefrorenen Assay-Zuordnungen widersprechen sich.")
        return {"version": 0, "descriptors": descriptors, "assay_key": original["assay_key"],
                "assay_block_hash": original["assay_block_hash"], "pdf_sha256": original["pdf_sha256"]}
    except ResultRevisionError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise _failure("Der urspruengliche Verarbeitungsnachweis ist unvollstaendig oder unlesbar.") from exc


def _proven_block(norm_text: str, source: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    from src.contentsplitter.api import AssayDescriptor, split_by_assay_name_and_key

    expected_hash = str(source.get("assay_block_hash") or "")
    if len(expected_hash) != 64:
        raise _failure("Der urspruengliche Block-Hash fehlt.")
    normalized_hash = _hash(norm_text.encode("utf-8"))
    if source.get("normalized_sha256") and source["normalized_sha256"] != normalized_hash:
        raise _failure("Der PDF-Text entspricht nicht dem urspruenglichen Parser-/Normalisierungsstand.")
    if "block_start" in source and "block_end" in source:
        start, end = source["block_start"], source["block_end"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(norm_text):
            raise _failure("Die urspruengliche Blockposition ist ungueltig.")
        block = norm_text[start:end]
    else:
        descriptors = source.get("descriptors")
        if not isinstance(descriptors, list) or not descriptors:
            raise _failure("Die eingefrorene Assay-Zuordnung fehlt.")
        assays = [AssayDescriptor(str(item["assay_key"]), str(item["assay_name"])) for item in descriptors]
        if len({assay.assay_key for assay in assays}) != len(assays):
            raise _failure("Die urspruengliche Assay-Zuordnung ist mehrdeutig.")
        blocks = split_by_assay_name_and_key(norm_text, assays)
        block = blocks[str(source["assay_key"])]
        # The old splitter's descriptors plus its exact persisted block hash
        # reconstruct the original occurrence. Never choose a new active name
        # or the first matching current assay as a substitute.
        if norm_text.count(block) != 1:
            raise _failure("Der urspruengliche Assay-Block kommt mehrfach vor.")
        start = norm_text.index(block)
        end = start + len(block)
    if _hash(block.encode("utf-8")) != expected_hash:
        raise _failure("Der Assay-Block stimmt nicht mit der urspruenglichen Extraktion ueberein.")
    return block, {**source, "normalized_sha256": normalized_hash, "block_start": start, "block_end": end}


def _extract_snapshot(pdf_path: str, source: dict[str, Any], ruleset: RuleSet, device_id: str) -> dict[str, Any]:
    """Child-main-thread only; uses the established pipeline APIs."""
    from src.extractor.api import ExtractionError, extract_record
    from src.normalizer.api import normalize_lines
    from src.parser.api import parse

    result: dict[str, Any] = {"source_verified": False, "payload": {}, "error": "", "missing_fields": []}
    try:
        document = parse(pdf_path)
        if not 0 < len(document.pages) <= 1000:
            raise _failure("Die PDF-Seitenzahl ist ungueltig oder groesser als 1000.")
        normalized = "\n".join(normalize_lines([line for page in document.pages for line in page.lines]))
        block, proven_source = _proven_block(normalized, source)
        result.update(source_verified=True, source_provenance=proven_source)
        record = extract_record(block, ruleset, device_id=device_id)
        result.update(payload=record.data, lot_id=record.lot_id, dedupe_key=record.dedupe_key,
                      dedupe_version=record.dedupe_version, dedupe_basis=record.dedupe_basis)
    except ExtractionError as exc:
        result.update(payload=exc.partial_data, missing_fields=list(exc.missing_fields), error=str(exc))
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _reanalysis_worker(pdf_path: str, source: dict[str, Any], rule: dict[str, Any], device_id: str, folder: str) -> None:
    ruleset = RuleSet(**rule)
    result = _extract_snapshot(pdf_path, source, ruleset, device_id)
    (Path(folder) / "result.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def _run_isolated(pdf_bytes: bytes, source: dict[str, Any], ruleset: RuleSet, device_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + REANALYSIS_TIMEOUT_S
    if not _PROCESS_LOCK.acquire(timeout=REANALYSIS_TIMEOUT_S):
        raise _failure("Die Neuanalyse ist beschaeftigt oder hat das Zeitlimit ueberschritten.")
    process = None
    started = False
    try:
        with tempfile.TemporaryDirectory(prefix="arev2-reanalysis-") as temporary:
            folder = Path(temporary)
            source_path = folder / "source.pdf"
            source_path.write_bytes(pdf_bytes)
            try:
                rule = {"assay_key": ruleset.assay_key, "ruleset_file": ruleset.ruleset_file,
                        "data": ruleset.data, "source_text": ruleset.source_text, "source_sha256": ruleset.source_sha256}
                process = multiprocessing.get_context("spawn").Process(target=_reanalysis_worker,
                    args=(str(source_path), source, rule, device_id, temporary), daemon=True)
                process.start()
                started = True
                process.join(timeout=max(0, deadline - time.monotonic()))
                if process.is_alive():
                    raise _failure("Die Neuanalyse hat das Zeitlimit ueberschritten.")
                if process.exitcode != 0:
                    raise _failure("Der Analyseprozess wurde unerwartet beendet.")
                result_path = folder / "result.json"
                if result_path.stat().st_size > MAX_RESULT_BYTES:
                    raise _failure("Der Analysevergleich ist zu gross.")
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if not isinstance(result, dict) or type(result.get("source_verified")) is not bool or not isinstance(result.get("payload"), dict):
                    raise _failure("Der Analyseprozess lieferte ungueltige Daten.")
                return result
            finally:
                if process is not None:
                    if started and process.is_alive():
                        process.terminate()
                        process.join(timeout=0.5)
                    if started and process.is_alive():
                        process.kill()
                        process.join(timeout=0.5)
                    if not started or not process.is_alive():
                        process.close()
    except ResultRevisionError:
        raise
    except Exception as exc:
        raise _failure("Die Neuanalyse konnte nicht abgeschlossen werden.") from exc
    finally:
        _PROCESS_LOCK.release()


def reanalyze_run(project_root: str | Path, store_spec: dict[str, str], run_id: int, *,
                  expected_selection_token: str, request_id: str, operator_initials: str) -> dict[str, Any]:
    """Freeze one source/rule, compute outside locks, publish under DbWriter lock."""
    root = Path(project_root).resolve()
    if not isinstance(request_id, str) or not isinstance(operator_initials, str):
        raise ResultRevisionError("Bitte Initialen und eine eindeutige Anfragekennung angeben.")
    request_id = request_id.strip()
    operator_initials = operator_initials.strip()
    spec = dict(store_spec)
    if spec.get("driver", "sqlite") != "sqlite" or not isinstance(spec.get("path"), str):
        raise ResultRevisionError("Der Ergebnisspeicher wird nicht unterstuetzt.")
    spec["path"] = str(Path(spec["path"]).resolve())
    state = get_result_run(spec, int(run_id))
    if state is None:
        raise ResultRevisionError("Die Messung fehlt. Bitte aktualisieren.")
    # Retrying an exact request returns its frozen evidence without reparsing a
    # changed active rule, including after its candidate was already resolved.
    for revision in state["result_revisions"]:
        if revision["request_id"] == request_id:
            if revision["expected_selection_token"] != expected_selection_token or revision["created_by"] != operator_initials.strip():
                raise ResultRevisionConflictError("Die Anfragekennung wurde bereits fuer andere Daten verwendet.")
            return {"run_id": run_id, "revision_id": int(revision["revision_id"]), "request_id": request_id}
    if not request_id.strip() or not operator_initials.strip():
        raise ResultRevisionError("Bitte Initialen und eine eindeutige Anfragekennung angeben.")
    if state.get("revision_error") or state.get("payload_parse_error"):
        raise ResultRevisionError("Die Ergebnishistorie ist unlesbar. Bitte Datenbestand klaeren.")
    if state["selection_token"] != expected_selection_token:
        raise ResultRevisionConflictError("Die Messung hat sich geaendert. Bitte aktualisieren.")
    if list_run_validations_readonly(spec, [run_id]).latest(run_id) is not None:
        raise ResultRevisionConflictError("Die Messung ist bereits validiert.")
    from .api import processing_eligibility_error
    eligibility = processing_eligibility_error(root, state["job_id"], require_evidence=bool(state.get("source_provenance", {}).get("project_root")))
    if eligibility:
        raise ResultRevisionConflictError(eligibility)
    original = state["original_result"]
    snapshot: dict[str, Any] = {
        "assay_key": original["assay_key"], "device_id": original["device_id"], "payload": {},
        "lot_id": "", "dedupe_key": "", "dedupe_version": "", "dedupe_basis": {},
        "ruleset": {}, "ruleset_file": "", "rule_source_text": "", "rule_sha256": "",
        "source_verified": False, "source_provenance": {}, "missing_fields": [], "error": "",
    }
    try:
        if not str(original.get("device_id") or "").strip():
            raise _failure("Das urspruengliche Geraet ist nicht nachgewiesen.")
        ruleset = resolve_ruleset(original["assay_key"], str(root / "rules"), str(root / "rules" / "index.json"))
        snapshot.update(ruleset=ruleset.data, ruleset_file=ruleset.ruleset_file,
                        rule_source_text=ruleset.source_text, rule_sha256=ruleset.source_sha256)
        source = dict(state.get("source_provenance") or {})
        if not source.get("descriptors") or "block_start" not in source:
            source = _legacy_source_contract(root, original)
        if source.get("assay_key") != original["assay_key"] or source.get("assay_block_hash") != original["assay_block_hash"]:
            raise _failure("Der genaue urspruengliche Assay-Block ist nicht nachgewiesen.")
        expected_hash = str(original.get("pdf_sha256") or "")
        if len(expected_hash) != 64 or source.get("pdf_sha256") != expected_hash:
            raise _failure("Der vollstaendige urspruengliche PDF-Hash fehlt oder widerspricht sich.")
        resolution = resolve_current_path(root, original["job_id"], original["pdf_path"])
        if resolution.path_status == "ambiguous":
            raise _failure("Die archivierte PDF-Quelle ist nicht eindeutig.")
        path = Path(resolution.current_pdf_path)
        with path.open("rb") as stream:
            pdf_bytes = stream.read(MAX_PDF_BYTES + 1)
        if len(pdf_bytes) > MAX_PDF_BYTES:
            raise _failure("Die PDF ist groesser als 128 MB.")
        if _hash(pdf_bytes) != expected_hash:
            raise _failure("Die PDF stimmt nicht mit dem urspruenglichen SHA-256 ueberein.")
        source.update(current_pdf_path=str(path), ingestion_id=resolution.ingestion_id, project_root=str(root))
        snapshot["source_provenance"] = source
        snapshot.update(_run_isolated(pdf_bytes, source, ruleset, original["device_id"]))
    except Exception as exc:
        snapshot["error"] = str(exc)
    return append_result_revision(spec["path"], run_id, expected_selection_token=expected_selection_token,
        request_id=request_id, snapshot=snapshot, created_by=operator_initials, project_root=str(root))
