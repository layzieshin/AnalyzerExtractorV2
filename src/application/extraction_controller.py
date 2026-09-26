from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.ingestion.api import (
    IngestionError,
    SOURCE_MANUAL,
    StabilityScannerState,
    get_import_record as load_import_record,
    list_import_records,
    register_import,
    retry_archive as ingestion_retry_archive,
    run_watch_scan_cycle,
    validate_watch_path_pair,
)
from src.jobcontroller.api import get_job_evidence, retry_excel_export
from src.processing.api import (
    ProcessingConfig,
    config_from_runtime_defaults,
    enqueue_pdf,
    list_processing_jobs,
    process_next_pending,
    retry_failed,
)
from src.runtime.api import load_runtime_config

from .errors import ApplicationWatchError
from .models import (
    DesktopSettings,
    ImportRecordItem,
    IngestionInstanceItem,
    JobDiagnosisItem,
    ProcessingBatchSummary,
    ProcessingEnqueueOutcome,
    ProcessingItem,
    ProcessingOutcome,
    WatchCycleSummary,
)
from .presentation import (
    build_rework_context_label,
    classify_rework_diagnosis,
    friendly_processing_message,
    map_ingestion_display_status,
    normalize_stable_window_s,
)

_MANUAL_SOURCE = "test-app-manual"
SettingsProvider = Callable[[], DesktopSettings]
SubmitFunc = Callable[..., Any]


