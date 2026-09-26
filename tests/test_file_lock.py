import os
import time
from pathlib import Path

from src.runtime.file_lock import is_stale_lock, release_exclusive, try_acquire_exclusive


def test_acquire_and_release(tmp_path: Path):
    lock_path = tmp_path / "test.lock"
    assert try_acquire_exclusive(lock_path, stale_ttl_s=60.0) is True
    assert lock_path.exists()
    release_exclusive(lock_path)
    assert not lock_path.exists()


def test_fresh_lock_blocks(tmp_path: Path):
    lock_path = tmp_path / "held.lock"
    assert try_acquire_exclusive(lock_path, stale_ttl_s=60.0) is True
    assert try_acquire_exclusive(lock_path, stale_ttl_s=60.0) is False
    release_exclusive(lock_path)


def test_stale_lock_is_reclaimed(tmp_path: Path):
    lock_path = tmp_path / "stale.lock"
    lock_path.write_text("", encoding="utf-8")
    old = time.time() - 300.0
    os.utime(lock_path, (old, old))
    assert is_stale_lock(lock_path, stale_ttl_s=60.0) is True
    assert try_acquire_exclusive(lock_path, stale_ttl_s=60.0) is True
    release_exclusive(lock_path)


def test_non_stale_lock_not_reclaimed(tmp_path: Path):
    lock_path = tmp_path / "fresh.lock"
    lock_path.write_text("", encoding="utf-8")
    assert is_stale_lock(lock_path, stale_ttl_s=60.0) is False
    assert try_acquire_exclusive(lock_path, stale_ttl_s=60.0) is False
