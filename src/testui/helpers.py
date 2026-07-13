from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping


def classify_job_outcome(status: str, details: Dict[str, Any]) -> str:
    if status == "DONE":
        return "PASS"
    if status == "SKIPPED" and str(details.get("reason", "")) == "already_done":
        return "PASS"
    if status == "SKIPPED":
        return "WARN"
    return "FAIL"


def load_job_state(project_root: str, job_id: str) -> Dict[str, Any] | None:
    if not job_id:
        return None
    state_path = Path(project_root) / "jobs" / f"{job_id}.json"
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def humanize_job_error(error: str | None = None, reason: str | None = None) -> str:
    if reason == "already_done":
        return "Bereits verarbeitet (Job-State DONE). Force rerun moeglich."
    if reason == "locked":
        return "Pipeline-Lock aktiv — Lauf uebersprungen."
    if not error:
        return ""

    err = str(error).strip()
    if err == "pdf_not_found":
        return "PDF-Datei nicht gefunden."
    if err == "no_assay_detected":
        return "Kein Assay im PDF erkannt."
    if err == "validation_failed":
        return "PDF-Validierung fehlgeschlagen (Validierungskriterien nicht erfuellt)."
    if err.startswith("excel_write_failed:"):
        return "Excel-Schreibfehler (Datei gesperrt oder Pfad nicht beschreibbar?)."
    if err.startswith("sqlite_write_failed:"):
        return "SQLite-Schreibfehler."
    if "required field not found" in err:
        return f"Pflichtfeld fehlt: {err}"
    if "dedupe basis missing" in err:
        return f"Dedupe-Basis unvollstaendig: {err}"
    if "dedupe fields empty" in err:
        return "Dedupe-Felder leer — Extraktion abgebrochen."
    return f"Unerwarteter Fehler: {err}"


def format_job_result_summary(
    *,
    pdf_path: str,
    job_id: str,
    status: str,
    details: Dict[str, Any],
    outcome: str | None = None,
) -> str:
    outcome = outcome or classify_job_outcome(status, details)
    name = Path(pdf_path).name if pdf_path else "?"
    parts = [f"{outcome} | {status} | {name}"]
    if job_id:
        parts.append(f"job_id={job_id}")
    reason = details.get("reason")
    if reason:
        parts.append(f"reason={reason}")
    msg = humanize_job_error(str(details.get("error") or ""), str(reason) if reason else None)
    if msg:
        parts.append(msg)
    assay_keys = details.get("assay_keys")
    if isinstance(assay_keys, list) and assay_keys:
        parts.append(f"assays={len(assay_keys)}")
    return " | ".join(parts)


def format_assay_overview_rows(writes: Any) -> List[Dict[str, str]]:
    if not isinstance(writes, list):
        return []
    rows: List[Dict[str, str]] = []
    for item in writes:
        if not isinstance(item, dict):
            continue
        missing = item.get("missing_required") or []
        missing_text = ",".join(missing) if isinstance(missing, list) and missing else "-"
        rows.append(
            {
                "assay_key": str(item.get("assay_key", "")),
                "assay_name": str(item.get("assay_name", "")),
                "ruleset_file": str(item.get("ruleset_file", "")),
                "lot_id": str(item.get("lot_id", "")),
                "dedupe_key": str(item.get("dedupe_key", "")),
                "missing_required": missing_text,
                "write_status": _summarize_write_status(item.get("outputs")),
            }
        )
    return rows


def format_assay_data_detail(write_item: Mapping[str, Any]) -> str:
    data = write_item.get("data")
    if not isinstance(data, dict):
        return "(keine Feldwerte)"
    lines: List[str] = []
    meta_lines = _format_dedupe_meta(write_item)
    if meta_lines:
        lines.extend(meta_lines)
        lines.append("")
        lines.append("--- Feldwerte ---")
    lines.extend(f"{key}: {value!r}" for key, value in sorted(data.items(), key=lambda kv: str(kv[0])))
    missing = write_item.get("missing_required")
    if isinstance(missing, list) and missing:
        lines.append("")
        lines.append(f"missing_required: {', '.join(str(k) for k in missing)}")
    optional_missing = _optional_missing_fields(data)
    if optional_missing:
        lines.append(f"optional_missing: {', '.join(optional_missing)}")
    return "\n".join(lines) if lines else "(keine Feldwerte)"


