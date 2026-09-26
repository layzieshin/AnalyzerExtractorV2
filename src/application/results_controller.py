from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.dbwriter.api import (
    discard_duplicate_candidate as dbwriter_discard_duplicate_candidate,
    get_duplicate_candidate,
    list_duplicate_candidates,
)
from src.ingestion.api import get_import_record, resolve_current_path
from src.jobcontroller.api import get_job_evidence, release_validated_run
from src.jobqueue.api import list_jobs
from src.resultstore.api import (
    compute_report_id,
    get_report_runs,
    get_result_run,
    get_result_store_status,
    list_report_summaries,
    list_result_assays,
    list_result_charges,
    list_result_runs,
)
from src.resultvalidation.api import (
    OperatorInitialsRequiredError,
    ResultValidationError,
    RunNotFoundError,
    RunValidation,
    UnsupportedValidationStoreError,
    ValidationAlreadyExistsError,
    ValidationAmbiguousError,
    ValidationMissingError,
    ValidationStoreBusyError,
    ValidationStoreMissingError,
    ValidationStoreUnreadableError,
    correct_validation,
    list_run_validations,
    validate_run,
)

from .desktop_actions import PathOpener, open_path
from .errors import PathOpenError, ReportNotFoundError, ValidationConflictError, ValidationInputError
from .models import (
    DesktopSettings,
    DuplicateCandidateDetail,
    DuplicateCandidateItem,
    DuplicateDecisionResult,
    DuplicateExistingRunItem,
    DuplicateFieldComparisonItem,
    ReportAssayGroup,
    ReportDetail,
    ReportFieldValue,
    ReportRunOccurrence,
    ReportSummaryItem,
    RunValidationItem,
    ValidationQueueItem,
    ResultAssayItem,
    ResultChargeItem,
    ResultRunItem,
    ResultRunList,
    ResultStoreStatus,
    _ValidationIndex,
)
from .presentation import map_ingestion_display_status

SettingsProvider = Callable[[], DesktopSettings]


def _empty_validation_index() -> _ValidationIndex:
    return _ValidationIndex({}, {}, frozenset())


