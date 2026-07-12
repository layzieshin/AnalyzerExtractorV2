from __future__ import annotations

import json
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


def _summarize_write_status(outputs: Any) -> str:
    lines = format_write_status_lines(outputs)
    if not lines:
        return "-"
    return "; ".join(line.split(" — ", 1)[0] for line in lines)


def _optional_missing_fields(data: Dict[str, Any]) -> List[str]:
    return sorted(key for key, value in data.items() if value is None or (isinstance(value, str) and not value.strip()))
