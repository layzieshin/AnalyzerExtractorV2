from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_WRAPPERS = [
    "main02.py",
    "rules_matrix_main.py",
    "rule_suite_main.py",
    "rules_validate_main.py",
    "test_app_main.py",
    "watchdog_main.py",
    "worker_main.py",
]
ADAPTER_SOURCES = ROOT_WRAPPERS + ["gui_min.py", "gui_min_ext.py"] + [
    str(path.relative_to(PROJECT_ROOT)) for path in sorted((PROJECT_ROOT / "rule_editor").glob("*.py"))
] + [
    str(path.relative_to(PROJECT_ROOT)) for path in sorted((PROJECT_ROOT / "interfaces" / "tk").glob("*.py"))
]


def _src_import_violations(rel_path: str) -> list[str]:
    source_path = PROJECT_ROOT / rel_path
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    violations: list[str] = []

    for node in ast.walk(tree):
        module_name = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src" or alias.name.startswith("src."):
                    module_name = alias.name
                    if not _is_allowed_src_import(module_name):
                        violations.append(module_name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "src" or node.module.startswith("src.")):
                module_name = node.module
                if not _is_allowed_src_import(module_name):
                    violations.append(module_name)

    return sorted(set(violations))


def _is_allowed_src_import(module_name: str) -> bool:
    parts = module_name.split(".")
    return len(parts) >= 3 and parts[0] == "src" and parts[-1] == "api"


def test_root_wrappers_are_thin() -> None:
    for rel_path in ROOT_WRAPPERS:
        lines = (PROJECT_ROOT / rel_path).read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 15, f"{rel_path} should stay a thin wrapper, got {len(lines)} lines"


def test_adapters_only_import_src_public_apis() -> None:
    offenders: dict[str, list[str]] = {}
    for rel_path in ADAPTER_SOURCES:
        violations = _src_import_violations(rel_path)
        if violations:
            offenders[rel_path] = violations

    assert offenders == {}, f"Adapter imports must stay on src.*.api only: {offenders}"


def test_src_testui_has_no_tkinter_imports() -> None:
    offenders: list[str] = []
    for path in sorted((PROJECT_ROOT / "src" / "testui").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name == "tkinter" or alias.name.startswith("tkinter.") for alias in node.names):
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "tkinter" or node.module.startswith("tkinter.")):
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert sorted(set(offenders)) == []
