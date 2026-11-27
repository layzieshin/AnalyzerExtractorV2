"""Monthly planning and copy-before-remove journal in the ingestion owner.

ResultsController supplies freshly read, store-bound eligibility evidence;
this owner never opens Results/QC databases or infers a PDF plate from its name.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from src.runtime.api import try_acquire_owned_lock

from .monthly_files import PlainHandle, create_directories, identity, inspect_file, path_key, plain_path
from .monthly_models import ArchiveGroup, ArchiveSource, MonthlyArchiveError, MonthlyArchivePreview

MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _month_dir(archive, measured):
    year = archive / str(measured.year)
    plain_path(year, missing=True)
    candidates = []
    if year.exists():
        for entry in year.iterdir():
            if re.match(rf"^{measured.month:02d}(?:[_ .-]|$)", entry.name):
                plain_path(entry)
                if not entry.is_dir():
                    raise MonthlyArchiveError("Monatsziel ist kein Ordner.")
                candidates.append(entry)
    if len(candidates) > 1:
        raise MonthlyArchiveError("Mehrere vorhandene Varianten dieses Monatsordners.")
    return candidates[0] if candidates else year / f"{measured.month:02d}_{MONTHS[measured.month - 1]}"


def _normal_roots(input_path, archive_path):
    if any(not str(raw or "").strip() or not Path(raw).is_absolute() for raw in (input_path, archive_path)):
        raise MonthlyArchiveError("Eingang und Archiv müssen ausdrücklich als absolute Ordner angegeben werden.")
    source, archive = plain_path(input_path), plain_path(archive_path, missing=True)
    if not source.is_dir():
        raise MonthlyArchiveError("Eingangsordner fehlt.")
    if source != archive and (source in archive.parents or archive in source.parents):
        raise MonthlyArchiveError("Eingang und Archiv dürfen nicht ineinander liegen.")
    return source, archive


def preview_monthly_archive(project_root, *, input_path, archive_path, store_path, cutoff,
                            evidence_reader, res_assignments=None, without_res=(), _restored_sources=()):
    """Read-only preview including unknown PDFs; cutoff is inclusive."""
    source, archive = _normal_roots(input_path, archive_path)
    cutoff_date = date.fromisoformat(str(cutoff))
    files = []
    for path in sorted(source.iterdir(), key=lambda item: item.name.casefold()):
        if path.suffix.casefold() not in {".pdf", ".res"}:
            continue
        digest, size, identity = inspect_file(path)
        files.append(ArchiveSource(str(path), digest, size, identity, path.suffix[1:].casefold()))
    current_paths = {path_key(item.path) for item in files}
    files.extend(item for item in _restored_sources if path_key(item.path) not in current_paths)
    files.sort(key=lambda item: Path(item.path).name.casefold())
    pdfs = [item for item in files if item.kind == "pdf"]
    evidence = evidence_reader(tuple(item.path for item in pdfs))
    assignments = {path_key(key): path_key(value) for key, value in (res_assignments or {}).items()}
    exceptions = {path_key(value) for value in without_res}
    if not exceptions <= {path_key(item.path) for item in pdfs} or not set(assignments) <= {path_key(item.path) for item in pdfs}:
        raise MonthlyArchiveError("PDF-Auswahl für RES-Ausnahme/Zuordnung ist veraltet.")
    grouped, used_res = defaultdict(list), set()
    for item in pdfs:
        proof = evidence.get(item.path) or {}
        plate, measured = str(proof.get("plate") or ""), str(proof.get("date") or "")
        key = plate.casefold() if plate else f"unbekannt:{item.path}"
        grouped[key].append((item, proof, plate, measured))
    def uncertain_pdfs(plate):
        return [Path(item.path).name for rows in grouped.values() for item, proof, known_plate, _ in rows
                if not known_plate and (not proof.get("plate_candidates")
                    or plate.casefold() in {str(value).casefold() for value in proof["plate_candidates"]})]
    res_files = {path_key(item.path): item for item in files if item.kind == "res"}
    groups = []
    for res in assignments.values():
        if res not in res_files:
            raise MonthlyArchiveError("Manuell gewählte RES-Datei fehlt im Eingang.")
    effective_res, res_owners = {}, defaultdict(set)
    # Resolve the whole input before granting any group removal rights. A
    # manual choice overrides automatic matching for its entire plate; other
    # plates' automatic consumers still own their effective RES as well.
    for key, rows in grouped.items():
        manual_selected = {assignments[path_key(item.path)] for item, _, _, _ in rows if path_key(item.path) in assignments}
        matching_res = ([res_files[value] for value in sorted(manual_selected)] if manual_selected else
                        [item for item in res_files.values() if rows[0][2] and Path(item.path).stem.casefold() == key])
        effective_res[key] = manual_selected, matching_res
        for item in matching_res:
            res_owners[path_key(item.path)].add(key)
    for key, rows in grouped.items():
        reasons, members, no_res = [], [row[0] for row in rows], []
        names, dates = {row[2] for row in rows}, {row[3] for row in rows}
        plate = rows[0][2]
        measured = None
        if not plate or any(not name or name.casefold() != plate.casefold() for name in names):
            reasons.append("Platte ist nicht eindeutig belegt.")
        elif uncertain_pdfs(plate):
            reasons.append("Weitere PDF könnte zu dieser Platte gehören, ihre Zuordnung ist ungeklärt: " + ", ".join(uncertain_pdfs(plate)))
        try:
            if len(dates) != 1:
                raise ValueError()
            measured = date.fromisoformat(next(iter(dates)))
        except ValueError:
            reasons.append("Messdatum fehlt oder widerspricht sich.")
        if measured and measured > cutoff_date:
            reasons.append("Messdatum liegt nach dem Stichtag.")
        for item, proof, _, _ in rows:
            if proof.get("sha256") != item.sha256 or not proof.get("eligible"):
                reasons.append(str(proof.get("reason") or "Import/Validierung ist unvollständig oder nicht eindeutig."))
        contexts = {tuple(row[1]["origin_context"]) for row in rows if row[1].get("origin_context")}
        if len(contexts) > 1:
            reasons.append("Gleichnamige Platte stammt aus unterschiedlichen Geräten oder Eingängen.")
        target = ""
        try:
            if measured:
                target = str(_month_dir(archive, measured))
        except MonthlyArchiveError as exc:
            reasons.append(str(exc))
        manual_selected, matching_res = effective_res[key]
        if any(len(res_owners[path_key(item.path)]) > 1 for item in matching_res):
            reasons.append("RES wurde verschiedenen Platten zugeordnet.")
        archived_res = []
        if target and plate:
            res_dir = Path(target) / "res"
            plain_path(res_dir, missing=True)
            if res_dir.is_dir():
                archived_res = [entry for entry in res_dir.iterdir() if entry.suffix.casefold() == ".res" and entry.stem.casefold() == plate.casefold()]
                for entry in archived_res:
                    plain_path(entry)
            # Explicit historical RES association remains meaningful for a
            # later PDF export of this exact plate/date/store, even if its
            # chosen RES stem differs. Exceptions without RES never carry over.
            if not manual_selected:
                for journal_path in sorted(_journal_dir(project_root).glob("*.json")):
                    old = json.loads(journal_path.read_text(encoding="utf-8"))
                    if (old.get("status") == "complete" and old.get("assignments")
                            and old.get("plate", "").casefold() == plate.casefold()
                            and old.get("date") == measured.isoformat() and old.get("store_path") == path_key(store_path)):
                        for record in old["files"]:
                            candidate = Path(record["target"])
                            if record["kind"] == "res" and candidate.parent == res_dir and candidate not in archived_res:
                                try:
                                    if inspect_file(candidate)[0] == record["sha256"]:
                                        archived_res.append(candidate)
                                except (OSError, MonthlyArchiveError):
                                    pass
        if len(matching_res) + len(archived_res) > 1:
            same = (len(matching_res) == len(archived_res) == 1
                    and inspect_file(archived_res[0])[0] == matching_res[0].sha256)
            if not same:
                reasons.append("Mehrere passende RES-Dateien: Zuordnung nicht eindeutig.")
        if not matching_res and not archived_res:
            for item, _, _, _ in rows:
                if path_key(item.path) in exceptions:
                    no_res.append(item.path)
                else:
                    reasons.append(f"RES fehlt: {Path(item.path).name}")
        members.extend(matching_res)
        used_res.update(path_key(item.path) for item in matching_res)
        related_res = []
        if not matching_res:
            for entry in archived_res:
                digest, size, file_identity = inspect_file(entry)
                related_res.append(ArchiveSource(str(entry), digest, size, file_identity, "res"))
        proof_hash = _digest({"pdfs": [row[1] for row in rows], "archived_res": [asdict(item) for item in related_res]})
        group_id = _digest([key, sorted(dates)])
        groups.append(ArchiveGroup(group_id, plate or "Nicht zugeordnet", measured.isoformat() if measured else "", tuple(members), target,
                                  not reasons, tuple(dict.fromkeys(reasons)), proof_hash, tuple(no_res), tuple(related_res)))
    for key, item in res_files.items():
        if key in used_res:
            continue
        match = re.fullmatch(r"(\d{8})_.+", Path(item.path).stem)
        reason, measured, target = "", None, ""
        try:
            if not match:
                raise ValueError()
            measured = datetime.strptime(match[1], "%Y%m%d").date()
            target = str(_month_dir(archive, measured))
            if measured > cutoff_date:
                reason = "RES-Datum liegt nach dem Stichtag."
        except (ValueError, MonthlyArchiveError) as exc:
            reason = str(exc) if isinstance(exc, MonthlyArchiveError) else "Alleinige RES hat kein eindeutiges YYYYMMDD_Test-Datum."
        if uncertain_pdfs(Path(item.path).stem):
            reason = "RES könnte zu einer PDF mit ungeklärter Plattenzuordnung gehören. Erst diese PDF klären."
        groups.append(ArchiveGroup(_digest([item.path]), Path(item.path).stem, measured.isoformat() if measured else "", (item,), target,
                                  not reason, (reason,) if reason else (), _digest([])))
    payload = {"project_root": path_key(project_root), "input_path": str(source), "archive_path": str(archive),
               "store_path": path_key(store_path), "cutoff": cutoff_date.isoformat(),
               "groups": sorted((asdict(group) for group in groups), key=lambda group: group["group_id"]),
               "assignments": assignments, "exceptions": sorted(exceptions)}
    return MonthlyArchivePreview(payload["project_root"], str(source), str(archive), payload["store_path"], cutoff_date.isoformat(),
                                 tuple(sorted(groups, key=lambda group: group.group_id)), _digest(payload))


def _journal_dir(root):
    return Path(root) / "storage" / "ingestion" / "monthly"


def _save(path, data):
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _resume_group(path, journal, *, evidence_check=None):
    if journal.get("version") != 1:
        raise MonthlyArchiveError("Archivjournal-Version ist nicht lesbar.")
    source_root, archive_root = _normal_roots(journal["input_path"], journal["archive_path"])
    for item in journal["files"]:
        source, target = Path(item["source"]), Path(item["target"])
        if (source.parent != source_root or archive_root not in target.parents
                or source.name != target.name or source == target):
            raise MonthlyArchiveError("Archivjournal enthält einen fremden Dateipfad.")
    with ExitStack() as stack:
        sources, targets = {}, {}
        for item in journal["group"].get("related_res", ()):
            related = Path(item["path"])
            if related.parent != Path(journal["group"]["target_dir"]) / "res":
                raise MonthlyArchiveError("RES-Beleg gehört nicht zum bestätigten Monatsziel.")
            stack.enter_context(PlainHandle(related)).verify(item["sha256"], expected_identity=item["identity"])
        for item in journal["files"]:
            source, target = Path(item["source"]), Path(item["target"])
            create_directories(target.parent)
            if source.exists():
                sources[item["source"]] = stack.enter_context(PlainHandle(source))
                sources[item["source"]].verify(item["sha256"], expected_identity=item["identity"])
            elif not target.exists():
                raise MonthlyArchiveError(f"Quelle und Ziel fehlen: {source.name}")
            if target.exists():
                targets[item["target"]] = stack.enter_context(PlainHandle(target))
            else:
                partial = Path(item["partial"])
                partial_handle = stack.enter_context(PlainHandle(partial, write=True) if partial.exists() else PlainHandle(partial, create=True))
                partial_identity = list(partial_handle.original_identity[:2])
                if item.get("partial_identity") is not None and item["partial_identity"] != partial_identity:
                    raise MonthlyArchiveError("Private Teilkopie wurde ersetzt; Quelle bleibt erhalten.")
                if item.get("partial_identity") is None and not partial_handle.created:
                    raise MonthlyArchiveError("Unbekannte Teilkopie bleibt zur Klärung erhalten.")
                item["partial_identity"] = partial_identity
                _save(path, journal)  # Bind inode before the first copied byte.
                partial_handle.copy_from(sources[item["source"]])
                partial_handle.verify(item["sha256"])
                partial_handle.publish(target)
                copied_identity = identity(os.fstat(partial_handle.file.fileno()))
                partial_handle.close()
                # Downgrade to a pinned read handle so authentic evidence can
                # reread the verified destination after interrupted removals.
                published = stack.enter_context(PlainHandle(target))
                published.verify(item["sha256"], expected_identity=copied_identity)
                targets[item["target"]] = published
            targets[item["target"]].verify(item["sha256"])
            item["copied"] = True
            _save(path, journal)
        # ALL targets are open, fsynced and fully verified before the first
        # source removal. Handles prevent replacement/write races on Windows.
        for item in journal["files"]:
            targets[item["target"]].verify(item["sha256"])
        if evidence_check is not None:
            evidence_check()
        journal["status"] = "removing"
        _save(path, journal)
        for item in journal["files"]:
            source = sources.get(item["source"])
            if source is not None:
                source.remove(item["sha256"])
                source.close()  # Commit handle-based deletion before receipt.
            item["removed"] = True
            _save(path, journal)
            if item["kind"] == "pdf":
                from .locations import register_pdf_location
                register_pdf_location(journal["project_root"], item["source"], item["sha256"], item["target"], origin="monthly")
        journal["status"] = "complete"
        _save(path, journal)
    return journal


def commit_monthly_archive(project_root, preview, *, evidence_reader, selected_group_ids=None,
                           res_assignments=None, without_res=(), operator_initials=""):
    root = path_key(project_root)
    if root != preview.project_root:
        raise MonthlyArchiveError("Vorschau gehört zu einem anderen Arbeitsordner.")
    if (without_res or res_assignments) and not operator_initials.strip():
        raise MonthlyArchiveError("Für ausdrückliche RES-Zuordnung/Ausnahme sind Initialen erforderlich.")
    folder = create_directories(_journal_dir(root))
    lease = try_acquire_owned_lock(folder / "archive.owner")
    if lease is None:
        raise MonthlyArchiveError("Eingang aufräumen läuft bereits.")
    try:
        fresh = preview_monthly_archive(root, input_path=preview.input_path, archive_path=preview.archive_path,
            store_path=preview.store_path, cutoff=preview.cutoff, evidence_reader=evidence_reader,
            res_assignments=res_assignments, without_res=without_res)
        if fresh.token != preview.token:
            raise MonthlyArchiveError("Dateien, Zuordnung oder Nachweise haben sich seit der Vorschau geändert. Bitte neu prüfen.")
        selected = set(selected_group_ids) if selected_group_ids is not None else {group.group_id for group in fresh.groups if group.eligible}
        if not selected <= {group.group_id for group in fresh.groups if group.eligible}:
            raise MonthlyArchiveError("Auswahl enthält eine unvollständige/veraltete Gruppe.")
        completed = []
        for group in fresh.groups:
            if group.group_id not in selected:
                continue
            stamp = datetime.now(timezone.utc).isoformat()
            records = []
            journal_id = uuid.uuid4().hex
            for item in group.sources:
                target = Path(group.target_dir) / ("res" if item.kind == "res" else "") / Path(item.path).name
                records.append({"source": item.path, "target": str(target), "sha256": item.sha256,
                                "partial": str(target.with_name(f".{target.name}.{journal_id}.part")),
                                "identity": list(item.identity), "size": item.size, "kind": item.kind,
                                "copied": False, "removed": False,
                                "without_res": {"initials": operator_initials.strip(), "at_utc": stamp} if item.path in group.no_res_sources else None})
            journal = {"version": 1, "id": journal_id, "status": "copying", "group_id": group.group_id,
                       "project_root": root,
                       "plate": group.plate, "date": group.measured_date, "store_path": preview.store_path,
                       "input_path": preview.input_path, "archive_path": preview.archive_path,
                       "cutoff": preview.cutoff, "group": asdict(group),
                       "evidence_sha256": group.evidence_sha256, "initials": operator_initials.strip(), "at_utc": stamp,
                       "assignments": {key: value for key, value in (res_assignments or {}).items()
                                       if key in {item.path for item in group.sources if item.kind == "pdf"}}, "files": records}
            path = folder / f"{journal['id']}.json"
            _save(path, journal)
            def check(group=group):
                current = preview_monthly_archive(root, input_path=preview.input_path, archive_path=preview.archive_path,
                    store_path=preview.store_path, cutoff=preview.cutoff, evidence_reader=evidence_reader,
                    res_assignments={key: value for key, value in (res_assignments or {}).items() if Path(key).is_file()},
                    without_res=tuple(key for key in without_res if Path(key).is_file()))
                matching = next((row for row in current.groups if row.group_id == group.group_id), None)
                # Fresh membership, RES presence/association and live evidence,
                # not just another read of the old selected file paths.
                if matching is None or not matching.eligible or matching.sources != group.sources or matching.evidence_sha256 != group.evidence_sha256:
                    raise MonthlyArchiveError("Gruppe, RES oder Import-/Validierungsnachweis während Kopieren geändert; Eingang bleibt erhalten.")
            try:
                completed.append(_resume_group(path, journal, evidence_check=check))
            except Exception as exc:
                journal["error"] = str(exc)
                _save(path, journal)
                raise
        return tuple(completed)
    finally:
        lease.release()


def recover_monthly_archive(project_root, *, evidence_reader, store_path=None):
    folder = _journal_dir(project_root)
    if not folder.is_dir():
        return ()
    plain_path(folder)
    lease = try_acquire_owned_lock(folder / "archive.owner")
    if lease is None:
        raise MonthlyArchiveError("Eingang aufräumen läuft bereits.")
    try:
        result = []
        for path in sorted(folder.glob("*.json")):
            journal = json.loads(path.read_text(encoding="utf-8"))
            if path_key(journal.get("project_root", "")) != path_key(project_root):
                raise MonthlyArchiveError("Archivjournal gehört zu einem anderen Arbeitsordner.")
            if store_path is not None and path_key(journal["store_path"]) != path_key(store_path):
                continue
            if journal.get("status") == "complete":
                continue
            def check():
                restored = tuple(ArchiveSource(item["source"], item["sha256"], item["size"], tuple(item["identity"]), item["kind"])
                                 for item in journal["files"] if not Path(item["source"]).exists())
                fresh = preview_monthly_archive(project_root, input_path=journal["input_path"], archive_path=journal["archive_path"],
                    store_path=journal["store_path"], cutoff=journal["cutoff"], evidence_reader=evidence_reader,
                    res_assignments=journal["assignments"],
                    without_res=tuple(item["source"] for item in journal["files"] if item.get("without_res")),
                    _restored_sources=restored)
                current = next((group for group in fresh.groups if group.group_id == journal["group_id"]), None)
                if current is None or not current.eligible or _digest(asdict(current)) != _digest(journal["group"]):
                    raise MonthlyArchiveError("Gruppe, RES oder Nachweis seit Abbruch geändert; Wiederaufnahme erfordert Klärung.")
            check()
            result.append(_resume_group(path, journal, evidence_check=check))
        return tuple(result)
    finally:
        lease.release()
