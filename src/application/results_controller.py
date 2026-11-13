from __future__ import annotations

import json
from dataclasses import replace
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from src.dbwriter.api import (
    discard_duplicate_candidate as dbwriter_discard_duplicate_candidate,
    get_duplicate_candidate,
    list_duplicate_candidates,
    ResultRevisionError,
    select_result_revision,
)
from src.ingestion.api import get_import_record, resolve_current_path
from src.jobcontroller.api import get_job_evidence, reanalyze_run
from src.jobqueue.api import list_jobs
from src.qualitycontrol.api import (
    MutationContext, QCAnalysis, QCUsageSnapshot, QualityControlError, analyze_lot, close_lot, configure_lot, export_report_evidence,
    get_report_evidence, get_sd_reference_context, render_analysis_pdf, get_inventory as qc_get_inventory,
    get_lot_sources, get_lot_chronology, get_lot, list_lots, list_profiles, lot_identity, open_lot, reopen_lot,
)
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
    list_run_validations_readonly,
    ValidationStateConflictError,
    validate_run,
)

from .desktop_actions import PathOpener, open_path
from .errors import PathOpenError, PdfPreviewError, QualityControlApplicationError, ReanalysisError, ReportNotFoundError, ValidationConflictError, ValidationInputError
from .models import (
    DesktopSettings,
    QCLotCase,
    QCLotDetail,
    QCLotClosePreview,
    QCAnalysisView,
    QCReportVersion,
    DuplicateCandidateDetail,
    DuplicateCandidateItem,
    DuplicateDecisionResult,
    DuplicateExistingRunItem,
    DuplicateFieldComparisonItem,
    ReportAssayGroup,
    ReportDetail,
    ReportFieldValue,
    ReportPdfPage,
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
    ReanalysisBatchItem,
    ReanalysisBatchResult,
    ReanalysisComparison,
    ResultComparisonField,
)


from .presentation import map_ingestion_display_status
from .pdf_preview import render_pdf_page
from .rules_controller import RuleSuiteController


