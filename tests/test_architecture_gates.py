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
ROOT_BOUNDARY_SCRIPTS = ROOT_WRAPPERS + ["main.py", "rule_editor_main.py"]
ALLOWED_ROOT_PYTHON_SCRIPTS = frozenset(
    {
        "main.py",
        "main02.py",
        "test_app_main.py",
        "watchdog_main.py",
        "worker_main.py",
        "rule_editor_main.py",
        "rule_suite_main.py",
        "rules_validate_main.py",
        "rules_matrix_main.py",
        "gui_min.py",
        "gui_min_ext.py",
    }
)
NEW_TK_VIEW_ROOTS = (
    PROJECT_ROOT / "interfaces" / "tk" / "views",
    PROJECT_ROOT / "interfaces" / "tk" / "widgets",
)
DESKTOP_VIEW_MODELS_FILE = PROJECT_ROOT / "interfaces" / "tk" / "view_models.py"
TEST_APP_FILE = PROJECT_ROOT / "interfaces" / "tk" / "test_app.py"
ANALYZER_DESKTOP_APP_MARKER = "class AnalyzerDesktopApp"
EXPECTED_PHASE3_UI_FILES = frozenset(
    {
        "interfaces/tk/view_models.py",
        "interfaces/tk/views/__init__.py",
        "interfaces/tk/views/dashboard_view.py",
        "interfaces/tk/views/diagnostics_view.py",
        "interfaces/tk/views/results_view.py",
        "interfaces/tk/views/rules_view.py",
        "interfaces/tk/views/settings_view.py",
        "interfaces/tk/views/validation_view.py",
        "interfaces/tk/widgets/__init__.py",
        "interfaces/tk/widgets/common.py",
        "interfaces/tk/widgets/dialogs.py",
    }
)
APPLICATION_ROOT = PROJECT_ROOT / "src" / "application"
PROCESSING_ROOT = PROJECT_ROOT / "src" / "processing"
QUEUE_WORKER_ADAPTER = PROJECT_ROOT / "interfaces" / "common" / "queue_worker.py"
EXPECTED_CONTROLLER_MODULES = frozenset(
    {
        "src/application/extraction_controller.py",
        "src/application/results_controller.py",
        "src/application/rules_controller.py",
        "src/application/settings_controller.py",
    }
)
EXPECTED_CONTROLLER_CLASSES = frozenset(
    {
        "ExtractionController",
        "ResultsController",
        "RuleSuiteController",
        "SettingsController",
    }
)
EXPECTED_DESKTOP_SERVICE_FIELDS = frozenset({"extraction", "results", "rules", "settings"})
CONTROLLER_API_ALLOWLIST = {
    "src/application/extraction_controller.py": frozenset(
        {"src.processing.api", "src.ingestion.api", "src.jobcontroller.api", "src.runtime.api"}
    ),
    "src/application/results_controller.py": frozenset(
        {
            "src.resultstore.api",
            "src.resultvalidation.api",
            "src.ingestion.api",
            "src.dbwriter.api",
            "src.jobqueue.api",
            "src.jobcontroller.api",
        }
    ),
    "src/application/rules_controller.py": frozenset(
        {
            "src.rulesuite.api",
            "src.ruleresolver.api",
            "src.assaycandidate.api",
            "src.jobcontroller.api",
            "src.parser.api",
            "src.normalizer.api",
            "src.contentsplitter.api",
        }
    ),
    "src/application/settings_controller.py": frozenset({"src.runtime.api"}),
}
PROCESSING_ALLOWED_SRC_APIS = frozenset(
    {"src.jobqueue.api", "src.jobcontroller.api", "src.runtime.api", "src.ingestion.api"}
)
INGESTION_ROOT = PROJECT_ROOT / "src" / "ingestion"
WATCHDOG_ROOT = PROJECT_ROOT / "src" / "watchdog"
PHASE2_PACKAGE_ROOTS = (
    APPLICATION_ROOT,
    PROCESSING_ROOT,
    INGESTION_ROOT,
    WATCHDOG_ROOT,
)
INGESTION_FORBIDDEN_PREFIXES = (
    "tkinter",
    "interfaces",
    "sqlite3",
)
INGESTION_ALLOWED_SRC_APIS = frozenset({"src.jobqueue.api", "src.runtime.api"})
FORBIDDEN_VIEW_SRC_PREFIXES = (
    "src.jobqueue",
    "src.jobcontroller",
    "src.rulesuite",
    "src.resultstore",
    "src.dbwriter",
    "src.watchdog",
)
_FORBIDDEN_VIEW_STORAGE_MODULE_ROOTS = frozenset({"sqlite3", "pathlib", "os", "glob", "shutil"})
_FORBIDDEN_VIEW_IO_ATTRS = frozenset(
    {
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "glob",
        "rglob",
        "iterdir",
        "unlink",
        "replace",
        "rename",
        "touch",
        "mkdir",
        "rmdir",
        "open",
    }
)
_FORBIDDEN_VIEW_OS_SHUTIL_ATTRS = frozenset(
    {
        "remove",
        "unlink",
        "rename",
        "replace",
        "mkdir",
        "makedirs",
        "rmdir",
        "removedirs",
        "copy",
        "copy2",
        "copyfile",
        "copytree",
        "move",
        "rmtree",
        "chown",
        "chmod",
        "open",
    }
)