class ExtractionController:
    def __init__(
        self,
        project_root: str | Path,
        *,
        settings_provider: SettingsProvider,
        submit_func: SubmitFunc | None = None,
    ) -> None:
        self._project_root = Path(project_root).resolve()
        self._settings_provider = settings_provider
        self._submit_func = submit_func
        self._watch_scanner_state = None

    @property
    def project_root(self) -> Path:
        return self._project_root

    def enqueue_manual_pdfs(self, paths: list[str] | tuple[str, ...]) -> ProcessingBatchSummary:
        outcomes: list[ProcessingEnqueueOutcome] = []
        queued = 0
        skipped = 0
        errors = 0
        enqueue = self._make_enqueue_callable()
        for path in paths:
            pdf_path = str(path)
            file_name = Path(pdf_path).name
            try:
                result = register_import(
                    self._project_root,
                    pdf_path,
                    source_kind=SOURCE_MANUAL,
                    enqueue=enqueue,
                    source_label=_MANUAL_SOURCE,
                )
                record = result.record
                if result.created and result.queue_status == "PENDING":
                    queued += 1
                    outcomes.append(
                        ProcessingEnqueueOutcome(
                            pdf_path=pdf_path,
                            file_name=file_name,
                            outcome="queued",
                            job_id=record.processing_job_id,
                            ingestion_id=record.ingestion_id,
                        )
                    )
                elif not result.created or result.queue_status != "PENDING":
                    skipped += 1
                    outcomes.append(
                        ProcessingEnqueueOutcome(
                            pdf_path=pdf_path,
                            file_name=file_name,
                            outcome="skipped",
                            message=result.message or result.queue_status,
                            job_id=record.processing_job_id,
                            ingestion_id=record.ingestion_id,
                        )
                    )
            except Exception as exc:
                errors += 1
                outcomes.append(
                    ProcessingEnqueueOutcome(
                        pdf_path=pdf_path,
                        file_name=file_name,
                        outcome="error",
                        message=str(exc),
                    )
                )
        return ProcessingBatchSummary(
            outcomes=tuple(outcomes),
            queued=queued,
            skipped=skipped,
            errors=errors,
        )

    def run_watch_cycle(self, *, stable_window_s: float | None = None) -> WatchCycleSummary:
        settings = self._settings_provider()
        if not settings.watch_enabled:
            return WatchCycleSummary(enabled=False, disabled_reason="watch_disabled")

        watch_input = settings.watch_input_path
        watch_backup = settings.watch_backup_path
        try:
            validate_watch_path_pair(watch_input, watch_backup)
        except Exception as exc:
            raise ApplicationWatchError(str(exc)) from exc

        if self._watch_scanner_state is None:
            self._watch_scanner_state = StabilityScannerState()

        effective_stable_window = (
            normalize_stable_window_s(float(stable_window_s))
            if stable_window_s is not None
            else normalize_stable_window_s(float(load_runtime_config(self._project_root).watch_stable_window_s))
        )
        try:
            cycle = run_watch_scan_cycle(
                self._project_root,
                watch_input_path=watch_input,
                watch_backup_path=watch_backup,
                stable_window_s=effective_stable_window,
                enqueue=self._make_enqueue_callable(),
                state=self._watch_scanner_state,
                recursive=settings.watch_recursive,
            )
        except IngestionError as exc:
            raise ApplicationWatchError(str(exc)) from exc
        except Exception as exc:
            raise ApplicationWatchError(str(exc)) from exc
        outcomes = tuple(
            ProcessingEnqueueOutcome(
                pdf_path=item.pdf_path,
                file_name=Path(item.pdf_path).name,
                outcome=item.outcome,
                message=item.message,
                job_id=item.job_id,
                ingestion_id=item.ingestion_id,
            )
            for item in cycle.outcomes
        )
        return WatchCycleSummary(
            enabled=cycle.enabled,
            busy=cycle.busy,
            recovery_count=cycle.recovery_count,
            scanned_count=cycle.scanned_count,
            outcomes=outcomes,
        )

    def list_import_records(self) -> list[ImportRecordItem]:
        return [_to_import_record_item(record) for record in list_import_records(self._project_root)]

    def get_import_record(self, ingestion_id: str) -> ImportRecordItem | None:
        record = load_import_record(self._project_root, ingestion_id)
        if record is None:
            return None
        return _to_import_record_item(record)

    def retry_archive(self, ingestion_id: str) -> ImportRecordItem:
        record = ingestion_retry_archive(self._project_root, ingestion_id)
        return _to_import_record_item(record)

    def list_processing_items(self) -> list[ProcessingItem]:
        return [_to_processing_item(job) for job in list_processing_jobs(self._project_root)]

    def retry_failed(self, job_id: str) -> ProcessingItem:
        job = retry_failed(self._project_root, job_id)
        return _to_processing_item(job)

    def retry_excel_export(self, job_id: str) -> ProcessingOutcome:
        result = retry_excel_export(self._project_root, job_id)
        details = getattr(result, "details", {})
        message = str(details.get("error") or "") if isinstance(details, dict) else ""
        pdf_path = str(getattr(result, "pdf_path", ""))
        return ProcessingOutcome(
            processed=True,
            job_id=str(getattr(result, "job_id", job_id)),
            pdf_path=pdf_path,
            file_name=Path(pdf_path).name if pdf_path else "",
            queue_status="DONE",
            submit_status=str(getattr(result, "status", "")),
            message=message,
        )

    def process_next(self) -> ProcessingOutcome:
        result = process_next_pending(
            self._project_root,
            self._processing_config(),
            submit_func=self._submit_func,
        )
        return _to_processing_outcome(result)

    def list_ingestion_instances(self) -> list[IngestionInstanceItem]:
        queue_by_job = {job.job_id: job for job in list_processing_jobs(self._project_root)}
        covered_jobs: set[str] = set()
        items: list[IngestionInstanceItem] = []
        for record in list_import_records(self._project_root):
            job = queue_by_job.get(record.processing_job_id)
            if record.processing_job_id:
                covered_jobs.add(record.processing_job_id)
            items.append(_to_ingestion_instance_item(record, job))
        for job in queue_by_job.values():
            if job.job_id in covered_jobs:
                continue
            items.append(_queue_only_ingestion_instance(job))
        return sorted(items, key=lambda item: (item.updated_at, item.file_name.casefold()), reverse=True)

    def get_ingestion_instance(self, ingestion_id: str) -> IngestionInstanceItem | None:
        record = load_import_record(self._project_root, ingestion_id)
        if record is None:
            return None
        queue_by_job = {job.job_id: job for job in list_processing_jobs(self._project_root)}
        return _to_ingestion_instance_item(record, queue_by_job.get(record.processing_job_id))

    def list_job_diagnoses(self) -> list[JobDiagnosisItem]:
        diagnoses: list[JobDiagnosisItem] = []
        for job in list_processing_jobs(self._project_root):
            evidence = get_job_evidence(self._project_root, job.job_id)
            if str(job.status) != "FAILED" and not (evidence and evidence.retry_kind == "export_only"):
                continue
            item = self.get_job_diagnosis(job.job_id)
            if item is not None:
                diagnoses.append(item)
        return sorted(diagnoses, key=lambda item: item.file_name.casefold())

    def get_job_diagnosis(self, job_id: str) -> JobDiagnosisItem | None:
        jobs = {job.job_id: job for job in list_processing_jobs(self._project_root)}
        job = jobs.get(job_id)
        if job is None:
            return None
        evidence = get_job_evidence(self._project_root, job_id)
        state_error = evidence.error if evidence is not None and evidence.state_available else ""
        classified = classify_rework_diagnosis(job.last_error, state_error)
        if classified is None:
            return None
        error_label, root_error = classified
        normalized_dump = evidence.normalized_dump_path if evidence is not None else ""
        block_dumps = evidence.block_dump_paths if evidence is not None else ()
        context_label = (
            evidence.context_source_label
            if evidence is not None and evidence.context_source_label
            else build_rework_context_label(normalized_dump, block_dumps)
        )
        technical = root_error or job.last_error or state_error
        context_text = evidence.context_text if evidence is not None else ""
        context_truncated = bool(evidence and evidence.context_truncated)
        context_available = bool(evidence and evidence.context_available)
        return JobDiagnosisItem(
            job_id=job.job_id,
            pdf_path=job.pdf_path,
            file_name=Path(job.pdf_path).name,
            queue_status=job.status,
            error_label=error_label,
            root_error=root_error,
            context_label=context_label,
            friendly_message=friendly_processing_message(technical),
            technical_detail=technical,
            normalized_dump_path=normalized_dump,
            block_dump_paths=block_dumps,
            state_available=bool(evidence and evidence.state_available),
            context_text=context_text,
            context_truncated=context_truncated,
            context_available=context_available,
            retry_kind=evidence.retry_kind if evidence is not None and evidence.retry_kind else "full_processing",
        )

    def _make_enqueue_callable(self):
        root = self._project_root

        def enqueue(pdf_path: str, source: str, expected_sha256: str | None) -> object:
            return enqueue_pdf(
                root,
                pdf_path,
                source=source,
                expected_sha256=expected_sha256,
            )

        return enqueue

    def _processing_config(self) -> ProcessingConfig:
        runtime_defaults = config_from_runtime_defaults(self._project_root)
        desktop = self._settings_provider()
        return ProcessingConfig(
            output_mode=desktop.output_mode,
            sqlite_path=desktop.sqlite_path,
            device_id=desktop.device_id,
            queue_processing_ttl_s=runtime_defaults.queue_processing_ttl_s,
            queue_claim_lock_ttl_s=runtime_defaults.queue_claim_lock_ttl_s,
            queue_max_attempts=runtime_defaults.queue_max_attempts,
            pipeline_lock_ttl_s=runtime_defaults.pipeline_lock_ttl_s,
            sqlite_busy_timeout_ms=runtime_defaults.sqlite_busy_timeout_ms,
            sqlite_retry_count=runtime_defaults.sqlite_retry_count,
            sqlite_retry_sleep_s=runtime_defaults.sqlite_retry_sleep_s,
        )