def _named_rows(rows: list[dict[str, Any]], project_root: Path) -> list[dict[str, Any]]:
    """Presentation only: immutable selected/original name, job evidence, catalog."""
    jobs: dict[str, Any] = {}
    catalog = None
    result = []
    for row in rows:
        key = str(row.get("assay_key") or "")
        selected = int(row.get("revision_id") or 0)
        if selected:
            revision = next((item for item in row.get("result_revisions", []) if item.get("revision_id") == selected), {})
            rules = revision.get("result", {}).get("ruleset", {})
        else:
            rules = row.get("source_provenance", {}).get("ruleset", {})
        name = str(rules.get("assay_name") or "").strip() if isinstance(rules, dict) else ""
        job_id = str(row.get("job_id") or (row.get("meta") or {}).get("job_id") or "")
        if not name and job_id:
            if job_id not in jobs:
                jobs[job_id] = get_job_evidence(project_root, job_id)
            evidence = jobs[job_id]
            steps = evidence.steps if evidence is not None and evidence.state_available else ()
            for field in ("writes", "assays"):
                names = []
                for step in steps:
                    items = step.get(field) if isinstance(step, dict) else None
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if not isinstance(item, dict) or item.get("assay_key") != key:
                            continue
                        candidate = item.get("assay_name")
                        if isinstance(candidate, str) and candidate.strip():
                            names.append(candidate.strip())
                if names:
                    name = " / ".join(dict.fromkeys(names))
                    break
        if not name:
            if catalog is None:
                try:
                    catalog = {item.assay_key: item.assay_name.strip()
                               for item in RuleSuiteController(project_root).list_inventory(kind="active")}
                except (OSError, ValueError, RuntimeError):
                    catalog = {}
            name = catalog.get(key, "")
        result.append({**row, "_assay_name": name or "Assayname fehlt"})
    return result


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

    def _capture_store(self, expected_path: str | None = None) -> dict[str, str]:
        spec = self._store_spec()
        spec["path"] = str(Path(spec["path"]).resolve())
        if expected_path and str(Path(expected_path).resolve()) != spec["path"]:
            raise ValidationConflictError("Der Ergebnisspeicher wurde geaendert. Bitte aktualisieren.")
        return spec

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

    @staticmethod
    def _qc_usage_case(case, usage):
        entry = next((row for row in usage.to_dict()["lots"] if row["kit_lot"] == case.kit_lot), None)
        if entry is None:
            return replace(case, close_reason="Kein Nutzungsnachweis vorhanden.")
        available = entry["close_available"] and case.state != "closed"
        last = entry["last_usage"]["display"] if entry["last_usage"] else "nicht bestimmbar"
        if entry["close_available"]:
            witness = entry["witnesses"][0]
            reason = f"Zuletzt {last}; Charge {witness['kit_lot']} sicher später benutzt: {witness['interval']['display']}."
        elif not entry["last_usage_reliable"]:
            reason = "Letzte Nutzung ungeklärt: Datum, offene Ergebnisauswahl oder Konfiguration prüfen."
        else:
            reason = "Keine sicher spätere Nutzung einer anderen Charge belegt; gleiche oder überlappende Zeitangaben bleiben ungeklärt."
        if case.state == "closed":
            reason = "Bereits abgeschlossen. " + reason
        return replace(case, last_usage=last, chronology_status="proven" if entry["last_usage_reliable"] else "unclear",
            close_available=available, close_reason=reason)

    def list_qc_lots(self) -> tuple[QCLotCase, ...]:
        spec = self._capture_store()
        try:
            inventory = qc_get_inventory(spec)
            devices = {row["device_id"]: row for row in inventory["snapshot"]["devices"]}
            profiles = list_profiles(spec)
            lots = {row["lot_key"]: row for row in list_lots(spec)}
            named = _named_rows(list_result_runs(spec, limit=None)["runs"], self._project_root)
            identities = {(row.get("device_id"), row.get("assay_key"), row.get("lot_id"))
                          for row in named if row.get("lot_id") and row.get("device_id")}
            identities.update((row["device_id"], row["assay_key"], row["kit_lot"]) for row in lots.values())
            for row in named:
                candidate = (row.get("pending_revision") or {}).get("result") or {}
                if isinstance(candidate.get("lot_id"), str) and candidate["lot_id"].strip():
                    identities.add((row.get("device_id"), row.get("assay_key"), candidate["lot_id"]))
            cases, chronology = [], {}
            for device_id, assay, kit_lot in sorted(identities):
                key = lot_identity(device_id, assay, kit_lot)
                lot = lots.get(key)
                options = [(row["version_id"], row["snapshot"]["name"]) for row in profiles
                           if row["snapshot"]["device_id"] == device_id and row["snapshot"]["assay_key"] == assay]
                selected = int(lot["snapshot"]["profile_version_id"]) if lot else (options[0][0] if len(options) == 1 else 0)
                if lot and selected not in {value[0] for value in options}:
                    options.insert(0, (selected, "Gespeichertes Prüfprofil"))
                device = devices.get(device_id, {})
                name = str(device.get("display_name") or f"{device_id} (unvollständig)")
                case = QCLotCase(spec["path"], key, device_id, name, assay, kit_lot,
                    lot["state"] if lot else "unconfigured", int(lot["version_id"]) if lot else 0,
                    selected, tuple(options), str(lot["snapshot"].get("start_date") or "") if lot else "",
                    " / ".join(dict.fromkeys(row["_assay_name"] for row in named
                        if (row.get("device_id"), row.get("assay_key"), row.get("lot_id")) == (device_id, assay, kit_lot))) or "Assayname fehlt")
                if selected:
                    if selected not in chronology:
                        chronology[selected] = get_lot_chronology(spec, profile_version_id=selected)
                    case = self._qc_usage_case(case, chronology[selected])
                else:
                    case = replace(case, close_reason="Bitte ein passendes Prüfprofil ausdrücklich auswählen.")
                cases.append(case)
            return tuple(cases)
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def _qc_case_store(self, case: QCLotCase) -> dict[str, str]:
        try:
            return self._capture_store(case.store_path)
        except ValidationConflictError as exc:
            raise QualityControlApplicationError("Der Ergebnisspeicher wurde gewechselt. Bitte die QC-Chargen neu laden.") from exc

    def get_qc_lot_detail(self, case: QCLotCase, *, profile_version_id: int | None = None) -> QCLotDetail:
        spec = self._qc_case_store(case)
        selected = profile_version_id or case.profile_version_id
        if selected not in {value[0] for value in case.profile_options}:
            raise QualityControlApplicationError("Bitte ein passendes Prüfprofil wählen.")
        try:
            manifest = get_lot_sources(spec, profile_version_id=selected, kit_lot=case.kit_lot)
            if (manifest["device_id"], manifest["assay_key"]) != (case.device_id, case.assay_key):
                raise QualityControlApplicationError("Das Profil gehört zu einem anderen Gerät oder Assay.")
            lot = get_lot(spec, case.lot_key) if case.version_id else None
            if lot and lot["version_id"] != case.version_id:
                raise QualityControlApplicationError("Die Charge wurde geändert. Bitte neu laden.")
            usage = get_lot_chronology(spec, profile_version_id=selected)
            current_case = self._qc_usage_case(replace(case, profile_version_id=selected, start_date=manifest["start_date"] or ""), usage)
            changed = bool(lot and lot["state"] == "closed" and lot["snapshot"]["source_manifest"]["source_token"] != manifest["source_token"])
            return QCLotDetail(current_case, manifest, lot["snapshot"]["sd_references"] if lot else {},
                usage.snapshot_json, usage.snapshot_sha256, changed)
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def save_qc_lot(self, detail: QCLotDetail, sd_references: dict[str, Any], *, operator_initials: str,
                    request_id: str) -> dict[str, Any]:
        case = detail.case
        spec = self._qc_case_store(case)
        try:
            context = MutationContext(operator_initials, request_id)
            if case.state == "unconfigured":
                return open_lot(spec, profile_version_id=case.profile_version_id, kit_lot=case.kit_lot,
                    expected_source_token=detail.source_manifest["source_token"], sd_references=sd_references, context=context)
            if case.state != "open":
                raise QualityControlApplicationError("Die Charge ist abgeschlossen. Bitte zuerst ausdrücklich wieder öffnen.")
            return configure_lot(spec, case.lot_key, expected_version_id=case.version_id,
                profile_version_id=case.profile_version_id, expected_source_token=detail.source_manifest["source_token"],
                sd_references=sd_references, context=context)
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def reopen_qc_lot(self, detail: QCLotDetail, *, operator_initials: str, request_id: str, reason: str) -> dict[str, Any]:
        spec = self._qc_case_store(detail.case)
        try:
            return reopen_lot(spec, detail.case.lot_key, expected_version_id=detail.case.version_id,
                expected_source_token=detail.source_manifest["source_token"], context=MutationContext(operator_initials, request_id, reason))
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def _qc_current_lot(self, case: QCLotCase, spec: dict[str, str]) -> dict[str, Any] | None:
        current = next((row for row in list_lots(spec) if row["lot_key"] == case.lot_key), None)
        if (current["version_id"] if current else 0) != case.version_id:
            raise QualityControlApplicationError("Die Charge wurde geändert. Bitte neu laden.")
        return current

    def _qc_evidence(self, case: QCLotCase, version_id: int, spec: dict[str, str]) -> dict[str, Any]:
        version = next((row for row in list_lots(spec, include_history=True)
                        if row["lot_key"] == case.lot_key and row["version_id"] == version_id and row["state"] == "closed"), None)
        if version is None:
            raise QualityControlApplicationError("Der Nachweis gehört nicht zur ausgewählten Charge.")
        evidence = get_report_evidence(spec, lot_version_id=version_id)
        if evidence is None:
            raise QualityControlApplicationError("Der gespeicherte PDF-Nachweis fehlt.")
        return evidence

    def list_qc_report_versions(self, case: QCLotCase) -> tuple[QCReportVersion, ...]:
        spec = self._qc_case_store(case)
        try:
            result = []
            for row in list_lots(spec, include_history=True):
                if row["lot_key"] != case.lot_key or row["state"] != "closed":
                    continue
                evidence = self._qc_evidence(case, row["version_id"], spec)
                result.append(QCReportVersion(spec["path"], case.lot_key, row["version_id"], evidence["created_at_utc"],
                    row["snapshot"]["profile_version_id"], evidence["model_sha256"], evidence["pdf_sha256"],
                    int(evidence["model"]["source_manifest"]["population_count"])))
            return tuple(result)
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def get_qc_analysis(self, detail: QCLotDetail, *, evidence_lot_version_id: int | None = None) -> QCAnalysisView:
        case = detail.case
        spec = self._qc_case_store(case)
        try:
            archived_id = evidence_lot_version_id if evidence_lot_version_id is not None else (case.version_id if case.state == "closed" else None)
            if archived_id is not None:
                evidence = self._qc_evidence(case, archived_id, spec)
                analysis = QCAnalysis.freeze(evidence["model"])
                if not analysis.is_supported:
                    raise QualityControlApplicationError("Diese gespeicherte Analysefassung kann nicht als Diagramm angezeigt werden; der originale PDF-Nachweis bleibt exportierbar.")
                return QCAnalysisView(case, analysis.model_json, analysis.model_sha256, archived_id, evidence["pdf_sha256"])
            current = self._qc_current_lot(case, spec)
            manifest = get_lot_sources(spec, profile_version_id=case.profile_version_id, kit_lot=case.kit_lot)
            references = current["snapshot"]["sd_references"] if current else {}
            if manifest["source_token"] != detail.source_manifest["source_token"] or references != detail.sd_references:
                raise QualityControlApplicationError("Messwerte, Validierungen oder Referenzen wurden geändert. Bitte neu laden.")
            sd_context = get_sd_reference_context(spec, lot_key=case.lot_key, expected_version_id=case.version_id) if current else {}
            analysis = analyze_lot(manifest, references, sd_reference_context=sd_context)
            names = _named_rows([row for row in list_result_runs(spec, limit=None)["runs"]
                if row.get("id") in {item["run_id"] for item in manifest["population"]}], self._project_root)
            by_id = {row["id"]: row for row in names}
            if any(item["run_id"] not in by_id or
                   (int(by_id[item["run_id"]].get("revision_id") or 0), by_id[item["run_id"]].get("selection_token")) !=
                   (item["revision_id"], item["selection_token"]) for item in manifest["population"]):
                raise QualityControlApplicationError("Die Ergebnisnamen wurden geändert. Bitte neu laden.")
            model = analysis.to_dict()
            model["presentation"] = {"assay_name": " / ".join(dict.fromkeys(row["_assay_name"] for row in names)) or "Assayname fehlt",
                "run_assay_names": {str(row["id"]): row["_assay_name"] for row in names}}
            analysis = QCAnalysis.freeze(model)
            self._qc_current_lot(case, spec)
            return QCAnalysisView(case, analysis.model_json, analysis.model_sha256)
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def list_qc_close_witnesses(self, detail: QCLotDetail) -> tuple[QCLotDetail, ...]:
        spec = self._qc_case_store(detail.case)
        try:
            self._qc_current_lot(detail.case, spec)
            usage = get_lot_chronology(spec, profile_version_id=detail.case.profile_version_id)
            own = next((row for row in usage.to_dict()["lots"] if row["kit_lot"] == detail.case.kit_lot), None)
            identities = {row["kit_lot"] for row in own["witnesses"]} if own else set()
            return tuple(self.get_qc_lot_detail(case, profile_version_id=detail.case.profile_version_id)
                for case in self.list_qc_lots() if case.kit_lot in identities and
                (case.device_id, case.assay_key) == (detail.case.device_id, detail.case.assay_key))
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def prepare_qc_lot_close(self, detail: QCLotDetail) -> QCLotClosePreview:
        """Read-only preparation; cancellation cannot leave an opened/closed lot."""
        case = detail.case
        spec = self._qc_case_store(case)
        try:
            current = self._qc_current_lot(case, spec)
            if case.state == "closed":
                raise QualityControlApplicationError("Die Charge ist bereits abgeschlossen.")
            if current and current["snapshot"]["profile_version_id"] != case.profile_version_id:
                raise QualityControlApplicationError("Die ausgewählte Profiländerung ist noch nicht gespeichert. Bitte zuerst die Chargenkonfiguration speichern.")
            captured = self.get_qc_lot_detail(case)
            if captured.source_manifest["source_token"] != detail.source_manifest["source_token"]:
                raise QualityControlApplicationError("Die Quellen wurden geändert. Bitte neu laden.")
            usage = json.loads(captured.chronology_json)
            own = next((row for row in usage["lots"] if row["kit_lot"] == case.kit_lot), None)
            if not own or not own["witnesses"]:
                raise QualityControlApplicationError(captured.case.close_reason)
            witness = own["witnesses"][0]
            witness_source = get_lot_sources(spec, profile_version_id=case.profile_version_id, kit_lot=witness["kit_lot"])
            analysis_view = self.get_qc_analysis(captured)
            analysis = QCAnalysis(analysis_view.model_json, analysis_view.model_sha256)
            report = render_analysis_pdf(analysis)
            import hashlib
            if (report.model_sha256 != analysis.model_sha256 or report.renderer_id != analysis.to_dict()["renderer_id"]
                    or hashlib.sha256(report.pdf_bytes).hexdigest() != report.pdf_sha256):
                raise QualityControlApplicationError("Die vorbereitete PDF gehört nicht zum eingefrorenen Modell oder ihre Prüfsumme ist ungültig.")
            self._qc_case_store(case)
            self._qc_current_lot(case, spec)
            if get_lot_chronology(spec, profile_version_id=case.profile_version_id).snapshot_sha256 != captured.chronology_sha256:
                raise QualityControlApplicationError("Der Nutzungs- oder Konfigurationsstand wurde während der Vorbereitung geändert. Bitte neu prüfen.")
            latest = self.get_qc_analysis(captured)
            if latest.model_sha256 != analysis_view.model_sha256:
                raise QualityControlApplicationError("Die Auswertung wurde während der Vorbereitung geändert. Bitte neu prüfen.")
            block = "Keine vollständigen, eindeutig validierten Zielchargenwerte. Bitte die ausgeschlossenen Werte klären." if not captured.source_manifest["included"] else ""
            return QCLotClosePreview(captured, analysis_view, captured.chronology_json, captured.chronology_sha256,
                witness["kit_lot"], witness_source["source_token"], report.pdf_bytes, report.pdf_sha256,
                report.renderer_id, report.page_count, block)
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def close_qc_lot(self, preview: QCLotClosePreview, *, operator_initials: str, request_id: str) -> dict[str, Any]:
        """Publish only the exact prepared model/PDF; no final-click rendering."""
        case = preview.detail.case
        spec = self._qc_case_store(case)
        if preview.block_reason:
            raise QualityControlApplicationError(preview.block_reason)
        if preview.analysis.evidence_lot_version_id is not None or preview.analysis.case != case:
            raise QualityControlApplicationError("Bitte einen aktuellen Abschlussvorschlag prüfen.")
        try:
            QCUsageSnapshot(preview.chronology_json, preview.chronology_sha256)
            latest = next((row for row in list_lots(spec) if row["lot_key"] == case.lot_key), None)
            # Exact repeat requests still reach the store's intent check, even
            # after publication changed the head or later sources arrived.
            if latest is None or latest["request_id"] != request_id:
                self._qc_current_lot(case, spec)
                expected = self.get_qc_analysis(preview.detail)
                if expected.model_json != preview.analysis.model_json or expected.model_sha256 != preview.analysis.model_sha256:
                    raise QualityControlApplicationError("Die vorbereitete Auswertung ist veraltet. Bitte neu prüfen.")
            model = QCAnalysis(preview.analysis.model_json, preview.analysis.model_sha256).to_dict()
            return close_lot(spec, case.lot_key, expected_version_id=case.version_id, profile_version_id=case.profile_version_id,
                expected_source_token=preview.detail.source_manifest["source_token"], witness_kit_lot=preview.witness_kit_lot,
                expected_witness_source_token=preview.witness_source_token, expected_chronology_token=preview.chronology_sha256,
                analysis_model=model, pdf_bytes=preview.pdf_bytes, pdf_sha256=preview.pdf_sha256,
                algorithm_id=model["algorithm_id"], renderer_id=preview.renderer_id, context=MutationContext(operator_initials, request_id))
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def export_qc_report(self, case: QCLotCase, *, evidence_lot_version_id: int,
                         destination: str | Path, include_explanations: bool = False) -> dict[str, Any]:
        spec = self._qc_case_store(case)
        try:
            self._qc_evidence(case, evidence_lot_version_id, spec)
            return export_report_evidence(spec, lot_version_id=evidence_lot_version_id, destination=destination, include_explanations=include_explanations)
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def list_assays(self) -> list[ResultAssayItem]:
        rows = list_result_assays(self._store_spec())
        names = _named_rows(list_result_runs(self._store_spec(), limit=None)["runs"], self._project_root)
        return [ResultAssayItem(assay_key=str(row.get("assay_key") or ""), assay_name=" / ".join(dict.fromkeys(
            item["_assay_name"] for item in names if item.get("assay_key") == row.get("assay_key"))) or "Assayname fehlt") for row in rows]

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
        runs = tuple(_to_run_item(row, project_root=self._project_root) for row in _named_rows(list(raw.get("runs") or []), self._project_root))
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
        return _to_run_item(_named_rows([raw], self._project_root)[0], project_root=self._project_root)

    def list_recent_reports(self, *, limit: int = 50) -> list[ReportSummaryItem]:
        spec = self._capture_store()
        raw = list_report_summaries(spec, limit=limit)
        prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        all_run_ids: list[int] = []
        for row in raw.get("reports") or []:
            report_id = str(row.get("report_id") or "")
            detail_raw = get_report_runs(spec, report_id) if report_id else None
            runs = _named_rows(list(detail_raw.get("runs") or []), self._project_root) if detail_raw else []
            prepared.append((row, runs))
            all_run_ids.extend(_run_ids(runs))
        index = self._load_validation_index(all_run_ids, store_spec=spec) if prepared else _empty_validation_index()
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
        spec = self._capture_store()
        raw = get_report_runs(spec, target)
        if raw is None:
            return None
        runs = _named_rows(list(raw.get("runs") or []), self._project_root)
        raw["runs"] = runs
        raw["store_path"] = spec["path"]
        for row in runs:
            row["store_path"] = spec["path"]
        index = self._load_validation_index(_run_ids(runs), store_spec=spec)
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
        spec = self._capture_store()
        path_contexts: dict[tuple[str, str], tuple[str, str, str, bool, str, str]] = {}
        queue_status_by_job = {str(job.job_id): str(job.status) for job in list_jobs(str(self._project_root))}
        terminal_by_job: dict[str, bool] = {}
        open_items: list[ValidationQueueItem] = []
        page_size = 500
        offset = 0
        while True:
            raw = list_result_runs(spec, limit=page_size, offset=offset)
            runs = _named_rows(list(raw.get("runs") or []), self._project_root)
            index = self._load_validation_index(_run_ids(runs), store_spec=spec) if runs else _empty_validation_index()
            for row in runs:
                run_id = row.get("id")
                if run_id is None or row.get("payload_parse_error"):
                    continue
                run_key = int(run_id)
                ambiguous = run_key in index.ambiguous_run_ids
                record = index.latest_by_run_id.get(run_key)
                if record is not None:
                    if _validation_matches_row(record, row) and not ambiguous:
                        continue
                    ambiguous = True
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
                report_id = str(row.get("report_id") or "") or compute_report_id(
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
                        revision_id=int(row.get("revision_id") or 0),
                        selection_token=str(row.get("selection_token") or ""),
                        store_path=spec["path"],
                        comparison=_comparison(row),
                        reanalysis_history=_reanalysis_history(row),
                        missing_fields=tuple(row.get("missing_fields") or ()),
                        revision_error=str(row.get("revision_error") or ""),
                        assay_name=str(row.get("_assay_name") or "Assayname fehlt"),
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
        *,
        expected_selection_token: str | None = None,
        store_path: str | None = None,
        request_id: str | None = None,
    ) -> RunValidationItem:
        spec = self._capture_store(store_path)
        self._require_run_in_report(report_id, run_id, store_spec=spec)
        try:
            record = validate_run(spec, int(run_id), operator_initials, comment,
                expected_selection_token=expected_selection_token, request_id=request_id, project_root=str(self._project_root))
        except ResultValidationError as exc:
            raise _map_validation_error(exc) from exc
        return _to_validation_item(record)

    def correct_report_run(
        self,
        report_id: str,
        run_id: int,
        operator_initials: str,
        comment: str = "",
        *,
        expected_selection_token: str | None = None,
        store_path: str | None = None,
        request_id: str | None = None,
    ) -> RunValidationItem:
        spec = self._capture_store(store_path)
        self._require_run_in_report(report_id, run_id, store_spec=spec)
        try:
            record = correct_validation(spec, int(run_id), operator_initials, comment,
                expected_selection_token=expected_selection_token, request_id=request_id, project_root=str(self._project_root))
        except ResultValidationError as exc:
            raise _map_validation_error(exc) from exc
        return _to_validation_item(record)

    def reanalyze_selected_cases(self, cases: Sequence[ValidationQueueItem], operator_initials: str,
                                 *, request_id: str) -> ReanalysisBatchResult:
        """One captured store, sequential work, per-case results and no validation."""
        captured = tuple(cases)
        if not operator_initials.strip() or not request_id.strip():
            raise ReanalysisError("Bitte Initialen und Anfragekennung angeben.")
        spec = self._capture_store()
        items: list[ReanalysisBatchItem] = []
        seen: set[int] = set()
        for case in captured:
            if case.run_id in seen:
                continue
            seen.add(case.run_id)
            revision_id = None
            error = ""
            try:
                if case.store_path and str(Path(case.store_path).resolve()) != spec["path"]:
                    raise ReanalysisError("Der Ergebnisspeicher wurde geaendert. Bitte aktualisieren.")
                if case.validation_ambiguous or case.revision_error:
                    raise ReanalysisError("Die Ergebnishistorie ist ungeklaert. Bitte zuerst den Datenbestand klaeren.")
                self._require_run_in_report(case.report_id, case.run_id, store_spec=spec)
                result = reanalyze_run(self._project_root, spec, case.run_id,
                    expected_selection_token=case.selection_token, request_id=f"{request_id}:{case.run_id}",
                    operator_initials=operator_initials)
                revision_id = int(result["revision_id"])
                state = get_result_run(spec, case.run_id)
                revision = next(row for row in state["result_revisions"] if row["revision_id"] == revision_id)
                error = str(revision["result"].get("error") or "")
            except (ResultRevisionError, ResultValidationError, ReanalysisError, ValidationInputError, ReportNotFoundError) as exc:
                error = str(exc)
            items.append(ReanalysisBatchItem(case.report_id, case.run_id, revision_id, error))
        return ReanalysisBatchResult(tuple(items), spec["path"])

    def choose_reanalysis_result(self, case: ValidationQueueItem, action: str, operator_initials: str,
                                 *, request_id: str, note: str = "") -> None:
        spec = self._capture_store(case.store_path)
        self._require_run_in_report(case.report_id, case.run_id, store_spec=spec)
        if case.comparison is None:
            raise ReanalysisError("Kein aktueller Vergleich vorhanden. Bitte aktualisieren.")
        try:
            select_result_revision(spec["path"], case.run_id, case.comparison.revision_id,
                expected_selection_token=case.selection_token, action=action, request_id=request_id,
                decided_by=operator_initials, note=note)
        except (ResultRevisionError, ResultValidationError) as exc:
            raise ReanalysisError(str(exc)) from exc

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

    def render_report_pdf_page(self, report_id: str, *, page_index: int = 0, zoom: float = 1.0) -> ReportPdfPage:
        """Resolve a report through ingestion, then render it in an isolated process."""
        detail = self.get_report_detail(report_id)
        if detail is None:
            raise PdfPreviewError("Der Bericht ist nicht mehr verfuegbar. Bitte aktualisieren.")
        if detail.path_status == "ambiguous":
            raise PdfPreviewError("Die PDF-Quelle ist nicht eindeutig. Bitte den Import klaeren.")
        path = str(detail.current_pdf_path or detail.pdf_path or "").strip()
        if not path or not Path(path).is_file():
            raise PdfPreviewError("Die PDF-Quelle wurde nicht gefunden. Bitte den Import pruefen.")
        return render_pdf_page(detail.report_id, path, page_index=page_index, zoom=zoom)

    def list_duplicate_candidates(self, *, status: str = "pending") -> list[DuplicateCandidateItem]:
        rows = list_duplicate_candidates(self._settings_provider().sqlite_path, status=status)
        return [_to_duplicate_candidate_item(row) for row in _named_rows(rows, self._project_root)]

    def get_duplicate_candidate_detail(self, candidate_id: int) -> DuplicateCandidateDetail | None:
        spec = self._capture_store()
        raw = get_duplicate_candidate(spec["path"], int(candidate_id))
        if raw is None:
            return None
        candidate = raw.get("candidate")
        if not isinstance(candidate, dict):
            return None
        existing = raw.get("existing") if isinstance(raw.get("existing"), dict) else {}
        comparison = raw.get("field_comparison")
        if existing.get("run_id"):
            selected = get_result_run(spec, int(existing["run_id"]))
            if selected:
                existing = {
                    **existing,
                    **{key: selected[key] for key in ("lot_id", "dedupe_key", "dedupe_version", "dedupe_basis", "payload")},
                    "_assay_name": _named_rows([selected], self._project_root)[0]["_assay_name"],
                }
                existing_payload, candidate_payload = existing["payload"], candidate.get("payload")
                if isinstance(existing_payload, dict) and isinstance(candidate_payload, dict):
                    comparison = [
                        {"field": key, "existing": existing_payload.get(key), "candidate": candidate_payload.get(key),
                         "same": existing_payload.get(key) == candidate_payload.get(key)}
                        for key in sorted(set(existing_payload) | set(candidate_payload), key=str)
                    ]
        return DuplicateCandidateDetail(
            candidate=_to_duplicate_candidate_item(_named_rows([candidate], self._project_root)[0]),
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

    def _load_validation_index(self, run_ids: list[int], *, store_spec: dict[str, str] | None = None) -> _ValidationIndex:
        spec = store_spec if store_spec is not None else self._capture_store()
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
                listed = list_run_validations_readonly(spec, pending)
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

    def _require_run_in_report(self, report_id: str, run_id: int, *, store_spec: dict[str, str] | None = None) -> dict[str, Any]:
        target = str(report_id or "").strip()
        spec = store_spec if store_spec is not None else self._capture_store()
        raw = get_report_runs(spec, target) if target else None
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
        if row.get("payload_parse_error") or row.get("revision_error") or row.get("pending_revision") or row.get("missing_fields"):
            review_required = True
        run_id = row.get("id")
        if run_id is None:
            continue
        run_key = int(run_id)
        if run_key in index.ambiguous_run_ids:
            review_required = True
            continue
        record = index.latest_by_run_id.get(run_key)
        if record is not None:
            if _validation_matches_row(record, row):
                validated += 1
            else:
                review_required = True
    coverage = _coverage_status(validated, len(runs))
    if review_required or _processing_needs_review(processing_status):
        return coverage, "Prüfung erforderlich"
    return coverage, coverage


def _validation_matches_row(record: RunValidation, row: dict[str, Any]) -> bool:
    return record.revision_id == int(row.get("revision_id") or 0) and record.selection_id == row.get("selection_id")


def _comparison(row: dict[str, Any]) -> ReanalysisComparison | None:
    if row.get("revision_error"):
        return None
    pending = row.get("pending_revision")
    if not pending:
        return None
    candidate = pending["result"]
    old = dict(row.get("source_provenance") or {})
    selected_revision = next((item for item in row["result_revisions"] if item["revision_id"] == row["revision_id"]), None)
    if selected_revision is not None:
        old = dict(selected_revision["result"])
    old.update({key: row.get(key) for key in ("payload", "lot_id", "device_id", "dedupe_key", "dedupe_basis", "dedupe_version", "ruleset_file")})
    old["revision_id"] = int(row.get("revision_id") or 0)
    old["selection_id"] = row.get("selection_id")
    new = dict(candidate)
    new.update({key: pending[key] for key in ("revision_id", "request_id", "created_by", "created_at", "supersedes_revision_id")})
    old_payload = row["payload"]
    new_payload = candidate.get("payload") or {}
    fields = tuple(ResultComparisonField(str(key), _stringify_value(old_payload.get(key)),
        _stringify_value(new_payload.get(key)), old_payload.get(key) != new_payload.get(key))
        for key in sorted(set(old_payload) | set(new_payload), key=str.casefold))
    metadata = tuple(ResultComparisonField(str(key), _metadata_value(old.get(key)),
        _metadata_value(new.get(key)), old.get(key) != new.get(key))
        for key in sorted((set(old) | set(new)) - {"payload"}, key=str.casefold))
    configured = [str(field["key"]) for field in candidate.get("ruleset", {}).get("extract_rules", {}).get("fields", []) if field.get("key")]
    def complete(payload):
        return bool(configured) and all(payload.get(key) is not None and str(payload[key]).strip() for key in configured)
    verified = bool(candidate.get("source_verified") and candidate.get("ruleset") and candidate.get("rule_sha256"))
    old_complete = complete(old_payload)
    new_complete = complete(new_payload)
    error = str(candidate.get("error") or "")
    if not old_complete:
        missing = [key for key in configured if old_payload.get(key) is None or not str(old_payload[key]).strip()]
        error = (error + "\n" if error else "") + "Alte Werte erfuellen den aktuellen Feldvertrag nicht: " + ", ".join(missing)
    return ReanalysisComparison(int(pending["revision_id"]), fields, metadata, verified,
        verified and old_complete and not row.get("revision_error"),
        verified and new_complete and not candidate.get("error") and not row.get("revision_error"), error)


def _metadata_value(value: object) -> str:
    return "" if value is None else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _reanalysis_history(row: dict[str, Any]) -> tuple[ReportFieldValue, ...]:
    if row.get("revision_error"):
        return (ReportFieldValue("Nacharbeit", str(row["revision_error"])),)
    history = []
    for revision in row.get("result_revisions") or []:
        detail = f"{revision['created_at']} | {revision['created_by']} | Anfrage {revision['request_id']}"
        error = revision["result"].get("error")
        history.append(ReportFieldValue(f"Analyse {revision['revision_id']}", detail + (f" | Nacharbeit: {error}" if error else " | vollstaendig")))
    for selection in row.get("result_selections") or []:
        action = "Neue Werte uebernommen" if selection["action"] == "accept_new" else "Alte Werte behalten"
        history.append(ReportFieldValue(f"Auswahl {selection['selection_id']}",
            f"{selection['created_at']} | {selection['decided_by']} | {action} | Revision {selection['revision_id']} | {selection['note']}"))
    return tuple(history)


def _map_validation_error(exc: ResultValidationError) -> ValidationConflictError | ValidationInputError:
    if isinstance(exc, ValidationStateConflictError):
        return ValidationConflictError(str(exc))
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
        revision_id=record.revision_id,
        selection_id=record.selection_id,
        selection_token=record.selection_token,
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
        assay_names=tuple(dict.fromkeys(str(item.get("_assay_name") or "Assayname fehlt") for item in report_runs)),
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
        store_path=str(raw.get("store_path") or ""),
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
            if current_record is not None and not _validation_matches_row(current_record, row):
                ambiguous = True
                current_record = None
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
                    revision_id=int(row.get("revision_id") or 0),
                    selection_token=str(row.get("selection_token") or ""),
                    store_path=str(row.get("store_path") or ""),
                    reanalysis_pending=row.get("pending_revision") is not None,
                    missing_fields=tuple(row.get("missing_fields") or ()),
                    assay_name=str(row.get("_assay_name") or "Assayname fehlt"),
                )
            )
        groups.append(
            ReportAssayGroup(
                assay_key=assay_key,
                ruleset_file=str(first.get("ruleset_file") or ""),
                occurrences=tuple(occurrences),
                assay_display_label=" / ".join(dict.fromkeys(str(row.get("_assay_name") or "Assayname fehlt") for row in assay_rows)),
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
        assay_name=str(row.get("_assay_name") or "Assayname fehlt"),
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
        assay_name=str(row.get("_assay_name") or "Assayname fehlt"),
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
        revision_id=int(row.get("revision_id") or 0),
        selection_token=str(row.get("selection_token") or ""),
        revision_history=tuple(row.get("result_revisions") or ()),
        selection_history=tuple(row.get("result_selections") or ()),
        revision_error=str(row.get("revision_error") or ""),
        assay_name=str(row.get("_assay_name") or "Assayname fehlt"),
    )
