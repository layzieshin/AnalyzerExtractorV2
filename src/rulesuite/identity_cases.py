"""Private RuleSuite evidence for a known report name with a new manufacturer ID.

Names are suggestions for a later explicit decision, never routing aliases.
The catalogue is runtime data, not part of the distributable rules directory.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.assaycandidate.api import canonical_assay_key
from src.contentsplitter.api import AssaySection
from src.resultstore.api import get_result_store_status, iter_original_report_sources

from .errors import RuleSuiteError
from .json_io import _read_json_object, _write_json_atomic
from .lifecycle import rulesuite_lifecycle_lock


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _path_key(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def _name_key(name: str) -> str:
    # Only spelling/case/whitespace, not a fuzzy family or filename heuristic.
    return " ".join(str(name).split()).casefold()


def _catalogue_path(root: Path) -> Path:
    current = root
    for part in ("storage", "rulesuite"):
        expected = current / part
        if expected.resolve() != expected:
            raise RuleSuiteError("identity_case_storage_redirected")
        current = expected
    path = current / "identity_cases.json"
    if path.resolve() != path:
        raise RuleSuiteError("identity_case_storage_redirected")
    return path


def _load_catalogue(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "cases": {}}
    data = _read_json_object(path)
    if data.get("version") != 1 or not isinstance(data.get("cases"), dict):
        raise RuleSuiteError("identity_case_catalogue_invalid")
    for key, case in data["cases"].items():
        if not isinstance(case, dict) or case.get("case_id") != key or not isinstance(case.get("sources"), list):
            raise RuleSuiteError("identity_case_catalogue_invalid")
    return data


def _active_catalogue(root: Path, *, expected_index_sha256: str | None = None) -> tuple[dict[str, dict[str, Any]], str]:
    rules = root / "rules"
    raw_index = (rules / "index.json").read_bytes()
    if expected_index_sha256 is not None and hashlib.sha256(raw_index).hexdigest() != expected_index_sha256:
        raise RuleSuiteError("identity_case_active_rules_changed")
    index = json.loads(raw_index)
    active: dict[str, dict[str, Any]] = {}
    signature = [hashlib.sha256(raw_index).hexdigest()]
    for entry in index.get("assays", []):
        key, filename = str(entry.get("assay_key") or ""), str(entry.get("ruleset_file") or "")
        if not key or not filename:
            continue
        canonical = canonical_assay_key(key)
        if canonical in active:
            raise RuleSuiteError("assay_key_ambiguous_in_index")
        path = rules / filename
        if not path.resolve().is_relative_to(rules.resolve()):
            raise RuleSuiteError("identity_case_rule_path_invalid")
        try:
            payload = path.read_bytes()
            rule = json.loads(payload)
            sha = hashlib.sha256(payload).hexdigest()
            name = str(rule.get("assay_name") or "") if isinstance(rule, dict) and rule.get("assay_key") == key else ""
        except (OSError, ValueError, TypeError):
            # An unrelated invalid rule is not silently repaired by discovery.
            sha, name = "unavailable", ""
        active[canonical] = {"assay_key": key, "assay_name": name, "ruleset_file": filename, "rule_sha256": sha}
        signature.append([key, filename, sha])
    return active, _digest(signature)


def _historical_names(root: Path, store_path: str, active: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Read frozen original report identity, not a revised display-name guess."""
    if not Path(store_path).exists():
        return []
    spec = {"driver": "sqlite", "path": store_path}
    status = get_result_store_status(spec)
    if not status.get("available"):
        if status.get("message") == "Tabelle 'runs' nicht vorhanden.":
            return []
        raise RuleSuiteError("identity_case_history_unreadable")
    if status.get("missing_core_columns"):
        raise RuleSuiteError("identity_case_history_incompatible")
    names: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    jobs: dict[str, Any] = {}
    for row in iter_original_report_sources(spec, assay_keys=[item["assay_key"] for item in active.values()]):
        original = row
        key = canonical_assay_key(str(original.get("assay_key") or ""))
        if key not in active or row.get("revision_error"):
            continue
        source = row.get("source_provenance") or {}
        pdf_sha = str(original.get("pdf_sha256") or "").lower()
        if len(pdf_sha) != 64 or any(char not in "0123456789abcdef" for char in pdf_sha):
            continue
        source_root = str(source.get("project_root") or "")
        if source_root and _path_key(source_root) != _path_key(root):
            continue
        descriptors = []
        if (str(source.get("pdf_sha256") or "").lower() == pdf_sha
                and canonical_assay_key(str(source.get("assay_key") or "")) == key):
            descriptors = source.get("descriptors") or []
        if not descriptors:
            # Older completed jobs also conserved their actual splitter names.
            from src.jobcontroller.api import get_job_evidence

            job_id = str(original.get("job_id") or "")
            if job_id != pdf_sha[:16]:
                continue
            if job_id not in jobs:
                jobs[job_id] = get_job_evidence(root, job_id, expected_pdf_sha256=pdf_sha,
                                               expected_pdf_path=str(original.get("pdf_path") or ""))
            job = jobs[job_id]
            if (job is None or not job.state_available or job.status != "DONE"
                    or _path_key(job.pdf_path) != _path_key(str(original.get("pdf_path") or ""))):
                continue
            descriptors = [item for step in job.steps if step.get("step") == "contentsplitter"
                           for item in step.get("assays", [])]
        for descriptor in descriptors:
            if not isinstance(descriptor, dict) or canonical_assay_key(str(descriptor.get("assay_key") or "")) != key:
                continue
            name = str(descriptor.get("assay_name") or "").strip()
            identity = (key, _name_key(name))
            if name and identity not in seen:
                seen.add(identity)
                names.append({"name": name, "key": key, "kind": "report_history", "run_id": original.get("id"),
                              "report_id": str(row.get("report_id") or ""), "pdf_sha256": pdf_sha})
    return names