def _relative_py_paths(base: Path) -> list[str]:
    if not base.is_dir():
        return []
    return [str(path.relative_to(PROJECT_ROOT)) for path in sorted(base.rglob("*.py"))]


ADAPTER_SOURCES = ROOT_BOUNDARY_SCRIPTS + ["gui_min.py", "gui_min_ext.py"] + _relative_py_paths(
    PROJECT_ROOT / "rule_editor"
) + _relative_py_paths(PROJECT_ROOT / "interfaces")


def _parse_module(source: str, *, filename: str = "<test>") -> ast.Module:
    return ast.parse(source, filename=filename)


def _is_exact_public_api_import(module_name: str) -> bool:
    parts = module_name.split(".")
    return len(parts) == 3 and parts[0] == "src" and parts[2] == "api"


def _package_name_from_root(root: Path) -> str:
    return root.name


def _is_same_package_import(module_name: str, package_name: str) -> bool:
    return module_name == f"src.{package_name}" or module_name.startswith(f"src.{package_name}.")


def _is_application_internal_import(module_name: str) -> bool:
    return module_name == "src.application" or module_name.startswith("src.application.")


def _is_allowed_view_src_import(module_name: str) -> bool:
    return module_name == "src.application.api"


def _read_python_source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _src_import_violations(rel_path: str, *, allow_application_internal: bool = False) -> list[str]:
    source_path = PROJECT_ROOT / rel_path
    tree = ast.parse(_read_python_source(source_path), filename=str(source_path))
    violations: list[str] = []

    for node in ast.walk(tree):
        module_name = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src" or alias.name.startswith("src."):
                    module_name = alias.name
                    if not _is_allowed_src_import(module_name, allow_application_internal=allow_application_internal):
                        violations.append(module_name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "src" or node.module.startswith("src.")):
                module_name = node.module
                if not _is_allowed_src_import(module_name, allow_application_internal=allow_application_internal):
                    violations.append(module_name)

    return sorted(set(violations))


def _is_allowed_src_import(module_name: str, *, allow_application_internal: bool = False) -> bool:
    if allow_application_internal and _is_application_internal_import(module_name):
        return True
    return _is_exact_public_api_import(module_name)


