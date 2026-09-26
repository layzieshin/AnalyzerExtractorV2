"""Regelwerk-Lifecycle: inaktivieren und Inventar-Löschung (AP-16D)."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator
from uuid import uuid4

from src.runtime.api import release_exclusive, try_acquire_exclusive

from .errors import RuleSuiteError
from .json_io import _read_json_object, _write_json_atomic
from .templates import draft_path_for_assay

_PROTECTED_FILES = {"index.json", "template.json"}
_LIFECYCLE_LOCK_NAME = ".lifecycle.lock"
_LIFECYCLE_LOCK_TTL_S = 120.0


def _lifecycle_lock_path(project_root: str) -> Path:
    return Path(project_root) / "rules" / _LIFECYCLE_LOCK_NAME


@contextmanager
def rulesuite_lifecycle_lock(project_root: str) -> Iterator[None]:
    """Serialize mutating lifecycle decisions. Release the lock file in every exit path."""
    lock_path = _lifecycle_lock_path(project_root)
    acquired = False
    try:
        acquired = try_acquire_exclusive(lock_path, _LIFECYCLE_LOCK_TTL_S)
        if not acquired:
            raise RuleSuiteError("lifecycle_lock_busy")
        yield
    finally:
        if acquired:
            release_exclusive(lock_path)


_DRAFT_LOCK_TTL_S = 30.0


def _draft_lock_path(draft_path: str | Path) -> Path:
    path = Path(draft_path)
    return path.parent / f".{path.name}.lock"


@contextmanager
def rulesuite_draft_lock(draft_path: str | Path) -> Iterator[None]:
    """Serialize one draft mutation. The lock file lives beside the draft and is always released."""
    lock_path = _draft_lock_path(draft_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    acquired = False
    try:
        acquired = try_acquire_exclusive(lock_path, _DRAFT_LOCK_TTL_S)
        if not acquired:
            raise RuleSuiteError("draft_lock_busy")
        yield
    finally:
        if acquired:
            release_exclusive(lock_path)


def _validate_ruleset_filename(file_name: str) -> str:
    name = file_name.strip()
    if not name:
        raise RuleSuiteError("protected_or_invalid_ruleset_file:")
    lowered = name.lower()
    if lowered in _PROTECTED_FILES:
        raise RuleSuiteError(f"protected_or_invalid_ruleset_file: {name}")
    if name != Path(name).name or ".." in name or "/" in name or "\\" in name:
        raise RuleSuiteError(f"protected_or_invalid_ruleset_file: {name}")
    return name


def _unique_destination(directory: Path, stem: str, suffix: str = ".json") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = directory / f"{stem}.{timestamp}{suffix}"
    counter = 1
    while destination.exists():
        destination = directory / f"{stem}.{timestamp}_{counter}{suffix}"
        counter += 1
    return destination


def _inventory_base_dir(project_root: str, kind: str) -> Path:
    root = Path(project_root)
    if kind == "draft":
        return (root / "rules" / "drafts").resolve()
    if kind == "inactive":
        return (root / "rules" / "inactive").resolve()
    if kind == "active":
        return (root / "rules").resolve()
    raise RuleSuiteError(f"unsupported_inventory_kind: {kind}")


def _resolve_inventory_path(project_root: str, kind: str, path_or_key: str) -> Path:
    if kind == "active":
        raise RuleSuiteError("active_must_be_deactivated_first")

    base = _inventory_base_dir(project_root, kind)
    candidate = Path(path_or_key)
    if not candidate.is_absolute():
        candidate = base / path_or_key
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise RuleSuiteError("path_outside_allowed_directory") from exc
    return resolved


def deactivate_ruleset(project_root: str, assay_key: str) -> Dict[str, Any]:
    with rulesuite_lifecycle_lock(project_root):
        return _deactivate_ruleset_unlocked(project_root, assay_key)


def _deactivate_ruleset_unlocked(project_root: str, assay_key: str) -> Dict[str, Any]:
    key = assay_key.strip()
    if not key:
        raise RuleSuiteError("assay_key required")

    rules_dir = Path(project_root) / "rules"
    index_path = rules_dir / "index.json"
    index = _read_json_object(index_path)
    assays = index.get("assays", [])
    if not isinstance(assays, list):
        raise RuleSuiteError("index.assays must be list")

    target_row = next(
        (row for row in assays if isinstance(row, dict) and str(row.get("assay_key", "")).strip() == key),
        None,
    )
    if target_row is None:
        raise RuleSuiteError(f"assay_not_found: {key}")

    file_name = _validate_ruleset_filename(str(target_row.get("ruleset_file", "")))
    source = rules_dir / file_name
    inactive_path: str | None = None
    if source.exists():
        inactive_dir = rules_dir / "inactive"
        destination = _unique_destination(inactive_dir, source.stem)
        source.replace(destination)
        inactive_path = str(destination)

    index["assays"] = [
        row
        for row in assays
        if not (isinstance(row, dict) and str(row.get("assay_key", "")).strip() == key)
    ]
    _write_json_atomic(index_path, index)

    return {
        "assay_key": key,
        "ruleset_file": file_name,
        "inactive_path": inactive_path,
    }


def delete_inventory_item(project_root: str, kind: str, path_or_key: str) -> Dict[str, Any]:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind == "active":
        raise RuleSuiteError("active_must_be_deactivated_first")
    if normalized_kind in {"history", "trash"}:
        raise RuleSuiteError("read_only_inventory_kind")

    source = _resolve_inventory_path(project_root, normalized_kind, path_or_key)
    if not source.exists():
        raise RuleSuiteError(f"inventory_item_not_found: {source}")

    trash_dir = Path(project_root) / "rules" / "trash"
    destination = _unique_destination(trash_dir, source.stem)
    source.replace(destination)

    return {
        "kind": normalized_kind,
        "source_path": str(source),
        "trash_path": str(destination),
    }


def _resolve_history_path(project_root: str, history_path: str) -> Path:
    base = (Path(project_root) / "rules" / "history").resolve()
    candidate = Path(str(history_path or "").strip())
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise RuleSuiteError("path_outside_allowed_directory") from exc
    if resolved == base or base not in resolved.parents:
        raise RuleSuiteError("path_outside_allowed_directory")
    return resolved


def _contained_draft_path(project_root: str, assay_key: str) -> Path:
    base = (Path(project_root) / "rules" / "drafts").resolve()
    resolved = Path(draft_path_for_assay(project_root, assay_key)).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise RuleSuiteError("path_outside_allowed_directory") from exc
    if resolved == base or base not in resolved.parents:
        raise RuleSuiteError("path_outside_allowed_directory")
    return resolved


def _publish_bytes_exclusive(path: Path, payload: bytes) -> bytes | None:
    """Publish a new file without replacing an existing one.

    Bytes are written to an exclusive temp file, then published with ``os.link``.
    An existing target is left untouched and reported as ``None``.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuleSuiteError("draft_publish_failed") from exc
    if path.exists():
        return None

    tmp = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = None
    try:
        fd = os.open(tmp, flags)
        view = memoryview(payload)
        while view:
            written_count = os.write(fd, view)
            if written_count <= 0:
                raise RuleSuiteError("draft_publish_failed")
            view = view[written_count:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        if path.exists():
            return None
        try:
            os.link(tmp, path)
        except FileExistsError:
            return None
        except OSError as exc:
            if path.exists():
                return None
            raise RuleSuiteError("draft_publish_failed") from exc
        return payload
    except RuleSuiteError:
        raise
    except OSError as exc:
        raise RuleSuiteError("draft_publish_failed") from exc
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        _best_effort_remove(tmp)


def _publish_new_draft_exclusive(path: Path, data: Dict[str, Any]) -> bytes | None:
    """Create a new draft file without replacing an existing one."""
    payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    return _publish_bytes_exclusive(path, payload)


def _best_effort_remove(path: Path) -> None:
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
    except OSError:
        return


def _history_draft_result(
    status: str,
    draft_path: Path,
    assay_key: str,
    assay_name: str,
    history_file: Path,
    warning: str | None = None,
) -> Dict[str, Any]:
    result = {
        "status": status,
        "draft_path": str(draft_path),
        "assay_key": assay_key,
        "assay_name": assay_name,
        "history_path": str(history_file),
    }
    if warning:
        result["warning"] = warning
    return result


def open_history_as_draft(project_root: str, history_path: str) -> Dict[str, Any]:
    history_file = _resolve_history_path(project_root, history_path)
    source_bytes = history_file.read_bytes()
    data = _read_json_object(history_file)
    if history_file.read_bytes() != source_bytes:
        raise RuleSuiteError("history_source_changed_during_read")
    assay_key = str(data.get("assay_key", "")).strip()
    assay_name = str(data.get("assay_name", "")).strip()
    if not assay_key:
        raise RuleSuiteError("history_missing_assay_key")

    draft_path = _contained_draft_path(project_root, assay_key)
    if draft_path.exists():
        return _history_draft_result("exists", draft_path, assay_key, assay_name, history_file)
    if history_file.read_bytes() != source_bytes:
        raise RuleSuiteError("history_source_changed_during_copy")

    written = _publish_new_draft_exclusive(draft_path, data)
    if written is None:
        return _history_draft_result("exists", draft_path, assay_key, assay_name, history_file)
    if history_file.read_bytes() != source_bytes:
        return _history_draft_result(
            "created_with_source_change",
            draft_path,
            assay_key,
            assay_name,
            history_file,
            warning="history_source_changed_during_copy",
        )
    return _history_draft_result("created", draft_path, assay_key, assay_name, history_file)


def open_inactive_as_draft(project_root: str, inactive_path: str) -> Dict[str, Any]:
    inactive_file = _resolve_inventory_path(project_root, "inactive", inactive_path)
    data = _read_json_object(inactive_file)
    assay_key = str(data.get("assay_key", "")).strip()
    assay_name = str(data.get("assay_name", "")).strip()
    if not assay_key:
        raise RuleSuiteError("inactive_missing_assay_key")

    draft_path = Path(draft_path_for_assay(project_root, assay_key))
    if draft_path.exists():
        return {
            "status": "exists",
            "draft_path": str(draft_path),
            "assay_key": assay_key,
            "assay_name": assay_name,
            "inactive_path": str(inactive_file),
        }

    draft_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(draft_path, data)
    return {
        "status": "created",
        "draft_path": str(draft_path),
        "assay_key": assay_key,
        "assay_name": assay_name,
        "inactive_path": str(inactive_file),
    }


def _active_ruleset_path(project_root: str, assay_key: str) -> tuple[Path, str, bytes]:
    key = assay_key.strip()
    if not key:
        raise RuleSuiteError("assay_key required")
    rules_dir = (Path(project_root) / "rules").resolve()
    index = _read_json_object(rules_dir / "index.json")
    assays = index.get("assays", [])
    if not isinstance(assays, list):
        raise RuleSuiteError("index.assays must be list")
    matches = [
        row
        for row in assays
        if isinstance(row, dict) and str(row.get("assay_key", "")).strip() == key
    ]
    if len(matches) != 1:
        if matches:
            raise RuleSuiteError("active_ruleset_identity_ambiguous")
        raise RuleSuiteError(f"assay_not_found: {key}")
    file_name = _validate_ruleset_filename(str(matches[0].get("ruleset_file", "")))
    source = (rules_dir / file_name).resolve()
    try:
        source.relative_to(rules_dir)
    except ValueError as exc:
        raise RuleSuiteError("path_outside_allowed_directory") from exc
    if source.parent != rules_dir or not source.is_file():
        raise RuleSuiteError("path_outside_allowed_directory")
    try:
        source_bytes = source.read_bytes()
        data = json.loads(source_bytes.decode("utf-8"))
    except Exception as exc:
        raise RuleSuiteError(f"json_read_failed: {source}: {exc}") from exc
    if not isinstance(data, dict) or str(data.get("assay_key", "")).strip() != key:
        raise RuleSuiteError("active_ruleset_identity_ambiguous")
    return source, file_name, source_bytes


def _assert_existing_draft_identity(draft_path: Path, assay_key: str) -> None:
    """Accept an existing draft only when it is one object for this assay key."""
    try:
        data = json.loads(draft_path.read_bytes().decode("utf-8"))
    except Exception as exc:
        raise RuleSuiteError("draft_identity_conflict") from exc
    if not isinstance(data, dict) or data.get("assay_key") != assay_key:
        raise RuleSuiteError("draft_identity_conflict")


def _rollback_published_draft(draft_path: Path, source_bytes: bytes, source_changed: bool) -> None:
    """Drop this call's published bytes, or fail closed when the target was replaced."""
    try:
        current = draft_path.read_bytes()
    except OSError as exc:
        raise RuleSuiteError("draft_target_conflict") from exc
    if current != source_bytes:
        raise RuleSuiteError("draft_target_conflict")
    if source_changed:
        _best_effort_remove(draft_path)
        raise RuleSuiteError("active_ruleset_changed_during_copy")
    raise RuleSuiteError("draft_target_conflict")


def open_active_as_draft(project_root: str, assay_key: str) -> Dict[str, Any]:
    """Copy the active ruleset bytes into a draft without replacing an existing draft."""
    key = assay_key.strip()
    source, file_name, source_bytes = _active_ruleset_path(project_root, key)
    draft_path = _contained_draft_path(project_root, key)
    if draft_path.exists():
        _assert_existing_draft_identity(draft_path, key)
        return _active_draft_result("exists", draft_path, key, file_name)
    if source.read_bytes() != source_bytes:
        raise RuleSuiteError("active_ruleset_changed_during_read")
    written = _publish_bytes_exclusive(draft_path, source_bytes)
    if written is None:
        _assert_existing_draft_identity(draft_path, key)
        return _active_draft_result("exists", draft_path, key, file_name)
    try:
        current_source = source.read_bytes()
        current_draft = draft_path.read_bytes()
    except OSError as exc:
        raise RuleSuiteError("draft_target_conflict") from exc
    if current_source != source_bytes or current_draft != source_bytes:
        _rollback_published_draft(draft_path, source_bytes, current_source != source_bytes)
    return _active_draft_result("created", draft_path, key, file_name)


def _active_draft_result(status: str, draft_path: Path, assay_key: str, ruleset_file: str) -> Dict[str, Any]:
    return {
        "status": status,
        "draft_path": str(draft_path),
        "assay_key": assay_key,
        "ruleset_file": ruleset_file,
    }


def _resolve_never_active_draft(project_root: str, draft_path: str) -> Path:
    base = (Path(project_root) / "rules" / "drafts").resolve()
    candidate = Path(str(draft_path or "").strip())
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise RuleSuiteError("path_outside_allowed_directory") from exc
    if resolved.parent != base or not resolved.is_file() or not resolved.name.endswith(".draft.json"):
        raise RuleSuiteError("path_outside_allowed_directory")
    return resolved


def _artifact_assay_key(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuleSuiteError(f"lifecycle_artifact_unreadable: {path}") from exc
    if not isinstance(data, dict):
        raise RuleSuiteError(f"lifecycle_artifact_unreadable: {path}")
    if "assay_key" not in data:
        return None
    raw = data.get("assay_key")
    if not isinstance(raw, str) or not raw.strip():
        raise RuleSuiteError("ruleset_identity_ambiguous")
    return raw.strip()


def _assert_no_activation_trace(project_root: str, assay_key: str) -> None:
    rules_dir = (Path(project_root) / "rules").resolve()
    index_path = rules_dir / "index.json"
    try:
        index = _read_json_object(index_path)
    except RuleSuiteError as exc:
        raise RuleSuiteError(f"lifecycle_artifact_unreadable: {index_path}") from exc
    assays = index.get("assays", [])
    if not isinstance(assays, list):
        raise RuleSuiteError("ruleset_identity_ambiguous")
    for row in assays:
        if not isinstance(row, dict):
            raise RuleSuiteError("ruleset_identity_ambiguous")
        if str(row.get("assay_key", "")).strip() == assay_key:
            raise RuleSuiteError("ruleset_activation_trace")
    roots = [rules_dir]
    for kind in ("inactive", "history", "trash"):
        folder = rules_dir / kind
        if folder.exists():
            if not folder.is_dir():
                raise RuleSuiteError(f"lifecycle_artifact_unreadable: {folder}")
            roots.append(folder)
    seen: set[Path] = set()
    for folder in roots:
        try:
            candidates = list(folder.rglob("*"))
        except OSError as exc:
            raise RuleSuiteError(f"lifecycle_artifact_unreadable: {folder}") from exc
        for path in candidates:
            if path in seen or not path.is_file():
                continue
            if folder == rules_dir and path.parent != rules_dir:
                continue
            seen.add(path)
            if path.name.lower() in _PROTECTED_FILES:
                continue
            if path.suffix.lower() != ".json":
                continue
            found = _artifact_assay_key(path)
            if found == assay_key:
                raise RuleSuiteError("ruleset_activation_trace")


def _discard_quarantine(path: Path) -> None:
    path.unlink()


def _restore_quarantine(quarantine: list[tuple[Path, Path]], snapshots: dict[Path, bytes]) -> None:
    for dest, bak in reversed(quarantine):
        try:
            if bak.exists():
                if not dest.exists():
                    os.replace(bak, dest)
            elif not dest.exists() and dest in snapshots:
                dest.write_bytes(snapshots[dest])
        except OSError:
            continue


def delete_never_active_ruleset(project_root: str, draft_path: str) -> Dict[str, Any]:
    """Delete a draft that has never been activated, plus its readiness proof."""
    with rulesuite_lifecycle_lock(project_root):
        return _delete_never_active_ruleset_unlocked(project_root, draft_path)


def _delete_never_active_ruleset_unlocked(project_root: str, draft_path: str) -> Dict[str, Any]:
    draft = _resolve_never_active_draft(project_root, draft_path)
    original = draft.read_bytes()
    try:
        data = json.loads(original.decode("utf-8"))
    except Exception as exc:
        raise RuleSuiteError(f"lifecycle_artifact_unreadable: {draft}") from exc
    if not isinstance(data, dict):
        raise RuleSuiteError("ruleset_identity_ambiguous")
    raw_key = data.get("assay_key")
    if not isinstance(raw_key, str) or not raw_key.strip():
        raise RuleSuiteError("ruleset_identity_ambiguous")
    assay_key = raw_key.strip()
    expected_name = Path(draft_path_for_assay(project_root, assay_key)).name
    if draft.name != expected_name:
        raise RuleSuiteError("ruleset_identity_ambiguous")
    if draft.read_bytes() != original:
        raise RuleSuiteError("ruleset_identity_ambiguous")
    _assert_no_activation_trace(project_root, assay_key)
    if draft.read_bytes() != original:
        raise RuleSuiteError("ruleset_identity_ambiguous")

    readiness = draft.with_name(draft.name + ".readiness")
    targets = [draft]
    if readiness.exists():
        if not readiness.is_file() or readiness.parent != draft.parent:
            raise RuleSuiteError("ruleset_identity_ambiguous")
        targets.append(readiness)
    snapshots = {path: path.read_bytes() for path in targets}
    quarantine: list[tuple[Path, Path]] = []
    try:
        for path in targets:
            bak = path.with_name(f".{path.name}.{uuid4().hex}.deleting")
            os.replace(path, bak)
            quarantine.append((path, bak))
        for _dest, bak in quarantine:
            _discard_quarantine(bak)
    except Exception as exc:
        _restore_quarantine(quarantine, snapshots)
        raise RuleSuiteError("delete_never_active_failed") from exc
    if draft.exists() or readiness.exists():
        raise RuleSuiteError("delete_never_active_failed")
    return {
        "status": "deleted",
        "draft_path": str(draft),
        "assay_key": assay_key,
        "readiness_removed": readiness in snapshots,
    }


def delete_ruleset(project_root: str, assay_key: str) -> Dict[str, Any]:
    """Compatibility wrapper: deactivates instead of deleting active rules."""
    return deactivate_ruleset(project_root, assay_key)
