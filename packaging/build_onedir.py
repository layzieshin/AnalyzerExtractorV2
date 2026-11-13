from __future__ import annotations

import argparse
import importlib
import importlib.util
import importlib.metadata
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
import platform
import tomllib
from datetime import datetime, timezone
from pathlib import Path


APP_NAME = "AnalyzerResultExtractorV2"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = PROJECT_ROOT / "test_app_main.py"
RULES_SOURCE = PROJECT_ROOT / "rules"
DIST_ROOT = PROJECT_ROOT / "packaging" / "dist_output"
WORK_ROOT = PROJECT_ROOT / "packaging" / "build_work"
APP_DIR = DIST_ROOT / APP_NAME
ZIP_PATH = DIST_ROOT / f"{APP_NAME}.zip"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DESKTOP_RUNTIME_IMPORTS = [
    "interfaces.tk.desktop_theme",
    "interfaces.tk.task_runner",
    "interfaces.tk.view_models",
    "interfaces.tk.views",
    "interfaces.tk.widgets.dialogs",
    "src.application.api",
    "src.processing.api",
    "src.ingestion.api",
    "src.runtime.api",
    "src.qualitycontrol.api",
    "src.qualitycontrol.pdf_report",
]

REQUIRED_IMPORTS = [
    "fitz",
    "openpyxl",
    "tkinter",
    "interfaces.tk.test_app",
    "rule_editor_main",
    "src.parser.api",
    "src.normalizer.api",
    "src.assaychooser.api",
    "src.ruleresolver.api",
    "src.extractor.api",
    "src.writer.api",
    "src.dbwriter.api",
    "src.jobcontroller.api",
    "src.assaycandidate.api",
    "src.jobqueue.api",
    "src.testui.api",
    "src.resultstore.api",
    "src.rulesuite.api",
    *DESKTOP_RUNTIME_IMPORTS,
]

PYINSTALLER_HIDDEN_IMPORTS = [
    "fitz",
    "pymupdf",
    "openpyxl",
    "rule_editor_main",
    *DESKTOP_RUNTIME_IMPORTS,
]

SECRET_NAME_MARKERS = (
    ".env",
    "credential",
    "credentials",
    "private_key",
    "secret",
    ".pem",
    ".pfx",
    ".key",
)


def main() -> None:
    args = _parse_args()
    os.chdir(PROJECT_ROOT)
    inputs = _product_inputs()
    _preflight()
    _assert_inputs_unchanged(inputs)
    build_info = _make_build_info(inputs)
    _clean_outputs()
    _run_pyinstaller(diet_experiment=args.diet_experiment)
    _prune_unneeded_bundle_payload()
    _prepare_runtime_tree()
    _assert_inputs_unchanged(inputs)
    _write_build_info(build_info)
    _verify_bundle()
    _run_bundle_smoke_check()
    _write_zip()
    _print_size_report()
    print(f"[build] done: {APP_DIR}")
    print(f"[build] zip:  {ZIP_PATH}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build AREV2 onedir bundle")
    parser.add_argument(
        "--diet-experiment",
        action="store_true",
        help="Skip --collect-all for pymupdf/fitz; hidden imports remain",
    )
    return parser.parse_args()


def _preflight() -> None:
    print("[preflight] checking project files")
    _require_file(ENTRY_POINT)
    _require_file(RULES_SOURCE / "index.json")

    print("[preflight] checking imports")
    for module_name in REQUIRED_IMPORTS:
        importlib.import_module(module_name)

    print("[preflight] checking rules integrity")
    from src.ruleresolver.api import validate_rules_integrity

    report = validate_rules_integrity(str(RULES_SOURCE), str(RULES_SOURCE / "index.json"))
    if any(bool(v) for v in report.values()):
        raise SystemExit("[preflight] rules integrity failed:\n" + json.dumps(report, indent=2, ensure_ascii=False))

    print("[preflight] running pytest")
    _run([sys.executable, "-m", "pytest", "tests", "-q", "-o", "faulthandler_timeout=60"], cwd=PROJECT_ROOT)


