from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def _resolve_watch_input_path(
    watch_dir: str,
    watch_input_path: str | None,
) -> str:
    dir_text = str(watch_dir or "").strip()
    input_text = str(watch_input_path or "").strip() if watch_input_path is not None else ""
    if dir_text and input_text and dir_text != input_text:
        raise ValueError("conflicting_watch_dir_and_watch_input_path")
    return input_text or dir_text


@dataclass(frozen=True)
class DesktopSettings:
    output_mode: str
    sqlite_path: str
    watch_enabled: bool = False
    watch_input_path: str = ""
    watch_backup_path: str = ""
    watch_recursive: bool = False
    device_id: str | None = None
    operator_initials: str = ""

    def __init__(
        self,
        output_mode: str,
        sqlite_path: str,
        watch_dir: str = "",
        device_id: str | None = None,
        *,
        watch_enabled: bool = False,
        watch_input_path: str | None = None,
        watch_backup_path: str = "",
        watch_recursive: bool = False,
        operator_initials: str = "",
    ) -> None:
        resolved_input = _resolve_watch_input_path(watch_dir, watch_input_path)
        if not isinstance(operator_initials, str):
            raise ValueError("invalid_operator_initials_type")
        object.__setattr__(self, "output_mode", output_mode)
        object.__setattr__(self, "sqlite_path", sqlite_path)
        object.__setattr__(self, "watch_enabled", watch_enabled)
        object.__setattr__(self, "watch_input_path", resolved_input)
        object.__setattr__(self, "watch_backup_path", watch_backup_path)
        object.__setattr__(self, "watch_recursive", bool(watch_recursive))
        object.__setattr__(self, "device_id", device_id)
        object.__setattr__(self, "operator_initials", operator_initials.strip())

    @property
    def watch_dir(self) -> str:
        return self.watch_input_path


@dataclass(frozen=True)
class ProcessingEnqueueOutcome:
    pdf_path: str
    file_name: str
    outcome: str
    message: str = ""
    job_id: str = ""
    ingestion_id: str = ""


@dataclass(frozen=True)
class ProcessingBatchSummary:
    outcomes: tuple[ProcessingEnqueueOutcome, ...]
    queued: int
    skipped: int
    errors: int


@dataclass(frozen=True)
class ProcessingOutcome:
    processed: bool
    job_id: str = ""
    pdf_path: str = ""
    file_name: str = ""
    queue_status: str = ""
    submit_status: str = ""
    message: str = ""


@dataclass(frozen=True)
class ProcessingItem:
    job_id: str
    pdf_path: str
    file_name: str
    status: str
    source: str
    worker_id: str
    attempts: int
    last_error: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ImportRecordItem:
    ingestion_id: str
    source_kind: str
    original_path: str
    current_path: str
    processing_job_id: str
    processing_status: str
    archive_status: str
    content_sha256: str
    archived_at_utc: str = ""
    last_error: str = ""
    archive_error: str = ""


@dataclass(frozen=True)
class WatchCycleSummary:
    enabled: bool
    disabled_reason: str = ""
    busy: bool = False
    recovery_count: int = 0
    scanned_count: int = 0
    outcomes: tuple[ProcessingEnqueueOutcome, ...] = ()


@dataclass(frozen=True)
class ResultStoreStatus:
    available: bool
    driver: str
    path: str
    message: str
    has_runs_table: bool
    columns: tuple[str, ...]
    missing_core_columns: tuple[str, ...]
    schema_warnings: tuple[str, ...]


@dataclass(frozen=True)
class ResultAssayItem:
    assay_key: str
    assay_name: str = ""


@dataclass(frozen=True)
class ResultChargeItem:
    lot_id: str
    charge: str


