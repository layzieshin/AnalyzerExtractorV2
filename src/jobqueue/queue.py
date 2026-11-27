from __future__ import annotations

import hashlib
import json
import os
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from src.runtime.api import try_acquire_owned_lock, try_acquire_scoped_exclusive

from .model import QueueJob


class QueueError(RuntimeError):
    pass


_ATTEMPT_LEASES: dict[str, object] = {}


def release_attempt(attempt_id: str, *, require_thread: bool = True) -> None:
    owned = _ATTEMPT_LEASES.get(attempt_id)
    if owned is not None:
        lease, thread = owned
        if require_thread and thread != threading.get_ident():
            raise QueueError("attempt_owner_thread_mismatch")
        _ATTEMPT_LEASES.pop(attempt_id)
        lease.release()


class JobQueue:
    def __init__(
        self,
        processing_ttl_s: float = 300.0,
        claim_lock_ttl_s: float = 120.0,
        max_attempts: int = 5,
    ) -> None:
        self.processing_ttl_s = processing_ttl_s
        self.claim_lock_ttl_s = claim_lock_ttl_s
        self.max_attempts = max_attempts
        self._short_leases = {}
        self._binding_cache = {}

    def _binding(self, project_root, data):
        root = str(Path(project_root).resolve())
        if root not in self._binding_cache:
            from src.rulesuite.api import list_assay_identity_job_bindings
            self._binding_cache[root] = list_assay_identity_job_bindings(root)
        binding = self._binding_cache[root].get(str(data.get("job_id") or ""))
        stored = data.get("identity_binding")
        if binding is None:
            if stored:
                raise QueueError("identity_case_binding_evidence_missing")
            return None
        if binding.get("error"):
            raise QueueError(binding["error"])
        same_path = os.path.normcase(str(Path(str(data.get("pdf_path") or "")).resolve())) == binding["pdf_path"]
        if same_path and not data.get("content_sha256"):
            # A genuinely complete old SQLite receipt can qualify a legacy
            # queue row without a full SHA; path/name/PID alone cannot.
            if self._completion(project_root, data, binding)["complete"]:
                data["content_sha256"] = binding["content_sha256"]
        if not same_path or data.get("content_sha256") != binding["content_sha256"]:
            raise QueueError("identity_case_binding_source_mismatch")
        if stored and any(stored.get(key) != binding[key] for key in ("job_id", "content_sha256", "pdf_path", "store_path", "device_id")):
            raise QueueError("identity_case_binding_changed")
        data["identity_binding"] = dict(binding)
        return binding

    def enqueue_pdf_job(
        self,
        project_root: str,
        pdf_path: str,
        source: str = "watchdog",
        *,
        expected_sha256: str | None = None,
    ) -> QueueJob:
        pdf = Path(pdf_path)
        self._binding_cache = {}
        if not pdf.exists():
            raise QueueError(f"pdf_not_found: {pdf}")

        content_sha256 = self._hash_file_full(pdf)
        if expected_sha256 is not None and expected_sha256 != content_sha256:
            raise QueueError(
                f"content_sha256_mismatch: expected={expected_sha256} actual={content_sha256}"
            )

        queue_dir = self._queue_dir(project_root)
        queue_dir.mkdir(parents=True, exist_ok=True)
        lock_dir = self._lock_dir(project_root)
        lock_dir.mkdir(parents=True, exist_ok=True)

        job_id = content_sha256[:16]
        path = queue_dir / f"{job_id}.json"
        now = _now_iso()

        data: Dict[str, object] = {
            "job_id": job_id,
            "pdf_path": str(pdf),
            "status": "PENDING",
            "created_at": now,
            "updated_at": now,
            "source": source,
            "worker_id": "",
            "attempts": 0,
            "last_error": "",
            "content_sha256": content_sha256,
        }
        if self._binding(project_root, data):
            # A newly and explicitly submitted manual import is not a retry of
            # an old queue row. It may be claimed once, only in the recorded
            # store/device/source context; it is never a generic PENDING job.
            data["identity_manual_submit"] = source in {"manual", "test-app-manual"}
            if not data["identity_manual_submit"]:
                data["status"], data["last_error"] = "FAILED", "assay_identity_change_pending"
        if self._try_create(path, data):
            return self._as_job(data)

        existing = self._load(path)
        existing_sha = str(existing.get("content_sha256") or "")
        if existing_sha and existing_sha != content_sha256:
            raise QueueError(
                f"content_sha256_collision: job_id={job_id} "
                f"existing={existing_sha} new={content_sha256}"
            )
        return self._as_job(existing)

    def claim_next_job(self, project_root: str, worker_id: str, *, job_id: str | None = None,
                       retry_failed: bool = False, expected_sha256: str | None = None,
                       expected_pdf_path: str | None = None, store_path: str | None = None,
                       device_id: str | None = None, managed_attempt: bool = False) -> QueueJob | None:
        self._binding_cache = {}
        if retry_failed and not job_id:
            raise QueueError("exact_job_required_for_retry")
        self.recover_stale_jobs(project_root, self.processing_ttl_s, job_id=job_id, _keep_cache=True)
        queue_dir = self._queue_dir(project_root)
        queue_dir.mkdir(parents=True, exist_ok=True)
        lock_dir = self._lock_dir(project_root)
        lock_dir.mkdir(parents=True, exist_ok=True)

        for p in sorted(queue_dir.glob("*.json")):
            if job_id is not None and p.stem != job_id:
                continue
            lock_path = lock_dir / f"{p.stem}.claim.lock"
            if not self._acquire_lock(lock_path):
                continue
            try:
                data = self._load(p)
                current = data.get("status")
                if current != "PENDING" and not (retry_failed and current == "FAILED"):
                    continue
                try:
                    binding = self._binding(project_root, data)
                except QueueError as exc:
                    data["status"], data["last_error"] = "FAILED", str(exc)
                    self._save(p, data)
                    if job_id is not None:
                        raise
                    continue
                if binding:
                    from src.runtime.api import resolve_device_id
                    selected_device = resolve_device_id(project_root, device_id,
                        store_spec={"driver": "sqlite", "path": store_path}) if store_path else device_id
                    matches = (job_id == data["job_id"] and expected_sha256 == binding["content_sha256"]
                               and expected_pdf_path is not None and os.path.normcase(str(Path(expected_pdf_path).resolve())) == binding["pdf_path"]
                               and store_path is not None and os.path.normcase(str(Path(store_path).resolve())) == binding["store_path"]
                               and selected_device == binding["device_id"])
                    manual = (current == "PENDING" and data.get("identity_manual_submit") is True
                              and store_path is not None and os.path.normcase(str(Path(store_path).resolve())) == binding["store_path"]
                              and selected_device == binding["device_id"] and job_id in {None, data["job_id"]})
                    matches = matches or manual
                    if not matches:
                        if current == "PENDING" and data.get("identity_manual_submit") is True:
                            # A foreign poll must not consume this protected
                            # explicit submission. Only its correct worker may
                            # claim it; unlike a stale old global PENDING row.
                            if job_id is not None:
                                raise QueueError("identity_case_bound_retry_required")
                            continue
                        # Old deferred/PENDING rows are checked before the
                        # first ordinary worker can accidentally claim them.
                        # A genuine complete DB receipt only reconciles queue.
                        if self._reconcile_bound_if_complete(project_root, data, binding):
                            self._save(p, data)
                            continue
                        data["status"], data["last_error"] = "FAILED", "assay_identity_change_pending"
                        self._save(p, data)
                        if job_id is not None:
                            raise QueueError("identity_case_bound_retry_required")
                        continue
                if expected_sha256 is not None and data.get("content_sha256") != expected_sha256:
                    raise QueueError("source_changed_since_ingest: queue_identity_mismatch")
                if expected_pdf_path is not None and os.path.normcase(str(Path(str(data.get("pdf_path") or "")).resolve())) != os.path.normcase(str(Path(expected_pdf_path).resolve())):
                    raise QueueError("source_changed_since_ingest: queue_path_mismatch")
                if retry_failed and current == "FAILED":
                    data["attempts"] = 0
                    data["last_error"] = "identity_case_retry"
                attempt_id = ""
                if binding or managed_attempt:
                    lease = try_acquire_owned_lock(self._lock_dir(project_root) / f"{p.stem}.attempt.owner")
                    if lease is None:
                        continue
                    attempt_id = uuid.uuid4().hex
                    _ATTEMPT_LEASES[attempt_id] = lease, threading.get_ident()
                attempts = int(data.get("attempts", 0)) + 1
                data["attempts"] = attempts
                data["updated_at"] = _now_iso()
                if attempts > self.max_attempts:
                    data["status"] = "FAILED"
                    data["last_error"] = "max_attempts_exceeded"
                    data["worker_id"] = ""
                    self._save(p, data)
                    release_attempt(attempt_id)
                    continue
                data["status"] = "PROCESSING"
                data.pop("identity_manual_submit", None)
                data["worker_id"] = worker_id
                data["attempt_id"] = attempt_id
                try:
                    self._save(p, data)
                except Exception:
                    release_attempt(attempt_id)
                    raise
                return self._as_job(data)
            finally:
                self._release_lock(lock_path)
        return None

    def mark_job_done(self, project_root: str, job_id: str, worker_id: str = "", *, attempt_id: str | None = None) -> QueueJob:
        return self._set_status(
            project_root,
            job_id,
            "DONE",
            "",
            allowed_current={"PROCESSING", "DONE"},
            worker_id=worker_id,
            attempt_id=attempt_id,
        )

    def mark_job_failed(self, project_root: str, job_id: str, error: str, worker_id: str = "", *, attempt_id: str | None = None) -> QueueJob:
        return self._set_status(
            project_root,
            job_id,
            "FAILED",
            error,
            allowed_current={"PROCESSING", "FAILED"},
            worker_id=worker_id,
            attempt_id=attempt_id,
        )

    def mark_job_pending(self, project_root: str, job_id: str, reason: str, worker_id: str = "", *, attempt_id: str | None = None) -> QueueJob:
        return self._set_status(
            project_root,
            job_id,
            "PENDING",
            reason,
            allowed_current={"PROCESSING", "PENDING", "FAILED"},
            worker_id=worker_id,
            clear_worker=True,
            attempt_id=attempt_id,
        )

    def retry_failed_job(
        self,
        project_root: str,
        job_id: str,
        reason: str = "retry_requested",
        worker_id: str = "",
    ) -> QueueJob:
        queue_dir = self._queue_dir(project_root)
        self._binding_cache = {}
        queue_dir.mkdir(parents=True, exist_ok=True)
        lock_dir = self._lock_dir(project_root)
        lock_dir.mkdir(parents=True, exist_ok=True)
        path = queue_dir / f"{job_id}.json"
        if not path.exists():
            raise QueueError(f"job_not_found: {job_id}")
        lock_path = lock_dir / f"{job_id}.claim.lock"
        if not self._acquire_lock(lock_path):
            raise QueueError(f"job_locked: {job_id}")
        try:
            data = self._load(path)
            if self._binding(project_root, data):
                raise QueueError("identity_case_bound_retry_required")
            current = str(data.get("status", ""))
            if current != "FAILED":
                raise QueueError(f"job_not_failed: {job_id}")
            data["status"] = "PENDING"
            data["attempts"] = 0
            data["worker_id"] = ""
            data["last_error"] = reason
            data["updated_at"] = _now_iso()
            self._save(path, data)
            return self._as_job(data)
        finally:
            self._release_lock(lock_path)

    def list_jobs(self, project_root: str, *, create_missing: bool = True) -> List[QueueJob]:
        queue_dir = self._queue_dir(project_root)
        if create_missing:
            queue_dir.mkdir(parents=True, exist_ok=True)
        jobs: List[QueueJob] = []
        for p in sorted(queue_dir.glob("*.json")):
            jobs.append(self._as_job(self._load(p)))
        jobs.sort(key=lambda j: (j.updated_at, j.job_id))
        return jobs

    @staticmethod
    def _completion(project_root, data, binding):
        from src.jobcontroller.api import verify_completed_job
        return verify_completed_job(project_root, data["job_id"], expected_sha256=binding["content_sha256"],
            expected_pdf_path=binding["pdf_path"], store_path=binding["store_path"], device_id=binding["device_id"])

    def _reconcile_bound_if_complete(self, project_root, data, binding):
        lease = try_acquire_owned_lock(self._lock_dir(project_root) / f"{data['job_id']}.attempt.owner")
        if lease is None:
            return False
        try:
            if not self._completion(project_root, data, binding)["complete"]:
                return False
            data.update(status="DONE", worker_id="", last_error="", updated_at=_now_iso())
            return True
        finally:
            lease.release()

    def reconcile_completed_job(self, project_root, job_id, *, expected_sha256, expected_pdf_path, store_path, device_id):
        """Reconcile only queue after a real, complete persisted job outcome."""
        self._binding_cache = {}
        path = self._queue_dir(project_root) / f"{job_id}.json"
        if not path.is_file():
            raise QueueError("identity_case_queue_job_missing")
        lock = self._lock_dir(project_root) / f"{job_id}.claim.lock"
        if not self._acquire_lock(lock):
            raise QueueError(f"job_locked: {job_id}")
        try:
            data = self._load(path)
            binding = self._binding(project_root, data)
            if binding is None:
                return None  # Ordinary/legacy queue completion is unchanged.
            requested = {"content_sha256": expected_sha256, "pdf_path": os.path.normcase(str(Path(expected_pdf_path).resolve())),
                         "store_path": os.path.normcase(str(Path(store_path).resolve())), "device_id": device_id}
            if binding is None or any(binding[key] != value for key, value in requested.items()):
                raise QueueError("identity_case_bound_context_mismatch")
            receipt = self._completion(project_root, data, binding)
            if not receipt["complete"]:
                raise QueueError(receipt["reason"])
            if not self._reconcile_bound_if_complete(project_root, data, binding):
                raise QueueError("identity_case_attempt_still_active")
            self._save(path, data)
            return self._as_job(data)
        finally:
            self._release_lock(lock)

    def recover_stale_jobs(self, project_root: str, processing_ttl_s: float, *, job_id: str | None = None, _keep_cache: bool = False) -> int:
        if not _keep_cache:
            self._binding_cache = {}
        queue_dir = self._queue_dir(project_root)
        queue_dir.mkdir(parents=True, exist_ok=True)
        lock_dir = self._lock_dir(project_root)
        lock_dir.mkdir(parents=True, exist_ok=True)

        recovered = 0
        now = datetime.now(timezone.utc)
        for path in sorted(queue_dir.glob("*.json")):
            if job_id is not None and path.stem != job_id:
                continue
            lock_path = lock_dir / f"{path.stem}.claim.lock"
            if not self._acquire_lock(lock_path):
                continue
            try:
                data = self._load(path)
                if data.get("status") != "PROCESSING":
                    continue
                updated = _parse_iso(str(data.get("updated_at", "")))
                if updated is None:
                    continue
                age_s = (now - updated).total_seconds()
                modern = bool(data.get("attempt_id"))
                if not modern and age_s <= processing_ttl_s:
                    continue
                lease = try_acquire_owned_lock(lock_dir / f"{path.stem}.attempt.owner")
                if lease is None:
                    continue  # A living attempt cannot be overtaken, at any age.
                lease.release()
                try:
                    binding = self._binding(project_root, data)
                except QueueError as exc:
                    data.update(status="FAILED", worker_id="", last_error=str(exc), updated_at=_now_iso())
                    self._save(path, data)
                    if job_id is not None:
                        raise
                    recovered += 1
                    continue
                data["status"] = "FAILED" if binding else "PENDING"
                data["worker_id"] = ""
                data["last_error"] = "identity_case_attempt_interrupted" if binding else "stale_processing_requeued"
                data["updated_at"] = _now_iso()
                self._save(path, data)
                recovered += 1
            finally:
                self._release_lock(lock_path)
        return recovered

    def _set_status(
        self,
        project_root: str,
        job_id: str,
        status: str,
        error: str,
        allowed_current: set[str],
        worker_id: str = "",
        clear_worker: bool = False,
        attempt_id: str | None = None,
    ) -> QueueJob:
        queue_dir = self._queue_dir(project_root)
        self._binding_cache = {}
        queue_dir.mkdir(parents=True, exist_ok=True)
        lock_dir = self._lock_dir(project_root)
        lock_dir.mkdir(parents=True, exist_ok=True)
        path = queue_dir / f"{job_id}.json"
        if not path.exists():
            raise QueueError(f"job_not_found: {job_id}")
        lock_path = lock_dir / f"{job_id}.claim.lock"
        if not self._acquire_lock(lock_path):
            raise QueueError(f"job_locked: {job_id}")
        try:
            data = self._load(path)
            binding = self._binding(project_root, data)
            current = str(data.get("status", ""))
            if current not in allowed_current:
                raise QueueError(f"invalid_status_transition: {current}->{status}")
            if worker_id:
                current_worker = str(data.get("worker_id", ""))
                if current_worker and current_worker != worker_id:
                    raise QueueError(f"worker_mismatch: expected={current_worker} got={worker_id}")
            current_attempt = str(data.get("attempt_id") or "")
            if attempt_id is not None and attempt_id != current_attempt:
                raise QueueError("attempt_mismatch")
            if binding and (not attempt_id or attempt_id not in _ATTEMPT_LEASES):
                raise QueueError("identity_case_attempt_owner_required")
            owned = _ATTEMPT_LEASES.get(current_attempt)
            if current_attempt and (owned is None or (binding and owned[1] != threading.get_ident())):
                raise QueueError("attempt_owner_required")
            if binding and status == "DONE":
                from src.jobcontroller.api import verify_completed_job
                receipt = verify_completed_job(project_root, job_id, expected_sha256=binding["content_sha256"],
                    expected_pdf_path=binding["pdf_path"], store_path=binding["store_path"], device_id=binding["device_id"])
                if not receipt["complete"]:
                    raise QueueError(receipt["reason"])
            if binding and status == "PENDING":
                status = "FAILED"
            data["status"] = status
            data["last_error"] = error
            if clear_worker:
                data["worker_id"] = ""
            data["updated_at"] = _now_iso()
            self._save(path, data)
            if current_attempt:
                release_attempt(current_attempt, require_thread=bool(binding))
            return self._as_job(data)
        finally:
            self._release_lock(lock_path)

    def _hash_file_full(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def verify_job_content_sha256(self, project_root: str, job_id: str) -> None:
        path = self._queue_dir(project_root) / f"{job_id}.json"
        if not path.exists():
            raise QueueError(f"job_not_found: {job_id}")
        data = self._load(path)
        expected = str(data.get("content_sha256") or "")
        if not expected:
            return
        pdf = Path(str(data.get("pdf_path", "")))
        if not pdf.is_file():
            raise QueueError("source_changed_since_ingest: pdf_missing")
        actual = self._hash_file_full(pdf)
        if actual != expected:
            raise QueueError("source_changed_since_ingest")

    def _queue_dir(self, project_root: str) -> Path:
        root = Path(project_root)
        return root / "jobs" / "queue"

    def _lock_dir(self, project_root: str) -> Path:
        root = Path(project_root)
        return root / "jobs" / "queue_locks"

    def _load(self, path: Path) -> Dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, path: Path, data: Dict[str, object]) -> None:
        tmp = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _try_create(self, path: Path, data: Dict[str, object]) -> bool:
        payload = json.dumps(data, indent=2).encode("utf-8")
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        try:
            os.write(fd, payload)
            return True
        finally:
            os.close(fd)

    def _acquire_lock(self, path: Path) -> bool:
        lease = try_acquire_scoped_exclusive(path, self.claim_lock_ttl_s)
        if lease is None:
            return False
        self._short_leases[str(path)] = lease
        return True

    def _release_lock(self, path: Path) -> None:
        lease = self._short_leases.pop(str(path), None)
        if lease is not None:
            lease.release()

    def _as_job(self, data: Dict[str, object]) -> QueueJob:
        return QueueJob(
            job_id=str(data.get("job_id", "")),
            pdf_path=str(data.get("pdf_path", "")),
            status=str(data.get("status", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            source=str(data.get("source", "")),
            worker_id=str(data.get("worker_id", "")),
            attempts=int(data.get("attempts", 0)),
            last_error=str(data.get("last_error", "")),
            content_sha256=str(data.get("content_sha256") or ""),
            attempt_id=str(data.get("attempt_id") or ""),
            identity_binding=dict(data.get("identity_binding") or {}),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None
