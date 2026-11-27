"""Synthetic monthly grouping, exclusive copy-before-remove and recovery."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from src.ingestion.api import (MonthlyArchiveError, commit_monthly_archive,
                               preview_monthly_archive, recover_monthly_archive)


def _fixture(root):
    incoming, archive = root / "incoming", root / "archive"
    incoming.mkdir()
    proof = {}
    def pdf(name, plate="20261125_Test", date="2026-11-25", eligible=True):
        path = incoming / name
        path.write_bytes(f"synthetic bytes {name}".encode())
        proof[str(path)] = {"plate": plate, "date": date, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "eligible": eligible, "run_ids": [len(proof) + 1], "validation_ids": [len(proof) + 10]}
        return path
    def reader(paths):
        return {path: proof[path] for path in paths if path in proof}
    def preview(**kwargs):
        return preview_monthly_archive(root, input_path=incoming, archive_path=archive, store_path=root / "results.sqlite3",
                                       cutoff="2026-11-25", evidence_reader=reader, **kwargs)
    def commit(plan, **kwargs):
        return commit_monthly_archive(root, plan, evidence_reader=reader, **kwargs)
    return incoming, archive, proof, pdf, reader, preview, commit


def test_preview_is_strictly_read_only_and_groups_actual_plate_not_random_pdf_name(tmp_path):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first, second = pdf("random.pdf"), pdf("other-assay.pdf")
    res = incoming / "20261125_tEsT.RES"
    res.write_bytes(b"uninterpreted res bytes")
    before = {path: path.read_bytes() for path in incoming.iterdir()}
    plan = preview()
    assert not archive.exists() and not (tmp_path / "storage").exists()
    assert len(plan.groups) == 1 and plan.groups[0].eligible
    assert {Path(item.path).name for item in plan.groups[0].sources} == {first.name, second.name, res.name}
    assert all(path.read_bytes() == payload for path, payload in before.items())
    result = commit(plan)
    assert result[0]["status"] == "complete" and not list(incoming.iterdir())
    assert (archive / "2026/11_November/random.pdf").read_bytes() == before[first]
    assert (archive / "2026/11_November/res/20261125_tEsT.RES").read_bytes() == before[res]


@pytest.mark.parametrize("candidates", [(), ("20261125_Test", "20261125_Other")])
def test_unknown_or_conflicting_pdf_plate_candidates_block_plausible_standalone_res(tmp_path, candidates):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    source = pdf("broken.pdf", plate="", date="", eligible=False)
    proof[str(source)]["plate_candidates"] = candidates
    (incoming / "20261125_Test.res").write_bytes(b"possibly related")
    unrelated = incoming / "20261124_Unrelated.res"
    unrelated.write_bytes(b"standalone")
    plan = preview()
    selected = next(group for group in plan.groups if group.plate == "20261125_Test")
    assert not selected.eligible and "ungeklärter Plattenzuordnung" in " ".join(selected.reasons)
    other = next(group for group in plan.groups if group.plate == "20261124_Unrelated")
    assert other.eligible is bool(candidates)  # Unknown/unreadable can belong to any loose RES.


def test_ambiguous_pdf_candidates_also_block_an_already_known_eligible_plate(tmp_path):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    pdf("valid.pdf")
    ambiguous = pdf("mixed.pdf", plate="", date="2026-11-25", eligible=False)
    proof[str(ambiguous)]["plate_candidates"] = ("20261125_Test", "20261125_Other")
    res = incoming / "20261125_Test.res"
    res.write_bytes(b"related to valid PDF, also possibly the mixed one")
    plan = preview()
    selected = next(group for group in plan.groups if group.plate == "20261125_Test")
    assert not selected.eligible and "Weitere PDF" in " ".join(selected.reasons)
    assert commit(plan) == () and res.exists()


@pytest.mark.parametrize("defect", ["invalid", "unknown", "date_conflict", "after_cutoff"])
def test_one_incomplete_or_unclear_pdf_blocks_whole_related_plate(tmp_path, defect):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first, second = pdf("first.pdf"), pdf("second.pdf")
    (incoming / "20261125_Test.res").write_bytes(b"res")
    if defect == "invalid":
        proof[str(second)]["eligible"] = False
    elif defect == "unknown":
        proof[str(second)] = {"plate": "20261125_Test", "date": "2026-11-25", "eligible": False}
    elif defect == "date_conflict":
        proof[str(second)]["date"] = "2026-11-24"
    else:
        proof[str(first)]["date"] = proof[str(second)]["date"] = "2026-11-26"
    plan = preview()
    assert len(plan.groups) == 1 and not plan.groups[0].eligible and plan.groups[0].reasons
    assert commit(plan) == () and first.exists() and second.exists() and not archive.exists()


def test_unknown_pdf_is_visible_and_never_grouped_using_its_filename(tmp_path):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    path = pdf("20261125_Test.pdf", plate="", date="", eligible=False)
    plan = preview()
    assert plan.groups[0].plate == "Nicht zugeordnet" and not plan.groups[0].eligible
    assert path.exists() and not archive.exists()


def test_without_res_is_explicit_per_pdf_and_requires_initials_and_timestamp(tmp_path):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first, second = pdf("first.pdf"), pdf("second.pdf")
    assert not preview().groups[0].eligible
    assert not preview(without_res=(str(first),)).groups[0].eligible
    chosen = (str(first), str(second))
    plan = preview(without_res=chosen)
    assert plan.groups[0].eligible
    with pytest.raises(MonthlyArchiveError, match="Initialen"):
        commit(plan, without_res=chosen)
    result = commit(plan, without_res=chosen, operator_initials="MK")
    assert all(row["without_res"]["initials"] == "MK" and row["without_res"]["at_utc"] for row in result[0]["files"])
    third = pdf("late.pdf")
    assert not preview().groups[0].eligible and third.exists()


def test_manual_res_mapping_is_confirmed_not_automatic_fuzzy_matching(tmp_path):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    source = pdf("report.pdf")
    res = incoming / "Different_Name.res"
    res.write_bytes(b"res")
    assert not any(group.eligible for group in preview().groups)
    mapping = {str(source): str(res)}
    plan = preview(res_assignments=mapping)
    assert len(plan.groups) == 1 and plan.groups[0].eligible
    with pytest.raises(MonthlyArchiveError, match="Initialen"):
        commit(plan, res_assignments=mapping)
    assert commit(plan, res_assignments=mapping, operator_initials="MK")[0]["assignments"] == mapping
    late = pdf("later-export.pdf")
    later = preview()
    assert len(later.groups) == 1 and later.groups[0].eligible and not later.groups[0].no_res_sources
    commit(later)
    assert not late.exists() and (archive / "2026/11_November/res/Different_Name.res").is_file()


@pytest.mark.parametrize("manual_first", [True, False])
@pytest.mark.parametrize("selected_plates", [("20261125_A",), ("20261125_B",), ("20261125_B", "20261125_A")])
def test_shared_manual_and_automatic_res_blocks_every_owner_before_any_removal(tmp_path, monkeypatch, manual_first, selected_plates):
    from src.ingestion.monthly_files import PlainHandle
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first = pdf("01-a.pdf" if manual_first else "02-a.pdf", plate="20261125_A")
    second = pdf("02-b.pdf" if manual_first else "01-b.pdf", plate="20261125_B")
    shared = incoming / "20261125_B.RES"
    shared.write_bytes(b"one RES cannot belong to two physical plates")
    mapping = {str(first): str(shared)}
    before = {path: path.read_bytes() for path in incoming.iterdir()}
    plan = preview(res_assignments=mapping)
    groups = {group.plate: group for group in plan.groups}
    assert set(groups) == {"20261125_A", "20261125_B"}
    assert all(not group.eligible for group in groups.values())
    assert all("RES wurde verschiedenen Platten zugeordnet." in group.reasons for group in groups.values())
    assert not archive.exists() and not (tmp_path / "storage").exists()
    monkeypatch.setattr(PlainHandle, "remove", lambda *_args: pytest.fail("A conflicting RES must never grant source removal rights"))
    with pytest.raises(MonthlyArchiveError, match="unvollständigen|unvollständige"):
        commit(plan, selected_group_ids=tuple(groups[plate].group_id for plate in selected_plates),
               res_assignments=mapping, operator_initials="MK")
    assert commit(plan, res_assignments=mapping, operator_initials="MK") == ()
    assert first.exists() and second.exists() and not archive.exists()
    assert {path: path.read_bytes() for path in incoming.iterdir()} == before


def test_one_res_can_serve_multiple_pdfs_of_the_same_casefold_plate(tmp_path):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first = pdf("one.pdf", plate="20261125_Test")
    second = pdf("two.pdf", plate="20261125_tEsT")
    for path in (first, second):
        proof[str(path)]["origin_context"] = ("DEVICE", str(incoming))
    shared = incoming / "20261125_TEST.res"
    shared.write_bytes(b"one physical plate, multiple assay printouts")
    mapping = {str(first): str(shared)}
    plan = preview(res_assignments=mapping)
    assert len(plan.groups) == 1 and plan.groups[0].eligible
    assert {source.path for source in plan.groups[0].sources} == {str(first), str(second), str(shared)}
    assert commit(plan, res_assignments=mapping, operator_initials="MK")[0]["status"] == "complete"
    assert not list(incoming.iterdir())


def test_res_owners_use_manual_precedence_for_the_whole_plate(tmp_path):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first = pdf("a.pdf", plate="20261125_A")
    second = pdf("b.pdf", plate="20261125_B")
    second_assay = pdf("b-extra.pdf", plate="20261125_B")
    matching_b = incoming / "20261125_B.res"
    chosen_b = incoming / "Explicit_B.res"
    matching_b.write_bytes(b"explicitly used by A")
    chosen_b.write_bytes(b"B explicitly chooses this instead of its automatic stem")
    mapping = {str(first): str(matching_b), str(second): str(chosen_b)}
    plan = preview(res_assignments=mapping)
    groups = {group.plate: group for group in plan.groups}
    assert len(groups) == 2 and all(group.eligible for group in groups.values())
    assert {source.path for source in groups["20261125_A"].sources} == {str(first), str(matching_b)}
    assert {source.path for source in groups["20261125_B"].sources} == {str(second), str(second_assay), str(chosen_b)}
    assert len(commit(plan, res_assignments=mapping, operator_initials="MK")) == 2
    assert not list(incoming.iterdir())


def test_res_only_late_files_and_existing_unique_month_variant_are_supported(tmp_path):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    month = archive / "2026/11 November"
    month.mkdir(parents=True)
    res = incoming / "20261125_Test.res"
    res.write_bytes(b"res only first")
    plan = preview()
    assert plan.groups[0].eligible and Path(plan.groups[0].target_dir) == month
    commit(plan)
    later = pdf("late combined.pdf")
    plan = preview()
    assert plan.groups[0].eligible
    commit(plan)
    assert (month / later.name).is_file() and (month / "res" / res.name).is_file()


def test_late_pdf_binds_already_archived_res_hash_and_keeps_it_pinned_through_removal(tmp_path, monkeypatch):
    from src.ingestion.monthly_files import PlainHandle
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    res = incoming / "20261125_Test.res"
    res.write_bytes(b"original RES")
    commit(preview())
    target_res = archive / "2026/11_November/res" / res.name
    late = pdf("late.pdf")
    plan = preview()
    assert len(plan.groups[0].related_res) == 1
    target_res.write_bytes(b"changed RES")
    with pytest.raises(MonthlyArchiveError, match="seit der Vorschau"):
        commit(plan)
    assert late.exists()
    original = PlainHandle.remove
    def remove(self, expected):
        if os.name == "nt":
            with pytest.raises(OSError):
                target_res.write_bytes(b"may not replace while a related PDF is removed")
        original(self, expected)
    monkeypatch.setattr(PlainHandle, "remove", remove)
    assert commit(preview())[0]["status"] == "complete"
    assert target_res.read_bytes() == b"changed RES"


@pytest.mark.parametrize("change", ["bytes", "evidence", "new_file", "collision"])
def test_confirmation_rechecks_source_group_evidence_and_collision(tmp_path, change):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first = pdf("first.pdf")
    (incoming / "20261125_Test.res").write_bytes(b"res")
    plan = preview()
    if change == "bytes":
        first.write_bytes(b"replacement")
    elif change == "evidence":
        proof[str(first)]["validation_ids"] = [999]
    elif change == "new_file":
        pdf("second.pdf")
    else:
        target = archive / "2026/11_November" / first.name
        target.parent.mkdir(parents=True)
        target.write_bytes(b"foreign destination never overwritten")
    with pytest.raises((MonthlyArchiveError, OSError)):
        commit(plan)
    assert first.exists()
    if change == "collision":
        assert target.read_bytes() == b"foreign destination never overwritten"


def test_all_targets_are_copied_verified_before_any_source_is_removed_and_resume_after_first_removal(tmp_path, monkeypatch):
    from src.ingestion.monthly_files import PlainHandle
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first, second = pdf("first.pdf"), pdf("second.pdf")
    res = incoming / "20261125_Test.res"
    res.write_bytes(b"res")
    initial = {path.name: path.read_bytes() for path in incoming.iterdir()}
    original, verify = PlainHandle.remove, PlainHandle.verify
    calls, verified = [], set()
    targets = {archive / "2026/11_November" / ("res" if name.endswith(".res") else "") / name for name in initial}
    def track_verify(self, expected, *, expected_identity=None):
        verify(self, expected, expected_identity=expected_identity)
        if self.path in targets:
            verified.add(self.path)
    monkeypatch.setattr(PlainHandle, "verify", track_verify)
    def interrupt(self, expected):
        # Destination handles deliberately deny concurrent ordinary opens on
        # Windows: observe their genuine full-hash verification, not a second
        # unsafe path-only read while exclusive write handles are held.
        assert verified == targets
        if calls:
            raise RuntimeError("synthetic process interruption between sources")
        calls.append(self.path.name)
        original(self, expected)
    monkeypatch.setattr(PlainHandle, "remove", interrupt)
    with pytest.raises(RuntimeError, match="interruption"):
        commit(preview())
    assert len(list(incoming.iterdir())) == 2
    assert all((archive / "2026/11_November" / ("res" if name.endswith(".res") else "") / name).read_bytes() == payload
               for name, payload in initial.items())
    monkeypatch.setattr(PlainHandle, "remove", original)
    recovered = recover_monthly_archive(tmp_path, evidence_reader=reader)
    assert recovered[0]["status"] == "complete" and not list(incoming.iterdir())
    assert recover_monthly_archive(tmp_path, evidence_reader=reader) == ()


def test_changed_target_after_interruption_never_allows_remaining_source_removal(tmp_path, monkeypatch):
    from src.ingestion.monthly_files import PlainHandle
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first, second = pdf("first.pdf"), pdf("second.pdf")
    res = incoming / "20261125_Test.res"
    res.write_bytes(b"res")
    original = PlainHandle.remove
    def interrupt(self, expected):
        raise RuntimeError("before removal")
    monkeypatch.setattr(PlainHandle, "remove", interrupt)
    with pytest.raises(RuntimeError):
        commit(preview())
    monkeypatch.setattr(PlainHandle, "remove", original)
    target = archive / "2026/11_November/first.pdf"
    target.write_bytes(b"foreign replacement")
    with pytest.raises(MonthlyArchiveError, match="SHA"):
        recover_monthly_archive(tmp_path, evidence_reader=reader)
    assert first.exists() and second.exists() and res.exists() and target.read_bytes() == b"foreign replacement"


@pytest.mark.skipif(os.name != "nt", reason="Windows handle deletion/sharing contract")
def test_windows_source_replacement_is_prevented_not_blindly_unlinked(tmp_path, monkeypatch):
    from src.ingestion.monthly_files import PlainHandle
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    source = pdf("first.pdf")
    (incoming / "20261125_Test.res").write_bytes(b"res")
    replacement = tmp_path / "foreign.pdf"
    replacement.write_bytes(b"foreign new data")
    original = PlainHandle.remove
    def attempt_replace(self, expected):
        if self.path == source:
            with pytest.raises(PermissionError):
                os.replace(replacement, source)
        original(self, expected)
    monkeypatch.setattr(PlainHandle, "remove", attempt_replace)
    commit(preview())
    assert replacement.read_bytes() == b"foreign new data" and not source.exists()


def test_single_writer_does_not_need_watch_and_ambiguous_month_folders_block(tmp_path):
    from src.runtime.api import try_acquire_owned_lock
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    pdf("file.pdf")
    (incoming / "20261125_Test.res").write_bytes(b"res")
    folder = tmp_path / "storage/ingestion/monthly"
    lease = try_acquire_owned_lock(folder / "archive.owner")
    try:
        with pytest.raises(MonthlyArchiveError, match="bereits"):
            commit(preview())
    finally:
        lease.release()
    (archive / "2026/11 November").mkdir(parents=True)
    (archive / "2026/11_November").mkdir()
    assert not preview().groups[0].eligible


def test_primary_same_result_root_scans_only_loose_files_and_archives_into_its_month(tmp_path):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first = pdf("arbitrary printout.pdf")
    res = incoming / "20261125_Test.res"
    res.write_bytes(b"res")
    existing = incoming / "2026/04_ April/res"
    existing.mkdir(parents=True)
    (existing / "20260401_Other.res").write_bytes(b"must not scan or touch")
    plan = preview_monthly_archive(tmp_path, input_path=incoming, archive_path=incoming, store_path=tmp_path / "db.sqlite3",
                                   cutoff="2026-11-25", evidence_reader=reader)
    assert len(plan.groups) == 1 and plan.groups[0].eligible
    commit_monthly_archive(tmp_path, plan, evidence_reader=reader)
    assert (incoming / "2026/11_November" / first.name).is_file()
    assert (incoming / "2026/11_November/res" / res.name).is_file()
    assert (existing / "20260401_Other.res").read_bytes() == b"must not scan or touch"


@pytest.mark.parametrize("which,value", [("input_path", ""), ("archive_path", ""),
                                        ("input_path", "relative"), ("archive_path", "relative")])
def test_empty_or_relative_roots_never_default_to_working_directory(tmp_path, which, value):
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    args = {"input_path": str(incoming), "archive_path": str(archive)}
    args[which] = value
    with pytest.raises(MonthlyArchiveError, match="absolute"):
        preview_monthly_archive(tmp_path, **args, store_path=tmp_path / "db.sqlite3", cutoff="2026-11-25", evidence_reader=reader)
    assert not archive.exists() and not (tmp_path / "storage").exists()


def test_interrupted_partial_copy_is_owned_resumable_and_not_a_final_name_collision(tmp_path, monkeypatch):
    from src.ingestion.monthly_files import PlainHandle
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    first = pdf("first.pdf")
    (incoming / "20261125_Test.res").write_bytes(b"res")
    copy = PlainHandle.copy_from
    def partial(self, source):
        self.file.write(source.file.read(3))
        self.file.flush()
        os.fsync(self.file.fileno())
        raise RuntimeError("power loss mid stream before copy receipt")
    monkeypatch.setattr(PlainHandle, "copy_from", partial)
    with pytest.raises(RuntimeError, match="mid stream"):
        commit(preview())
    assert first.exists() and not (archive / "2026/11_November/first.pdf").exists()
    journals = list((tmp_path / "storage/ingestion/monthly").glob("*.json"))
    data = json.loads(journals[0].read_text(encoding="utf-8"))
    assert data["files"][0]["partial_identity"] and not data["files"][0]["copied"]
    monkeypatch.setattr(PlainHandle, "copy_from", copy)
    assert recover_monthly_archive(tmp_path, evidence_reader=reader)[0]["status"] == "complete"
    assert not first.exists()
    assert not list((archive / "2026/11_November").rglob("*.part"))


@pytest.mark.parametrize("arrival", ["pdf", "res", "archived_res_removed"])
def test_group_members_and_res_rechecked_after_copy_before_first_source_removal(tmp_path, monkeypatch, arrival):
    from src.ingestion.monthly_files import PlainHandle
    incoming, archive, proof, pdf, reader, preview, commit = _fixture(tmp_path)
    source = pdf("first.pdf")
    untouched = incoming / "unrelated.dat"
    untouched.write_bytes(b"unrelated source must remain exact")
    res = incoming / "20261125_Test.res"
    res.write_bytes(b"res")
    if arrival == "res":
        res.unlink()
    if arrival == "archived_res_removed":
        commit(preview())
        source = pdf("late.pdf")
        existing_res = archive / "2026/11_November/res/20261125_Test.res"
    copy, calls = PlainHandle.copy_from, []
    def copy_and_arrive(self, original):
        copy(self, original)
        if not calls:
            calls.append(True)
            if arrival == "pdf":
                pdf("additional.pdf")
            elif arrival == "res":
                res.write_bytes(b"matching RES arrived after explicit no-RES preview")
            else:
                existing_res.unlink()
    monkeypatch.setattr(PlainHandle, "copy_from", copy_and_arrive)
    exceptions = (str(source),) if arrival == "res" else ()
    if arrival == "archived_res_removed" and os.name == "nt":
        with pytest.raises(PermissionError) as blocked:
            commit(preview(without_res=exceptions), without_res=exceptions, operator_initials="MK")
        assert blocked.value.winerror == 32  # Pinned RES cannot be removed at all.
        assert existing_res.read_bytes() == b"res"
    else:
        with pytest.raises(MonthlyArchiveError, match="Gruppe"):
            commit(preview(without_res=exceptions), without_res=exceptions, operator_initials="MK")
    assert source.exists() and untouched.read_bytes() == b"unrelated source must remain exact"
