from __future__ import annotations

from pathlib import Path
import hashlib
import tempfile
from typing import Any
from collections.abc import Callable, Iterator

from src.assaycandidate.api import annotate_assay_candidates, canonical_assay_key, find_assay_candidates, load_known_assay_keys
from src.contentsplitter.api import split_assay_sections
from src.jobcontroller.api import get_job_diagnostic_sources, get_job_evidence
from src.normalizer.api import normalize_lines
from src.parser.api import parse
from src.ruleresolver.api import validate_rules_integrity as ruleresolver_validate_rules_integrity
from src.rulesuite.api import (
    AuthoringReadinessError,
    RuleSuiteError,
    REQUIRED_HEADER_FIELD_KEYS,
    activate_draft,
    activate_new_draft,
    add_field,
    adopt_candidate_field,
    adopt_candidate_fields,
    batch_check_fields,
    build_regex_from_builder_spec,
    check_authoring_readiness,
    check_candidates,
    check_required_fields,
    clone_ruleset_to_draft,
    create_blank_draft,
    create_authoring_proof,
    create_draft,
    create_draft_from_ruleset,
    create_draft_from_template,
    create_draft_from_template_if_missing,
    deactivate_ruleset,
    delete_inventory_item,
    delete_never_active_ruleset,
    prepare_draft_discard,
    discard_draft,
    delete_ruleset,
    diff_draft_vs_active,
    draft_path_for_assay,
    duplicate_field,
    derive_draft,
    get_assay_text,
    list_fields,
    list_rulesuite_inventory,
    list_assay_identity_cases,
    confirm_assay_identity_case,
    load_draft,
    locate_fields,
    move_field,
    open_active_as_draft,
    open_history_as_draft,
    open_inactive_as_draft,
    preview_extract,
    read_candidate_fields,
    remove_field,
    rename_field,
    replace_field,
    draft_content_revision,
    restore_draft_snapshot,
    save_draft,
    set_dedupe_fields,
    set_excel_rules,
    set_field_regex,
    set_lot_rule,
    suggest_builder_spec_from_selection,
    suggest_regex_from_selection,
    sync_column_mapping_from_fields,
    test_regex,
    update_draft_meta,
    update_field,
    validate_draft,
    verify_authoring_proof,
)

from .models import (AssayCandidateItem, AssayIdentityCaseItem, AssayIdentityCandidateItem,
                     AssayIdentitySourceItem, AssayIdentityRetryResult, DesktopSettings, RulesetInventoryItem)
from .presentation import friendly_processing_message