def _format_dedupe_meta(write_item: Mapping[str, Any]) -> List[str]:
    lines: List[str] = []
    for key, label in (
        ("device_id", "device_id"),
        ("dedupe_version", "dedupe_version"),
        ("dedupe_key", "dedupe_key"),
        ("duplicate_status", "duplicate_status"),
        ("duplicate_candidate_id", "duplicate_candidate_id"),
        ("existing_run_id", "existing_run_id"),
        ("pdf_sha256", "pdf_sha256"),
        ("assay_block_hash", "assay_block_hash"),
    ):
        value = write_item.get(key)
        if value:
            lines.append(f"{label}: {value}")
    basis = write_item.get("dedupe_basis")
    if isinstance(basis, dict) and basis:
        lines.append("dedupe_basis:")
        for key, value in sorted(basis.items(), key=lambda kv: str(kv[0])):
            lines.append(f"  {key}: {value}")
    return lines


def format_write_status_lines(outputs: Any) -> List[str]:
    if not isinstance(outputs, list):
        return []
    lines: List[str] = []
    for out in outputs:
        if not isinstance(out, dict):
            continue
        sink = str(out.get("sink", "?"))
        status = str(out.get("status", "?"))
        if sink == "excel":
            if status == "failed":
                lines.append(
                    f"Excel: NICHT geschrieben — {out.get('error', 'Fehler')} "
                    f"(Ziel: {out.get('excel_path', '?')})"
                )
            elif status == "skipped_duplicate_pending":
                lines.append("Excel: nicht geschrieben, Duplikat wartet auf Pruefung")
            elif status == "skipped":
                lines.append(f"Excel: uebersprungen (Dedupe) — {out.get('excel_path', '?')}")
            else:
                lines.append(
                    f"Excel: {status} — {out.get('excel_path', '')} | Sheet: {out.get('sheet', '')}"
                )
        elif sink == "sqlite":
            if status == "failed":
                lines.append(
                    f"SQLite: NICHT geschrieben — {out.get('error', 'Fehler')} "
                    f"(Ziel: {out.get('sqlite_path', '?')})"
                )
            elif status == "duplicate_pending":
                candidate = out.get("duplicate_candidate_id")
                suffix = f" | Candidate: {candidate}" if candidate else ""
                lines.append(f"SQLite: Duplikat zur Pruefung{suffix}")
            elif status == "skipped":
                lines.append(f"SQLite: uebersprungen (Dedupe) — {out.get('sqlite_path', '?')}")
            else:
                lines.append(
                    f"SQLite: {status} — {out.get('sqlite_path', '')} | Tabelle: {out.get('table', '')}"
                )
        else:
            lines.append(f"{sink}: {status}")
    return lines