def list_assay_identity_cases(project_root: str, *, store_path: str) -> list[dict[str, Any]]:
    if not str(store_path).strip():
        raise RuleSuiteError("identity_case_store_required")
    catalogue = _load_catalogue(_catalogue_path(Path(project_root).resolve()))
    store = _path_key(store_path)
    result = [copy.deepcopy(case) for case in catalogue["cases"].values() if case.get("store_path") == store]
    from .identity_authoring import identity_activation_committed
    for case in result:
        if case.get("activation"):
            case["status"] = "activated" if identity_activation_committed(Path(project_root).resolve(), case) else "activation_pending"
    return result


def list_assay_identity_job_bindings(project_root: str) -> dict[str, dict[str, Any]]:
    """One cheap index per worker claim, including pre-upgrade pending holds.

    Only recorded full source identities qualify; ambiguous stores/devices/paths
    remain explicit errors rather than guessing a current UI context.
    """
    root = Path(project_root).resolve()
    catalogue = _load_catalogue(_catalogue_path(root))
    bindings: dict[str, dict[str, Any]] = {}
    for case in catalogue["cases"].values():
        if case.get("project_root") != str(root):
            raise RuleSuiteError("identity_case_workspace_changed")
        for source in case["sources"]:
            job_id, sha = str(source.get("job_id") or ""), str(source.get("pdf_sha256") or "")
            if (len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha) or job_id != sha[:16]
                    or not source.get("pdf_path") or not source.get("device_id") or not case.get("store_path")):
                raise RuleSuiteError("identity_case_source_identity_invalid")
            binding = {"version": 1, "job_id": job_id, "content_sha256": sha, "pdf_path": _path_key(source["pdf_path"]),
                       "store_path": _path_key(case["store_path"]), "device_id": source["device_id"]}
            previous = bindings.get(job_id)
            if previous is not None:
                if previous.get("error") or any(previous.get(key) != value for key, value in binding.items()):
                    bindings[job_id] = {"error": "identity_case_binding_ambiguous"}
                    continue
                binding["case_ids"] = sorted(set(previous["case_ids"]) | {case["case_id"]})
            else:
                binding["case_ids"] = [case["case_id"]]
            bindings[job_id] = binding
    return bindings