def _to_import_record_item(record: object) -> ImportRecordItem:
    return ImportRecordItem(
        ingestion_id=str(getattr(record, "ingestion_id", "")),
        source_kind=str(getattr(record, "source_kind", "")),
        original_path=str(getattr(record, "original_path", "")),
        current_path=str(getattr(record, "current_path", "")),
        processing_job_id=str(getattr(record, "processing_job_id", "")),
        processing_status=str(getattr(record, "processing_status", "")),
        archive_status=str(getattr(record, "archive_status", "")),
        content_sha256=str(getattr(record, "content_sha256", "")),
        archived_at_utc=str(getattr(record, "archived_at_utc", "")),
        last_error=str(getattr(record, "last_error", "")),
        archive_error=str(getattr(record, "archive_error", "")),
    )


def _to_processing_item(job: object) -> ProcessingItem:
    return ProcessingItem(
        job_id=str(getattr(job, "job_id", "")),
        pdf_path=str(getattr(job, "pdf_path", "")),
        file_name=Path(str(getattr(job, "pdf_path", ""))).name,
        status=str(getattr(job, "status", "")),
        source=str(getattr(job, "source", "")),
        worker_id=str(getattr(job, "worker_id", "")),
        attempts=int(getattr(job, "attempts", 0) or 0),
        last_error=str(getattr(job, "last_error", "")),
        created_at=str(getattr(job, "created_at", "")),
        updated_at=str(getattr(job, "updated_at", "")),
    )