def format_write_outputs(details: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    writes = details.get("writes") or details.get("partial_writes") or []
    if not isinstance(writes, list):
        return lines

    for w in writes:
        if not isinstance(w, dict):
            continue
        assay_key = w.get("assay_key", "?")
        for line in format_write_status_lines(w.get("outputs")):
            lines.append(f"assay={assay_key} {line}")
    return lines


def format_partial_writes_note(details: Dict[str, Any]) -> str:
    partial = details.get("partial_writes")
    if not isinstance(partial, list) or not partial:
        return ""
    keys = [str(w.get("assay_key", "?")) for w in partial if isinstance(w, dict)]
    return f"Teilweise geschrieben vor Fehler: {', '.join(keys)}"


def format_rules_report(report: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for key in ("missing_files", "key_mismatches", "duplicate_json_key_files", "orphan_rulesets"):
        val = report.get(key, [])
        count = len(val) if isinstance(val, list) else 0
        lines.append(f"{key}: {count}")
    return lines


def format_device_choice(device: Mapping[str, object]) -> Dict[str, str]:
    device_id = _string_or_empty(device.get("device_id")).strip()
    display_name = _string_or_empty(device.get("display_name")).strip() or device_id
    active = device.get("active")
    status = "aktiv" if active is not False else "inaktiv"
    label = f"{display_name} ({device_id})" if device_id and display_name != device_id else device_id
    return {
        "device_id": device_id,
        "display_name": display_name,
        "label": label,
        "status": status,
    }


def format_queue_job_row(job: object | Mapping[str, object]) -> Dict[str, str]:
    return {
        "job_id": _object_field(job, "job_id"),
        "file": Path(_object_field(job, "pdf_path")).name,
        "path": _object_field(job, "pdf_path"),
        "status": _object_field(job, "status"),
        "source": _object_field(job, "source"),
        "worker_id": _object_field(job, "worker_id"),
        "attempts": _object_field(job, "attempts"),
        "last_error": _object_field(job, "last_error"),
        "updated_at": _object_field(job, "updated_at"),
    }


def normalize_file_row_key(path: str | Path) -> str:
    value = str(path or "").strip()
    if not value:
        return ""
    try:
        resolved = Path(value).expanduser().resolve(strict=False)
    except Exception:
        resolved = Path(value).expanduser().absolute()
    return os.path.normcase(str(resolved))


def merge_file_rows_with_queue(
    file_rows: List[Mapping[str, object]],
    queue_rows: List[object | Mapping[str, object]],
    *,
    include_queue_only: bool = False,
) -> List[Dict[str, str]]:
    queue_by_path: Dict[str, Dict[str, str]] = {}
    for queue in queue_rows:
        row = format_queue_job_row(queue)
        key = normalize_file_row_key(row.get("path", ""))
        if key:
            queue_by_path[key] = row

    merged: List[Dict[str, str]] = []
    seen_keys: set[str] = set()
    for item in file_rows:
        row = {str(key): _string_or_empty(value) for key, value in item.items()}
        key = normalize_file_row_key(row.get("path", ""))
        queue = queue_by_path.get(key)
        if queue:
            row["queue_status"] = queue["status"]
            row["job_id"] = queue["job_id"]
            row["last_error"] = queue["last_error"]
        if key:
            seen_keys.add(key)
        merged.append(row)

    if include_queue_only:
        for key, queue in queue_by_path.items():
            if key in seen_keys:
                continue
            merged.append(
                {
                    "file": queue["file"],
                    "path": queue["path"],
                    "source": queue["source"],
                    "queue_status": queue["status"],
                    "job_id": queue["job_id"],
                    "device_id": "",
                    "last_error": queue["last_error"],
                    "action": "queued",
                }
            )
    return merged


def format_extractor_file_row(row: Mapping[str, object]) -> Dict[str, str]:
    queue_status = _string_or_empty(row.get("queue_status"))
    raw_error = _string_or_empty(row.get("last_error"))
    return {
        "file": _string_or_empty(row.get("file")),
        "path": _string_or_empty(row.get("path")),
        "source": _extractor_source_label(row.get("source")),
        "queue_status": _extractor_queue_status_label(queue_status),
        "job_id": _string_or_empty(row.get("job_id")),
        "device_id": _string_or_empty(row.get("device_id")),
        "last_error": format_extractor_error_label(raw_error) if queue_status == "FAILED" else "",
        "action": _extractor_action_label(row.get("action")),
    }


def format_extractor_error_label(error: object) -> str:
    err = _string_or_empty(error).strip()
    if not err:
        return ""
    if err == "no_assay_detected":
        return "Assay nicht erkannt"
    if err == "validation_failed":
        return "Validierung fehlgeschlagen"
    if err == "max_attempts_exceeded":
        return "Maximale Versuche erreicht"
    if err.startswith("worker_submit_error:"):
        return "Technischer Verarbeitungsfehler"
    if err.startswith("excel_write_failed:"):
        return "Excel-Schreibfehler"
    if err.startswith("sqlite_write_failed:"):
        return "SQLite-Schreibfehler"
    if "content_split_failed" in err or "split_failed" in err or "split fehl" in err.lower():
        return "Aufteilung fehlgeschlagen"
    if "ruleset missing assay_name" in err:
        return "Regelset unvollständig"
    return "Technischer Fehler"


def classify_rework_error(queue_error: object, state_error: object) -> tuple[str, str] | None:
    queue_err = _string_or_empty(queue_error).strip()
    state_err = _string_or_empty(state_error).strip()
    root = queue_err
    if queue_err == "max_attempts_exceeded" and state_err:
        root = state_err
    elif state_err and _is_rule_relevant_rework_error(state_err) and not _is_rule_relevant_rework_error(queue_err):
        root = state_err

    if _is_ignored_rework_error(root):
        if _is_rule_relevant_rework_error(queue_err) and queue_err != "max_attempts_exceeded":
            root = queue_err
        else:
            return None
    if not _is_rule_relevant_rework_error(root):
        return None
    return _rework_error_label(root), root


def build_rework_items(
    project_root: str | Path,
    queue_jobs: List[object | Mapping[str, object]],
) -> List[Dict[str, Any]]:
    root = Path(project_root)
    items: List[Dict[str, Any]] = []
    for job in queue_jobs:
        row = format_queue_job_row(job)
        if row["status"] != "FAILED":
            continue
        job_id = row["job_id"]
        if not job_id:
            continue
        state = load_job_state(str(root), job_id)
        state_error = _string_or_empty(state.get("error") if state else "")
        classified = classify_rework_error(row["last_error"], state_error)
        if classified is None:
            continue
        error_label, root_error = classified
        normalized_dump, block_dumps = _collect_rework_artifacts(state)
        state_path = str(root / "jobs" / f"{job_id}.json")
        items.append(
            {
                "item_id": job_id,
                "job_id": job_id,
                "pdf_path": row["path"],
                "file": row["file"],
                "queue_status": row["status"],
                "queue_error": row["last_error"],
                "state_error": state_error,
                "error_label": error_label,
                "context_label": _build_rework_context_label(normalized_dump, block_dumps),
                "state_path": state_path if state is not None else "",
                "normalized_dump": normalized_dump,
                "block_dumps": block_dumps,
                "root_error": root_error,
            }
        )
    return sorted(items, key=lambda item: str(item.get("file", "")).casefold())


def format_rework_item_summary(item: Mapping[str, object]) -> Dict[str, str]:
    return {
        "file": _string_or_empty(item.get("file")),
        "error_label": _string_or_empty(item.get("error_label")),
        "queue_status": _extractor_queue_status_label(item.get("queue_status")),
        "job_id": _string_or_empty(item.get("job_id")),
        "context_label": _string_or_empty(item.get("context_label")) or "-",
    }


def format_rework_item_detail(item: Mapping[str, object]) -> str:
    lines = [
        f"Datei: {_string_or_empty(item.get('file'))}",
        f"Job-ID: {_string_or_empty(item.get('job_id'))}",
        f"PDF-Pfad: {_string_or_empty(item.get('pdf_path'))}",
        f"Status: {_extractor_queue_status_label(item.get('queue_status'))}",
        f"Fehlerklasse: {_string_or_empty(item.get('error_label'))}",
        f"Queue-Fehler: {_string_or_empty(item.get('queue_error')) or '-'}",
        f"State-Fehler: {_string_or_empty(item.get('state_error')) or '-'}",
        f"Root-Cause: {_string_or_empty(item.get('root_error')) or '-'}",
        f"Kontext: {_string_or_empty(item.get('context_label')) or '-'}",
        f"Job-State: {_string_or_empty(item.get('state_path')) or '-'}",
    ]
    normalized_dump = _string_or_empty(item.get("normalized_dump"))
    if normalized_dump:
        status = "vorhanden" if Path(normalized_dump).exists() else "nicht vorhanden"
        lines.append(f"Normalized dump: {normalized_dump} ({status})")
    else:
        lines.append("Normalized dump: -")

    block_dumps = item.get("block_dumps")
    if isinstance(block_dumps, Mapping) and block_dumps:
        lines.append("Block dumps:")
        for key in sorted(block_dumps.keys(), key=lambda value: str(value).casefold()):
            path = _string_or_empty(block_dumps[key])
            status = "vorhanden" if path and Path(path).exists() else "nicht vorhanden"
            lines.append(f"  {key}: {path or '-'} ({status})")
    else:
        lines.append("Block dumps: -")
    return "\n".join(lines)


REWORK_FILTER_LABELS = (
    "Alle",
    "Assay nicht erkannt",
    "Regelset unvollständig",
    "Aufteilung fehlgeschlagen",
)


def filter_rework_items(
    items: List[Mapping[str, object]],
    error_label: str = "Alle",
) -> List[Dict[str, Any]]:
    if error_label in ("", "Alle"):
        return [dict(item) for item in items]
    if error_label not in REWORK_FILTER_LABELS:
        return []
    return [
        dict(item)
        for item in items
        if _string_or_empty(item.get("error_label")) == error_label
    ]


def resolve_rework_context_source(item: Mapping[str, object]) -> tuple[str, str]:
    path = _string_or_empty(item.get("normalized_dump"))
    label = "Normalisierter Text"
    if path and Path(path).exists():
        return label, path

    block_dumps = item.get("block_dumps")
    if isinstance(block_dumps, Mapping):
        for key in sorted(block_dumps.keys(), key=lambda value: str(value).casefold()):
            candidate = _string_or_empty(block_dumps[key])
            if candidate and Path(candidate).exists():
                return f"Assay-Block {key}", candidate
        if block_dumps:
            first = sorted(block_dumps.keys(), key=lambda value: str(value).casefold())[0]
            candidate = _string_or_empty(block_dumps[first])
            if candidate:
                return f"Assay-Block {first}", candidate

    if path:
        return "Normalisierter Text (fehlend)", path
    return "", ""


def format_rework_context_text(
    item: Mapping[str, object],
    content: str | None,
    context_label: str,
    context_path: str,
) -> str:
    header = [
        f"Kontexttyp: {context_label or '-'}",
        f"PDF-Pfad: {_string_or_empty(item.get('pdf_path')) or '-'}",
        f"Dump-Pfad: {context_path or '-'}",
        f"Fehlerklasse: {_string_or_empty(item.get('error_label')) or '-'}",
        f"Queue-Fehler: {_string_or_empty(item.get('queue_error')) or '-'}",
        f"State-Fehler: {_string_or_empty(item.get('state_error')) or '-'}",
        f"Root-Cause: {_string_or_empty(item.get('root_error')) or '-'}",
    ]
    if content is not None:
        body = _format_numbered_lines(content)
    elif not context_path:
        body = "Kontext: nicht vorhanden"
    elif not Path(context_path).exists():
        body = f"Dump-Datei nicht vorhanden:\n{context_path}"
    else:
        body = f"Dump-Datei konnte nicht gelesen werden:\n{context_path}"
    return "\n".join(header) + "\n\n--- Inhalt ---\n" + body


def preferred_rework_dump_path(item: Mapping[str, object]) -> str:
    normalized_dump = _string_or_empty(item.get("normalized_dump"))
    if normalized_dump:
        return normalized_dump
    block_dumps = item.get("block_dumps")
    if isinstance(block_dumps, Mapping) and block_dumps:
        first = sorted(block_dumps.keys(), key=lambda value: str(value).casefold())[0]
        return _string_or_empty(block_dumps[first])
    return ""


def _format_numbered_lines(content: str) -> str:
    lines = content.splitlines()
    if not lines:
        return "0001 |"
    width = max(4, len(str(len(lines))))
    return "\n".join(f"{index:0{width}d} | {line}" for index, line in enumerate(lines, start=1))


def _is_ignored_rework_error(error: str) -> bool:
    err = error.strip().lower()
    if not err:
        return True
    if err == "pdf_not_found":
        return True
    if err.startswith("excel_write_failed:"):
        return True
    if err.startswith("sqlite_write_failed:"):
        return True
    if "duplicate" in err:
        return True
    if err.startswith("worker_submit_error:"):
        return True
    return False


def _is_rule_relevant_rework_error(error: str) -> bool:
    err = error.strip()
    lower = err.lower()
    if err == "no_assay_detected":
        return True
    if "ruleset missing assay_name" in err:
        return True
    if "content_split_failed" in lower or "split_failed" in lower:
        return True
    return False


def _rework_error_label(error: str) -> str:
    err = error.strip()
    lower = err.lower()
    if err == "no_assay_detected":
        return "Assay nicht erkannt"
    if "ruleset missing assay_name" in err:
        return "Regelset unvollständig"
    if "content_split_failed" in lower or "split_failed" in lower:
        return "Aufteilung fehlgeschlagen"
    return err


def _collect_rework_artifacts(state: Mapping[str, object] | None) -> tuple[str, Dict[str, str]]:
    normalized_dump = ""
    block_dumps: Dict[str, str] = {}
    if not state:
        return normalized_dump, block_dumps
    steps = state.get("steps")
    if not isinstance(steps, list):
        return normalized_dump, block_dumps
    for step in steps:
        if not isinstance(step, dict):
            continue
        dump = step.get("normalized_dump")
        if dump:
            normalized_dump = _string_or_empty(dump)
        dumps = step.get("block_dumps")
        if isinstance(dumps, Mapping):
            for key, value in dumps.items():
                if value:
                    block_dumps[str(key)] = _string_or_empty(value)
    return normalized_dump, dict(sorted(block_dumps.items(), key=lambda item: item[0].casefold()))


def _build_rework_context_label(normalized_dump: str, block_dumps: Mapping[str, str]) -> str:
    if normalized_dump and Path(normalized_dump).exists():
        return "Normalisierter Text"
    for key in sorted(block_dumps.keys(), key=lambda value: str(value).casefold()):
        path = block_dumps[key]
        if path and Path(path).exists():
            return f"Assay-Block {key}"
    if normalized_dump:
        return "Normalisierter Text (fehlend)"
    if block_dumps:
        first = sorted(block_dumps.keys(), key=lambda value: str(value).casefold())[0]
        return f"Assay-Block {first} (fehlend)"
    return "-"


def format_enqueue_result(job: object | Mapping[str, object]) -> str:
    row = format_queue_job_row(job)
    parts = [f"Queue: {row['status'] or '-'}", row["file"] or "?"]
    if row["job_id"]:
        parts.append(f"job_id={row['job_id']}")
    if row["source"]:
        parts.append(f"source={row['source']}")
    if row["last_error"]:
        parts.append(row["last_error"])
    return " | ".join(parts)


def format_submit_row_update(
    result: object | Mapping[str, object],
    device_id: str | None,
) -> Dict[str, str]:
    if isinstance(result, Mapping):
        status = _string_or_empty(result.get("status"))
        job_id = _string_or_empty(result.get("job_id"))
        details = result.get("details")
    else:
        status = _string_or_empty(getattr(result, "status", ""))
        job_id = _string_or_empty(getattr(result, "job_id", ""))
        details = getattr(result, "details", None)

    detail_map = details if isinstance(details, dict) else {}
    reason = detail_map.get("reason")
    error = detail_map.get("error")
    return {
        "job_id": job_id,
        "device_id": _string_or_empty(device_id),
        "action": classify_job_outcome(status, detail_map),
        "last_error": humanize_job_error(
            _string_or_empty(error),
            _string_or_empty(reason) if reason else None,
        ),
    }


def format_runtime_options_summary(options: Mapping[str, object]) -> List[str]:
    lines = [
        f"Output: {_string_or_empty(options.get('output_mode')) or '-'}",
        f"SQLite: {_string_or_empty(options.get('sqlite_path')) or '-'}",
        f"Watch: {_string_or_empty(options.get('watch_dir')) or '-'}",
        f"Geraet: {_string_or_empty(options.get('device_id')) or '-'}",
        f"Watch-Modus: {_string_or_empty(options.get('watch_mode')) or '-'}",
    ]
    return lines


def format_watch_file_row(path: str | Path, *, source: str = "watch") -> Dict[str, str]:
    p = Path(path)
    try:
        display_path = str(p.expanduser().resolve(strict=False))
    except Exception:
        display_path = str(p)
    return {
        "file": p.name,
        "path": display_path,
        "source": source,
        "queue_status": "",
        "job_id": "",
        "device_id": "",
        "last_error": "",
        "action": "bereit",
    }


def format_validation_status(report: Mapping[str, object]) -> Dict[str, str]:
    counts = {
        key: len(value) if isinstance(value, list) else 0
        for key, value in report.items()
    }
    total = sum(counts.values())
    return {
        "status": "OK" if total == 0 else "FEHLER",
        "summary": "Rules OK" if total == 0 else f"Rules mit Befunden: {total}",
        "missing_files": str(counts.get("missing_files", 0)),
        "key_mismatches": str(counts.get("key_mismatches", 0)),
        "duplicate_json_key_files": str(counts.get("duplicate_json_key_files", 0)),
        "content_errors": str(counts.get("content_errors", 0)),
        "orphan_rulesets": str(counts.get("orphan_rulesets", 0)),
    }


def format_duplicate_candidate_summary(row: Mapping[str, Any]) -> Dict[str, str]:
    return {
        "candidate_id": _string_or_empty(row.get("candidate_id")),
        "status": _duplicate_status_label(row.get("status")),
        "assay_key": _string_or_empty(row.get("assay_key")),
        "device_id": _string_or_empty(row.get("device_id")),
        "detected_at": _string_or_empty(row.get("detected_at")),
        "existing_run_id": _string_or_empty(row.get("existing_run_id")),
        "dedupe_key": _string_or_empty(row.get("dedupe_key")),
    }


def format_duplicate_candidate_detail(detail: Mapping[str, Any] | None) -> str:
    if not isinstance(detail, Mapping):
        return "(kein Kandidat)"
    candidate = detail.get("candidate")
    existing = detail.get("existing")
    if not isinstance(candidate, Mapping):
        return "(kein Kandidat)"

    lines: List[str] = ["--- Kandidat ---"]
    lines.extend(_duplicate_meta_lines(candidate, candidate=True))
    lines.append("")
    lines.append("--- Bestehender Run ---")
    if isinstance(existing, Mapping):
        lines.extend(_duplicate_meta_lines(existing, candidate=False))
    else:
        lines.append("(nicht gefunden)")
    return "\n".join(lines)


def format_duplicate_field_comparison(detail: Mapping[str, Any] | None) -> List[Dict[str, str]]:
    if not isinstance(detail, Mapping):
        return []
    comparison = detail.get("field_comparison")
    if not isinstance(comparison, list):
        return []
    rows: List[Dict[str, str]] = []
    for item in comparison:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "field": _string_or_empty(item.get("field")),
                "existing": _format_duplicate_value(item.get("existing")),
                "candidate": _format_duplicate_value(item.get("candidate")),
                "same": "Ja" if bool(item.get("same")) else "Nein",
            }
        )
    return rows


