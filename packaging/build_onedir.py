from __future__ import annotations

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
    os.chdir(PROJECT_ROOT)
    _preflight()
    _clean_outputs()
    _run_pyinstaller()
    _prepare_runtime_tree()
    _verify_bundle()
    _run_bundle_smoke_check()
    _write_zip()
    print(f"[build] done: {APP_DIR}")
    print(f"[build] zip:  {ZIP_PATH}")


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


def _run_pyinstaller() -> None:
    print("[build] running PyInstaller onedir")
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

    for package_name in ("fitz", "pymupdf", "openpyxl"):
        if importlib.util.find_spec(package_name) is not None:
            command.extend(["--collect-all", package_name])

    command.append(str(ENTRY_POINT))
    _run(command, cwd=PROJECT_ROOT)


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
