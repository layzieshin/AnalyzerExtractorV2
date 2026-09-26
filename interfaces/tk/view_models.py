from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator

from src.application.api import (
    AssayCandidateItem,
    DuplicateCandidateDetail,
    IngestionInstanceItem,
    ProcessingEnqueueOutcome,
    ProcessingOutcome,
    ReportAssayGroup,
    ReportDetail,
    ReportRunOccurrence,
    ReportSummaryItem,
    RulesetInventoryItem,
    WatchCycleSummary,
    friendly_processing_message,
)

_EXCEL_USER_MESSAGES = frozenset(
    {
        "Ergebnis gespeichert – Excel-Ausgabe fehlgeschlagen",
        "Excel-Ausgabe fehlgeschlagen",
    }
)

DESKTOP_VIEW_KEYS: tuple[str, ...] = (
    "dashboard",
    "results",
    "validation",
    "rules",
    "settings",
    "diagnostics",
)

NAV_LABELS: dict[str, str] = {
    "dashboard": "Auswertung",
    "results": "Ergebnisse",
    "validation": "Validierung",
    "rules": "Regelwerke",
    "settings": "Einstellungen",
    "diagnostics": "Diagnose",
}

PRIMARY_NAV_KEYS: tuple[str, ...] = ("dashboard", "results", "validation", "rules")
SECONDARY_NAV_KEYS: tuple[str, ...] = ("settings", "diagnostics")

DASHBOARD_RECENT_LIMIT = 10
DASHBOARD_REPORT_JOIN_LIMIT = 250


@dataclass(frozen=True)
class DashboardRecentRow:
    row_id: str
    status: str
    file_name: str
    summary: str
    time_text: str
    source: str
    report_id: str | None = None


@dataclass(frozen=True)
class BatchFileStatus:
    file_name: str
    pdf_path: str
    status_label: str
    detail: str = ""