class RuleSuiteController:
    def __init__(self, project_root: str | Path, *, settings_provider: Callable[[], DesktopSettings] | None = None,
                 authoring_source_reader: Callable[..., Iterator[dict[str, Any]]] | None = None,
                 identity_job_retry: Callable[..., Any] | None = None,
                 identity_jobs_reader: Callable[[], Any] | None = None,
                 identity_source_location: Callable[..., str] | None = None) -> None:
        self._project_root = Path(project_root).resolve()
        self._settings_provider = settings_provider
        self._authoring_source_reader = authoring_source_reader
        self._identity_job_retry = identity_job_retry
        self._identity_jobs_reader = identity_jobs_reader
        self._identity_source_location = identity_source_location

    def _identity_current_path(self, case, source, *, search_path=None, context_guard=None):
        if self._identity_source_location is None:
            if search_path:
                raise RuleSuiteError("PDF-Wiederfinden ist in diesem Kontext nicht verfügbar.")
            return source["pdf_path"]
        return self._identity_source_location(source["job_id"], pdf_path=source["pdf_path"],
            expected_sha256=source["pdf_sha256"], device_id=source["device_id"], store_path=case["store_path"], search_path=search_path,
            **({"context_guard": context_guard} if context_guard is not None else {}))

    def find_identity_pdf(self, case_id, source_id, search_path, *, store_path, expected_identity_token, context_guard=None):
        case = self._identity_action_case(case_id, store_path=store_path, expected_identity_token=expected_identity_token)
        source = next((row for row in case["sources"] if row["source_id"] == source_id), None)
        if source is None:
            raise RuleSuiteError("identity_case_source_selection_changed")
        return self._identity_current_path(case, source, search_path=search_path, context_guard=context_guard)

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def required_header_field_keys(self) -> tuple[str, ...]:
        return tuple(REQUIRED_HEADER_FIELD_KEYS)

    def load_normalized_pdf_text(self, pdf_path: str) -> str:
        document = parse(pdf_path)
        lines = [line for page in document.pages for line in page.lines]
        return "\n".join(normalize_lines(lines))

    def render_rule_pdf_page(self, pdf_path: str, *, page_index: int = 0, zoom: float = 1.0,
                             expected_sha256: str = "") -> dict[str, Any]:
        """Preview a manually selected local PDF through the existing bounded renderer."""
        from .pdf_preview import render_pdf_page
        from .errors import PdfPreviewError
        path, source_bytes, source_hash = self._rule_pdf_source(pdf_path)
        if expected_sha256 and source_hash != expected_sha256:
            raise PdfPreviewError("Die PDF wurde geändert. Bitte erneut laden und prüfen.")
        with tempfile.TemporaryDirectory(prefix="are-rule-original-") as temporary:
            snapshot = Path(temporary) / "selected.pdf"
            snapshot.write_bytes(source_bytes)
            page = render_pdf_page("", str(snapshot), page_index=page_index, zoom=zoom)
        return {"source_path": str(path), "source_sha256": source_hash, "page": page}

    @staticmethod
    def _rule_pdf_source(pdf_path: str) -> tuple[Path, bytes, str]:
        from .pdf_preview import MAX_PDF_BYTES
        from .errors import PdfPreviewError
        path = Path(pdf_path).resolve()
        if path.suffix.casefold() != ".pdf" or not path.is_file() or path.stat().st_size > MAX_PDF_BYTES:
            raise PdfPreviewError("Die gewählte PDF fehlt oder ist für die Vorschau zu groß.")
        with path.open("rb") as source:
            payload = source.read(MAX_PDF_BYTES + 1)
        if len(payload) > MAX_PDF_BYTES:
            raise PdfPreviewError("Die gewählte PDF ist für die Vorschau zu groß.")
        return path, payload, hashlib.sha256(payload).hexdigest()

    def load_authoring_pdf_context(self, pdf_path: str) -> dict[str, Any]:
        """Worker read: PDF text and the configured section keys for pure UI derivation."""
        known = load_known_assay_keys(str(self._project_root / "rules" / "index.json"))
        if known is None:
            raise ValueError("authoring_pdf_assay_index_unreadable")
        return {"normalized_text": self.load_normalized_pdf_text(pdf_path), "known_assay_keys": tuple(sorted(known))}

    def derive_assay_block(self, normalized_text: str, assay_key: str, assay_name: str, *, known_assay_keys=None) -> str:
        """Use the proof/import section owner, never the editable display name."""
        key = str(assay_key or "").strip()
        name = str(assay_name or "").strip()
        if not key or not name:
            raise ValueError("assay_key and assay_name are required")
        known = load_known_assay_keys(str(self._project_root / "rules" / "index.json")) if known_assay_keys is None else set(known_assay_keys)
        if known is None:
            raise ValueError("authoring_pdf_assay_index_unreadable")
        sections = split_assay_sections(str(normalized_text or ""), known_keys=known | {canonical_assay_key(key)})
        target = next((section for section in sections if section.assay_key == canonical_assay_key(key)), None)
        if target is None:
            raise ValueError("authoring_pdf_assay_header_missing_or_ambiguous")
        return target.text

    def list_inventory(self, kind: str = "all") -> list[RulesetInventoryItem]:
        rows = list_rulesuite_inventory(str(self._project_root), kind=kind)
        return [_to_inventory_item(row) for row in rows]

    def discover_assay_candidates(self, normalized_text: str) -> tuple[AssayCandidateItem, ...]:
        candidates = find_assay_candidates(str(normalized_text or ""))
        known_keys = load_known_assay_keys(str(self._project_root / "rules" / "index.json"))
        annotated = annotate_assay_candidates(candidates, known_keys)
        names = {item.assay_key: item.assay_name for item in self.list_inventory(kind="active")}
        return tuple(_to_assay_candidate_item({**row, "assay_name": names.get(row.get("assay_key"), "")}) for row in annotated)

    def discover_assay_candidates_for_job(self, job_id: str) -> tuple[AssayCandidateItem, ...]:
        sources = get_job_diagnostic_sources(self._project_root, job_id)
        if sources is None:
            return ()
        known_keys = load_known_assay_keys(str(self._project_root / "rules" / "index.json"))
        discovered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for text in [sources.normalized_text, *(text for _, text in sources.block_texts)]:
            if not str(text or "").strip():
                continue
            for candidate in find_assay_candidates(str(text)):
                candidate_id = str(candidate.get("candidate_id") or "")
                if candidate_id and candidate_id in seen:
                    continue
                if candidate_id:
                    seen.add(candidate_id)
                discovered.append(candidate)
        annotated = annotate_assay_candidates(discovered, known_keys)
        names = {item.assay_key: item.assay_name for item in self.list_inventory(kind="active")}
        return tuple(_to_assay_candidate_item({**row, "assay_name": names.get(row.get("assay_key"), "")}) for row in annotated)

    def validate_rules_integrity(self) -> dict[str, Any]:
        rules_dir = self._project_root / "rules"
        index_path = rules_dir / "index.json"
        return ruleresolver_validate_rules_integrity(str(rules_dir), str(index_path))

    def load_draft(self, draft_path: str) -> dict[str, Any]:
        return load_draft(draft_path)

    def save_draft(self, draft_path: str, data: dict[str, Any]) -> str:
        return save_draft(draft_path, data)

    def create_draft(self, assay_key: str) -> str:
        return create_draft(str(self._project_root), assay_key)

    def list_identity_cases(self, *, store_path: str | None = None) -> list[dict[str, Any]]:
        store = store_path if store_path is not None else self._authoring_settings().sqlite_path
        return list_assay_identity_cases(str(self._project_root), store_path=store)

    def _identity_source_done(self, source, evidence, queued, store_path):
        if queued is not None and queued.status != "DONE":
            return False
        from src.jobcontroller.api import verify_completed_job
        return verify_completed_job(self._project_root, source["job_id"], expected_sha256=source["pdf_sha256"],
            expected_pdf_path=source["pdf_path"], store_path=store_path, device_id=source["device_id"])["complete"]

    def get_identity_case_count(self, *, store_path: str) -> int:
        """Status-only count: no PDFs, rule inventories or diagnostic text."""
        cases = self.list_identity_cases(store_path=store_path)
        if not cases:
            return 0
        queue = {item.job_id: item for item in self._identity_jobs_reader()} if self._identity_jobs_reader is not None else {}
        jobs, count = {}, 0
        for case in cases:
            done = []
            for source in case["sources"]:
                key = source["job_id"], source["pdf_sha256"]
                if key not in jobs:
                    jobs[key] = get_job_evidence(self._project_root, key[0], expected_pdf_sha256=key[1], include_context=False)
                done.append(self._identity_source_done(source, jobs[key], queue.get(key[0]), store_path))
            count += not done or not all(done)
        return count

    def list_identity_case_items(self, *, store_path: str) -> list[AssayIdentityCaseItem]:
        cases = self.list_identity_cases(store_path=store_path)
        if not cases:
            return []
        active = {canonical_assay_key(item.assay_key) for item in self.list_inventory(kind="active") if item.valid}
        queue = {item.job_id: item for item in self._identity_jobs_reader()} if self._identity_jobs_reader is not None else {}
        jobs, result = {}, []
        for case in cases:
            sources = []
            for source in case["sources"]:
                job_id, sha = source["job_id"], source["pdf_sha256"]
                if (job_id, sha) not in jobs:
                    jobs[job_id, sha] = get_job_evidence(self._project_root, job_id, expected_pdf_sha256=sha, include_context=False)
                evidence = jobs[job_id, sha]
                queued = queue.get(job_id)
                same_store = evidence is not None and bool(evidence.store_path) and Path(evidence.store_path).resolve() == Path(store_path).resolve()
                same_device = evidence is not None and evidence.device_id == source["device_id"]
                done = self._identity_source_done(source, evidence, queued, store_path)
                status = "Verarbeitet" if done else "Läuft" if queued and queued.status == "PROCESSING" else "Offen"
                message = ""
                if evidence is None or not evidence.state_available:
                    message = "Verarbeitungsnachweis fehlt."
                elif evidence.store_path and not same_store:
                    message = "Verarbeitung gehört zu einem anderen Ergebnisspeicher."
                elif evidence and not same_device:
                    message = "Verarbeitung gehört zu einem anderen Gerät."
                elif evidence.status == "DONE" and not done:
                    message = "Der vollständige gespeicherte Verarbeitungsnachweis fehlt oder passt nicht zu dieser Quelle. Der Fall bleibt offen."
                elif evidence.error:
                    message = friendly_processing_message(evidence.error)
                if queued and queued.status == "FAILED" and queued.last_error:
                    message = friendly_processing_message(queued.last_error)
                    if queued.last_error == "assay_identity_change_pending":
                        status = "Zuordnung offen" if case["status"] != "activated" else "Wiederholung offen"
                elif self._identity_jobs_reader is not None and queued is None and not done:
                    message = "Kein ursprünglicher Importauftrag vorhanden. Die unveränderte PDF über den normalen Import erneut einreichen."
                try:
                    available = Path(self._identity_current_path(case, source)).is_file()
                except (OSError, RuntimeError, ValueError):
                    available = False
                if not available and not done:
                    message = "Die ursprüngliche PDF ist nicht mehr verfügbar."
                sources.append(AssayIdentitySourceItem(source["source_id"], job_id, source["pdf_path"],
                    Path(source["pdf_path"]).name, sha, source["device_id"], status, message, done, available))
            completed = bool(sources) and all(source.done for source in sources)
            activated = case["status"] == "activated" and case["assay_key"] in active
            assignment = case.get("assignment") or {}
            status = "Erledigt" if completed else "Verarbeitung offen" if activated else "Freigabe offen" if case["status"] == "activation_pending" else "Entwurf" if assignment else "Offen"
            result.append(AssayIdentityCaseItem(case["case_id"], case["store_path"], case["identity_token"],
                case["observed_names"][0], case["assay_key"], status,
                tuple(AssayIdentityCandidateItem(row["assay_key"], row["assay_name"] or "Assayname fehlt", row["rule_sha256"]) for row in case["candidate_assays"]),
                tuple(sources), assignment.get("draft_path", ""), assignment.get("source_assay_key", ""),
                assignment.get("initialization", ""), activated and not completed, completed))
        return result

    def _identity_action_case(self, case_id: str, *, store_path: str, expected_identity_token: str | None = None) -> dict[str, Any]:
        if not store_path or Path(store_path).resolve() != Path(self._authoring_settings().sqlite_path).resolve():
            raise RuleSuiteError("identity_case_store_changed")
        case = next((row for row in self.list_identity_cases(store_path=store_path) if row["case_id"] == case_id), None)
        if case is None or (expected_identity_token is not None and case["identity_token"] != expected_identity_token):
            raise RuleSuiteError("identity_case_selection_changed")
        return case

    def get_identity_editor_context(self, case_id: str, *, store_path: str, expected_identity_token: str,
                                    source_id: str = "") -> dict[str, Any]:
        case = self._identity_action_case(case_id, store_path=store_path, expected_identity_token=expected_identity_token)
        draft = str((case.get("assignment") or {}).get("draft_path") or "")
        if not draft:
            raise RuleSuiteError("identity_case_confirmation_required")
        data = self.load_draft(draft)
        if data.get("assay_key") != case["assay_key"]:
            raise RuleSuiteError("identity_case_draft_identity_changed")
        selected = next((source for source in case["sources"] if source["source_id"] == source_id), None) if source_id else next(iter(case["sources"]), None)
        pdf_path, message = "", "Test-PDF bitte im Arbeitsplatz wählen."
        if selected is not None:
            try:
                path, _payload, sha = self._rule_pdf_source(self._identity_current_path(case, selected))
                if sha != selected["pdf_sha256"]:
                    raise RuleSuiteError("identity_case_source_changed")
                pdf_path, message = str(path), ""
            except (OSError, RuntimeError, ValueError):
                message = "Ursprüngliche PDF fehlt oder wurde geändert. Bitte passende Test-PDF wählen."
        return {"case_id": case_id, "draft_path": draft, "draft_data": data, "test_pdf": pdf_path,
                "message": message, "inventory": self.list_inventory()}

    def open_identity_pdf(self, case_id: str, source_id: str, *, store_path: str, path_opener=None) -> str:
        from .desktop_actions import open_path

        case = self._identity_action_case(case_id, store_path=store_path)
        source = next((row for row in case["sources"] if row["source_id"] == source_id), None)
        if source is None:
            raise RuleSuiteError("identity_case_source_selection_changed")
        path, _payload, sha = self._rule_pdf_source(self._identity_current_path(case, source))
        if sha != source["pdf_sha256"]:
            raise RuleSuiteError("identity_case_source_changed")
        open_path(path, opener=path_opener)
        return str(path)

    def prepare_identity_retry(self, case_id: str, *, store_path: str, expected_identity_token: str) -> tuple[dict[str, str], ...]:
        self._identity_action_case(case_id, store_path=store_path, expected_identity_token=expected_identity_token)
        case = next(item for item in self.list_identity_case_items(store_path=store_path) if item.case_id == case_id)
        if case.completed:
            return ()
        if not case.can_retry:
            raise RuleSuiteError("identity_case_tested_activation_required")
        by_job = {}
        for source in case.sources:
            if source.done:
                continue
            if source.job_id in by_job and by_job[source.job_id]["device_id"] != source.device_id:
                raise RuleSuiteError("identity_case_source_device_ambiguous")
            by_job[source.job_id] = {"job_id": source.job_id, "pdf_path": source.pdf_path,
                "expected_sha256": source.pdf_sha256, "device_id": source.device_id, "store_path": case.store_path}
        return tuple(by_job.values())

    def retry_identity_case(self, case_id: str, *, store_path: str, expected_identity_token: str) -> AssayIdentityRetryResult:
        """Explicit case-only follow-up through the already bound queue owner."""
        plan = self.prepare_identity_retry(case_id, store_path=store_path, expected_identity_token=expected_identity_token)
        if self._identity_job_retry is None:
            raise RuleSuiteError("identity_case_retry_unavailable")
        outcomes, errors = [], []
        for source in plan:
            try:
                outcomes.append(self._identity_job_retry(**source))
            except Exception as exc:
                errors.append((source["job_id"], str(exc)))
        return AssayIdentityRetryResult(case_id, store_path, tuple(self.list_identity_case_items(store_path=store_path)),
                                         tuple(outcomes), tuple(errors))

    def confirm_identity_case(
        self, case_id: str, *, store_path: str, expected_identity_token: str,
        source_assay_key: str, expected_rule_sha256: str, initialization: str,
        assay_name: str | None = None,
    ) -> dict[str, Any]:
        if Path(store_path).resolve() != Path(self._authoring_settings().sqlite_path).resolve():
            raise RuleSuiteError("identity_case_store_changed")
        return confirm_assay_identity_case(str(self._project_root), case_id, store_path=store_path,
            expected_identity_token=expected_identity_token, source_assay_key=source_assay_key,
            expected_rule_sha256=expected_rule_sha256, initialization=initialization, assay_name=assay_name)

    def create_blank_draft(self, assay_key: str, assay_name: str) -> str:
        return create_blank_draft(str(self._project_root), assay_key, assay_name)

    def derive_draft(self, source_assay_key: str, new_assay_key: str, new_assay_name: str) -> str:
        return derive_draft(str(self._project_root), source_assay_key, new_assay_key, new_assay_name)

    def clone_ruleset_to_draft(
        self,
        source_assay_key: str,
        target_assay_key: str,
        target_assay_name: str,
        *,
        overwrite: bool = False,
        include_fields: bool = True,
    ) -> dict[str, Any]:
        return clone_ruleset_to_draft(
            str(self._project_root),
            source_assay_key,
            target_assay_key,
            target_assay_name,
            overwrite=overwrite,
            include_fields=include_fields,
        )

    def create_draft_from_template(self, assay_key: str, assay_name: str) -> str:
        return create_draft_from_template(str(self._project_root), assay_key, assay_name)

    def create_draft_from_template_if_missing(self, assay_key: str, assay_name: str) -> dict[str, Any]:
        return create_draft_from_template_if_missing(str(self._project_root), assay_key, assay_name)

    def create_draft_from_ruleset(
        self,
        source_assay_key: str,
        new_assay_key: str,
        new_assay_name: str,
    ) -> str:
        return create_draft_from_ruleset(str(self._project_root), source_assay_key, new_assay_key, new_assay_name)

    def draft_path_for_assay(self, assay_key: str) -> str:
        return draft_path_for_assay(str(self._project_root), assay_key)

    def deactivate_ruleset(self, assay_key: str) -> dict[str, Any]:
        return deactivate_ruleset(str(self._project_root), assay_key)

    def delete_ruleset(self, assay_key: str) -> dict[str, Any]:
        return delete_ruleset(str(self._project_root), assay_key)

    def delete_never_active_ruleset(self, draft_path: str) -> dict[str, Any]:
        return delete_never_active_ruleset(str(self._project_root), draft_path)

    def prepare_draft_discard(self, draft_path: str, *, expected_revision: str | None = None) -> dict[str, Any]:
        return prepare_draft_discard(str(self._project_root), draft_path, expected_revision=expected_revision)

    def discard_draft(self, draft_path: str, *, expected_revision: str, expected_readiness_revision: str | None) -> dict[str, Any]:
        return discard_draft(str(self._project_root), draft_path, expected_revision=expected_revision,
            expected_readiness_revision=expected_readiness_revision)

    def open_active_as_draft(self, assay_key: str) -> dict[str, Any]:
        return open_active_as_draft(str(self._project_root), assay_key)

    def update_draft_meta(
        self,
        draft_path: str,
        *,
        assay_key: str,
        assay_name: str,
        lot_regex: str,
        excel_filename_template: str,
        sheetname_template: str,
        return_receipt: bool = False,
    ) -> str | dict[str, Any]:
        return update_draft_meta(
            draft_path,
            assay_key=assay_key,
            assay_name=assay_name,
            lot_regex=lot_regex,
            excel_filename_template=excel_filename_template,
            sheetname_template=sheetname_template,
            return_receipt=return_receipt,
        )

    def draft_content_revision(self, draft_path: str) -> str:
        return draft_content_revision(draft_path)

    def restore_draft_snapshot(
        self,
        draft_path: str,
        data: dict[str, Any],
        *,
        expected_revision: str | None = None,
        return_receipt: bool = False,
    ) -> str | dict[str, Any]:
        return restore_draft_snapshot(
            draft_path,
            data,
            expected_revision=expected_revision,
            return_receipt=return_receipt,
        )

    def replace_field(
        self,
        draft_path: str,
        selected_key: str,
        *,
        key: str,
        regex: str,
        required: bool,
        search_from: dict[str, Any] | None,
        excel_column: str | None = None,
        dedupe_member: bool | None = None,
        return_receipt: bool = False,
    ) -> str | dict[str, Any]:
        return replace_field(
            draft_path,
            selected_key,
            key=key,
            regex=regex,
            required=required,
            search_from=search_from,
            excel_column=excel_column,
            dedupe_member=dedupe_member,
            return_receipt=return_receipt,
        )

    def delete_inventory_item(self, kind: str, path_or_key: str) -> dict[str, Any]:
        return delete_inventory_item(str(self._project_root), kind, path_or_key)

    def open_history_as_draft(self, history_path: str) -> dict[str, Any]:
        return open_history_as_draft(str(self._project_root), history_path)

    def open_inactive_as_draft(self, inactive_path: str) -> dict[str, Any]:
        return open_inactive_as_draft(str(self._project_root), inactive_path)

    def activate_draft(self, assay_key: str, draft_path: str, *, assay_name: str | None = None,
                       authoring_proof: dict[str, Any] | None = None, expected_mode: str | None = None) -> str:
        report = self._require_authoring_proof(assay_key, draft_path)
        proof = report.get("proof", {})
        if authoring_proof is not None and proof != authoring_proof:
            raise AuthoringReadinessError("authoring_proof_attempt_changed")
        mode = self.diff_draft_vs_active(assay_key, draft_path).get("mode") if assay_name is not None else "update"
        if expected_mode is not None and mode != expected_mode:
            raise AuthoringReadinessError("authoring_proof_active_mapping_changed")
        # The authoring UI supplies intent, never a cached inventory decision.
        # The core rechecks the tested mapping and exact bytes under its lock.
        if assay_name is not None and mode == "create":
            return activate_new_draft(str(self._project_root), assay_key, assay_name, draft_path,
                                      **({"authoring_proof": proof} if proof.get("version") in {1, 2} else {}))
        return activate_draft(str(self._project_root), assay_key, draft_path,
                              **({"authoring_proof": proof} if proof.get("version") in {1, 2} else {}))

    def activate_new_draft(self, assay_key: str, assay_name: str, draft_path: str) -> str:
        report = self._require_authoring_proof(assay_key, draft_path)
        proof = report.get("proof", {})
        return activate_new_draft(str(self._project_root), assay_key, assay_name, draft_path,
                                  **({"authoring_proof": proof} if proof.get("version") in {1, 2} else {}))

    def create_authoring_proof(
        self,
        assay_key: str,
        draft_path: str,
        failing_pdf_path: str,
        reference_pdf_path: str | None = None,
    ) -> dict[str, Any]:
        # Explicit legacy two-PDF callers retain V1. The product's one-Test-PDF
        # action always uses automatic, read-only V2 source discovery.
        return create_authoring_proof(
            str(self._project_root),
            assay_key,
            draft_path,
            failing_pdf_path,
            reference_pdf_path,
            **({"automatic_sources": lambda: self._authoring_sources(assay_key)} if reference_pdf_path is None else {}),
            identity_store_path=str(Path(self._authoring_settings().sqlite_path).resolve()),
        )

    def verify_authoring_proof(self, assay_key: str, draft_path: str) -> dict[str, Any]:
        report = verify_authoring_proof(str(self._project_root), assay_key, draft_path)
        identity_store = report.get("proof", {}).get("identity_case", {}).get("store_path")
        if report.get("ok") and identity_store and Path(self._authoring_settings().sqlite_path).resolve() != Path(identity_store).resolve():
            return {**report, "ok": False, "errors": ["identity_case_store_changed"]}
        source = report.get("proof", {}).get("secondary", {}).get("source", {})
        if report.get("ok") and source.get("store_path") and str(Path(self._authoring_settings().sqlite_path).resolve()) != source["store_path"]:
            return {**report, "ok": False, "errors": ["authoring_proof_source_store_changed"]}
        return report

    def _authoring_settings(self) -> DesktopSettings:
        if self._settings_provider is not None:
            return self._settings_provider()
        from .settings_controller import SettingsController
        return SettingsController(self._project_root).load()

    def _authoring_sources(self, assay_key: str) -> Iterator[dict[str, Any]]:
        reader = self._authoring_source_reader
        if reader is None:
            from .results_controller import ResultsController
            reader = ResultsController(self._project_root, settings_provider=self._authoring_settings)._authoring_sources
        key = canonical_assay_key(assay_key)
        return reader(matches_assay=lambda candidate: canonical_assay_key(candidate) == key)

    def _require_authoring_proof(self, assay_key: str, draft_path: str) -> dict[str, Any]:
        report = self.verify_authoring_proof(assay_key, draft_path)
        if report.get("ok"):
            return report
        errors = ",".join(str(item) for item in report.get("errors", [])) or "authoring_proof_invalid"
        raise AuthoringReadinessError(errors)

    def list_fields(self, assay_key: str) -> list[str]:
        return list_fields(str(self._project_root), assay_key)

    def add_field(
        self,
        draft_path: str,
        key: str,
        regex: str,
        *,
        required: bool = False,
        search_from: dict[str, Any] | None = None,
        excel_column: str | None = None,
        dedupe_member: bool | None = None,
        return_receipt: bool = False,
    ) -> str | dict[str, Any]:
        return add_field(
            draft_path,
            key,
            regex,
            required=required,
            search_from=search_from,
            excel_column=excel_column,
            dedupe_member=dedupe_member,
            return_receipt=return_receipt,
        )

    def remove_field(self, draft_path: str, field_key: str, *, return_receipt: bool = False) -> str | dict[str, Any]:
        return remove_field(draft_path, field_key, return_receipt=return_receipt)

    def rename_field(self, draft_path: str, old_key: str, new_key: str) -> str:
        return rename_field(draft_path, old_key, new_key)

    def duplicate_field(
        self, draft_path: str, source_key: str, new_key: str, *, return_receipt: bool = False
    ) -> str | dict[str, Any]:
        return duplicate_field(draft_path, source_key, new_key, return_receipt=return_receipt)

    def move_field(
        self, draft_path: str, field_key: str, direction: str, *, return_receipt: bool = False
    ) -> str | dict[str, Any]:
        return move_field(draft_path, field_key, direction, return_receipt=return_receipt)

    def update_field(
        self,
        draft_path: str,
        field_key: str,
        *,
        regex: str | None = None,
        required: bool | None = None,
        search_from: dict[str, Any] | None = None,
    ) -> str:
        return update_field(
            draft_path,
            field_key,
            regex=regex,
            required=required,
            search_from=search_from,
        )

    def set_field_regex(self, draft_path: str, field_key: str, regex: str) -> str:
        return set_field_regex(draft_path, field_key, regex)

    def set_lot_rule(self, draft_path: str, regex: str) -> str:
        return set_lot_rule(draft_path, regex)

    def set_dedupe_fields(self, draft_path: str, fields: list[str]) -> str:
        return set_dedupe_fields(draft_path, fields)

    def set_excel_rules(
        self,
        draft_path: str,
        filename_template: str,
        sheet_template: str,
        column_mapping: dict[str, str],
    ) -> str:
        return set_excel_rules(draft_path, filename_template, sheet_template, column_mapping)

    def sync_column_mapping_from_fields(self, draft_path: str) -> str:
        return sync_column_mapping_from_fields(draft_path)

    def get_assay_text(
        self,
        pdf_path: str,
        assay_key: str,
        assay_name: str,
        *,
        draft_path: str | None = None,
    ) -> dict[str, Any]:
        path, payload, source_hash = self._rule_pdf_source(pdf_path)
        with tempfile.TemporaryDirectory(prefix="are-rule-text-") as temporary:
            snapshot = Path(temporary) / "selected.pdf"
            snapshot.write_bytes(payload)
            try:
                out = get_assay_text(str(self._project_root), str(snapshot), assay_key, assay_name, draft_path=draft_path, strict=True)
            except RuleSuiteError as exc:
                if str(exc) not in {"authoring_pdf_assay_header_missing_or_ambiguous", "authoring_pdf_assay_header_ambiguous"}:
                    raise
                # A readable original remains useful for authoring even when no
                # safe text section can be derived. Never substitute full text.
                out = {"assay_block": "", "detected_assays": [], "text_error": str(exc)}
        return {**out, "pdf_path": str(path), "source_sha256": source_hash}

    def test_regex(
        self,
        text: str,
        regex: str,
        *,
        group: int = 1,
        search_from: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return test_regex(text, regex, group=group, search_from=search_from)

    def suggest_regex_from_selection(
        self,
        line_text: str,
        selected_text: str,
        *,
        selection_start: int | None = None,
        selection_end: int | None = None,
    ) -> dict[str, Any]:
        return suggest_regex_from_selection(
            line_text,
            selected_text,
            selection_start=selection_start,
            selection_end=selection_end,
        )

    def suggest_builder_spec_from_selection(
        self,
        line_text: str,
        selected_text: str,
        *,
        selection_start: int | None = None,
        selection_end: int | None = None,
        line_index: int | None = None,
    ) -> dict[str, Any]:
        return suggest_builder_spec_from_selection(
            line_text,
            selected_text,
            selection_start=selection_start,
            selection_end=selection_end,
            line_index=line_index,
        )

    def build_regex_from_builder_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        return build_regex_from_builder_spec(spec)

    def batch_check_fields(self, draft_path: str, assay_text: str, *, group: int = 1) -> dict[str, Any]:
        return batch_check_fields(draft_path, assay_text, group=group)

    def check_required_fields(self, draft_path: str, assay_text: str, *, group: int = 1) -> dict[str, Any]:
        return check_required_fields(draft_path, assay_text, group=group)

    def check_authoring_readiness(
        self,
        draft_path: str,
        assay_text: str | None = None,
        *,
        group: int = 1,
    ) -> dict[str, Any]:
        return check_authoring_readiness(draft_path, assay_text, group=group)

    def locate_fields(self, draft_path: str, assay_text: str, *, group: int = 1) -> dict[str, Any]:
        return locate_fields(draft_path, assay_text, group=group)

    def validate_draft(self, draft_path: str) -> dict[str, Any]:
        return validate_draft(draft_path)

    def diff_draft_vs_active(self, assay_key: str, draft_path: str) -> dict[str, Any]:
        return diff_draft_vs_active(str(self._project_root), assay_key, draft_path)

    def preview_extract(
        self,
        pdf_path: str,
        assay_key: str,
        *,
        draft_path: str | None = None,
    ) -> dict[str, Any]:
        return preview_extract(str(self._project_root), pdf_path, assay_key, draft_path=draft_path, strict=True)

    def read_candidate_fields(
        self,
        *,
        source: str | None = None,
        source_assay_key: str | None = None,
    ) -> dict[str, Any]:
        return read_candidate_fields(
            str(self._project_root),
            source=source,
            source_assay_key=source_assay_key,
        )

    def check_candidates(
        self,
        assay_text: str,
        draft_path: str,
        candidate_source: dict[str, Any],
        *,
        dismissed_keys: tuple[str, ...] | list[str] = (),
        group: int = 1,
    ) -> dict[str, Any]:
        return check_candidates(
            str(self._project_root),
            assay_text,
            draft_path,
            candidate_source,
            dismissed_keys=dismissed_keys,
            group=group,
        )

    def adopt_candidate_field(
        self,
        draft_path: str,
        field_key: str,
        candidate_source: dict[str, Any],
        *,
        regex: str | None = None,
        required: bool | None = None,
        search_from: dict[str, Any] | None = None,
        search_from_set: bool = False,
    ) -> str:
        return adopt_candidate_field(
            str(self._project_root),
            draft_path,
            field_key,
            candidate_source,
            regex=regex,
            required=required,
            search_from=search_from,
            search_from_set=search_from_set,
        )

    def adopt_candidate_fields(
        self,
        draft_path: str,
        candidate_source: dict[str, Any],
        field_keys: list[str] | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        return adopt_candidate_fields(
            str(self._project_root),
            draft_path,
            candidate_source,
            field_keys=field_keys,
            overwrite=overwrite,
        )


def _to_assay_candidate_item(row: dict[str, Any]) -> AssayCandidateItem:
    return AssayCandidateItem(
        candidate_id=str(row.get("candidate_id") or ""),
        assay_key=str(row.get("assay_key") or ""),
        assay_name_hint=str(row.get("assay_name_hint") or ""),
        test_file=str(row.get("test_file") or ""),
        line_no=str(row.get("line_no") or ""),
        line_text=str(row.get("line_text") or ""),
        reason=str(row.get("reason") or ""),
        confidence=str(row.get("confidence") or ""),
        known_status=str(row.get("known_status") or ""),
        assay_name=str(row.get("assay_name") or "Assayname fehlt"),
    )


def _to_inventory_item(row: dict[str, Any]) -> RulesetInventoryItem:
    return RulesetInventoryItem(
        kind=str(row.get("kind") or ""),
        display_type=str(row.get("display_type") or ""),
        assay_key=str(row.get("assay_key") or ""),
        assay_name=str(row.get("assay_name") or ""),
        path=str(row.get("path") or ""),
        ruleset_file=str(row.get("ruleset_file") or ""),
        field_count=int(row.get("field_count") or 0),
        valid=bool(row.get("valid")),
        error=row.get("error"),
        modified_at=str(row.get("modified_at") or ""),
        sha256=str(row.get("sha256") or ""),
        read_only=bool(row.get("read_only")),
    )