@dataclass(frozen=True)
class ResultRunItem:
    id: int | None
    job_id: str
    pdf_path: str
    assay_key: str
    lot_id: str
    charge: str
    dedupe_key: str
    device_id: str
    dedupe_version: str
    pdf_sha256: str
    assay_block_hash: str
    ruleset_file: str
    created_at: str
    payload: dict[str, Any]
    dedupe_basis: dict[str, Any]
    result_date: str
    payload_parse_error: str | None
    dedupe_basis_parse_error: str | None
    source_pdf_path: str = ""
    current_pdf_path: str = ""
    ingestion_id: str = ""
    path_status: str = ""
    revision_id: int = 0
    selection_token: str = ""
    revision_history: tuple[dict[str, Any], ...] = ()
    selection_history: tuple[dict[str, Any], ...] = ()
    revision_error: str = ""

    assay_name: str = ""


@dataclass(frozen=True)
class ResultRunList:
    runs: tuple[ResultRunItem, ...]
    limit: int
    truncated: bool
    total_returned: int


@dataclass(frozen=True)
class RulesetInventoryItem:
    kind: str
    display_type: str
    assay_key: str
    assay_name: str
    path: str
    ruleset_file: str
    field_count: int
    valid: bool
    error: str | None
    modified_at: str = ""
    sha256: str = ""
    read_only: bool = False


@dataclass(frozen=True)
class IngestionInstanceItem:
    ingestion_id: str
    job_id: str
    file_name: str
    source_kind: str
    original_path: str
    current_path: str
    processing_status: str
    queue_status: str
    archive_status: str
    display_status: str
    friendly_message: str
    technical_detail: str
    created_at: str = ""
    updated_at: str = ""
    queue_only: bool = False


@dataclass(frozen=True)
class JobDiagnosisItem:
    job_id: str
    pdf_path: str
    file_name: str
    queue_status: str
    error_label: str
    root_error: str
    context_label: str
    friendly_message: str
    technical_detail: str
    normalized_dump_path: str = ""
    block_dump_paths: tuple[tuple[str, str], ...] = ()
    state_available: bool = False
    context_text: str = ""
    context_truncated: bool = False
    context_available: bool = False
    retry_kind: str = "full_processing"


@dataclass(frozen=True)
class ReportFieldValue:
    field_key: str
    value: str


@dataclass(frozen=True)
class ReportRunOccurrence:
    run_id: int | None
    lot_id: str
    charge: str
    device_id: str
    dedupe_key: str
    created_at: str
    fields: tuple[ReportFieldValue, ...]
    payload_parse_error: str | None = None
    current_validation: RunValidationItem | None = None
    validation_history: tuple[RunValidationItem, ...] = ()
    validation_ambiguous: bool = False
    revision_id: int = 0
    selection_token: str = ""
    store_path: str = ""
    reanalysis_pending: bool = False
    missing_fields: tuple[str, ...] = ()
    assay_name: str = ""
    device_name: str = ""
    revalidation_required: bool = False


@dataclass(frozen=True)
class ReportAssayGroup:
    assay_key: str
    ruleset_file: str
    occurrences: tuple[ReportRunOccurrence, ...]
    assay_display_label: str = ""


@dataclass(frozen=True)
class ReportSummaryItem:
    report_id: str
    job_id: str
    pdf_path: str
    file_name: str
    current_pdf_path: str
    run_count: int
    assay_count: int
    latest_created_at: str
    path_status: str = ""
    pdf_sha256: str = ""
    ingestion_id: str = ""
    earliest_created_at: str = ""
    device_ids: tuple[str, ...] = ()
    assay_keys: tuple[str, ...] = ()
    display_status: str = ""
    archive_status: str = ""
    path_available: bool = False
    validation_status: str = ""
    report_status: str = ""
    assay_names: tuple[str, ...] = ()
    device_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunValidationItem:
    validation_id: int
    run_id: int
    operator_initials: str
    validated_at_utc: str
    comment: str
    supersedes_validation_id: int | None
    created_at_utc: str | None
    excel_export_status: str = "not_required"
    excel_export_error: str = ""
    revision_id: int = 0
    selection_id: int | None = None
    selection_token: str = ""
    device_assignment_id: int = 0