def observe_assay_identity_changes(
    project_root: str, *, store_path: str, pdf_path: str, pdf_sha256: str,
    job_id: str, device_id: str, normalized_text: str, sections: Iterable[AssaySection],
    expected_index_sha256: str | None = None,
) -> list[dict[str, Any]]:
    """Persist qualifying observations atomically before the import's first sink.

    The returned cases are deliberately unresolved. Unrelated unknown assay
    names retain their pre-existing workflow. Source additions do not change
    the identity token that a later explicit assignment will bind.
    """
    if not str(store_path).strip():
        raise RuleSuiteError("identity_case_store_required")
    root, store = Path(project_root).resolve(), _path_key(store_path)
    if expected_index_sha256 is not None and hashlib.sha256((root / "rules" / "index.json").read_bytes()).hexdigest() != expected_index_sha256:
        raise RuleSuiteError("identity_case_active_rules_changed")
    rows = list(sections)
    active, signature = _active_catalogue(root, expected_index_sha256=expected_index_sha256)
    unknown = [section for section in rows if section.assay_key not in active]
    if not unknown:
        return []
    evidence = [{"key": key, "name": item["assay_name"], "kind": "configured_display_name"}
                for key, item in active.items() if item["assay_name"]]
    evidence.extend({"key": row.assay_key, "name": row.assay_name, "kind": "current_report"}
                    for row in rows if row.assay_key in active)
    evidence.extend(_historical_names(root, store, active))
    observations = []
    for section in unknown:
        matched = [item for item in evidence if _name_key(item["name"]) == _name_key(section.assay_name)]
        if not matched:
            continue
        if normalized_text[section.start:section.end] != section.text:
            raise RuleSuiteError("identity_case_source_block_unproven")
        if len(pdf_sha256) != 64 or any(char not in "0123456789abcdef" for char in pdf_sha256.lower()) or job_id != pdf_sha256[:16]:
            raise RuleSuiteError("identity_case_source_hash_invalid")
        source = {"job_id": job_id, "pdf_path": _path_key(pdf_path), "pdf_sha256": pdf_sha256.lower(),
                  "normalized_sha256": hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
                  "assay_block_sha256": hashlib.sha256(section.text.encode("utf-8")).hexdigest(),
                  "block_start": section.start, "block_end": section.end, "device_id": device_id,
                  "assay_name": section.assay_name, "raw_assay_key": section.raw_assay_key}
        source["source_id"] = _digest(source)
        candidates = []
        for key in sorted({item["key"] for item in matched}):
            item = dict(active[key])
            item["name_evidence"] = sorted((dict(row) for row in matched if row["key"] == key), key=_digest)
            candidates.append(item)
        observations.append((section, source, candidates))
    if not observations:
        return []
    path = _catalogue_path(root)
    with rulesuite_lifecycle_lock(str(root)):
        if _active_catalogue(root)[1] != signature:
            raise RuleSuiteError("identity_case_active_rules_changed")
        path = _catalogue_path(root)
        catalogue = _load_catalogue(path)
        changed, result = False, []
        for section, source, candidates in observations:
            case_id = _digest([store, section.assay_key])
            case = catalogue["cases"].get(case_id)
            if case is None:
                case = {"case_id": case_id, "store_path": store, "project_root": str(root), "status": "open",
                        "assay_key": section.assay_key, "observed_names": [], "candidate_assays": [],
                        "sources": [], "source_revision": 0, "created_at_utc": datetime.now(timezone.utc).isoformat()}
                catalogue["cases"][case_id] = case
            previous = _digest(case)
            if section.assay_name not in case["observed_names"]:
                case["observed_names"].append(section.assay_name)
            by_key = {item["assay_key"]: item for item in case["candidate_assays"]}
            by_key.update({item["assay_key"]: item for item in candidates})
            case["candidate_assays"] = [by_key[key] for key in sorted(by_key)]
            case["requires_selection"] = len(by_key) != 1
            case["identity_token"] = _digest([case_id, sorted({_name_key(name) for name in case["observed_names"]}), sorted(by_key)])
            if source["source_id"] not in {item["source_id"] for item in case["sources"]}:
                case["sources"].append(source)
                case["source_revision"] += 1
            changed = changed or _digest(case) != previous
            result.append(copy.deepcopy(case))
        if changed:
            _write_json_atomic(path, catalogue)
        return result