def _product_inputs() -> list[dict[str, object]]:
    """Hash raw build-input bytes, without Git newline normalization or private paths."""
    runtime_dirs = {"jobs", "locks", "input", "output", "storage", "__pycache__", ".tmp", ".pytest_cache", "build", "dist"}
    paths = {PROJECT_ROOT / "pyproject.toml", PROJECT_ROOT / "README.md", PROJECT_ROOT / "packaging" / "build_onedir.py"}
    paths.update(PROJECT_ROOT.glob("*.py"))
    for package in ("src", "interfaces", "rule_editor"):
        paths.update(path for path in (PROJECT_ROOT / package).rglob("*") if path.is_file()
                     and not any(part.casefold() in runtime_dirs for part in path.relative_to(PROJECT_ROOT).parts[:-1])
                     and path.suffix not in {".pyc", ".pyo"})
    paths.update(path for path in RULES_SOURCE.rglob("*") if path.is_file()
                 and not any(part.lower() in {"drafts", "__pycache__"} for part in path.relative_to(RULES_SOURCE).parts)
                 and path.suffix not in {".pyc", ".pyo"})
    result = []
    root = PROJECT_ROOT.resolve()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise SystemExit("[preflight] a product input escapes the project root")
        raw = resolved.read_bytes()
        result.append({"path": resolved.relative_to(root).as_posix(), "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    return sorted(result, key=lambda item: str(item["path"]))


def _fingerprint(inputs: list[dict[str, object]]) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _assert_inputs_unchanged(expected: list[dict[str, object]]) -> None:
    if _fingerprint(_product_inputs()) != _fingerprint(expected):
        raise SystemExit("[preflight] product inputs changed after qualification; cleanup/publication stopped")


def _git_identity() -> tuple[str, bool | None]:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=PROJECT_ROOT,
            capture_output=True, text=True, check=True, timeout=10).stdout.strip())
        if len(head) != 40 or any(char not in "0123456789abcdef" for char in head.lower()):
            raise ValueError("invalid base revision")
        return head, dirty
    except (OSError, ValueError, subprocess.SubprocessError):
        return "UNAVAILABLE", None


def _make_build_info(inputs: list[dict[str, object]]) -> dict[str, object]:
    version = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    base_commit, dirty = _git_identity()
    dependencies = {}
    for package in ("PyMuPDF", "openpyxl", "PyInstaller"):
        try:
            dependencies[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            dependencies[package] = "UNAVAILABLE"
    return {"product": APP_NAME, "version": version, "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_commit": base_commit, "dirty_snapshot": dirty, "source_tree_fingerprint": _fingerprint(inputs),
            "fingerprint_contract": "raw-product-input-bytes-v1", "inputs": inputs, "dependencies": dependencies,
            "python_version": platform.python_version(), "platform": f"{sys.platform}-{platform.machine()}",
            "source_identity": "dirty-snapshot" if dirty else ("base-commit" if dirty is False else "snapshot-without-git-proof")}


def _write_build_info(info: dict[str, object]) -> None:
    (APP_DIR / "build-info.json").write_text(json.dumps(info, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _validate_output_targets() -> None:
    root = PROJECT_ROOT.resolve()
    expected = (root / "packaging" / "build_work", root / "packaging" / "dist_output" / APP_NAME,
                root / "packaging" / "dist_output" / f"{APP_NAME}.zip")
    for actual, allowed in zip((WORK_ROOT, APP_DIR, ZIP_PATH), expected):
        resolved = actual.resolve()
        if resolved != allowed.resolve() or not resolved.is_relative_to(root):
            raise SystemExit("[build] output target differs from the three authorized packaging targets")


def _clean_outputs() -> None:
    print("[build] cleaning previous packaging outputs")
    _validate_output_targets()
    for path in (WORK_ROOT, APP_DIR, ZIP_PATH):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)


def _run_pyinstaller(*, diet_experiment: bool = False) -> None:
    mode = "diet-experiment" if diet_experiment else "default"
    print(f"[build] running PyInstaller onedir ({mode})")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_ROOT),
        "--workpath",
        str(WORK_ROOT),
        "--specpath",
        str(WORK_ROOT),
        "--contents-directory",
        "_internal",
        "--paths",
        str(PROJECT_ROOT),
    ]
    for hidden_import in PYINSTALLER_HIDDEN_IMPORTS:
        command.extend(["--hidden-import", hidden_import])

    collect_all_packages = ["openpyxl"]
    if not diet_experiment:
        collect_all_packages = ["fitz", "pymupdf", "openpyxl"]

    for package_name in collect_all_packages:
        if importlib.util.find_spec(package_name) is not None:
            command.extend(["--collect-all", package_name])

    command.append(str(ENTRY_POINT))
    _run(command, cwd=PROJECT_ROOT)


def _prune_unneeded_bundle_payload() -> None:
    tzdata_dir = APP_DIR / "_internal" / "_tcl_data" / "tzdata"
    if not tzdata_dir.exists():
        print("[build] tzdata prune: nothing to remove")
        return
    if not tzdata_dir.resolve().is_relative_to(APP_DIR.resolve()):
        raise SystemExit("[build] tzdata target escapes the application output")

    files = [path for path in tzdata_dir.rglob("*") if path.is_file()]
    total_bytes = sum(path.stat().st_size for path in files)
    shutil.rmtree(tzdata_dir)
    print(
        "[build] tzdata prune: removed "
        f"{len(files)} files, {total_bytes / (1024 * 1024):.2f} MB"
    )


