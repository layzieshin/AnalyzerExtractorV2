from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.application.api import DesktopSettings, ResultsController, ValidationConflictError
from src.application import results_controller
from src.dbwriter.api import append_result_revision, write_record_sqlite
from src.extractor.api import AssayRecord
from src.resultstore.api import get_result_run
from src.resultvalidation.api import list_run_validations_readonly
from src.ruleresolver.api import RuleSet


def _rule():
    return RuleSet("A", "A.json", {"extract_rules": {"fields": [{"key": "value", "required": False}]}})


def _populate(path, root):
    for run in range(2):
        write_record_sqlite(AssayRecord("A", "old-lot", f"old-{run}", {"value": f"old-{run}", "retained": "whole"}, "original-device"),
                            _rule(), str(path), pdf_path=str(root / "source.pdf"))


def _fake_reanalyze(root, spec, run, *, expected_selection_token, request_id, operator_initials):
    snapshot = {"assay_key": "A", "device_id": "original-device", "payload": {"value": f"new-{run}", "added": "whole"},
                "lot_id": "new-lot", "dedupe_key": f"new-{run}", "dedupe_version": "v2", "dedupe_basis": {},
                "ruleset_file": "A.json", "ruleset": _rule().data, "rule_sha256": "a"*64,
                "source_verified": True, "source_provenance": {"pdf_sha256": "b"*64}, "error": ""}
    return append_result_revision(spec["path"], run, expected_selection_token=expected_selection_token,
                                  request_id=request_id, snapshot=snapshot, created_by=operator_initials)


def _controller(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    path = root / "first.sqlite"
    _populate(path, root)
    settings = [DesktopSettings(output_mode="sqlite", sqlite_path=str(path))]
    return root, path, settings, ResultsController(root, settings_provider=lambda: settings[0])


def test_batch_whole_comparison_human_selection_then_separate_bound_validation(tmp_path, monkeypatch):
    root, path, _, controller = _controller(tmp_path)
    monkeypatch.setattr(results_controller, "reanalyze_run", _fake_reanalyze)
    cases = controller.list_open_validation_cases()
    assert len(cases) == 2 and all(case.selection_token for case in cases)
    batch = controller.reanalyze_selected_cases(cases, "RR", request_id="batch")
    assert len(batch.items) == 2 and all(item.revision_id and not item.error for item in batch.items)
    pending = controller.list_open_validation_cases()
    case = pending[0]
    fields = {row.field_key: (row.old_value, row.new_value) for row in case.comparison.fields}
    assert fields["retained"] == ("whole", "") and fields["added"] == ("", "whole")
    assert case.comparison.can_keep_old and case.comparison.can_accept_new
    assert any(row.field_key == "rule_sha256" for row in case.comparison.metadata)
    assert list_run_validations_readonly({"path": str(path)}, [1, 2]).records == ()
    with pytest.raises(ValidationConflictError, match="zuerst"):
        controller.validate_report_run(case.report_id, case.run_id, "RR", expected_selection_token=case.selection_token, store_path=case.store_path)
    controller.choose_reanalysis_result(case, "accept_new", "RR", request_id="choose")
    chosen = next(item for item in controller.list_open_validation_cases() if item.run_id == case.run_id)
    assert chosen.comparison is None and chosen.revision_id == case.comparison.revision_id
    assert any(row.field_key.startswith("Auswahl") for row in chosen.reanalysis_history)
    assert list_run_validations_readonly({"path": str(path)}, [1, 2]).records == ()
    with pytest.raises(ValidationConflictError, match="geaendert"):
        controller.validate_report_run(case.report_id, case.run_id, "RR", expected_selection_token=case.selection_token, store_path=case.store_path)
    validation = controller.validate_report_run(chosen.report_id, chosen.run_id, "RR", expected_selection_token=chosen.selection_token, store_path=chosen.store_path)
    assert validation.revision_id == chosen.revision_id and validation.selection_token == chosen.selection_token
    corrected = controller.correct_report_run(chosen.report_id, chosen.run_id, "CC", expected_selection_token=chosen.selection_token, store_path=chosen.store_path)
    assert corrected.supersedes_validation_id == validation.validation_id
    assert len(controller.list_open_validation_cases()) == 1
    detail = controller.get_report_detail(case.report_id)
    occurrence = next(occ for group in detail.assay_groups for occ in group.occurrences if occ.run_id == case.run_id)
    assert occurrence.selection_token == chosen.selection_token and occurrence.store_path == str(path)
    assert occurrence.current_validation.revision_id == chosen.revision_id
    run = controller.get_run_detail(case.run_id)
    assert len(run.revision_history) == len(run.selection_history) == 1


def test_batch_captures_one_store_even_if_settings_change_and_same_ids_exist(tmp_path, monkeypatch):
    root, first, settings, controller = _controller(tmp_path)
    second = root / "second.sqlite"
    _populate(second, root)
    cases = controller.list_open_validation_cases()
    seen = []
    def reanalyze(*args, **kwargs):
        seen.append(args[1]["path"])
        settings[0] = replace(settings[0], sqlite_path=str(second))
        return _fake_reanalyze(*args, **kwargs)
    monkeypatch.setattr(results_controller, "reanalyze_run", reanalyze)
    batch = controller.reanalyze_selected_cases(cases, "RR", request_id="batch")
    assert seen == [str(first), str(first)] and batch.store_path == str(first)
    assert all(get_result_run({"path": str(first)}, run)["pending_revision"] for run in (1, 2))
    assert all(get_result_run({"path": str(second)}, run)["pending_revision"] is None for run in (1, 2))
    for operation in (
        lambda: controller.validate_report_run(cases[0].report_id, cases[0].run_id, "RR", expected_selection_token=cases[0].selection_token, store_path=cases[0].store_path),
        lambda: controller.choose_reanalysis_result(cases[0], "keep_old", "RR", request_id="choose"),
    ):
        with pytest.raises(ValidationConflictError, match="Ergebnisspeicher"):
            operation()
    rejected = controller.reanalyze_selected_cases(cases, "RR", request_id="another-batch")
    assert all(item.revision_id is None and "Ergebnisspeicher" in item.error for item in rejected.items)


def test_browsing_complete_population_is_readonly_and_batch_continues_per_case(tmp_path, monkeypatch):
    root, path, _, controller = _controller(tmp_path)
    before = path.read_bytes(), path.stat().st_mtime_ns
    cases = controller.list_open_validation_cases()
    controller.list_recent_reports()
    controller.get_report_detail(cases[0].report_id)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    bad = replace(cases[0], selection_token="stale")
    monkeypatch.setattr(results_controller, "reanalyze_run", _fake_reanalyze)
    result = controller.reanalyze_selected_cases((bad, cases[1]), "RR", request_id="mixed")
    assert result.items[0].revision_id is None and result.items[0].error
    assert result.items[1].revision_id is not None and not result.items[1].error
