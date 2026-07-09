"""Rekursiver Struktur-Diff zwischen aktivem Ruleset und Draft."""
from __future__ import annotations

from typing import Any, Dict, List


def collect_diffs(path: str, active: Any, draft: Any, out: List[Dict[str, Any]]) -> None:
    if type(active) is not type(draft):
        out.append({"path": path, "active": active, "draft": draft})
        return

    if isinstance(active, dict):
        keys = sorted(set(active.keys()) | set(draft.keys()))
        for k in keys:
            next_path = f"{path}.{k}"
            if k not in active:
                out.append({"path": next_path, "active": None, "draft": draft.get(k)})
                continue
            if k not in draft:
                out.append({"path": next_path, "active": active.get(k), "draft": None})
                continue
            collect_diffs(next_path, active.get(k), draft.get(k), out)
        return

    if isinstance(active, list):
        max_len = max(len(active), len(draft))
        for i in range(max_len):
            next_path = f"{path}[{i}]"
            if i >= len(active):
                out.append({"path": next_path, "active": None, "draft": draft[i]})
                continue
            if i >= len(draft):
                out.append({"path": next_path, "active": active[i], "draft": None})
                continue
            collect_diffs(next_path, active[i], draft[i], out)
        return

    if active != draft:
        out.append({"path": path, "active": active, "draft": draft})
