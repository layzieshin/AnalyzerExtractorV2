"""Immutable preview/confirmation models for the existing ingestion owner."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArchiveSource:
    path: str
    sha256: str
    size: int
    identity: tuple[int, int, int, int]
    kind: str


@dataclass(frozen=True)
class ArchiveGroup:
    group_id: str
    plate: str
    measured_date: str
    sources: tuple[ArchiveSource, ...]
    target_dir: str
    eligible: bool
    reasons: tuple[str, ...]
    evidence_sha256: str
    no_res_sources: tuple[str, ...] = ()
    related_res: tuple[ArchiveSource, ...] = ()


@dataclass(frozen=True)
class MonthlyArchivePreview:
    project_root: str
    input_path: str
    archive_path: str
    store_path: str
    cutoff: str
    groups: tuple[ArchiveGroup, ...]
    token: str


class MonthlyArchiveError(RuntimeError):
    pass