@dataclass(frozen=True)
class ReportPdfPage:
    """One bounded PDF page; image_data contains a standalone RGB PPM image."""

    report_id: str
    page_index: int
    page_count: int
    zoom: float
    width: int
    height: int
    image_data: bytes


@dataclass(frozen=True)
class ValidationQueueItem:
    """One assay run awaiting an effective human validation."""

    report_id: str
    run_id: int
    file_name: str
    current_pdf_path: str
    assay_key: str
    lot_id: str
    device_id: str
    created_at: str
    fields: tuple[ReportFieldValue, ...]
    validation_ambiguous: bool = False
    revision_id: int = 0
    selection_token: str = ""
    store_path: str = ""
    comparison: ReanalysisComparison | None = None
    reanalysis_history: tuple[ReportFieldValue, ...] = ()
    missing_fields: tuple[str, ...] = ()
    revision_error: str = ""
    assay_name: str = ""
    candidate_id: int | None = None
    device_assignment_id: int = 0
    device_context_token: str = ""
    device_options: tuple[tuple[str, str], ...] = ()
    suggested_device_id: str = ""
    revalidation_required: bool = False
    validation_current: bool = False
    device_impact: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultComparisonField:
    field_key: str
    old_value: str
    new_value: str
    changed: bool = False


@dataclass(frozen=True)
class ReanalysisComparison:
    revision_id: int
    fields: tuple[ResultComparisonField, ...]
    metadata: tuple[ResultComparisonField, ...]
    source_verified: bool
    can_keep_old: bool
    can_accept_new: bool
    error: str = ""


@dataclass(frozen=True)
class ReanalysisBatchItem:
    report_id: str
    run_id: int
    revision_id: int | None
    error: str = ""


@dataclass(frozen=True)
class ReanalysisBatchResult:
    items: tuple[ReanalysisBatchItem, ...]
    store_path: str


@dataclass(frozen=True)
class _ValidationIndex:
    """Application-internal validation read model used by ResultsController."""

    latest_by_run_id: dict[int, Any]
    history_by_run_id: dict[int, tuple[Any, ...]]
    ambiguous_run_ids: frozenset[int]


@dataclass(frozen=True)
class ReportDetail:
    report_id: str
    job_id: str
    pdf_path: str
    file_name: str
    current_pdf_path: str
    ingestion_id: str
    path_status: str
    assay_groups: tuple[ReportAssayGroup, ...]
    pdf_sha256: str = ""
    earliest_created_at: str = ""
    latest_created_at: str = ""
    device_ids: tuple[str, ...] = ()
    display_status: str = ""
    archive_status: str = ""
    path_available: bool = False
    validation_status: str = ""
    report_status: str = ""
    store_path: str = ""
    device_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class DuplicateFieldComparisonItem:
    field_key: str
    existing_value: str
    candidate_value: str
    changed: bool


@dataclass(frozen=True)
class DuplicateCandidateItem:
    candidate_id: int
    status: str
    assay_key: str
    dedupe_key: str
    existing_run_id: int
    detected_at: str
    device_id: str = ""
    dedupe_version: str = ""
    pdf_sha256: str = ""
    assay_block_hash: str = ""
    decision_at: str = ""
    decision_by: str = ""
    decision_note: str = ""
    dedupe_basis: dict[str, Any] = field(default_factory=dict)
    candidate_meta: dict[str, Any] = field(default_factory=dict)
    assay_name: str = ""


@dataclass(frozen=True)
class DuplicateExistingRunItem:
    run_id: int
    job_id: str
    pdf_path: str
    assay_key: str
    lot_id: str
    charge: str
    dedupe_key: str
    device_id: str
    dedupe_version: str
    created_at: str
    dedupe_basis: dict[str, Any] = field(default_factory=dict)
    assay_name: str = ""