def _prepare_runtime_tree() -> None:
    print("[build] preparing runtime folders")
    _require_dir(APP_DIR)
    rules_target = APP_DIR / "rules"
    if rules_target.exists():
        if not rules_target.resolve().is_relative_to(APP_DIR.resolve()):
            raise SystemExit("[build] rule target escapes the application output")
        shutil.rmtree(rules_target)
    shutil.copytree(
        RULES_SOURCE,
        rules_target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "drafts"),
    )

    for rel in ("jobs", "output/final", "input/watch"):
        (APP_DIR / rel).mkdir(parents=True, exist_ok=True)


def _verify_bundle() -> None:
    print("[verify] checking bundle structure")
    exe = APP_DIR / f"{APP_NAME}.exe"
    _require_file(exe)
    _require_dir(APP_DIR / "_internal")
    _require_file(APP_DIR / "rules" / "index.json")
    _require_file(APP_DIR / "build-info.json")
    build_info = json.loads((APP_DIR / "build-info.json").read_text(encoding="utf-8"))
    declared = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if build_info.get("version") != declared or build_info.get("source_tree_fingerprint") != _fingerprint(build_info.get("inputs", [])):
        raise SystemExit("[verify] product version or input fingerprint differs from build metadata")
    for item in build_info["inputs"]:
        if str(item["path"]).startswith("rules/"):
            target = APP_DIR / str(item["path"])
            if not target.resolve().is_relative_to(APP_DIR.resolve()) or hashlib.sha256(target.read_bytes()).hexdigest() != item["sha256"]:
                raise SystemExit("[verify] bundled rule bytes differ from qualified input bytes")
    _require_dir(APP_DIR / "jobs")
    _require_dir(APP_DIR / "output" / "final")
    _require_dir(APP_DIR / "input" / "watch")
    if (APP_DIR / "rules" / "drafts").exists():
        raise SystemExit("[verify] rules/drafts must not be bundled")
    tzdata_dir = APP_DIR / "_internal" / "_tcl_data" / "tzdata"
    if tzdata_dir.exists():
        raise SystemExit("[verify] bundled tzdata must be pruned")
    _check_no_obvious_secret_files(APP_DIR)

    print("[verify] checking bundled rules")
    from src.ruleresolver.api import validate_rules_integrity

    report = validate_rules_integrity(str(APP_DIR / "rules"), str(APP_DIR / "rules" / "index.json"))
    if any(bool(v) for v in report.values()):
        raise SystemExit("[verify] bundled rules integrity failed:\n" + json.dumps(report, indent=2, ensure_ascii=False))


def _run_bundle_smoke_check() -> None:
    print("[verify] running bundled EXE smoke check")
    exe = APP_DIR / f"{APP_NAME}.exe"
    env = os.environ.copy()
    env["ARE_HOME"] = str(APP_DIR)
    env["ARE_SMOKE_EXIT"] = "1"
    _run([str(exe)], cwd=APP_DIR, env=env, timeout=45)


def _write_zip() -> None:
    print("[build] writing zip")
    _validate_output_targets()
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(APP_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(DIST_ROOT))
    _require_file(ZIP_PATH)


def _print_size_report() -> None:
    print("[build] size report")
    onedir_bytes = _tree_size(APP_DIR)
    print(f"[build] onedir total: {_format_mib(onedir_bytes)}")

    internal_dir = APP_DIR / "_internal"
    if internal_dir.is_dir():
        top_entries = sorted(
            ((entry.name, _tree_size(entry)) for entry in internal_dir.iterdir()),
            key=lambda item: item[1],
            reverse=True,
        )
        print("[build] top _internal entries:")
        for name, size_bytes in top_entries[:12]:
            print(f"[build]   {name}: {_format_mib(size_bytes)}")

    largest_files = sorted(
        ((path, path.stat().st_size) for path in APP_DIR.rglob("*") if path.is_file()),
        key=lambda item: item[1],
        reverse=True,
    )
    print("[build] top files:")
    for path, size_bytes in largest_files[:15]:
        print(f"[build]   {path.relative_to(APP_DIR)}: {_format_mib(size_bytes)}")

    if ZIP_PATH.is_file():
        print(f"[build] zip total: {_format_mib(ZIP_PATH.stat().st_size)}")


def _tree_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _format_mib(size_bytes: int) -> str:
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def _check_no_obvious_secret_files(root: Path) -> None:
    hits = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if any(marker in lowered for marker in SECRET_NAME_MARKERS):
            hits.append(str(path.relative_to(root)))
    if hits:
        raise SystemExit("[verify] possible secret files in bundle:\n" + "\n".join(sorted(hits)))


def _run(
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> None:
    print("[cmd] " + " ".join(command))
    subprocess.run(command, cwd=cwd, env=env, timeout=timeout, check=True)


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"required file missing: {path}")


def _require_dir(path: Path) -> None:
    if not path.is_dir():
        raise SystemExit(f"required directory missing: {path}")


if __name__ == "__main__":
    main()