def _summarize_write_status(outputs: Any) -> str:
    lines = format_write_status_lines(outputs)
    if not lines:
        return "-"
    return "; ".join(line.split(" — ", 1)[0] for line in lines)


def _optional_missing_fields(data: Dict[str, Any]) -> List[str]:
    return sorted(key for key, value in data.items() if value is None or (isinstance(value, str) and not value.strip()))


def _duplicate_status_label(status: object) -> str:
    value = str(status or "")
    if value == "pending":
        return "wartet auf Pruefung"
    if value == "deleted":
        return "verworfen"
    return value


def _extractor_source_label(source: object) -> str:
    value = _string_or_empty(source)
    return {
        "test-app-auto-watch": "Automatisch gefunden",
        "test-app-watch": "Aus Suchordner",
        "watch": "Aus Suchordner",
        "test-app-manual": "Manuell hinzugefügt",
        "manual": "Manuell hinzugefügt",
    }.get(value, value)


def _extractor_queue_status_label(status: object) -> str:
    value = _string_or_empty(status)
    return {
        "PENDING": "Wartet",
        "PROCESSING": "In Arbeit",
        "DONE": "Fertig",
        "FAILED": "Fehler",
    }.get(value, value)


def _extractor_action_label(action: object) -> str:
    value = _string_or_empty(action)
    return {
        "queued": "Wartet auf Extraktion",
        "bereit": "Bereit",
    }.get(value, value)