def _module_imports_in_file(rel_path: str) -> set[str]:
    source_path = PROJECT_ROOT / rel_path
    tree = ast.parse(_read_python_source(source_path), filename=str(source_path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _is_forbidden_view_storage_module(module_name: str) -> bool:
    return module_name.split(".")[0] in _FORBIDDEN_VIEW_STORAGE_MODULE_ROOTS


def _view_storage_import_violations(tree: ast.AST) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_view_storage_module(alias.name):
                    violations.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and _is_forbidden_view_storage_module(node.module):
                violations.append(f"from {node.module} import ...")
    return violations


def _view_storage_io_violations_in_source(source: str, *, filename: str = "<test>") -> list[str]:
    tree = _parse_module(source, filename=filename)
    violations = _view_storage_import_violations(tree)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            violations.append("open()")
        elif isinstance(func, ast.Attribute):
            if func.attr in _FORBIDDEN_VIEW_IO_ATTRS:
                violations.append(f".{func.attr}()")
            elif isinstance(func.value, ast.Name):
                if func.value.id == "os" and func.attr in _FORBIDDEN_VIEW_OS_SHUTIL_ATTRS:
                    violations.append(f"os.{func.attr}()")
                elif func.value.id == "shutil" and func.attr in _FORBIDDEN_VIEW_OS_SHUTIL_ATTRS:
                    violations.append(f"shutil.{func.attr}()")

    return sorted(set(violations))


def _view_storage_io_violations_in_file(rel_path: str) -> list[str]:
    source_path = PROJECT_ROOT / rel_path
    return _view_storage_io_violations_in_source(
        _read_python_source(source_path),
        filename=str(source_path),
    )


def _files_under(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return [path.relative_to(PROJECT_ROOT).as_posix() for path in sorted(root.rglob("*.py"))]


def _view_files_to_scan() -> list[str]:
    rel_paths = []
    for root in NEW_TK_VIEW_ROOTS:
        rel_paths.extend(_files_under(root))
    rel_paths.append(DESKTOP_VIEW_MODELS_FILE.relative_to(PROJECT_ROOT).as_posix())
    return sorted(set(rel_paths))


def _analyzer_desktop_app_source() -> str:
    source = _read_python_source(TEST_APP_FILE)
    marker_index = source.index(ANALYZER_DESKTOP_APP_MARKER)
    return source[marker_index:]


def _desktop_ui_surface_scan_targets() -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for rel_path in sorted(_discovered_phase3_ui_files()):
        targets.append((rel_path, _read_python_source(PROJECT_ROOT / rel_path)))
    targets.append(
        (
            "interfaces/tk/test_app.py::AnalyzerDesktopApp",
            _analyzer_desktop_app_source(),
        )
    )
    return targets


def _discovered_phase3_ui_files() -> set[str]:
    return set(_view_files_to_scan())


def _build_import_name_map(tree: ast.Module) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                mapping[alias.asname or alias.name] = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                mapping[alias.asname or alias.name.split(".")[0]] = alias.name
    return mapping


def _analyzer_desktop_app_src_violations_from_trees(
    module_tree: ast.Module,
    class_tree: ast.Module,
) -> list[str]:
    class_node = None
    for node in class_tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AnalyzerDesktopApp":
            class_node = node
            break
    if class_node is None:
        return ["AnalyzerDesktopApp missing"]
    import_map = _build_import_name_map(module_tree)
    for node in ast.walk(class_node):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                import_map[alias.asname or alias.name] = node.module
    offenders: list[str] = []
    for node in ast.walk(class_node):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
            if not _is_allowed_view_src_import(node.module):
                offenders.append(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src.") and not _is_allowed_view_src_import(alias.name):
                    offenders.append(alias.name)
    for node in ast.walk(class_node):
        if isinstance(node, ast.Name) and node.id == "resolve_app_root":
            offenders.append("resolve_app_root")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            module_name = import_map.get(node.id)
            if module_name and module_name.startswith("src.") and not _is_allowed_view_src_import(module_name):
                offenders.append(f"{node.id}<-{module_name}")
    return sorted(set(offenders))


def _analyzer_desktop_app_src_violations() -> list[str]:
    module_source = _read_python_source(TEST_APP_FILE)
    class_source = _analyzer_desktop_app_source()
    return _analyzer_desktop_app_src_violations_from_trees(
        ast.parse(module_source, filename=str(TEST_APP_FILE)),
        ast.parse(class_source, filename="AnalyzerDesktopApp"),
    )


def test_root_wrappers_are_thin() -> None:
    for rel_path in ROOT_WRAPPERS:
        lines = _read_python_source(PROJECT_ROOT / rel_path).splitlines()
        assert len(lines) <= 15, f"{rel_path} should stay a thin wrapper, got {len(lines)} lines"


def test_no_unknown_root_python_scripts() -> None:
    discovered = {path.name for path in PROJECT_ROOT.glob("*.py")}
    if discovered == ALLOWED_ROOT_PYTHON_SCRIPTS:
        return
    extras = sorted(discovered - ALLOWED_ROOT_PYTHON_SCRIPTS)
    missing = sorted(ALLOWED_ROOT_PYTHON_SCRIPTS - discovered)
    parts: list[str] = []
    if extras:
        parts.append(
            "Unexpected root Python scripts (add to allowlist + AGENTS.md): "
            + ", ".join(extras)
        )
    if missing:
        parts.append(
            "Inventoried root Python scripts missing from project root: "
            + ", ".join(missing)
        )
    assert False, "; ".join(parts)


def test_exact_public_api_import_parser_rejects_nested_api_paths() -> None:
    assert _is_exact_public_api_import("src.rulesuite.api") is True
    assert _is_exact_public_api_import("src.foo.bar.api") is False
    assert _is_exact_public_api_import("src.application.api") is True
    assert _is_allowed_src_import("src.rulesuite.api") is True
    assert _is_allowed_src_import("src.rulesuite.rulesuite") is False


def test_adapters_only_import_src_public_apis() -> None:
    offenders: dict[str, list[str]] = {}
    for rel_path in ADAPTER_SOURCES:
        violations = _src_import_violations(rel_path)
        if violations:
            offenders[rel_path] = violations

    assert offenders == {}, f"Adapter imports must stay on src.<module>.api only: {offenders}"


def test_test_app_section_keys_are_unique() -> None:
    from interfaces.tk.test_app import SECTION_KEYS

    assert len(SECTION_KEYS) == len(set(SECTION_KEYS))


def test_src_testui_has_no_tkinter_imports() -> None:
    offenders: list[str] = []
    for path in sorted((PROJECT_ROOT / "src" / "testui").glob("*.py")):
        tree = ast.parse(_read_python_source(path), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name == "tkinter" or alias.name.startswith("tkinter.") for alias in node.names):
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "tkinter" or node.module.startswith("tkinter.")):
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
    assert sorted(set(offenders)) == []


def test_application_and_processing_packages_exist() -> None:
    assert APPLICATION_ROOT.is_dir(), "src/application must exist"
    assert PROCESSING_ROOT.is_dir(), "src/processing must exist"
    assert (APPLICATION_ROOT / "api.py").is_file()
    assert (PROCESSING_ROOT / "api.py").is_file()


def test_application_layer_has_no_tkinter_interfaces_or_sqlite_imports() -> None:
    offenders: list[str] = []
    for rel_path in _files_under(APPLICATION_ROOT):
        modules = _module_imports_in_file(rel_path)
        for module in modules:
            if module == "tkinter" or module.startswith("tkinter."):
                offenders.append(f"{rel_path}: {module}")
            if module == "interfaces" or module.startswith("interfaces."):
                offenders.append(f"{rel_path}: {module}")
            if module == "sqlite3" or module.startswith("sqlite3."):
                offenders.append(f"{rel_path}: {module}")
            if module.startswith("src.") and not (
                _is_application_internal_import(module) or _is_exact_public_api_import(module)
            ):
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_application_controllers_reject_forbidden_ui_adapter_and_sqlite_imports() -> None:
    offenders: list[str] = []
    for rel_path in sorted(CONTROLLER_API_ALLOWLIST):
        modules = _module_imports_in_file(rel_path)
        for module in modules:
            if module == "tkinter" or module.startswith("tkinter."):
                offenders.append(f"{rel_path}: {module}")
            if module == "interfaces" or module.startswith("interfaces."):
                offenders.append(f"{rel_path}: {module}")
            if module == "sqlite3" or module.startswith("sqlite3."):
                offenders.append(f"{rel_path}: {module}")
            if module.startswith("src.") and not (
                _is_application_internal_import(module)
                or module in CONTROLLER_API_ALLOWLIST[rel_path]
            ):
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_application_controllers_use_only_allowed_public_apis() -> None:
    offenders: list[str] = []
    for rel_path, allowed in CONTROLLER_API_ALLOWLIST.items():
        modules = _module_imports_in_file(rel_path)
        for module in sorted(modules):
            if not module.startswith("src."):
                continue
            if _is_application_internal_import(module):
                continue
            if module not in allowed:
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_processing_layer_uses_only_allowed_public_apis() -> None:
    offenders: list[str] = []
    for rel_path in _files_under(PROCESSING_ROOT):
        modules = _module_imports_in_file(rel_path)
        for module in modules:
            if module == "interfaces" or module.startswith("interfaces."):
                offenders.append(f"{rel_path}: {module}")
            if module.startswith("src.") and module not in PROCESSING_ALLOWED_SRC_APIS:
                if module.startswith("src.processing."):
                    continue
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_processing_layer_has_no_tkinter_interfaces_or_sqlite_imports() -> None:
    offenders: list[str] = []
    for rel_path in _files_under(PROCESSING_ROOT):
        modules = _module_imports_in_file(rel_path)
        for module in modules:
            if module == "tkinter" or module.startswith("tkinter."):
                offenders.append(f"{rel_path}: {module}")
            if module == "interfaces" or module.startswith("interfaces."):
                offenders.append(f"{rel_path}: {module}")
            if module == "sqlite3" or module.startswith("sqlite3."):
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_application_has_exactly_four_controller_modules_and_classes() -> None:
    controller_modules = {
        rel_path.replace("\\", "/")
        for rel_path in _files_under(APPLICATION_ROOT)
        if rel_path.endswith("_controller.py")
    }
    assert controller_modules == EXPECTED_CONTROLLER_MODULES

    discovered_classes: set[str] = set()
    for rel_path in sorted(EXPECTED_CONTROLLER_MODULES):
        source_path = PROJECT_ROOT / Path(rel_path)
        tree = ast.parse(_read_python_source(source_path), filename=str(source_path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                discovered_classes.add(node.name)
    assert discovered_classes == EXPECTED_CONTROLLER_CLASSES


def test_desktop_app_services_has_exactly_four_fields() -> None:
    import dataclasses

    from src.application.services import DesktopAppServices

    field_names = {field.name for field in dataclasses.fields(DesktopAppServices)}
    assert field_names == EXPECTED_DESKTOP_SERVICE_FIELDS


def test_queue_worker_adapter_is_thin_reexport() -> None:
    assert QUEUE_WORKER_ADAPTER.is_file()
    source = _read_python_source(QUEUE_WORKER_ADAPTER)
    lines = [line.strip() for line in source.splitlines() if line.strip() and not line.strip().startswith("#")]
    assert len(lines) <= 20, "queue_worker adapter should stay a thin re-export"
    modules = {
        module
        for module in _module_imports_in_file(str(QUEUE_WORKER_ADAPTER.relative_to(PROJECT_ROOT)))
        if module.startswith("src.")
    }
    assert modules == {"src.processing.api"}
    assert "def process_next_pending" not in source
    assert "class QueueWorkerConfig" not in source


def test_application_public_api_has_no_tkinter_names() -> None:
    public_files = [
        "src/application/api.py",
        "src/application/models.py",
        "src/application/errors.py",
    ]
    forbidden_tokens = ("tkinter", "StringVar", "BooleanVar", "Treeview", "messagebox")
    offenders: list[str] = []
    for rel_path in public_files:
        source = _read_python_source(PROJECT_ROOT / rel_path).lower()
        for token in forbidden_tokens:
            if token.lower() in source:
                offenders.append(f"{rel_path}: {token}")
    assert offenders == []


def test_phase3_ui_files_exact_inventory() -> None:
    discovered = _discovered_phase3_ui_files()
    assert discovered == EXPECTED_PHASE3_UI_FILES
    source = _read_python_source(TEST_APP_FILE)
    assert ANALYZER_DESKTOP_APP_MARKER in source


def test_analyzer_desktop_app_uses_only_application_api() -> None:
    assert _analyzer_desktop_app_src_violations() == []


def test_analyzer_desktop_gate_detects_global_runtime_import_usage() -> None:
    sample_module = """
from src.runtime.api import resolve_app_root

class AnalyzerDesktopApp:
    def boot(self):
        return resolve_app_root()
"""
    offenders = _analyzer_desktop_app_src_violations_from_trees(
        ast.parse(sample_module),
        ast.parse(sample_module),
    )
    assert "resolve_app_root" in offenders
    assert any("resolve_app_root<-src.runtime.api" in item for item in offenders)


def test_new_tk_views_do_not_bypass_public_apis() -> None:
    offenders: list[str] = []
    for rel_path, source in _desktop_ui_surface_scan_targets():
        tree = ast.parse(source, filename=rel_path)
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        for module in modules:
            if module.startswith("src.") and not _is_allowed_view_src_import(module):
                offenders.append(f"{rel_path}: {module}")
            if module in FORBIDDEN_VIEW_SRC_PREFIXES or any(
                module.startswith(prefix + ".") for prefix in FORBIDDEN_VIEW_SRC_PREFIXES
            ):
                offenders.append(f"{rel_path}: {module}")
        offenders.extend(
            f"{rel_path}: {item}" for item in _view_storage_io_violations_in_source(source, filename=rel_path)
        )
    assert offenders == []


def test_view_storage_io_gate_detects_joinpath_read_text() -> None:
    offenders = _view_storage_io_violations_in_source(
        """
from pathlib import Path

def load_rule(root: str) -> str:
    return Path(root).joinpath("rules", "A.json").read_text(encoding="utf-8")
"""
    )
    assert "from pathlib import ..." in offenders
    assert ".read_text()" in offenders


def test_view_storage_io_gate_detects_path_division_read_text() -> None:
    offenders = _view_storage_io_violations_in_source(
        """
from pathlib import Path

def load_rule(root: str) -> str:
    return (Path(root) / "rules" / "A.json").read_text(encoding="utf-8")
"""
    )
    assert ".read_text()" in offenders


def test_view_storage_io_gate_detects_assigned_path_read_text() -> None:
    offenders = _view_storage_io_violations_in_source(
        """
from pathlib import Path

def load_rule() -> str:
    p = Path("rules/A.json")
    return p.read_text(encoding="utf-8")
"""
    )
    assert ".read_text()" in offenders


def test_view_storage_io_gate_detects_path_glob() -> None:
    offenders = _view_storage_io_violations_in_source(
        """
from pathlib import Path

def list_rules(root: str) -> list[str]:
    return [str(p) for p in Path(root, "rules").glob("*.json")]
"""
    )
    assert ".glob()" in offenders


def test_view_storage_io_gate_detects_open_on_path() -> None:
    offenders_builtin = _view_storage_io_violations_in_source(
        """
from pathlib import Path

def load_index(root: str) -> str:
    with open(Path(root) / "rules" / "index.json", encoding="utf-8") as handle:
        return handle.read()
"""
    )
    assert "open()" in offenders_builtin

    offenders_path_open = _view_storage_io_violations_in_source(
        """
from pathlib import Path

def load_index(path: Path) -> str:
    with path.open(encoding="utf-8") as handle:
        return handle.read()
"""
    )
    assert ".open()" in offenders_path_open


def test_view_storage_io_gate_detects_docs_read_text_without_rules_marker() -> None:
    offenders = _view_storage_io_violations_in_source(
        """
from pathlib import Path

def load_guide() -> str:
    return Path("docs/ruleset-guide.md").read_text(encoding="utf-8")
"""
    )
    assert ".read_text()" in offenders
    assert all("rules" not in item.lower() or item.startswith(".") for item in offenders)


def test_view_storage_io_gate_detects_overrules_read_text() -> None:
    offenders = _view_storage_io_violations_in_source(
        """
from pathlib import Path

def load_notes() -> str:
    return Path("notes/overrules.txt").read_text(encoding="utf-8")
"""
    )
    assert ".read_text()" in offenders


def test_view_storage_io_gate_detects_os_and_shutil_actions() -> None:
    offenders = _view_storage_io_violations_in_source(
        """
import os
import shutil

def cleanup(path: str) -> None:
    os.remove(path)
    shutil.copy("a.txt", "b.txt")
"""
    )
    assert "import os" in offenders
    assert "import shutil" in offenders
    assert "os.remove()" in offenders
    assert "shutil.copy()" in offenders


def test_view_storage_io_gate_allows_application_api_usage() -> None:
    offenders = _view_storage_io_violations_in_source(
        """
from src.application.api import create_desktop_services

def load_inventory(project_root: str):
    services = create_desktop_services(project_root)
    return services.rules.list_inventory()
"""
    )
    assert offenders == []


def test_view_storage_io_gate_allows_non_io_expressions() -> None:
    offenders = _view_storage_io_violations_in_source(
        """
def format_label(name: str) -> str:
    return name.strip().upper()

def toggle_flag(current: bool) -> bool:
    return not current
"""
    )
    assert offenders == []


def test_view_storage_io_gate_will_apply_when_views_exist() -> None:
    live_offenders: list[str] = []
    for rel_path, source in _desktop_ui_surface_scan_targets():
        live_offenders.extend(
            f"{rel_path}: {item}" for item in _view_storage_io_violations_in_source(source, filename=rel_path)
        )
    assert live_offenders == []
    assert _view_storage_io_violations_in_source('open("rules/index.json")') == ["open()"]


def test_interfaces_adapters_recursively_use_public_src_apis_only() -> None:
    offenders: dict[str, list[str]] = {}
    for rel_path in _relative_py_paths(PROJECT_ROOT / "interfaces"):
        violations = _src_import_violations(rel_path)
        if violations:
            offenders[rel_path] = violations
    assert offenders == {}, f"interfaces imports must stay on src.<module>.api only: {offenders}"


def test_rule_editor_recursively_uses_public_src_apis_only() -> None:
    """Allgemeiner Public-API-Vertrag bleibt in den Adapter-Tests. rule_editor ist enger."""
    offenders: dict[str, list[str]] = {}
    for rel_path in _relative_py_paths(PROJECT_ROOT / "rule_editor"):
        violations = [
            module
            for module in _module_imports_in_file(rel_path)
            if (module == "src" or module.startswith("src.")) and module != "src.application.api"
        ]
        if violations:
            offenders[rel_path] = sorted(set(violations))
    assert offenders == {}, f"rule_editor may import only src.application.api: {offenders}"


def test_root_boundary_scripts_use_public_src_apis_only() -> None:
    offenders: dict[str, list[str]] = {}
    for rel_path in ROOT_BOUNDARY_SCRIPTS:
        violations = _src_import_violations(rel_path)
        if violations:
            offenders[rel_path] = violations
    assert offenders == {}, f"Root boundary scripts must stay on src.<module>.api only: {offenders}"


def test_ingestion_package_exists_with_public_api() -> None:
    assert INGESTION_ROOT.is_dir(), "src/ingestion must exist"
    assert (INGESTION_ROOT / "api.py").is_file()


def test_ingestion_layer_has_no_tkinter_interfaces_or_sqlite_imports() -> None:
    offenders: list[str] = []
    for rel_path in _files_under(INGESTION_ROOT):
        modules = _module_imports_in_file(rel_path)
        for module in modules:
            if module == "tkinter" or module.startswith("tkinter."):
                offenders.append(f"{rel_path}: {module}")
            if module == "interfaces" or module.startswith("interfaces."):
                offenders.append(f"{rel_path}: {module}")
            if module == "sqlite3" or module.startswith("sqlite3."):
                offenders.append(f"{rel_path}: {module}")
            if module.startswith("src.") and module not in INGESTION_ALLOWED_SRC_APIS:
                if module.startswith("src.ingestion."):
                    continue
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_phase2_packages_cross_module_imports_use_public_api_only() -> None:
    offenders: list[str] = []
    for package_root in PHASE2_PACKAGE_ROOTS:
        package_name = _package_name_from_root(package_root)
        for rel_path in _files_under(package_root):
            modules = _module_imports_in_file(rel_path)
            for module in sorted(modules):
                if not module.startswith("src."):
                    continue
                if _is_same_package_import(module, package_name):
                    continue
                if _is_exact_public_api_import(module):
                    continue
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_ingestion_does_not_import_processing_or_resultstore() -> None:
    forbidden = {"src.processing", "src.processing.api", "src.resultstore", "src.resultstore.api"}
    offenders: list[str] = []
    for rel_path in _files_under(INGESTION_ROOT):
        modules = _module_imports_in_file(rel_path)
        for module in modules:
            if module in forbidden or any(module.startswith(prefix + ".") for prefix in forbidden):
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_resultstore_module_has_no_ingestion_imports() -> None:
    resultstore_root = PROJECT_ROOT / "src" / "resultstore"
    offenders: list[str] = []
    for rel_path in _files_under(resultstore_root):
        modules = _module_imports_in_file(rel_path)
        for module in modules:
            if module.startswith("src.ingestion"):
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []
