from __future__ import annotations

import os
import time
from pathlib import Path


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
