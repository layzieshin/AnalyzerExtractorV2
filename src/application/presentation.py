from __future__ import annotations

import math
from pathlib import Path

_PROC_REGISTERED = "REGISTERED"
_PROC_PENDING = "PENDING"
_PROC_PROCESSING = "PROCESSING"
_PROC_DONE = "DONE"
_PROC_FAILED = "FAILED"

_ARCH_NOT_REQUIRED = "NOT_REQUIRED"
_ARCH_PENDING = "PENDING"
_ARCH_MOVING = "MOVING"
_ARCH_ARCHIVED = "ARCHIVED"
_ARCH_FAILED = "ARCHIVE_FAILED"
_ARCH_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"

_ARCHIVE_ACTIVE = frozenset({_ARCH_PENDING, _ARCH_MOVING})


_QUEUE_TERMINAL = frozenset({_PROC_DONE, _PROC_FAILED})
_QUEUE_ACTIVE = frozenset({_PROC_PENDING, _PROC_PROCESSING})


def derive_effective_processing_status(processing_status: str, queue_status: str) -> str:
    queue = str(queue_status or "").strip().upper()
    if queue in _QUEUE_ACTIVE or queue in _QUEUE_TERMINAL:
        return queue
    return str(processing_status or "").strip().upper()


def map_ingestion_display_status(
    processing_status: str,
    archive_status: str,
    *,
    queue_status: str = "",
) -> str:
    proc = derive_effective_processing_status(processing_status, queue_status)
    arch = str(archive_status or "").strip().upper()

    if arch == _ARCH_RECOVERY_REQUIRED:
        return "Klaerung erforderlich"
    if arch == _ARCH_FAILED:
        return "Verarbeitet - Archivierung fehlgeschlagen"
    if proc == _PROC_FAILED:
        return "Verarbeitung fehlgeschlagen"
    if proc in {_PROC_REGISTERED, _PROC_PENDING}:
        return "Wartet"
    if proc == _PROC_PROCESSING:
        return "Wird verarbeitet"
    if proc == _PROC_DONE:
        if arch in _ARCHIVE_ACTIVE:
            return "Verarbeitet - wird archiviert"
        if arch in {_ARCH_ARCHIVED, _ARCH_NOT_REQUIRED}:
            return "Fertig"
        return "Fertig"
    return proc or "Unbekannt"


def friendly_processing_message(technical_detail: str) -> str:
    detail = str(technical_detail or "").strip()
    if not detail:
        return ""
    if detail == "pdf_not_found":
        return "Die PDF-Datei wurde nicht gefunden."
    if detail == "no_assay_detected":
        return "Im PDF wurde kein passender Assay erkannt."
    if detail == "validation_failed":
        return "Die PDF-Validierung ist fehlgeschlagen."
    if detail == "source_changed_since_ingest":
        return "Die Quelldatei hat sich seit dem Import geaendert."
    if detail == "watch_backup_path_missing":
        return "Der Archiv-Ordner ist nicht konfiguriert."
    if detail.startswith("excel_write_failed_after_save:"):
        return "Ergebnis gespeichert – Excel-Ausgabe fehlgeschlagen"
    if detail.startswith("excel_write_failed_after_validation:"):
        return "Validierung gespeichert – Excel-Ausgabe fehlgeschlagen"
    if detail == "excel_export_reconcile_required":
        return "Validierung gespeichert – Excel-Ausgabe wartet auf Wiederholung"
    if detail.startswith("excel_write_failed_after_validation:"):
        return "Validierung gespeichert – Excel-Ausgabe fehlgeschlagen"
    if detail.startswith("excel_write_failed:"):
        return "Excel-Ausgabe fehlgeschlagen"
    if detail.startswith("sqlite_write_failed:"):
        return "Die Ergebnisdatenbank konnte nicht geschrieben werden."
    if detail.startswith("configured_fields_empty:"):
        return "Felder nicht extrahiert"
    return "Bei der Verarbeitung ist ein technisches Problem aufgetreten."


def classify_rework_diagnosis(queue_error: str, state_error: str) -> tuple[str, str] | None:
    queue_err = str(queue_error or "").strip()
    state_err = str(state_error or "").strip()
    root = queue_err
    if queue_err == "max_attempts_exceeded" and state_err:
        root = state_err
    elif state_err and (
        _is_rule_relevant_rework_error(state_err)
        or state_err.startswith("excel_write_failed_after_validation:")
        or state_err == "excel_export_reconcile_required"
    ) and not _is_rule_relevant_rework_error(queue_err):
        root = state_err

    if (
        root.startswith("excel_write_failed_after_save:")
        or root.startswith("excel_write_failed_after_validation:")
        or root.startswith("excel_write_failed:")
    ):
        return "Excel-Ausgabe", root
    if root == "excel_export_reconcile_required":
        return "Excel-Ausgabe", root
    if _is_ignored_rework_error(root):
        if _is_rule_relevant_rework_error(queue_err) and queue_err != "max_attempts_exceeded":
            root = queue_err
        else:
            return None
    if not _is_rule_relevant_rework_error(root):
        return None
    return _rework_error_label(root), root


def build_rework_context_label(normalized_dump_path: str, block_dump_paths: tuple[tuple[str, str], ...]) -> str:
    if normalized_dump_path:
        dump_path = Path(normalized_dump_path)
        if dump_path.is_file():
            text, _ = _read_bounded_preview(dump_path)
            if text:
                return "Normalisierter Text"
    for assay_key, dump_path in sorted(block_dump_paths, key=lambda item: item[0].casefold()):
        if dump_path and Path(dump_path).is_file():
            return f"Assay-Block {assay_key}"
    if normalized_dump_path:
        return "Normalisierter Text (fehlend)"
    if block_dump_paths:
        first_key = sorted(block_dump_paths, key=lambda item: item[0].casefold())[0][0]
        return f"Assay-Block {first_key} (fehlend)"
    return "-"


def normalize_scan_interval_s(raw: float) -> float:
    value = float(raw)
    if not math.isfinite(value):
        return 3.0
    if value == 0.0:
        return 3.0
    if value < 0.0:
        return 0.5
    return max(0.5, value)


def normalize_stable_window_s(raw: float) -> float:
    value = float(raw)
    if not math.isfinite(value):
        return 1.0
    if value < 0.0:
        return 0.0
    return value


def _read_bounded_preview(path: Path, *, max_chars: int = 1) -> tuple[str, bool]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(max_chars + 1)
    except OSError:
        return "", False
    return text[:max_chars], len(text) > max_chars


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
    if err.startswith("configured_fields_empty:"):
        return True
    return False


def _rework_error_label(error: str) -> str:
    err = error.strip()
    lower = err.lower()
    if err == "no_assay_detected":
        return "Assay nicht erkannt"
    if "ruleset missing assay_name" in err:
        return "Regelset unvollstaendig"
    if "content_split_failed" in lower or "split_failed" in lower:
        return "Aufteilung fehlgeschlagen"
    if err.startswith("configured_fields_empty:"):
        return "Felder nicht extrahiert"
    return err
