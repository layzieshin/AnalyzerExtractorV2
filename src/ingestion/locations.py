"""Verified current locations; original imports/results/proofs stay immutable."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

from src.runtime.api import try_acquire_owned_lock

from .models import PathResolution
from .monthly_files import PlainHandle, create_directories, inspect_file, path_key, plain_path
from .monthly_models import MonthlyArchiveError


def _folder(root):
    return Path(root) / "storage" / "ingestion" / "locations"


def _key(original, digest):
    return hashlib.sha256(f"{path_key(original)}\n{digest}".encode()).hexdigest()


def _load(root):
    path = _folder(root) / "verified.json"
    if not path.exists():
        return {"version": 1, "sources": {}}
    plain_path(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("version") != 1 or not isinstance(value.get("sources"), dict):
        raise MonthlyArchiveError("Verifizierte PDF-Orte sind nicht lesbar.")
    return value


def register_pdf_location(project_root, original_path, expected_sha256, current_path, *, origin="manual", context_guard=None):
    """Register only an exact-hash normal file, without rewriting provenance."""
    current = plain_path(current_path)
    digest, _, _ = inspect_file(current)
    if digest != expected_sha256 or len(digest) != 64:
        raise MonthlyArchiveError("Die gewählte PDF entspricht nicht dem vollständigen Original-SHA.")
    folder = create_directories(_folder(project_root))
    lease = try_acquire_owned_lock(folder / "locations.owner")
    if lease is None:
        raise MonthlyArchiveError("PDF-Ortszuordnung wird gerade geändert.")
    try:
        from .monthly_archive import _save
        data = _load(project_root)
        data["sources"][_key(original_path, digest)] = {"original_path": path_key(original_path), "sha256": digest,
            "current_path": str(current), "origin": origin, "at_utc": datetime.now(timezone.utc).isoformat()}
        if context_guard is not None and not context_guard():
            raise MonthlyArchiveError("Auswahl oder Ergebnisspeicher wurde geändert. Bitte neu wählen.")
        _save(folder / "verified.json", data)
    finally:
        lease.release()
    return str(current)


def find_pdf_locations(search_path, expected_sha256):
    """Explicit file/folder search only; never traverses links/junctions."""
    selected = plain_path(search_path)
    found = []
    def walk(folder):
        for entry in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
            try:
                plain_path(entry)
                if entry.is_dir():
                    yield from walk(entry)
                elif entry.suffix.casefold() == ".pdf":
                    yield entry
            except (OSError, MonthlyArchiveError):
                continue
    for candidate in walk(selected) if selected.is_dir() else (selected,):
        try:
            if candidate.suffix.casefold() == ".pdf" and inspect_file(candidate)[0] == expected_sha256:
                found.append(str(candidate))
        except (OSError, MonthlyArchiveError):
            continue
    return tuple(found)


def resolve_recorded_location(project_root, resolution, job_id, expected_sha256=None):
    """Keep an existing valid location; use exact verified relocation if needed."""
    if resolution.path_status == "ambiguous":
        return resolution
    original = path_key(resolution.source_pdf_path)
    data = _load(project_root)
    receipts = [row for row in data["sources"].values() if row.get("original_path") == original
                and (row.get("sha256") == expected_sha256 if expected_sha256 else row.get("sha256", "")[:16] == job_id)]
    if not receipts and Path(resolution.current_pdf_path).is_file():
        return resolution  # No archive-journal scan for an ordinary live source.
    if not receipts:
        # A crash may have removed a source before publishing its location
        # index. The durable per-file journal then supplies the same exact SHA.
        folder = Path(project_root) / "storage/ingestion/monthly"
        if folder.is_dir():
            for path in sorted(folder.glob("*.json")):
                journal = json.loads(path.read_text(encoding="utf-8"))
                if path_key(journal.get("project_root", "")) != path_key(project_root):
                    continue
                if not all(item.get("copied") for item in journal.get("files", [])):
                    continue
                for item in journal.get("files", []):
                    if (path_key(item["source"]) == original and item.get("kind") == "pdf"
                            and (item["sha256"] == expected_sha256 if expected_sha256 else item["sha256"][:16] == job_id)):
                        receipts.append({"current_path": item["target"], "sha256": item["sha256"]})
    if not receipts:
        return resolution
    valid = {}
    for receipt in receipts:
        try:
            if inspect_file(receipt["current_path"])[0] == receipt["sha256"]:
                valid[path_key(receipt["current_path"])] = receipt["current_path"]
        except (OSError, MonthlyArchiveError):
            continue
    candidates = set(valid)
    if len(candidates) == 1:
        return PathResolution(resolution.source_pdf_path, next(iter(valid.values())), resolution.ingestion_id, "resolved")
    if len(candidates) > 1:
        return PathResolution(resolution.source_pdf_path, resolution.current_pdf_path, resolution.ingestion_id, "ambiguous")
    return PathResolution(resolution.source_pdf_path, "", resolution.ingestion_id, "unavailable")


def verified_pdf_location(project_root, original_path, expected_sha256, *, job_id=None):
    from .service import resolve_current_path
    job = job_id or expected_sha256[:16]
    resolution = resolve_current_path(project_root, job, str(original_path))
    current = resolve_recorded_location(project_root, resolution, job, expected_sha256)
    if current.path_status in {"ambiguous", "unavailable"} or inspect_file(current.current_pdf_path)[0] != expected_sha256:
        raise MonthlyArchiveError("PDF-Ort fehlt, ist mehrdeutig oder hat einen anderen vollständigen SHA.")
    return current.current_pdf_path


@contextmanager
def verified_pdf_source(project_root, original_path, expected_sha256, *, job_id=None):
    """Pin exact verified bytes during a reader or external-viewer dispatch."""
    path = verified_pdf_location(project_root, original_path, expected_sha256, job_id=job_id)
    with PlainHandle(path) as owned:
        owned.verify(expected_sha256)
        yield str(owned.path), owned.file
