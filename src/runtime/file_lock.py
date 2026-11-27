from __future__ import annotations

import os
import time
import json
import uuid
from pathlib import Path


class OwnedFileLease:
    """Kernel-held lease; death closes it and TTL never steals it.

    Release operates on this handle, never unlinks a possibly foreign guard.
    A legacy-visible marker is removed only by an exact owner-byte match.
    """
    def __init__(self, fd: int, *, marker: Path | None = None, marker_bytes: bytes = b""):
        self._fd, self._marker, self._marker_bytes = fd, marker, marker_bytes

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            if self._marker is not None:
                try:
                    if self._marker.read_bytes() == self._marker_bytes:
                        self._marker.unlink()
                except OSError:
                    pass
        finally:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


def try_acquire_owned_lock(path: Path) -> OwnedFileLease | None:
    """Nonblocking persistent guard file. It is intentionally never deleted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return OwnedFileLease(fd)
    except OSError:
        os.close(fd)
        return None


def try_acquire_scoped_exclusive(path: Path, stale_ttl_s: float, *, legacy_stale: bool = True) -> OwnedFileLease | None:
    guard = try_acquire_owned_lock(path.with_name(path.name + ".owner"))
    if guard is None:
        return None
    try:
        if path.exists():
            raw = path.read_bytes()
            try:
                owner = json.loads(raw)
            except (ValueError, UnicodeError):
                owner = None
            ours = isinstance(owner, dict) and owner.get("owned_lock") == 1 and isinstance(owner.get("token"), str)
            if not ours and (not legacy_stale or not is_stale_lock(path, stale_ttl_s)):
                guard.release()
                return None
            if path.read_bytes() != raw:
                guard.release()
                return None
            path.unlink()
        marker = json.dumps({"owned_lock": 1, "token": uuid.uuid4().hex}).encode("utf-8")
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, marker)
        finally:
            os.close(fd)
        guard._marker, guard._marker_bytes = path, marker
        return guard
    except OSError:
        guard.release()
        return None


def is_stale_lock(path: Path, stale_ttl_s: float) -> bool:
    if not path.exists():
        return False
    try:
        lock_mtime = path.stat().st_mtime
        return (time.time() - lock_mtime) > stale_ttl_s
    except Exception:
        return False


def try_acquire_exclusive(path: Path, stale_ttl_s: float) -> bool:
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        if not is_stale_lock(path, stale_ttl_s):
            return False
        try:
            path.unlink(missing_ok=True)
        except (OSError, PermissionError):
            return False
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except (FileExistsError, PermissionError):
            return False
    except PermissionError:
        return False


def release_exclusive(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
