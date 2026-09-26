from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.jobcontroller.api import submit


SEPARATOR = "=" * 78


def _print_header(title: str) -> None:
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)


def _print_key_value(key: str, value: Any, indent: int = 0) -> None:
    pad = " " * indent
    if isinstance(value, (dict, list)):
        print(f"{pad}{key}:")
        _pretty_print(value, indent + 2)
    else:
        print(f"{pad}{key}: {value}")


def _pretty_print(obj: Any, indent: int = 0) -> None:
    pad = " " * indent
    if isinstance(obj, dict):
        for key, value in obj.items():
            _print_key_value(str(key), value, indent)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                print(f"{pad}-")
                _pretty_print(item, indent + 2)
            else:
                print(f"{pad}- {item}")
    else:
        print(f"{pad}{obj}")


def _load_job_state(project_root: Path, job_id: str) -> dict[str, Any] | None:
    state_path = project_root / "jobs" / f"{job_id}.json"
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _print_phase_summary(state: dict[str, Any]) -> None:
    steps = state.get("steps", [])
    if not isinstance(steps, list) or not steps:
        _print_key_value("note", "no step details available")
        return

    for step_data in steps:
        if not isinstance(step_data, dict):
            continue
        step = step_data.get("step", "unknown")
        print()
        print(f"[{step}]")
        for key, value in step_data.items():
            if key == "step":
                continue
            _print_key_value(key, value, indent=2)


def run_one(project_root: Path, pdf: Path) -> None:
    _print_header(f"JOB: {pdf.name}")
    if not pdf.exists():
        _print_key_value("error", "pdf_not_found")
        _print_key_value("expected_path", str(pdf))
        return

    res = submit(str(pdf), str(project_root))
    _print_key_value("status", res.status)
    _print_key_value("job_id", res.job_id)
    _print_key_value("pdf_path", res.pdf_path)
    if res.details:
        _print_key_value("details", res.details)

    if res.job_id:
        state = _load_job_state(project_root, res.job_id)
        if state:
            print()
            _print_key_value("state_status", state.get("status"))
            if state.get("error"):
                _print_key_value("state_error", state.get("error"))
            _print_phase_summary(state)


def run_samples(project_root: Path) -> None:
    input_dir = project_root / "input"
    pdfs = [input_dir / "sample_single.pdf", input_dir / "sample_multi.pdf"]

    for pdf in pdfs:
        run_one(project_root, pdf)
        print()
        print(SEPARATOR)
        print()


def main() -> None:
    run_samples(Path(__file__).resolve().parents[2])