class ResultsController:
    def __init__(
        self,
        project_root: str | Path,
        *,
        settings_provider: SettingsProvider,
        path_opener: PathOpener | None = None,
    ) -> None:
        self._project_root = Path(project_root).resolve()
        self._settings_provider = settings_provider
        self._path_opener = path_opener

    @property
    def project_root(self) -> Path:
        return self._project_root

    def _store_spec(self) -> dict[str, str]:
        sqlite_path = self._settings_provider().sqlite_path
        return {"driver": "sqlite", "path": sqlite_path}

    def get_store_status(self) -> ResultStoreStatus:
        sqlite_path = self._settings_provider().sqlite_path
        raw = get_result_store_status(self._store_spec())
        return ResultStoreStatus(
            available=bool(raw.get("available")),
            driver=str(raw.get("driver") or "sqlite"),
            path=str(raw.get("path") or sqlite_path),
            message=str(raw.get("message") or ""),
            has_runs_table=bool(raw.get("has_runs_table")),
            columns=tuple(str(col) for col in (raw.get("columns") or [])),
            missing_core_columns=tuple(str(col) for col in (raw.get("missing_core_columns") or [])),
            schema_warnings=tuple(str(item) for item in (raw.get("schema_warnings") or [])),
        )

    def list_assays(self) -> list[ResultAssayItem]:
        rows = list_result_assays(self._store_spec())
        return [ResultAssayItem(assay_key=str(row.get("assay_key") or "")) for row in rows]

    def list_charges(self, assay_key: str) -> list[ResultChargeItem]:
        rows = list_result_charges(self._store_spec(), assay_key)
        return [
            ResultChargeItem(
                lot_id=str(row.get("lot_id") or ""),
                charge=str(row.get("charge") or row.get("lot_id") or ""),
            )
            for row in rows
        ]

    def list_runs(
        self,
        *,
        assay_key: str | None = None,
        charge: str | None = None,
        limit: int = 500,
    ) -> ResultRunList:
        raw = list_result_runs(
            self._store_spec(),
            assay_key=assay_key,
            charge=charge,
            limit=limit,
        )
        runs = tuple(_to_run_item(row, project_root=self._project_root) for row in (raw.get("runs") or []))
        return ResultRunList(
            runs=runs,
            limit=int(raw.get("limit") or limit),
            truncated=bool(raw.get("truncated")),
            total_returned=int(raw.get("total_returned") or len(runs)),
        )

    def get_run_detail(self, run_id: int) -> ResultRunItem | None:
        raw = get_result_run(self._store_spec(), int(run_id))
        if raw is None:
            return None
        return _to_run_item(raw, project_root=self._project_root)

    def list_recent_reports(self, *, limit: int = 50) -> list[ReportSummaryItem]:
        raw = list_report_summaries(self._store_spec(), limit=limit)
        prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        all_run_ids: list[int] = []
        for row in raw.get("reports") or []:
            report_id = str(row.get("report_id") or "")
            detail_raw = get_report_runs(self._store_spec(), report_id) if report_id else None
            runs = list(detail_raw.get("runs") or []) if detail_raw else []
            prepared.append((row, runs))
            all_run_ids.extend(_run_ids(runs))
        index = self._load_validation_index(all_run_ids) if prepared else _empty_validation_index()
        return [
            _to_report_summary(
                row,
                project_root=self._project_root,
                runs=runs,
                validation_index=index,
            )
            for row, runs in prepared
        ]

    def get_report_detail(self, report_id: str) -> ReportDetail | None:
        target = str(report_id or "").strip()
        if not target:
            return None
        raw = get_report_runs(self._store_spec(), target)
        if raw is None:
            return None
        runs = list(raw.get("runs") or [])
        index = self._load_validation_index(_run_ids(runs))
        return _to_report_detail(
            raw,
            project_root=self._project_root,
            validation_index=index,
        )

    def list_open_validation_cases(self, *, limit: int | None = None) -> list[ValidationQueueItem]:
        """Return successful assay runs without an unambiguous effective validation."""
        requested_limit = None if limit is None else max(0, int(limit))
        if requested_limit == 0:
            return []
        path_contexts: dict[tuple[str, str], tuple[str, str, str, bool, str, str]] = {}
        queue_status_by_job = {str(job.job_id): str(job.status) for job in list_jobs(str(self._project_root))}
        terminal_by_job: dict[str, bool] = {}
        open_items: list[ValidationQueueItem] = []
        page_size = 500
        offset = 0
        while True:
            raw = list_result_runs(self._store_spec(), limit=page_size, offset=offset)
            runs = list(raw.get("runs") or [])
            index = self._load_validation_index(_run_ids(runs)) if runs else _empty_validation_index()
            for row in runs:
                run_id = row.get("id")
                if run_id is None or row.get("payload_parse_error"):
                    continue
                run_key = int(run_id)
                ambiguous = run_key in index.ambiguous_run_ids
                if not ambiguous and run_key in index.latest_by_run_id:
                    continue
                job_id = str(row.get("job_id") or "")
                if job_id:
                    queue_status = queue_status_by_job.get(job_id)
                    if queue_status is not None and queue_status != "DONE":
                        continue
                    terminal = terminal_by_job.get(job_id)
                    if terminal is None:
                        evidence = get_job_evidence(self._project_root, job_id)
                        terminal = not (
                            evidence is not None
                            and evidence.state_available
                            and evidence.status != "DONE"
                        )
                        terminal_by_job[job_id] = terminal
                    if not terminal:
                        continue
                pdf_path = str(row.get("pdf_path") or "")
                context_key = (job_id, pdf_path)
                path_context = path_contexts.get(context_key)
                if path_context is None:
                    path_context = _report_path_context(
                        self._project_root,
                        job_id=job_id,
                        pdf_path=pdf_path,
                    )
                    path_contexts[context_key] = path_context
                current_pdf_path, _ingestion_id, _path_status, _available, display_status, _archive = path_context
                if _processing_needs_review(display_status):
                    continue
                payload = dict(row.get("payload") or {})
                fields = tuple(
                    ReportFieldValue(field_key=str(key), value=_stringify_value(value))
                    for key, value in sorted(payload.items(), key=lambda item: str(item[0]).casefold())
                )
                report_id = compute_report_id(
                    job_id,
                    pdf_path=pdf_path,
                    created_at=str(row.get("created_at") or ""),
                    run_id=run_key,
                )
                open_items.append(
                    ValidationQueueItem(
                        report_id=report_id,
                        run_id=run_key,
                        file_name=Path(pdf_path).name if pdf_path else "",
                        current_pdf_path=current_pdf_path or pdf_path,
                        assay_key=str(row.get("assay_key") or ""),
                        lot_id=str(row.get("lot_id") or ""),
                        device_id=str(row.get("device_id") or ""),
                        created_at=str(row.get("created_at") or ""),
                        fields=fields,
                        validation_ambiguous=ambiguous,
                    )
                )
            offset += len(runs)
            if not raw.get("truncated") or not runs:
                break
        return open_items if requested_limit is None else open_items[:requested_limit]

    def validate_report_run(
        self,
        report_id: str,
        run_id: int,
        operator_initials: str,
        comment: str = "",
    ) -> RunValidationItem:
        run = self._require_run_in_report(report_id, run_id)
        try:
            record = validate_run(self._store_spec(), int(run_id), operator_initials, comment)
        except ResultValidationError as exc:
            raise _map_validation_error(exc) from exc
        item = _to_validation_item(record)
        return self._release_validated_excel(run, item, correction=False)

    def correct_report_run(
        self,
        report_id: str,
        run_id: int,
        operator_initials: str,
        comment: str = "",
    ) -> RunValidationItem:
        run = self._require_run_in_report(report_id, run_id)
        try:
            record = correct_validation(self._store_spec(), int(run_id), operator_initials, comment)
        except ResultValidationError as exc:
            raise _map_validation_error(exc) from exc
        item = _to_validation_item(record)
        return self._release_validated_excel(run, item, correction=True)

    def _release_validated_excel(
        self,
        run: dict[str, Any],
        validation: RunValidationItem,
        *,
        correction: bool,
    ) -> RunValidationItem:
        result = release_validated_run(
            self._project_root,
            str(run.get("job_id") or ""),
            validation.run_id,
            operator_initials=validation.operator_initials,
            validated_at_utc=validation.validated_at_utc,
            validation_id=validation.validation_id,
            correction=correction,
        )
        status = str(getattr(result, "status", ""))
        details = getattr(result, "details", {})
        error = str(details.get("error") or "") if isinstance(details, dict) else ""
        return RunValidationItem(
            validation_id=validation.validation_id,
            run_id=validation.run_id,
            operator_initials=validation.operator_initials,
            validated_at_utc=validation.validated_at_utc,
            comment=validation.comment,
            supersedes_validation_id=validation.supersedes_validation_id,
            created_at_utc=validation.created_at_utc,
            excel_export_status="failed" if status == "FAILED" else "success",
            excel_export_error=error,
        )

    def open_report_pdf(self, report_id: str) -> str:
        detail = self.get_report_detail(report_id)
        if detail is None:
            raise ReportNotFoundError(f"report_not_found: {report_id}")
        if detail.path_status == "ambiguous":
            raise PathOpenError("report_pdf_ambiguous")
        pdf_path = str(detail.current_pdf_path or detail.pdf_path or "").strip()
        if not pdf_path:
            raise PathOpenError("report_pdf_missing")
        if not Path(pdf_path).is_file():
            raise PathOpenError(f"path_not_found: {pdf_path}")
        open_path(pdf_path, opener=self._path_opener)
        return pdf_path

    def list_duplicate_candidates(self, *, status: str = "pending") -> list[DuplicateCandidateItem]:
        rows = list_duplicate_candidates(self._settings_provider().sqlite_path, status=status)
        return [_to_duplicate_candidate_item(row) for row in rows]

    def get_duplicate_candidate_detail(self, candidate_id: int) -> DuplicateCandidateDetail | None:
        raw = get_duplicate_candidate(self._settings_provider().sqlite_path, int(candidate_id))
        if raw is None:
            return None
        candidate = raw.get("candidate")
        if not isinstance(candidate, dict):
            return None
        existing = raw.get("existing") if isinstance(raw.get("existing"), dict) else {}
        comparison = raw.get("field_comparison")
        return DuplicateCandidateDetail(
            candidate=_to_duplicate_candidate_item(candidate),
            existing=_to_duplicate_existing_run(existing),
            field_comparison=_to_field_comparison(comparison),
        )

    def discard_duplicate_candidate(
        self,
        candidate_id: int,
        *,
        decided_by: str = "desktop-app",
        note: str = "",
    ) -> DuplicateDecisionResult:
        raw = dbwriter_discard_duplicate_candidate(
            self._settings_provider().sqlite_path,
            int(candidate_id),
            decided_by=decided_by,
            note=note,
        )
        return DuplicateDecisionResult(
            candidate_id=int(raw.get("candidate_id") or candidate_id),
            status=str(raw.get("status") or ""),
            action=str(raw.get("action") or ""),
            decision_at=str(raw.get("decision_at") or ""),
            decision_by=str(raw.get("decision_by") or ""),
            decision_note=str(raw.get("decision_note") or ""),
        )

    def _load_validation_index(self, run_ids: list[int]) -> _ValidationIndex:
        pending: list[int] = []
        seen: set[int] = set()
        for run_id in run_ids:
            if run_id in seen:
                continue
            seen.add(run_id)
            pending.append(run_id)
        ambiguous: set[int] = set()
        listed = None
        while pending:
            try:
                listed = list_run_validations(self._store_spec(), pending)
                break
            except ValidationAmbiguousError as exc:
                bad_id = exc.run_id
                if not isinstance(bad_id, int) or isinstance(bad_id, bool) or bad_id not in pending:
                    raise _map_validation_error(exc) from exc
                ambiguous.add(bad_id)
                pending = [item for item in pending if item != bad_id]
            except ResultValidationError as exc:
                raise _map_validation_error(exc) from exc
        history: dict[int, tuple[RunValidation, ...]] = {}
        latest: dict[int, RunValidation] = {}
        if listed is not None:
            grouped: dict[int, list[RunValidation]] = {}
            for record in listed.records:
                grouped.setdefault(record.run_id, []).append(record)
            history = {run_id: tuple(items) for run_id, items in grouped.items()}
            latest = {int(run_id): record for run_id, record in listed.latest_by_run_id.items()}
        return _ValidationIndex(latest, history, frozenset(ambiguous))

    def _require_run_in_report(self, report_id: str, run_id: int) -> dict[str, Any]:
        target = str(report_id or "").strip()
        raw = get_report_runs(self._store_spec(), target) if target else None
        if raw is None:
            raise ReportNotFoundError(f"report_not_found: {report_id}")
        for row in raw.get("runs") or []:
            if row.get("id") is not None and int(row["id"]) == int(run_id):
                return row
        raise ValidationInputError("run_not_in_report")


