from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
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
    _preflight()
    _clean_outputs()
    _run_pyinstaller(diet_experiment=args.diet_experiment)
    _prune_unneeded_bundle_payload()
    _prepare_runtime_tree()
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
    _run([sys.executable, "-m", "pytest", "tests"], cwd=PROJECT_ROOT)


def _clean_outputs() -> None:
    print("[build] cleaning previous packaging outputs")
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
        "--hidden-import",
        "fitz",
        "--hidden-import",
        "pymupdf",
        "--hidden-import",
        "openpyxl",
        "--hidden-import",
        "rule_editor_main",
    ]

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