def _technical_detail(record: object, queue_job: object | None) -> str:
    archive_error = str(getattr(record, "archive_error", "") or "")
    last_error = str(getattr(record, "last_error", "") or "")
    if archive_error:
        return archive_error
    if last_error:
        return last_error
    if queue_job is not None:
        return str(getattr(queue_job, "last_error", "") or "")
    return ""


def _to_ingestion_instance_item(record: object, queue_job: object | None) -> IngestionInstanceItem:
    ledger_processing_status = str(getattr(record, "processing_status", ""))
    archive_status = str(getattr(record, "archive_status", ""))
    queue_status = str(getattr(queue_job, "status", "") if queue_job is not None else "")
    technical = _technical_detail(record, queue_job)
    return IngestionInstanceItem(
        ingestion_id=str(getattr(record, "ingestion_id", "")),
        job_id=str(getattr(record, "processing_job_id", "")),
        file_name=Path(str(getattr(record, "original_path", ""))).name,
        source_kind=str(getattr(record, "source_kind", "")),
        original_path=str(getattr(record, "original_path", "")),
        current_path=str(getattr(record, "current_path", "")),
        processing_status=ledger_processing_status,
        queue_status=queue_status,
        archive_status=archive_status,
        display_status=map_ingestion_display_status(
            ledger_processing_status,
            archive_status,
            queue_status=queue_status,
        ),
        friendly_message=friendly_processing_message(technical),
        technical_detail=technical,
        created_at=str(getattr(record, "discovered_at_utc", "")),
        updated_at=str(getattr(record, "updated_at_utc", "")),
        queue_only=False,
    )


def _queue_only_ingestion_instance(job: object) -> IngestionInstanceItem:
    pdf_path = str(getattr(job, "pdf_path", ""))
    status = str(getattr(job, "status", ""))
    processing_status = {
        "PENDING": "PENDING",
        "PROCESSING": "PROCESSING",
        "DONE": "DONE",
        "FAILED": "FAILED",
    }.get(status, "REGISTERED")
    technical = str(getattr(job, "last_error", "") or "")
    return IngestionInstanceItem(
        ingestion_id="",
        job_id=str(getattr(job, "job_id", "")),
        file_name=Path(pdf_path).name if pdf_path else "",
        source_kind="",
        original_path=pdf_path,
        current_path=pdf_path,
        processing_status=processing_status,
        queue_status=status,
        archive_status="NOT_REQUIRED",
        display_status=map_ingestion_display_status(
            processing_status,
            "NOT_REQUIRED",
            queue_status=status,
        ),
        friendly_message=friendly_processing_message(technical),
        technical_detail=technical,
        created_at=str(getattr(job, "created_at", "")),
        updated_at=str(getattr(job, "updated_at", "")),
        queue_only=True,
    )


def _to_processing_outcome(result: object) -> ProcessingOutcome:
    pdf_path = str(getattr(result, "pdf_path", ""))
    return ProcessingOutcome(
        processed=bool(getattr(result, "processed", False)),
        job_id=str(getattr(result, "job_id", "")),
        pdf_path=pdf_path,
        file_name=Path(pdf_path).name if pdf_path else "",
        queue_status=str(getattr(result, "queue_status", "")),
        submit_status=str(getattr(result, "submit_status", "")),
        message=str(getattr(result, "message", "")),
    )
