"""Presentation-independent archive eligibility used by ResultsController."""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path

from src.ingestion.api import hash_stable_pdf, resolve_current_path
from src.jobcontroller.api import inspect_pdf_archive_identity, verify_completed_job
from src.resultstore.api import list_result_runs


def _date(value):
    value = str(value).strip()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return datetime.strptime(value, "%d.%m.%Y").date().isoformat()


def headers(payload, *, fallback=None):
    plates = {str(payload[key]).strip().casefold(): str(payload[key]).strip()
              for key in ("PLATTE", "plate_name") if key in payload and str(payload[key] or "").strip()}
    dates = {_date(payload[key]) for key in ("DATUM", "date") if key in payload and str(payload[key] or "").strip()}
    if fallback:
        if fallback.get("plate"):
            plates[str(fallback["plate"]).casefold()] = fallback["plate"]
        if fallback.get("date"):
            dates.add(_date(fallback["date"]))
    if len(plates) != 1 or len(dates) != 1:
        raise ValueError("PLATTE/plate_name oder DATUM/date fehlen oder widersprechen sich.")
    return next(iter(plates.values())), next(iter(dates))


def _origin_context(original):
    return (str(original.get("device_id") or ""),
            os.path.normcase(str(Path(str(original.get("pdf_path") or "")).resolve().parent)))


def _validated_row(row, index):
    if row.get("pending_revision") or row.get("revision_error") or row.get("missing_fields"):
        raise ValueError("Ergebnisrevision ist unvollständig oder noch offen.")
    run_id = int(row["id"])
    if run_id in index.ambiguous_run_ids:
        raise ValueError("Validierungsnachweis ist mehrdeutig.")
    validation = index.latest_by_run_id.get(run_id)
    if validation is None:
        raise ValueError("Mindestens ein bekanntes Ergebnis dieser Platte ist nicht validiert.")
    from .results_controller import _validation_matches_row
    if not _validation_matches_row(validation, row):
        raise ValueError("Validierung gehört nicht zur ausgewählten Fassung.")
    return validation


def read_archive_evidence(controller, spec, paths, *, pdf_reader=inspect_pdf_archive_identity, context_guard=None):
    """Every expected assay must have its actual persisted and validated run."""
    rows = list_result_runs(spec, limit=None)["runs"]
    originals = [(row, row.get("original_result") or row) for row in rows]
    index = controller._load_validation_index([int(row["id"]) for row in rows], store_spec=spec)
    result = {}
    for raw_path in paths:
        if context_guard is not None and not context_guard():
            raise ValueError("Vorschau wurde geschlossen oder ihr Kontext geändert.")
        path = Path(raw_path)
        try:
            if not path.is_file():
                origin_rows = [(row, original) for row, original in originals if Path(str(original.get("pdf_path") or "")).resolve() == path.resolve()]
                if not origin_rows:
                    raise ValueError("Ursprünglicher Import für Wiederaufnahme fehlt.")
                original = origin_rows[0][1]
                path = Path(resolve_current_path(controller.project_root, original["job_id"], original["pdf_path"]).current_pdf_path)
            digest, _, _ = hash_stable_pdf(path)
            matches = [(row, original) for row, original in originals if original.get("pdf_sha256") == digest]
            known = {str(original["assay_key"]) for _, original in matches}
            identity = pdf_reader(str(path), expected_sha256=digest, known_assay_keys=known, project_root=controller.project_root)
            proof = {**identity, "eligible": False, "run_ids": [], "validations": []}
            result[raw_path] = proof
            if identity.get("error"):
                raise ValueError(identity["error"])
            if not matches:
                raise ValueError("PDF ist nicht vollständig importiert.")
            jobs = {(str(original.get("job_id") or ""), str(original.get("pdf_path") or ""), str(original.get("device_id") or "")) for _, original in matches}
            if len(jobs) != 1:
                raise ValueError("Importquelle oder Gerät ist mehrdeutig.")
            job, original_path, device = next(iter(jobs))
            proof["origin_context"] = _origin_context(matches[0][1])
            location = resolve_current_path(controller.project_root, job, original_path)
            if location.path_status == "ambiguous" or Path(location.current_pdf_path).resolve() != path.resolve():
                raise ValueError("PDF gehört nicht zum eindeutigen gespeicherten Importort.")
            completion = verify_completed_job(controller.project_root, job, expected_sha256=digest,
                expected_pdf_path=original_path, store_path=spec["path"], device_id=device, include_outputs=True)
            if not completion["complete"] or completion.get("duplicate_pending"):
                raise ValueError("Verarbeitung oder Duplikatklärung ist noch offen.")
            if set(completion["run_ids"]) != {int(row["id"]) for row, _ in matches}:
                raise ValueError("Nachweis umfasst nicht jedes erwartete Ergebnis.")
            if sorted(str(original["assay_key"]).casefold() for _, original in matches) != sorted(identity["assay_keys"]):
                raise ValueError("In der PDF sind nicht vollständig importierte Assays enthalten.")
            for row, original in matches:
                validation = _validated_row(row, index)
                plate, measured = headers(row["payload"], fallback=proof)
                proof.update(plate=plate, date=measured)
                proof["run_ids"].append(int(row["id"]))
                proof["validations"].append([validation.validation_id, row.get("selection_token", ""), row.get("selected_revision_id", 0)])
            proof["eligible"] = True
        except Exception as exc:
            if raw_path not in result:
                result[raw_path] = {"plate": "", "date": "", "sha256": "", "eligible": False}
            result[raw_path]["reason"] = str(exc)
    # Known runs of the same physical plate remain relevant even when their
    # printout is missing or was archived earlier. Never join a namesake plate
    # from a different device/original input directory merely by its label.
    completions = {}
    for proof in result.values():
        if not proof.get("eligible"):
            continue
        try:
            related = []
            for row, original in originals:
                if _origin_context(original) != proof["origin_context"]:
                    continue
                try:
                    plate, measured = headers(row["payload"])
                except ValueError:
                    authentic = next((item for item in result.values()
                                      if item.get("sha256") == original.get("pdf_sha256")), None)
                    try:
                        plate, measured = headers(original["payload"], fallback=authentic)
                    except ValueError:
                        continue  # No evidence that this historical row is this plate.
                if plate.casefold() != proof["plate"].casefold() or measured != proof["date"]:
                    continue
                headers(row["payload"], fallback=proof)
                validation = _validated_row(row, index)
                job = str(original.get("job_id") or "")
                if job not in completions:
                    completions[job] = verify_completed_job(controller.project_root, job,
                        expected_sha256=original.get("pdf_sha256", ""), expected_pdf_path=original.get("pdf_path", ""),
                        store_path=spec["path"], device_id=original.get("device_id", ""), include_outputs=True)
                receipt = completions[job]
                if not receipt["complete"] or receipt.get("duplicate_pending") or int(row["id"]) not in receipt.get("run_ids", ()):
                    raise ValueError("Ein bekannter Import dieser Platte ist noch unvollständig oder ungeklärt.")
                related.append([int(row["id"]), validation.validation_id, row.get("selection_token", ""), row.get("selected_revision_id", 0)])
            proof["plate_runs"] = sorted(related)
        except Exception as exc:
            proof.update(eligible=False, reason=str(exc))
    return result
