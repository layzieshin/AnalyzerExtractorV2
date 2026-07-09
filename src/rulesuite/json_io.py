"""JSON-Datei-Helfer fuer die RuleSuite (atomares Schreiben, sichere Namen)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .errors import RuleSuiteError


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_json_object(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuleSuiteError(f"json_read_failed: {path}: {e}") from e
    if not isinstance(data, dict):
        raise RuleSuiteError(f"json_root_not_object: {path}")
    return data


def _safe_key(assay_key: str) -> str:
    return assay_key.replace("(", "").replace(")", "").replace("/", "_")


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch for ch in name.strip() if ch not in '<>:"/\\|?*').strip()
    return cleaned