def _duplicate_meta_lines(data: Mapping[str, Any], *, candidate: bool) -> List[str]:
    keys = (
        ("candidate_id", "candidate_id"),
        ("status", "status"),
        ("existing_run_id", "existing_run_id"),
        ("assay_key", "assay_key"),
        ("device_id", "device_id"),
        ("dedupe_version", "dedupe_version"),
        ("dedupe_key", "dedupe_key"),
        ("detected_at", "detected_at"),
        ("decision_at", "decision_at"),
        ("decision_by", "decision_by"),
        ("decision_note", "decision_note"),
        ("pdf_sha256", "pdf_sha256"),
        ("assay_block_hash", "assay_block_hash"),
    )
    if not candidate:
        keys = (
            ("run_id", "run_id"),
            ("job_id", "job_id"),
            ("pdf_path", "pdf_path"),
            ("assay_key", "assay_key"),
            ("device_id", "device_id"),
            ("dedupe_version", "dedupe_version"),
            ("dedupe_key", "dedupe_key"),
            ("created_at", "created_at"),
        )
    lines: List[str] = []
    for key, label in keys:
        value = data.get(key)
        if value:
            if key == "status":
                value = _duplicate_status_label(value)
            lines.append(f"{label}: {value}")
    basis = data.get("dedupe_basis")
    if isinstance(basis, Mapping) and basis:
        lines.append("dedupe_basis:")
        for key, value in sorted(basis.items(), key=lambda kv: str(kv[0])):
            lines.append(f"  {key}: {value}")
    return lines


def _format_duplicate_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _string_or_empty(value: object) -> str:
    return "" if value is None else str(value)


def _object_field(obj: object | Mapping[str, object], key: str) -> str:
    if isinstance(obj, Mapping):
        return _string_or_empty(obj.get(key))
    return _string_or_empty(getattr(obj, key, None))