def _run_ids(runs: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for row in runs:
        run_id = row.get("id")
        if run_id is None:
            continue
        ids.append(int(run_id))
    return ids


def _processing_needs_review(display_status: str) -> bool:
    text = str(display_status or "").casefold()
    if "fehlgeschlagen" in text:
        return True
    return any(token in text for token in ("klaerung", "klärung", "klaerfall", "klärfall"))


def _coverage_status(validated: int, total: int) -> str:
    if total <= 0 or validated <= 0:
        return "Unvalidiert"
    if validated >= total:
        return "Validiert"
    return "Teilweise validiert"


def _validation_view(
    runs: list[dict[str, Any]],
    index: _ValidationIndex,
    processing_status: str,
) -> tuple[str, str]:
    validated = 0
    review_required = False
    for row in runs:
        if row.get("payload_parse_error"):
            review_required = True
        run_id = row.get("id")
        if run_id is None:
            continue
        run_key = int(run_id)
        if run_key in index.ambiguous_run_ids:
            review_required = True
            continue
        if run_key in index.latest_by_run_id:
            validated += 1
    coverage = _coverage_status(validated, len(runs))
    if review_required or _processing_needs_review(processing_status):
        return coverage, "Prüfung erforderlich"
    return coverage, coverage


def _map_validation_error(exc: ResultValidationError) -> ValidationConflictError | ValidationInputError:
    if isinstance(exc, ValidationAlreadyExistsError):
        return ValidationConflictError("validation_already_exists")
    if isinstance(exc, ValidationMissingError):
        return ValidationConflictError("validation_missing")
    if isinstance(exc, ValidationAmbiguousError):
        return ValidationConflictError("validation_ambiguous")
    if isinstance(exc, OperatorInitialsRequiredError):
        return ValidationInputError("operator_initials_required")
    if isinstance(exc, RunNotFoundError):
        return ValidationInputError("run_not_found")
    if isinstance(exc, ValidationStoreMissingError):
        return ValidationInputError("validation_store_missing")
    if isinstance(exc, ValidationStoreBusyError):
        return ValidationInputError("validation_store_busy")
    if isinstance(exc, (ValidationStoreUnreadableError, UnsupportedValidationStoreError)):
        detail = str(exc).strip()
        generic = {
            "Datenbank konnte nicht gelesen werden.",
            "Der Ergebnisspeicher wird nicht unterstützt.",
        }
        if detail and detail not in generic:
            return ValidationInputError(f"validation_store_unreadable: {detail}")
        return ValidationInputError("validation_store_unreadable")
    if str(exc).strip() == "Kommentar muss Text sein.":
        return ValidationInputError("validation_comment_invalid")
    return ValidationInputError("validation_store_unreadable")


def _to_validation_item(record: RunValidation) -> RunValidationItem:
    return RunValidationItem(
        validation_id=record.validation_id,
        run_id=record.run_id,
        operator_initials=record.operator_initials,
        validated_at_utc=record.validated_at_utc,
        comment=record.comment,
        supersedes_validation_id=record.supersedes_validation_id,
        created_at_utc=record.created_at_utc,
    )


def _report_path_context(
    project_root: Path,
    *,
    job_id: str,
    pdf_path: str,
) -> tuple[str, str, str, bool, str, str]:
    path_info = resolve_current_path(project_root, job_id, pdf_path)
    queue_status = ""
    if job_id:
        for job in list_jobs(str(project_root)):
            if job.job_id == job_id:
                queue_status = str(job.status or "")
                break

    ledger_processing = ""
    archive_status = ""
    if path_info.path_status == "resolved" and path_info.ingestion_id:
        record = get_import_record(project_root, path_info.ingestion_id)
        if record is not None:
            ledger_processing = str(record.processing_status or "")
            archive_status = str(record.archive_status or "")
    elif (
        path_info.path_status == "legacy_fallback"
        and not job_id
        and not queue_status
        and not path_info.ingestion_id
    ):
        ledger_processing = "DONE"

    display_status = map_ingestion_display_status(
        ledger_processing,
        archive_status,
        queue_status=queue_status,
    )
    current_path = path_info.current_pdf_path
    path_available = bool(current_path and Path(current_path).is_file())
    return (
        path_info.current_pdf_path,
        path_info.ingestion_id,
        path_info.path_status,
        path_available,
        display_status,
        archive_status,
    )


def _to_report_summary(
    row: dict[str, Any],
    *,
    project_root: Path,
    runs: list[dict[str, Any]] | None = None,
    validation_index: _ValidationIndex | None = None,
) -> ReportSummaryItem:
    job_id = str(row.get("job_id") or "")
    pdf_path = str(row.get("pdf_path") or "")
    report_id = str(row.get("report_id") or compute_report_id(job_id, pdf_path=pdf_path))
    current_pdf_path, ingestion_id, path_status, path_available, display_status, archive_status = _report_path_context(
        project_root,
        job_id=job_id,
        pdf_path=pdf_path,
    )
    assay_keys = tuple(str(key) for key in (row.get("assay_keys") or []))
    device_ids = tuple(str(device) for device in (row.get("device_ids") or []))
    report_runs = list(runs if runs is not None else [])
    index = validation_index if validation_index is not None else _empty_validation_index()
    validation_status, report_status = _validation_view(report_runs, index, display_status)
    return ReportSummaryItem(
        report_id=report_id,
        job_id=job_id,
        pdf_path=pdf_path,
        file_name=Path(pdf_path).name if pdf_path else "",
        current_pdf_path=current_pdf_path,
        run_count=int(row.get("run_count") or 0),
        assay_count=int(row.get("assay_count") or 0),
        latest_created_at=str(row.get("latest_created_at") or ""),
        path_status=path_status,
        pdf_sha256=str(row.get("pdf_sha256") or ""),
        ingestion_id=ingestion_id,
        earliest_created_at=str(row.get("earliest_created_at") or ""),
        device_ids=device_ids,
        assay_keys=assay_keys,
        display_status=display_status,
        archive_status=archive_status,
        path_available=path_available,
        validation_status=validation_status,
        report_status=report_status,
    )


def _to_report_detail(
    raw: dict[str, Any],
    *,
    project_root: Path,
    validation_index: _ValidationIndex | None = None,
) -> ReportDetail:
    runs = list(raw.get("runs") or [])
    index = validation_index if validation_index is not None else _empty_validation_index()
    summary = _to_report_summary(
        raw,
        project_root=project_root,
        runs=runs,
        validation_index=index,
    )
    assay_groups = _group_report_assays(runs, validation_index=index)
    return ReportDetail(
        report_id=summary.report_id,
        job_id=summary.job_id,
        pdf_path=summary.pdf_path,
        file_name=summary.file_name,
        current_pdf_path=summary.current_pdf_path,
        ingestion_id=summary.ingestion_id,
        path_status=summary.path_status,
        assay_groups=assay_groups,
        pdf_sha256=summary.pdf_sha256,
        earliest_created_at=summary.earliest_created_at,
        latest_created_at=summary.latest_created_at,
        device_ids=summary.device_ids,
        display_status=summary.display_status,
        archive_status=summary.archive_status,
        path_available=summary.path_available,
        validation_status=summary.validation_status,
        report_status=summary.report_status,
    )


def _group_report_assays(
    rows: list[dict[str, Any]],
    *,
    validation_index: _ValidationIndex | None = None,
) -> tuple[ReportAssayGroup, ...]:
    index = validation_index if validation_index is not None else _empty_validation_index()
    by_assay: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        assay_key = str(row.get("assay_key") or "")
        by_assay.setdefault(assay_key, []).append(row)
    groups: list[ReportAssayGroup] = []
    for assay_key in sorted(by_assay.keys(), key=str.casefold):
        assay_rows = by_assay[assay_key]
        first = assay_rows[0]
        occurrences: list[ReportRunOccurrence] = []
        for row in assay_rows:
            payload = dict(row.get("payload") or {})
            fields = tuple(
                ReportFieldValue(field_key=str(key), value=_stringify_value(value))
                for key, value in sorted(payload.items(), key=lambda item: str(item[0]).casefold())
            )
            run_id = row.get("id")
            run_key = int(run_id) if run_id is not None else None
            ambiguous = run_key is not None and run_key in index.ambiguous_run_ids
            current_record = None if ambiguous or run_key is None else index.latest_by_run_id.get(run_key)
            history_records = () if ambiguous or run_key is None else index.history_by_run_id.get(run_key, ())
            occurrences.append(
                ReportRunOccurrence(
                    run_id=run_key,
                    lot_id=str(row.get("lot_id") or ""),
                    charge=str(row.get("charge") or row.get("lot_id") or ""),
                    device_id=str(row.get("device_id") or ""),
                    dedupe_key=str(row.get("dedupe_key") or ""),
                    created_at=str(row.get("created_at") or ""),
                    fields=fields,
                    payload_parse_error=row.get("payload_parse_error"),
                    current_validation=_to_validation_item(current_record) if current_record is not None else None,
                    validation_history=tuple(_to_validation_item(item) for item in history_records),
                    validation_ambiguous=ambiguous,
                )
            )
        groups.append(
            ReportAssayGroup(
                assay_key=assay_key,
                ruleset_file=str(first.get("ruleset_file") or ""),
                occurrences=tuple(occurrences),
                assay_display_label=assay_key,
            )
        )
    return tuple(groups)


def _stringify_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "False" if value is False else "True"
    if isinstance(value, str):
        return value
    return str(value)


def _format_comparison_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "False" if value is False else "True"
    return str(value)


def _to_duplicate_candidate_item(row: dict[str, object]) -> DuplicateCandidateItem:
    dedupe_basis = row.get("dedupe_basis")
    candidate_meta = row.get("meta")
    return DuplicateCandidateItem(
        candidate_id=int(row.get("candidate_id") or row.get("id") or 0),
        status=str(row.get("status") or ""),
        assay_key=str(row.get("assay_key") or ""),
        dedupe_key=str(row.get("dedupe_key") or ""),
        existing_run_id=int(row.get("existing_run_id") or 0),
        detected_at=str(row.get("detected_at") or ""),
        device_id=str(row.get("device_id") or ""),
        dedupe_version=str(row.get("dedupe_version") or ""),
        pdf_sha256=str(row.get("pdf_sha256") or ""),
        assay_block_hash=str(row.get("assay_block_hash") or ""),
        decision_at=str(row.get("decision_at") or ""),
        decision_by=str(row.get("decision_by") or ""),
        decision_note=str(row.get("decision_note") or ""),
        dedupe_basis=dict(dedupe_basis) if isinstance(dedupe_basis, dict) else {},
        candidate_meta=dict(candidate_meta) if isinstance(candidate_meta, dict) else {},
    )


def _to_duplicate_existing_run(row: dict[str, object]) -> DuplicateExistingRunItem | None:
    if not row:
        return None
    run_id = row.get("run_id")
    if run_id in (None, "", 0):
        return None
    dedupe_basis = row.get("dedupe_basis")
    return DuplicateExistingRunItem(
        run_id=int(run_id),
        job_id=str(row.get("job_id") or ""),
        pdf_path=str(row.get("pdf_path") or ""),
        assay_key=str(row.get("assay_key") or ""),
        lot_id=str(row.get("lot_id") or ""),
        charge=str(row.get("lot_id") or ""),
        dedupe_key=str(row.get("dedupe_key") or ""),
        device_id=str(row.get("device_id") or ""),
        dedupe_version=str(row.get("dedupe_version") or ""),
        created_at=str(row.get("created_at") or ""),
        dedupe_basis=dict(dedupe_basis) if isinstance(dedupe_basis, dict) else {},
    )


def _to_field_comparison(raw: object) -> tuple[DuplicateFieldComparisonItem, ...]:
    if not isinstance(raw, list):
        return ()
    items: list[DuplicateFieldComparisonItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if "changed" in entry:
            changed = bool(entry["changed"])
        elif "same" in entry:
            changed = not bool(entry["same"])
        else:
            changed = False
        existing_raw = entry.get("existing")
        if existing_raw is None:
            existing_raw = entry.get("existing_value")
        candidate_raw = entry.get("candidate")
        if candidate_raw is None:
            candidate_raw = entry.get("candidate_value")
        items.append(
            DuplicateFieldComparisonItem(
                field_key=str(entry.get("field") or entry.get("field_key") or ""),
                existing_value=_format_comparison_value(existing_raw),
                candidate_value=_format_comparison_value(candidate_raw),
                changed=changed,
            )
        )
    return tuple(items)


def _to_run_item(row: dict[str, Any], *, project_root: Path) -> ResultRunItem:
    run_id = row.get("id")
    job_id = str(row.get("job_id") or "")
    pdf_path = str(row.get("pdf_path") or "")
    path_info = resolve_current_path(project_root, job_id, pdf_path)
    return ResultRunItem(
        id=int(run_id) if run_id is not None else None,
        job_id=job_id,
        pdf_path=pdf_path,
        assay_key=str(row.get("assay_key") or ""),
        lot_id=str(row.get("lot_id") or ""),
        charge=str(row.get("charge") or row.get("lot_id") or ""),
        dedupe_key=str(row.get("dedupe_key") or ""),
        device_id=str(row.get("device_id") or ""),
        dedupe_version=str(row.get("dedupe_version") or ""),
        pdf_sha256=str(row.get("pdf_sha256") or ""),
        assay_block_hash=str(row.get("assay_block_hash") or ""),
        ruleset_file=str(row.get("ruleset_file") or ""),
        created_at=str(row.get("created_at") or ""),
        payload=dict(row.get("payload") or {}),
        dedupe_basis=dict(row.get("dedupe_basis") or {}),
        result_date=str(row.get("result_date") or ""),
        payload_parse_error=row.get("payload_parse_error"),
        dedupe_basis_parse_error=row.get("dedupe_basis_parse_error"),
        source_pdf_path=path_info.source_pdf_path,
        current_pdf_path=path_info.current_pdf_path,
        ingestion_id=path_info.ingestion_id,
        path_status=path_info.path_status,
    )
