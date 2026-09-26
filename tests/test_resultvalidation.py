"""Synthetic coverage for the append-only run validation owner."""

from __future__ import annotations

import ast
import inspect
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.resultvalidation.api import (
    OperatorInitialsRequiredError,
    ResultValidationError,
    RunNotFoundError,
    RunValidation,
    ValidationAlreadyExistsError,
    ValidationMissingError,
    ValidationStoreMissingError,
    ValidationStoreUnreadableError,
    correct_validation,
    get_run_validation,
    list_run_validations,
    replace_validation,
    validate_run,
)

_MEASUREMENT = '{"analyte":"synthetic","value":"41.2","unit":"ng/mL"}'
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_ROOT = _PROJECT_ROOT / "src" / "resultvalidation"


def _spec(path: Path) -> dict[str, str]:
    return {"driver": "sqlite", "path": str(path)}


def _create_runs_db(path: Path, rows: list[tuple[int, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY,
                job_id TEXT,
                pdf_path TEXT,
                assay_key TEXT,
                lot_id TEXT,
                payload_json TEXT,
                created_at TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO runs (id, job_id, pdf_path, assay_key, lot_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (run_id, f"job-{run_id}", f"synthetic-{run_id}.pdf", "ASSAY", "LOT", payload, "2026-01-01T00:00:00+00:00")
                for run_id, payload in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _runs_state(path: Path) -> tuple[str | None, list[tuple[object, ...]]]:
    conn = sqlite3.connect(str(path))
    try:
        schema_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'runs'"
        ).fetchone()
        schema = None if schema_row is None else str(schema_row[0])
        rows = conn.execute(
            """
            SELECT id, job_id, pdf_path, assay_key, lot_id, payload_json, created_at
            FROM runs
            ORDER BY id
            """
        ).fetchall()
        return schema, [tuple(row) for row in rows]
    finally:
        conn.close()


def _validation_rows(path: Path) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(str(path))
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        if "run_validations" not in tables:
            return []
        rows = conn.execute(
            """
            SELECT validation_id, run_id, operator_initials, validated_at_utc,
                   comment, supersedes_validation_id, created_at_utc
            FROM run_validations
            ORDER BY validation_id
            """
        ).fetchall()
        return [tuple(row) for row in rows]
    finally:
        conn.close()


def test_first_validation_persists_domain_record(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite"
    _create_runs_db(path, [(1, _MEASUREMENT)])
    before = _runs_state(path)

    stored = validate_run(_spec(path), 1, "RR", comment="freigegeben")

    assert isinstance(stored, RunValidation)
    assert stored.run_id == 1
    assert stored.operator_initials == "RR"
    assert stored.comment == "freigegeben"
    assert stored.supersedes_validation_id is None
    assert get_run_validation(_spec(path), 1) == stored
    assert _runs_state(path) == before
    assert _validation_rows(path)[0][1:3] == (1, "RR")


def test_initials_are_trimmed_and_blank_initials_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite"
    _create_runs_db(path, [(1, _MEASUREMENT)])
    before = _runs_state(path)

    stored = validate_run(_spec(path), 1, "  ab  ", comment="  hinweis  ")

    assert stored.operator_initials == "ab"
    assert stored.comment == "hinweis"
    for blank in ("", "   ", "\t", "\n"):
        with pytest.raises(OperatorInitialsRequiredError):
            validate_run(_spec(path), 1, blank, comment="darf nicht geschrieben werden")
    with pytest.raises(OperatorInitialsRequiredError):
        validate_run(_spec(path), 1, None)  # type: ignore[arg-type]
    assert [row[2] for row in _validation_rows(path)] == ["ab"]
    assert _runs_state(path) == before


def test_timestamps_are_utc_iso_with_timezone(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite"
    _create_runs_db(path, [(1, _MEASUREMENT)])
    started = datetime.now(timezone.utc).replace(microsecond=0)

    stored = validate_run(_spec(path), 1, "UTC")

    parsed = datetime.fromisoformat(stored.validated_at_utc)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)
    assert stored.validated_at_utc.endswith("+00:00")
    assert stored.created_at_utc == stored.validated_at_utc
    assert abs((parsed - started).total_seconds()) < 120


def test_second_validate_run_does_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite"
    _create_runs_db(path, [(1, _MEASUREMENT)])
    before_runs = _runs_state(path)
    original = validate_run(_spec(path), 1, "RR", comment="erst")
    before_validations = _validation_rows(path)

    with pytest.raises(ValidationAlreadyExistsError):
        validate_run(_spec(path), 1, "ZZ", comment="zweiter versuch")

    assert get_run_validation(_spec(path), 1) == original
    assert _validation_rows(path) == before_validations
    assert _runs_state(path) == before_runs


def test_explicit_correction_appends_history(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite"
    _create_runs_db(path, [(1, _MEASUREMENT), (2, '{"analyte":"synthetic","value":"other"}')])
    before_runs = _runs_state(path)
    original = validate_run(_spec(path), 1, "RR", comment="erst")

    with pytest.raises(ValidationMissingError):
        correct_validation(_spec(path), 2, "RR")

    corrected = correct_validation(_spec(path), 1, "  kk  ", comment="  korrigiert  ")
    replaced = replace_validation(_spec(path), 1, "MM", comment="ersetzt")
    history = list_run_validations(_spec(path), [1])

    assert corrected.operator_initials == "kk"
    assert corrected.comment == "korrigiert"
    assert corrected.supersedes_validation_id == original.validation_id
    assert replaced.supersedes_validation_id == corrected.validation_id
    assert [record.validation_id for record in history.records] == [
        original.validation_id,
        corrected.validation_id,
        replaced.validation_id,
    ]
    assert history.records[0] == original
    assert history.latest(1) == replaced
    assert _validation_rows(path)[0] == (
        original.validation_id,
        original.run_id,
        original.operator_initials,
        original.validated_at_utc,
        original.comment,
        original.supersedes_validation_id,
        original.created_at_utc,
    )
    assert _runs_state(path) == before_runs
    assert _runs_state(path)[1][0][5] == _MEASUREMENT


def test_list_run_validations_reports_latest_for_many_runs(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite"
    _create_runs_db(path, [(1, _MEASUREMENT), (2, '{"analyte":"synthetic","value":"2"}'), (3, '{"analyte":"synthetic","value":"3"}')])
    before_runs = _runs_state(path)
    first = validate_run(_spec(path), 1, "AA", comment="eins")
    second = validate_run(_spec(path), 2, "BB", comment="zwei")
    corrected = correct_validation(_spec(path), 1, "CC", comment="neu")

    listed = list_run_validations(_spec(path), [3, 1, 1, 2])

    assert get_run_validation(_spec(path), 3) is None
    assert listed.latest(3) is None
    assert listed.latest(1) == corrected
    assert listed.latest(2) == second
    assert listed.records[0] == first
    assert corrected.supersedes_validation_id == first.validation_id
    assert [record.run_id for record in listed.records] == [1, 2, 1]
    assert _runs_state(path) == before_runs


def test_existing_database_without_validation_table_is_extended(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    _create_runs_db(path, [(7, _MEASUREMENT)])
    before = _runs_state(path)
    conn = sqlite3.connect(str(path))
    try:
        names = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()
    assert "run_validations" not in names

    assert get_run_validation(_spec(path), 7) is None

    conn = sqlite3.connect(str(path))
    try:
        columns = conn.execute("PRAGMA table_info(run_validations)").fetchall()
    finally:
        conn.close()
    by_name = {str(row[1]): row for row in columns}
    assert set(by_name) == {
        "validation_id",
        "run_id",
        "operator_initials",
        "validated_at_utc",
        "comment",
        "supersedes_validation_id",
        "created_at_utc",
    }
    assert by_name["validation_id"][5] == 1
    assert by_name["created_at_utc"][3] == 0
    assert by_name["supersedes_validation_id"][3] == 0
    assert _runs_state(path) == before

    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            INSERT INTO run_validations (
                run_id, operator_initials, validated_at_utc, comment,
                supersedes_validation_id, created_at_utc
            ) VALUES (7, 'QL', '2026-02-02T00:00:00+00:00', 'alt', NULL, NULL)
            """
        )
        conn.commit()
    finally:
        conn.close()
    legacy = get_run_validation(_spec(path), 7)
    assert legacy is not None
    assert legacy.created_at_utc is None
    assert legacy.comment == "alt"
    assert _runs_state(path) == before


def test_missing_database_raises_and_does_not_create_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite"
    spec = _spec(path)

    with pytest.raises(ValidationStoreMissingError):
        validate_run(spec, 1, "RR")
    with pytest.raises(ValidationStoreMissingError):
        get_run_validation(spec, 1)
    with pytest.raises(ValidationStoreMissingError):
        list_run_validations(spec, [1])
    with pytest.raises(ValidationStoreMissingError):
        correct_validation(spec, 1, "RR")

    assert not path.exists()


def test_missing_run_raises_and_leaves_database_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "results.sqlite"
    _create_runs_db(path, [(1, _MEASUREMENT)])
    before = _runs_state(path)

    with pytest.raises(RunNotFoundError):
        validate_run(_spec(path), 99, "RR")
    with pytest.raises(RunNotFoundError):
        get_run_validation(_spec(path), 99)
    with pytest.raises(RunNotFoundError):
        correct_validation(_spec(path), 99, "RR")

    assert _validation_rows(path) == []
    assert _runs_state(path) == before


def test_unreadable_database_without_runs_table_raises(tmp_path: Path) -> None:
    path = tmp_path / "empty.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.close()

    with pytest.raises(ValidationStoreUnreadableError):
        validate_run(_spec(path), 1, "RR")
    assert _validation_rows(path) == []


def test_parallel_validate_run_keeps_a_single_head(tmp_path: Path) -> None:
    path = tmp_path / "parallel.sqlite"
    _create_runs_db(path, [(1, _MEASUREMENT)])
    before = _runs_state(path)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt() -> None:
        barrier.wait(timeout=10)
        try:
            validate_run(_spec(path), 1, "PP", comment="parallel")
        except ValidationAlreadyExistsError:
            kind = "exists"
        except ResultValidationError as exc:
            kind = type(exc).__name__
        else:
            kind = "ok"
        with lock:
            outcomes.append(kind)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["exists", "ok"]
    assert len(_validation_rows(path)) == 1
    assert _runs_state(path) == before


def test_public_api_and_architecture_boundary() -> None:
    import src.resultvalidation.api as validation_api

    assert "sqlite3" not in validation_api.__dict__
    expected = {
        "get_run_validation",
        "list_run_validations",
        "validate_run",
        "correct_validation",
        "replace_validation",
    }
    assert expected <= set(validation_api.__all__)
    for name in expected:
        signature = inspect.signature(getattr(validation_api, name))
        assert "store_spec" in signature.parameters
    assert list(inspect.signature(validate_run).parameters) == [
        "store_spec",
        "run_id",
        "operator_initials",
        "comment",
    ]
    assert inspect.signature(validate_run).parameters["comment"].default == ""
    assert list(inspect.signature(replace_validation).parameters) == [
        "store_spec",
        "run_id",
        "operator_initials",
        "comment",
    ]
    assert set(RunValidation.__dataclass_fields__) == {
        "validation_id",
        "run_id",
        "operator_initials",
        "validated_at_utc",
        "comment",
        "supersedes_validation_id",
        "created_at_utc",
    }

    resultstore_imports: list[str] = []
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "\t" not in source
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules.append(node.module)
            for module in modules:
                if module == "sqlite3" or module.startswith("sqlite3."):
                    assert path.name == "store.py"
                if module.startswith("src.") and module != "src.resultstore.api":
                    if module == "src.resultvalidation" or module.startswith("src.resultvalidation."):
                        continue
                    pytest.fail(f"{path.name} imports {module}")
                if module == "src.resultstore.api":
                    resultstore_imports.append(path.name)
            if isinstance(node, ast.Call) and _is_sql_call(node):
                for literal in _string_literals(node):
                    lowered = literal.lower()
                    assert "insert into runs" not in lowered
                    assert "update " not in lowered
                    assert "delete " not in lowered
                    assert "alter " not in lowered
                    assert " from runs" not in lowered
                    assert "join runs" not in lowered
    assert resultstore_imports == ["store.py"]


def _is_sql_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    return func.attr in {"execute", "executemany", "executescript"}


def _string_literals(node: ast.AST) -> list[str]:
    literals: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            literals.append(child.value)
    return literals
