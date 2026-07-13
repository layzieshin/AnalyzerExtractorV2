from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from src.runtime.api import release_exclusive, try_acquire_exclusive

from .model import QueueJob


class QueueError(RuntimeError):
    pass


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

    def enqueue_pdf_job(self, project_root: str, pdf_path: str, source: str = "watchdog") -> QueueJob:
        pdf = Path(pdf_path)
        if not pdf.exists():
            raise QueueError(f"pdf_not_found: {pdf}")

        queue_dir = self._queue_dir(project_root)
        queue_dir.mkdir(parents=True, exist_ok=True)
        lock_dir = self._lock_dir(project_root)
        lock_dir.mkdir(parents=True, exist_ok=True)

        job_id = self._hash_file(pdf)
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
        }
        if self._try_create(path, data):
            return self._as_job(data)

        existing = self._load(path)
        return self._as_job(existing)

    def claim_next_job(self, project_root: str, worker_id: str) -> QueueJob | None:
        self.recover_stale_jobs(project_root, self.processing_ttl_s)
        queue_dir = self._queue_dir(project_root)
        queue_dir.mkdir(parents=True, exist_ok=True)
        lock_dir = self._lock_dir(project_root)
        lock_dir.mkdir(parents=True, exist_ok=True)

        for p in sorted(queue_dir.glob("*.json")):
            lock_path = lock_dir / f"{p.stem}.claim.lock"
            if not self._acquire_lock(lock_path):
                continue
            try:
                data = self._load(p)
                if data.get("status") != "PENDING":
                    continue
                attempts = int(data.get("attempts", 0)) + 1
                data["attempts"] = attempts
                data["updated_at"] = _now_iso()
                if attempts > self.max_attempts:
                    data["status"] = "FAILED"
                    data["last_error"] = "max_attempts_exceeded"
                    data["worker_id"] = ""
                    self._save(p, data)
                    continue
                data["status"] = "PROCESSING"
                data["worker_id"] = worker_id
                self._save(p, data)
                return self._as_job(data)
            finally:
                self._release_lock(lock_path)
        return None

    def mark_job_done(self, project_root: str, job_id: str, worker_id: str = "") -> QueueJob:
        return self._set_status(
            project_root,
            job_id,
            "DONE",
            "",
            allowed_current={"PROCESSING", "DONE"},
            worker_id=worker_id,
        )

    def mark_job_failed(self, project_root: str, job_id: str, error: str, worker_id: str = "") -> QueueJob:
        return self._set_status(
            project_root,
            job_id,
            "FAILED",
            error,
            allowed_current={"PROCESSING", "FAILED"},
            worker_id=worker_id,
        )

    def mark_job_pending(self, project_root: str, job_id: str, reason: str, worker_id: str = "") -> QueueJob:
        return self._set_status(
            project_root,
            job_id,
            "PENDING",
            reason,
            allowed_current={"PROCESSING", "PENDING", "FAILED"},
            worker_id=worker_id,
            clear_worker=True,
        )

    def retry_failed_job(
        self,
        project_root: str,
        job_id: str,
        reason: str = "retry_requested",
        worker_id: str = "",
    ) -> QueueJob:
        queue_dir = self._queue_dir(project_root)
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

    def list_jobs(self, project_root: str) -> List[QueueJob]:
        queue_dir = self._queue_dir(project_root)
        queue_dir.mkdir(parents=True, exist_ok=True)
        jobs: List[QueueJob] = []
        for p in sorted(queue_dir.glob("*.json")):
            jobs.append(self._as_job(self._load(p)))
        jobs.sort(key=lambda j: (j.updated_at, j.job_id))
        return jobs

    def recover_stale_jobs(self, project_root: str, processing_ttl_s: float) -> int:
        queue_dir = self._queue_dir(project_root)
        queue_dir.mkdir(parents=True, exist_ok=True)
        lock_dir = self._lock_dir(project_root)
        lock_dir.mkdir(parents=True, exist_ok=True)

        recovered = 0
        now = datetime.now(timezone.utc)
        for path in sorted(queue_dir.glob("*.json")):
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
                if age_s <= processing_ttl_s:
                    continue
                data["status"] = "PENDING"
                data["worker_id"] = ""
                data["last_error"] = "stale_processing_requeued"
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
    ) -> QueueJob:
        queue_dir = self._queue_dir(project_root)
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
            current = str(data.get("status", ""))
            if current not in allowed_current:
                raise QueueError(f"invalid_status_transition: {current}->{status}")
            if worker_id:
                current_worker = str(data.get("worker_id", ""))
                if current_worker and current_worker != worker_id:
                    raise QueueError(f"worker_mismatch: expected={current_worker} got={worker_id}")
            data["status"] = status
            data["last_error"] = error
            if clear_worker:
                data["worker_id"] = ""
            data["updated_at"] = _now_iso()
            self._save(path, data)
            return self._as_job(data)
        finally:
            self._release_lock(lock_path)

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

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
        return try_acquire_exclusive(path, self.claim_lock_ttl_s)

    def _release_lock(self, path: Path) -> None:
        release_exclusive(path)

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
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None
