from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from src.jobcontroller.api import submit

SEPARATOR = "=" * 78


def _h(title: str) -> None:
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)


def _kv(k: str, v: Any, indent: int = 0) -> None:
    pad = " " * indent
    if isinstance(v, (dict, list)):
        print(f"{pad}{k}:")
        _pp(v, indent + 2)
    else:
        print(f"{pad}{k}: {v}")


def _pp(obj: Any, indent: int = 0) -> None:
    pad = " " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            _kv(str(k), v, indent)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                print(f"{pad}-")
                _pp(item, indent + 2)
            else:
                print(f"{pad}- {item}")
    else:
        print(f"{pad}{obj}")


def _load_job_state(project_root: Path, job_id: str) -> Dict[str, Any] | None:
    state_path = project_root / "jobs" / f"{job_id}.json"
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _print_phase_summary(state: Dict[str, Any]) -> None:
    steps: List[Dict[str, Any]] = state.get("steps", [])
    if not steps:
        _kv("note", "no step details available")
        return

    for s in steps:
        step = s.get("step", "unknown")
        print()
        print(f"[{step}]")
        for k, v in s.items():
            if k == "step":
                continue
            _kv(k, v, indent=2)


def run_one(project_root: Path, pdf: Path) -> None:
    _h(f"JOB: {pdf.name}")
    if not pdf.exists():
        _kv("error", "pdf_not_found")
        _kv("expected_path", str(pdf))
        return

    res = submit(str(pdf), str(project_root))
    _kv("status", res.status)
    _kv("job_id", res.job_id)
    _kv("pdf_path", res.pdf_path)
    if res.details:
        _kv("details", res.details)

    if res.job_id:
        state = _load_job_state(project_root, res.job_id)
        if state:
            print()
            _kv("state_status", state.get("status"))
            if state.get("error"):
                _kv("state_error", state.get("error"))
            _print_phase_summary(state)


def main() -> None:
    project_root = Path(__file__).resolve().parent
    input_dir = project_root / "input"
    pdfs = [input_dir / "sample_single.pdf", input_dir / "sample_multi.pdf"]

    for pdf in pdfs:
        run_one(project_root, pdf)
        print()
        print(SEPARATOR)
        print()


if __name__ == "__main__":
    main()