@dataclass(frozen=True)
class DuplicateCandidateDetail:
    candidate: DuplicateCandidateItem
    existing: DuplicateExistingRunItem | None
    field_comparison: tuple[DuplicateFieldComparisonItem, ...]


@dataclass(frozen=True)
class DuplicateDecisionResult:
    candidate_id: int
    status: str
    action: str
    decision_at: str
    decision_by: str
    decision_note: str


@dataclass(frozen=True)
class AssayCandidateItem:
    candidate_id: str
    assay_key: str
    assay_name_hint: str
    test_file: str
    line_no: str
    line_text: str
    reason: str
    confidence: str
    known_status: str = ""
    assay_name: str = ""


@dataclass(frozen=True)
class WatchTimingSettings:
    scan_interval_s: float
    stable_window_s: float


@dataclass(frozen=True)
class DeviceInventoryItem:
    device_id: str
    display_name: str
    active: bool
    serial_number: str = ""
    lnr: str = ""
    eva: str = ""
    incomplete: bool = False
    legacy: bool = False

    @property
    def choice_label(self) -> str:
        return f"{self.display_name} ({self.device_id})" + (" · unvollständig" if self.incomplete else "")

    @property
    def choice_label(self) -> str:
        return f"{self.display_name} ({self.device_id})" + (" · unvollständig" if self.incomplete else "")


@dataclass(frozen=True)
class DeviceInventoryStatus:
    status: str
    path: str
    message: str
    using_fallback: bool
    devices: tuple[DeviceInventoryItem, ...]
    default_device_id: str


@dataclass(frozen=True)
class QCAssayConfigurationItem:
    assay_key: str
    assay_name: str
    device_id: str = ""
    device_name: str = ""
    profile_id: str = ""
    profile_name: str = ""
    profile_version_id: int = 0
    level_count: int = 0
    status: str = "QK noch nicht eingerichtet"
    issues: tuple[str, ...] = ()
    draft_id: str = ""


@dataclass(frozen=True)
class QCConfigurationState:
    store_path: str
    inventory: dict[str, Any]
    profiles: tuple[dict[str, Any], ...]
    legacy_source_sha256: str = ""
    legacy_message: str = ""
    assays: tuple[tuple[str, str], ...] = ()
    field_choices: dict[str, tuple[str, ...]] = field(default_factory=dict)
    assay_rows: tuple[QCAssayConfigurationItem, ...] = ()
    catalog_error: str = ""
    retained_drafts: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class QCLotCase:
    store_path: str
    lot_key: str
    device_id: str
    device_name: str
    assay_key: str
    kit_lot: str
    state: str
    version_id: int
    profile_version_id: int
    profile_options: tuple[tuple[int, str], ...]
    start_date: str = ""
    assay_name: str = ""
    last_usage: str = ""
    chronology_status: str = "unavailable"
    close_available: bool = False
    close_reason: str = ""


@dataclass(frozen=True)
class QCLotDetail:
    case: QCLotCase
    source_manifest: dict[str, Any]
    sd_references: dict[str, Any]
    chronology_json: str = ""
    chronology_sha256: str = ""
    source_changed: bool = False


@dataclass(frozen=True)
class QCAnalysisView:
    case: QCLotCase
    model_json: str
    model_sha256: str
    evidence_lot_version_id: int | None = None
    pdf_sha256: str = ""

    @property
    def model(self) -> dict[str, Any]:
        return json.loads(self.model_json)


@dataclass(frozen=True)
class QCLotClosePreview:
    detail: QCLotDetail
    analysis: QCAnalysisView
    chronology_json: str
    chronology_sha256: str
    witness_kit_lot: str
    witness_source_token: str
    pdf_bytes: bytes
    pdf_sha256: str
    renderer_id: str
    page_count: int
    block_reason: str = ""


@dataclass(frozen=True)
class QCReportVersion:
    store_path: str
    lot_key: str
    version_id: int
    created_at_utc: str
    profile_version_id: int
    model_sha256: str
    pdf_sha256: str
    source_count: int