def format_timestamp(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        if len(text) >= 16 and text[4] == "-":
            return f"{text[:10]} {text[11:16]}"
        return text


def format_source_kind(source_kind: str) -> str:
    mapping = {
        "manual": "Manuell",
        "watch_folder": "Auto-Import",
    }
    return mapping.get(str(source_kind or "").strip().lower(), source_kind or "-")


def status_badge_kind(display_status: str) -> str:
    text = str(display_status or "").casefold()
    if any(
        token in text
        for token in ("fehlgeschlagen", "fehler", "klärung", "klaerung", "klärfall", "prüfung", "pruefung")
    ):
        return "error"
    if "teilweise" in text:
        return "warning"
    if "unvalidiert" in text:
        return "neutral"
    if "validiert" in text or "fertig" in text:
        return "success"
    if any(token in text for token in ("wartet", "wird verarbeitet", "archiviert")):
        return "warning"
    return "neutral"


def rules_inventory_item_id(item: RulesetInventoryItem, index: int) -> str:
    kind = str(item.kind or "unknown").strip().lower() or "unknown"
    source = str(item.path or item.ruleset_file or index).strip()
    assay = str(item.assay_key or "unknown").strip()
    return f"{kind}::{assay}::{index}::{source}"


def report_list_status(item: ReportSummaryItem) -> str:
    return item.report_status or item.display_status or "-"


def report_summary_row_values(item: ReportSummaryItem) -> tuple[str, str, str, str, str]:
    assay_text = ", ".join(item.assay_keys) if item.assay_keys else str(item.assay_count or 0)
    device_text = ", ".join(item.device_ids) if item.device_ids else "-"
    return (
        item.file_name or "-",
        report_list_status(item),
        assay_text,
        format_timestamp(item.latest_created_at),
        device_text,
    )


def build_dashboard_recent_rows(
    ingestions: tuple[IngestionInstanceItem, ...] | list[IngestionInstanceItem],
    reports: tuple[ReportSummaryItem, ...] | list[ReportSummaryItem],
    *,
    limit: int = DASHBOARD_RECENT_LIMIT,
) -> tuple[DashboardRecentRow, ...]:
    report_by_job = {item.job_id: item for item in reports if item.job_id}
    rows: list[DashboardRecentRow] = []
    visible_limit = max(5, min(limit, DASHBOARD_RECENT_LIMIT))
    for item in ingestions[:visible_limit]:
        report = report_by_job.get(item.job_id)
        status = item.display_status or "-"
        if item.friendly_message in _EXCEL_USER_MESSAGES:
            summary = item.friendly_message
            report_id = report.report_id if report is not None else None
            row_id = item.ingestion_id or item.job_id or item.file_name
            rows.append(
                DashboardRecentRow(
                    row_id=row_id,
                    status=status,
                    file_name=item.file_name or "-",
                    summary=summary,
                    time_text=format_timestamp(item.updated_at or item.created_at),
                    source=format_source_kind(item.source_kind),
                    report_id=report_id,
                )
            )
            continue
        if report is not None:
            summary_parts: list[str] = []
            if report.assay_count:
                summary_parts.append(f"{report.assay_count} Assay(s)")
            if report.run_count:
                summary_parts.append(f"{report.run_count} Ergebnis(se)")
            elif report.assay_count:
                summary_parts.append("0 Ergebnis(se)")
            if report.device_ids:
                summary_parts.append(f"Gerät {', '.join(report.device_ids)}")
            summary = " | ".join(summary_parts) if summary_parts else (item.friendly_message or "-")
            report_id = report.report_id
        else:
            summary = item.friendly_message or (
                "Verarbeitet" if item.display_status == "Fertig" else str(item.display_status or "-")
            )
            report_id = None
        row_id = item.ingestion_id or item.job_id or item.file_name
        rows.append(
            DashboardRecentRow(
                row_id=row_id,
                status=status,
                file_name=item.file_name or "-",
                summary=summary,
                time_text=format_timestamp(item.updated_at or item.created_at),
                source=format_source_kind(item.source_kind),
                report_id=report_id,
            )
        )
    return tuple(rows)


GENERIC_ACTION_FAILED_MESSAGE = "Die Aktion ist fehlgeschlagen."

_USER_ERROR_MESSAGES: dict[str, str] = {
    "watch_input_path_required": "Bitte einen Eingabeordner für den Auto-Import angeben.",
    "watch_backup_path_required": "Bitte einen Archivordner für den Auto-Import angeben.",
    "watch_input_backup_same_path": "Eingabe- und Archivordner dürfen nicht identisch sein.",
    "watch_backup_under_input": "Der Archivordner darf nicht im Eingabeordner liegen.",
    "watch_input_under_backup": "Der Eingabeordner darf nicht im Archivordner liegen.",
    "watch_backup_path_missing": "Für die Archivierung ist kein Archivordner konfiguriert.",
    "sqlite_path_required": "Bitte einen Pfad für die SQLite-Datenbank angeben.",
    "watch_disabled": "Der Auto-Import ist deaktiviert.",
    "invalid_device_id_type": "Die Geräteauswahl ist ungültig.",
    "conflicting_watch_dir_and_watch_input_path": "Eingabeordner und Watch-Verzeichnis widersprechen sich.",
    "path_empty": "Der Pfad ist leer.",
    "desktop_settings_save_failed": "Die Einstellungen konnten nicht gespeichert werden.",
    "watch_input_not_directory": "Der Eingabeordner ist kein Verzeichnis.",
    "watch_backup_path_is_file": "Der Archivpfad ist eine Datei und kein Ordner.",
    "invalid_output_mode": "Ungültiger Ausgabemodus.",
    "path_not_found": "Der Pfad wurde nicht gefunden.",
    "path_open_failed": "Der Pfad konnte nicht geöffnet werden.",
    "operator_initials_required": "Bitte Initialen für die Validierung angeben.",
    "invalid_operator_initials_type": "Die Operator-Initialen sind ungültig.",
    "validation_already_exists": "Für diese Messung gibt es bereits eine Validierung. Nutze die Korrektur.",
    "validation_missing": "Es gibt noch keine Validierung, die korrigiert werden kann.",
    "validation_ambiguous": "Die Validierungshistorie ist nicht eindeutig. Es wurde nichts gespeichert.",
    "run_not_in_report": "Die Messung gehört nicht zu diesem Bericht.",
    "run_not_found": "Die Messung wurde nicht gefunden.",
    "validation_store_missing": "Die Ergebnisdatenbank wurde nicht gefunden.",
    "validation_store_busy": "Die Ergebnisdatenbank wird gerade verwendet. Bitte erneut versuchen.",
    "validation_store_unreadable": "Die Ergebnisdatenbank konnte nicht gelesen werden.",
    "validation_comment_invalid": "Der Validierungskommentar ist ungültig.",
}


def format_user_error_message(error: BaseException | str) -> str:
    text = str(error).strip() if isinstance(error, BaseException) else str(error or "").strip()
    if not text:
        return GENERIC_ACTION_FAILED_MESSAGE
    code, _separator, _remainder = text.partition(":")
    code = code.strip()
    if code in _USER_ERROR_MESSAGES:
        return _USER_ERROR_MESSAGES[code]
    return GENERIC_ACTION_FAILED_MESSAGE


def user_error_dialog_parts(error: BaseException | str) -> tuple[str, str]:
    message = format_user_error_message(error)
    raw = str(error).strip() if isinstance(error, BaseException) else str(error or "").strip()
    details = raw if raw and message != raw else ""
    return message, details


def build_batch_file_statuses(
    enqueue_outcomes: tuple[ProcessingEnqueueOutcome, ...] | list[ProcessingEnqueueOutcome],
    processing_outcomes: tuple[ProcessingOutcome, ...] | list[ProcessingOutcome],
) -> tuple[BatchFileStatus, ...]:
    processing_by_path = {outcome.pdf_path: outcome for outcome in processing_outcomes}
    processing_by_name = {outcome.file_name: outcome for outcome in processing_outcomes if outcome.file_name}
    statuses: list[BatchFileStatus] = []

    def lookup_processing(enqueue: ProcessingEnqueueOutcome) -> ProcessingOutcome | None:
        label = enqueue.file_name or enqueue.pdf_path
        return processing_by_path.get(enqueue.pdf_path) or processing_by_name.get(label)

    def status_from_processing(enqueue: ProcessingEnqueueOutcome, processed: ProcessingOutcome) -> BatchFileStatus:
        label = enqueue.file_name or enqueue.pdf_path
        if processed.queue_status == "DONE" and processed.submit_status in {"", "ok", "success", "DONE"}:
            return BatchFileStatus(
                file_name=label,
                pdf_path=enqueue.pdf_path,
                status_label="Erfolgreich",
                detail=processed.message or "Verarbeitung abgeschlossen",
            )
        if processed.queue_status == "FAILED" or processed.submit_status == "FAILED":
            detail = processed.message or "Verarbeitung fehlgeschlagen"
            friendly = friendly_processing_message(processed.message)
            if friendly in _EXCEL_USER_MESSAGES:
                detail = friendly
            return BatchFileStatus(
                file_name=label,
                pdf_path=enqueue.pdf_path,
                status_label="Fehler",
                detail=detail,
            )
        return BatchFileStatus(
            file_name=label,
            pdf_path=enqueue.pdf_path,
            status_label=processed.queue_status or processed.submit_status or "Verarbeitet",
            detail=processed.message or "",
        )

    for enqueue in enqueue_outcomes:
        label = enqueue.file_name or enqueue.pdf_path
        if enqueue.outcome == "error":
            statuses.append(
                BatchFileStatus(
                    file_name=label,
                    pdf_path=enqueue.pdf_path,
                    status_label="Fehler",
                    detail=enqueue.message or "Import fehlgeschlagen",
                )
            )
            continue
        if enqueue.outcome == "skipped":
            statuses.append(
                BatchFileStatus(
                    file_name=label,
                    pdf_path=enqueue.pdf_path,
                    status_label="Übersprungen",
                    detail=enqueue.message or "Bereits verarbeitet",
                )
            )
            continue
        processed = lookup_processing(enqueue)
        if processed is not None:
            statuses.append(status_from_processing(enqueue, processed))
            continue
        if enqueue.outcome == "registered":
            statuses.append(
                BatchFileStatus(
                    file_name=label,
                    pdf_path=enqueue.pdf_path,
                    status_label="Registriert",
                    detail=enqueue.message or "Import registriert",
                )
            )
            continue
        statuses.append(
            BatchFileStatus(
                file_name=label,
                pdf_path=enqueue.pdf_path,
                status_label="Eingereiht",
                detail=enqueue.message or "Wartet auf Verarbeitung",
            )
        )
    return tuple(statuses)


def format_batch_status_message(statuses: tuple[BatchFileStatus, ...]) -> str:
    if not statuses:
        return ""
    return " | ".join(
        f"{row.file_name}: {row.status_label}" + (f" ({row.detail})" if row.detail else "")
        for row in statuses
    )


def _watch_registered_count(summary: WatchCycleSummary) -> int:
    return sum(
        1
        for item in summary.outcomes
        if str(item.outcome or "").strip().lower() in {"registered", "queued"}
    )


def format_watch_cycle_summary(summary: WatchCycleSummary | None, *, error: str = "") -> str:
    if error:
        return f"Auto-Import: Fehler – {format_user_error_message(error)}"
    if summary is None:
        return "Auto-Import: noch kein Lauf in dieser Sitzung."
    if not summary.enabled:
        reason = summary.disabled_reason or "watch_disabled"
        return f"Auto-Import: {format_user_error_message(reason)}"
    registered = _watch_registered_count(summary)
    errors = sum(1 for item in summary.outcomes if item.outcome == "error")
    parts = [
        f"Letzter Lauf: {summary.scanned_count} gescannt",
        f"{registered} registriert",
    ]
    if summary.recovery_count:
        parts.append(f"{summary.recovery_count} Recovery")
    if summary.busy:
        parts.append("Ordner beschäftigt")
    if errors:
        parts.append(f"{errors} Fehler")
    return "Auto-Import: " + ", ".join(parts)


def iter_report_occurrences(
    detail: ReportDetail,
) -> Iterator[tuple[str, ReportAssayGroup, ReportRunOccurrence]]:
    global_index = 0
    for group_index, group in enumerate(detail.assay_groups):
        for occ_index, occurrence in enumerate(group.occurrences):
            yield (
                occurrence_id(group, occurrence, global_index=global_index, group_index=group_index, occ_index=occ_index),
                group,
                occurrence,
            )
            global_index += 1


def occurrence_id(
    group: ReportAssayGroup,
    occurrence: ReportRunOccurrence,
    *,
    global_index: int,
    group_index: int,
    occ_index: int,
) -> str:
    assay = group.assay_key or group.assay_display_label or f"group{group_index}"
    if occurrence.run_id is not None:
        run_part = str(occurrence.run_id)
    else:
        run_part = f"g{global_index}"
    dedupe = str(occurrence.dedupe_key or "").strip() or f"occ{occ_index}"
    lot = str(occurrence.lot_id or occurrence.charge or "").strip() or f"lot{occ_index}"
    return f"{assay}::{run_part}::{dedupe}::{lot}::{global_index}"


def occurrence_list_rows(detail: ReportDetail) -> list[tuple[str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str]] = []
    for occ_id, group, occurrence in iter_report_occurrences(detail):
        rows.append(
            (
                occ_id,
                group.assay_key or group.assay_display_label or "-",
                occurrence.charge or occurrence.lot_id or "-",
                occurrence.device_id or "-",
                format_timestamp(occurrence.created_at),
            )
        )
    return rows


def occurrence_field_rows(detail: ReportDetail, occurrence_id_value: str) -> tuple[tuple[str, str], ...]:
    for occ_id, _group, occurrence in iter_report_occurrences(detail):
        if occ_id != occurrence_id_value:
            continue
        return tuple((field.field_key, field.value) for field in occurrence.fields)
    return ()


def report_detail_header_lines(detail: ReportDetail) -> tuple[str, str, str, str]:
    device_text = ", ".join(detail.device_ids) if detail.device_ids else "-"
    return (
        detail.file_name or "-",
        format_timestamp(detail.latest_created_at),
        device_text,
        detail.report_status or detail.display_status or "-",
    )


def validation_status_line(occurrence: ReportRunOccurrence | None) -> str:
    if occurrence is None:
        return "Keine Messung ausgewählt."
    if occurrence.validation_ambiguous:
        return "Validierung nicht eindeutig. Es wird nichts geändert."
    current = occurrence.current_validation
    if current is None:
        return "Unvalidiert"
    comment = f" — {current.comment}" if current.comment else ""
    return f"Validiert von {current.operator_initials} am {format_timestamp(current.validated_at_utc)}{comment}"


def validation_history_rows(occurrence: ReportRunOccurrence | None) -> list[tuple[str, str, str, str]]:
    if occurrence is None:
        return []
    current_id = occurrence.current_validation.validation_id if occurrence.current_validation else None
    rows: list[tuple[str, str, str, str]] = []
    for record in occurrence.validation_history:
        if occurrence.validation_ambiguous:
            state = "Unklar"
        elif current_id is not None and record.validation_id == current_id:
            state = "Aktuell"
        else:
            state = "Ersetzt"
        rows.append(
            (
                state,
                record.operator_initials or "-",
                format_timestamp(record.validated_at_utc),
                record.comment or "-",
            )
        )
    return rows


def format_assay_candidate_lines(candidates: tuple[AssayCandidateItem, ...] | list[AssayCandidateItem]) -> list[str]:
    lines: list[str] = []
    for candidate in candidates:
        lines.append(
            " | ".join(
                part
                for part in (
                    f"Assay: {candidate.assay_key}",
                    f"Name: {candidate.assay_name_hint}",
                    f"Status: {candidate.known_status}",
                    f"Konfidenz: {candidate.confidence}",
                    f"Grund: {candidate.reason}",
                    f"Zeile {candidate.line_no}: {candidate.line_text}",
                    f"Testdatei: {candidate.test_file}",
                )
                if part
            )
        )
    return lines


def format_duplicate_detail_lines(detail: DuplicateCandidateDetail) -> str:
    candidate = detail.candidate
    lines = [
        f"Kandidat-ID: {candidate.candidate_id}",
        f"Assay: {candidate.assay_key}",
        f"Status: {candidate.status}",
        f"Bestehender Lauf-ID: {candidate.existing_run_id}",
        f"Dedupe-Key: {candidate.dedupe_key}",
        f"Dedupe-Version: {candidate.dedupe_version}",
        f"PDF-SHA256: {candidate.pdf_sha256}",
        f"Assay-Block-Hash: {candidate.assay_block_hash}",
        f"Gerät: {candidate.device_id}",
        f"Erkannt: {candidate.detected_at}",
        f"Entscheidung: {candidate.decision_at} von {candidate.decision_by}",
        f"Entscheidungsnotiz: {candidate.decision_note}",
        f"Dedupe-Basis: {candidate.dedupe_basis}",
        f"Meta: {candidate.candidate_meta}",
    ]
    if detail.existing is not None:
        existing = detail.existing
        lines.extend(
            [
                "",
                "Bestehender Lauf:",
                f"  Run-ID: {existing.run_id}",
                f"  Job: {existing.job_id}",
                f"  PDF: {existing.pdf_path}",
                f"  Assay: {existing.assay_key}",
                f"  Lot: {existing.lot_id}",
                f"  Charge: {existing.charge}",
                f"  Dedupe-Key: {existing.dedupe_key}",
                f"  Gerät: {existing.device_id}",
                f"  Dedupe-Version: {existing.dedupe_version}",
                f"  Erstellt: {existing.created_at}",
                f"  Dedupe-Basis: {existing.dedupe_basis}",
            ]
        )
    if detail.field_comparison:
        lines.append("")
        lines.append("Feldvergleich:")
        for field in detail.field_comparison:
            marker = "*" if field.changed else "="
            lines.append(f"{marker} {field.field_key}: {field.existing_value} -> {field.candidate_value}")
    return "\n".join(lines)


def watch_enabled_label(enabled: bool) -> str:
    return "Aktiv" if enabled else "Inaktiv"


def integrity_summary(report: dict[str, object]) -> tuple[int, int]:
    total = len(report)
    failed = sum(1 for value in report.values() if value)
    return total, failed
